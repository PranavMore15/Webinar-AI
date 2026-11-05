import unittest
from datetime import datetime, timezone
from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob
from app.services.pipeline_service import run_job_pipeline

class TestDashboardRoutes(unittest.TestCase):
    """
    Unit tests for dashboard API endpoints including active job statuses,
    job execution cancellation, and pipeline lifecycle guards.
    """
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app.config['SECRET_KEY'] = 'test-secret'
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.create_all()
        self.user = User(username='status_tester', email='tester@webinarai.edu', role='user', is_active=True)
        self.user.set_password('Pass1234!')
        db.session.add(self.user)
        db.session.commit()

        self.job = ProcessingJob(
            user_id=self.user.id,
            title='Test Webinar Processing',
            input_type='video',
            input_file_name='test_video.mp4',
            input_file_path='/tmp/test_video.mp4',
            overall_status='processing',
            total_recipients=5,
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(self.job)
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_active_job_statuses_returns_complete_metadata(self):
        """Verify /api/jobs/active-statuses returns input_type, input_file_name, total_recipients, and created_at."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['role'] = 'user'

        resp = self.client.get('/api/jobs/active-statuses')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertTrue(data['success'])
        self.assertIsInstance(data['jobs'], list)
        self.assertEqual(len(data['jobs']), 1)

        job = data['jobs'][0]
        self.assertEqual(job['id'], self.job.id)
        self.assertEqual(job['input_type'], 'video')
        self.assertEqual(job['input_file_name'], 'test_video.mp4')
        self.assertEqual(job['total_recipients'], 5)
        self.assertEqual(job['overall_status'], 'processing')
        self.assertIn('created_at', job)
        self.assertTrue(len(job['created_at']) > 0)

    def test_cancel_job_success(self):
        """Verify an authenticated user can cancel their active processing job."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['role'] = 'user'

        resp = self.client.post(f'/api/jobs/{self.job.id}/cancel')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertTrue(data['success'])
        self.assertEqual(data['job']['overall_status'], 'cancelled')
        self.assertIn('cancelled', data['message'].lower())

        updated_job = db.session.get(ProcessingJob, self.job.id)
        self.assertEqual(updated_job.overall_status, 'cancelled')
        self.assertEqual(updated_job.error_message, 'Job execution cancelled by user.')
        self.assertEqual(updated_job.transcript_status, 'cancelled')
        self.assertEqual(updated_job.summary_status, 'cancelled')
        self.assertEqual(updated_job.pdf_status, 'cancelled')
        self.assertEqual(updated_job.email_status, 'cancelled')

    def test_cancel_job_permission_denied(self):
        """Verify a non-owner user cannot cancel another user's job."""
        other_user = User(username='other_user', email='other@webinarai.edu', role='user', is_active=True)
        other_user.set_password('Pass1234!')
        db.session.add(other_user)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = other_user.id
            sess['role'] = 'user'

        resp = self.client.post(f'/api/jobs/{self.job.id}/cancel')
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('Access denied', data['message'])

        # Ensure job status remains unchanged
        unchanged_job = db.session.get(ProcessingJob, self.job.id)
        self.assertEqual(unchanged_job.overall_status, 'processing')

    def test_cancel_job_admin_forbidden_by_role_guard(self):
        """Verify admin accounts are forbidden from processing workspace endpoints by @user_required."""
        admin = User(username='admin_user', email='admin@webinarai.edu', role='admin', is_active=True)
        admin.set_password('AdminPass123!')
        db.session.add(admin)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = admin.id
            sess['role'] = 'admin'

        resp = self.client.post(f'/api/jobs/{self.job.id}/cancel')
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('Administrator accounts cannot access the processing workspace', data['message'])

    def test_cancel_job_terminal_state_rejected(self):
        """Verify cancelling an already completed, failed, or cancelled job returns 400."""
        self.job.overall_status = 'completed'
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['role'] = 'user'

        resp = self.client.post(f'/api/jobs/{self.job.id}/cancel')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('already completed', data['message'])

    def test_cancel_job_not_found(self):
        """Verify cancelling non-existent job returns 404."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['role'] = 'user'

        resp = self.client.post('/api/jobs/99999/cancel')
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertFalse(data['success'])

    def test_pipeline_halts_on_cancelled_job(self):
        """Verify run_job_pipeline aborts early without doing work when job is cancelled."""
        self.job.overall_status = 'cancelled'
        db.session.commit()

        res = run_job_pipeline(self.job.id, self.app)
        self.assertFalse(res['success'])
        self.assertEqual(res['overall_status'], 'cancelled')
        self.assertEqual(res['stage'], 'cancelled')

    def test_job_status_transcribing_dynamic_label_and_percent(self):
        """Verify /api/jobs/<id>/status dynamically calculates progress and label during transcription."""
        self.job.overall_status = 'transcribing'
        self.job.error_message = 'Transcribing speech with Gemini AI (high-speed path)...'
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['role'] = 'user'

        resp = self.client.get(f'/api/jobs/{self.job.id}/status')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        job_data = data['job']
        self.assertEqual(job_data['progress_percent'], 30)
        self.assertIn('Transcribing speech with Gemini AI', job_data['stage_label'])

    def test_job_status_transcribing_audio_extraction(self):
        """Verify status reflects audio extraction milestone."""
        self.job.overall_status = 'transcribing'
        self.job.error_message = 'Extracting audio track from webinar video...'
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['role'] = 'user'

        resp = self.client.get(f'/api/jobs/{self.job.id}/status')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        job_data = data['job']
        self.assertEqual(job_data['progress_percent'], 20)
        self.assertIn('Extracting audio track', job_data['stage_label'])

    def test_job_status_transcribing_whisper_chunks(self):
        """Verify status reflects chunk progress during local Whisper inference."""
        self.job.overall_status = 'transcribing'
        self.job.error_message = 'Transcribing audio chunk 1 of 2 with local Whisper AI...'
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['role'] = 'user'

        resp = self.client.get(f'/api/jobs/{self.job.id}/status')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        job_data = data['job']
        self.assertEqual(job_data['progress_percent'], 30)
        self.assertIn('chunk 1 of 2', job_data['stage_label'])

    def test_active_job_statuses_includes_dynamic_transcribing_label(self):
        """Verify /api/jobs/active-statuses includes dynamic stage_label during transcription."""
        self.job.overall_status = 'transcribing'
        self.job.error_message = 'Transcribing speech with Gemini AI (high-speed path)...'
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['role'] = 'user'

        resp = self.client.get('/api/jobs/active-statuses')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        job = data['jobs'][0]
        self.assertEqual(job['progress_percent'], 30)
        self.assertIn('Gemini AI', job['stage_label'])

if __name__ == '__main__':
    unittest.main()

