"""
Unit and integration tests for Automated Pipeline Execution & Live Progress Tracking.
Validates:
1. Sequential execution through transcript -> Gemini summary -> PDF generation -> email delivery.
2. Graceful exception capture and failure status marking.
3. Live status API endpoints (/api/jobs/<id>/status, /api/jobs/active-statuses).
4. Ownership security enforcement.
"""

import unittest
from unittest.mock import patch, MagicMock
from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob, JobRecipient
from app.services import pipeline_service


class TestPipelineAndStatus(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Create test users
        self.user = User(username='student_user', role='user')
        self.user.set_password('password123')
        self.other_user = User(username='other_user', role='user')
        self.other_user.set_password('password123')
        db.session.add_all([self.user, self.other_user])
        db.session.commit()

        # Create test job
        self.job = ProcessingJob(
            user_id=self.user.id,
            title='Test Webinar Pipeline',
            input_type='transcript',
            input_file_name='test_lecture.vtt',
            input_file_path='/tmp/test_lecture.vtt',
            overall_status='ready',
            total_recipients=1
        )
        db.session.add(self.job)
        db.session.commit()

        self.recipient = JobRecipient(
            job_id=self.job.id,
            email='student@university.edu',
            student_name='Alice Student',
            delivery_status='pending'
        )
        db.session.add(self.recipient)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    @patch('app.services.transcript_service.process_webinar_to_transcript')
    @patch('app.services.gemini_service.summarize_transcript')
    @patch('app.services.gemini_service.save_job_summary')
    @patch('app.services.pdf_service.generate_job_pdf')
    @patch('app.services.email_service.send_webinar_summary_emails')
    def test_run_job_pipeline_success(
        self, mock_email, mock_pdf, mock_save_sum, mock_sum, mock_transcript
    ):
        """Pipeline successfully walks through all stages and marks overall_status='completed'."""
        mock_transcript.return_value = {'success': True, 'transcript_text': 'Test lecture transcript'}
        mock_sum.return_value = {'title': 'AI Brief', 'summary': 'Detailed contents'}
        mock_save_sum.return_value = '/tmp/summary.json'
        mock_pdf.return_value = {'success': True, 'pdf_path': 'pdfs/test.pdf'}
        mock_email.return_value = {'success': True, 'sent_count': 1, 'failed_count': 0}

        result = pipeline_service.run_job_pipeline(self.job.id, self.app)

        self.assertTrue(result['success'])
        self.assertEqual(result['overall_status'], 'completed')

        # Verify DB persisted state
        db.session.expire_all()
        updated_job = db.session.get(ProcessingJob, self.job.id)
        self.assertEqual(updated_job.transcript_status, 'completed')
        self.assertEqual(updated_job.summary_status, 'completed')
        self.assertEqual(updated_job.pdf_status, 'completed')
        self.assertEqual(updated_job.email_status, 'completed')
        self.assertEqual(updated_job.overall_status, 'completed')

    @patch('app.services.transcript_service.process_webinar_to_transcript')
    def test_run_job_pipeline_failure_marks_failed(self, mock_transcript):
        """A failure in any stage halts pipeline, marks stage failed and records error_message."""
        mock_transcript.side_effect = RuntimeError("VTT file corrupted or empty.")

        result = pipeline_service.run_job_pipeline(self.job.id, self.app)

        self.assertFalse(result['success'])
        self.assertEqual(result['stage'], 'transcript')

        db.session.expire_all()
        updated_job = db.session.get(ProcessingJob, self.job.id)
        self.assertEqual(updated_job.transcript_status, 'failed')
        self.assertEqual(updated_job.overall_status, 'failed')
        self.assertIn("VTT file corrupted", updated_job.error_message)

    def test_job_status_api_endpoint(self):
        """GET /api/jobs/<id>/status returns progress percentage and human-readable stage labels."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['role'] = 'user'

        resp = self.client.get(f'/api/jobs/{self.job.id}/status')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertTrue(data['success'])
        self.assertEqual(data['job']['id'], self.job.id)
        self.assertIn('progress_percent', data['job'])
        self.assertIn('stage_label', data['job'])
        self.assertIn('is_active', data['job'])

    def test_job_status_unauthorized_access(self):
        """Non-owner user cannot access job status (tenant isolation 403)."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.other_user.id
            sess['role'] = 'user'

        resp = self.client.get(f'/api/jobs/{self.job.id}/status')
        self.assertEqual(resp.status_code, 403)

    def test_active_job_statuses_api(self):
        """GET /api/jobs/active-statuses returns array of recent jobs with progress metrics."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['role'] = 'user'

        resp = self.client.get('/api/jobs/active-statuses')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        self.assertTrue(data['success'])
        self.assertIsInstance(data['jobs'], list)
        self.assertEqual(len(data['jobs']), 1)
        self.assertEqual(data['jobs'][0]['id'], self.job.id)


if __name__ == '__main__':
    unittest.main()
