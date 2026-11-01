import os
import unittest
from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob, JobRecipient

class TestJobLifecycleTableIntegration(unittest.TestCase):
    """
    End-to-end integration check simulating job submission, active status polling,
    and dashboard page rendering for in-progress jobs.
    """
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app.config['SECRET_KEY'] = 'test-lifecycle-secret'
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.create_all()
        self.user = User(username='lifecycle_user', email='lifecycle@webinarai.edu', role='user', is_active=True)
        self.user.set_password('LifeCyclePass123!')
        db.session.add(self.user)
        db.session.commit()
        self.user_id = self.user.id

        self.client = self.app.test_client()

        # Create dummy file to simulate stored webinar upload
        self.dummy_media_path = os.path.join(self.app.config['UPLOAD_FOLDER'], 'integration_test_webinar.mp4')
        with open(self.dummy_media_path, 'wb') as f:
            f.write(b'\x00\x00\x00 ftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free')

    def tearDown(self):
        if os.path.exists(self.dummy_media_path):
            try:
                os.remove(self.dummy_media_path)
            except OSError:
                pass
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user_id
            sess['username'] = 'lifecycle_user'
            sess['role'] = 'user'

    def test_job_submission_active_status_and_dashboard_render(self):
        """Simulate job submission via API, verify active statuses polling payload, and check dashboard template rendering."""
        self._login()

        # Step 1: Pre-stage webinar and CSV session state
        with self.client.session_transaction() as sess:
            sess['current_webinar_upload'] = {
                'original_filename': 'integration_test_webinar.mp4',
                'storage_path': self.dummy_media_path,
                'input_type': 'video',
                'source_type': 'manual',
                'source_url': None
            }
            sess['current_csv_validation'] = {
                'valid_unique_count': 2,
                'valid_recipients': [
                    {'email': 'student1@webinarai.edu', 'name': 'Student One'},
                    {'email': 'student2@webinarai.edu', 'name': 'Student Two'}
                ]
            }

        # Step 2: Submit job via /api/submit-job
        resp = self.client.post('/api/submit-job', json={'title': 'Integration Test Webinar Job'})
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIn('job', data)
        job_info = data['job']
        job_id = job_info['id']
        self.assertEqual(job_info['input_type'], 'video')
        self.assertEqual(job_info['input_file_name'], 'integration_test_webinar.mp4')
        self.assertEqual(job_info['total_recipients'], 2)
        self.assertEqual(job_info['overall_status'], 'ready')

        # Step 3: Verify /api/jobs/active-statuses returns full metadata
        status_resp = self.client.get('/api/jobs/active-statuses')
        self.assertEqual(status_resp.status_code, 200)
        status_data = status_resp.get_json()
        self.assertTrue(status_data['success'])
        self.assertGreaterEqual(len(status_data['jobs']), 1)
        active_job = next((j for j in status_data['jobs'] if j['id'] == job_id), None)
        self.assertIsNotNone(active_job)
        self.assertEqual(active_job['input_file_name'], 'integration_test_webinar.mp4')
        self.assertEqual(active_job['input_type'], 'video')
        self.assertEqual(active_job['total_recipients'], 2)
        self.assertTrue(active_job['is_active'])
        self.assertIn('created_at', active_job)
        self.assertTrue(len(active_job['created_at']) > 0)

        # Step 4: Verify /dashboard renders the active job in the table with spinning active badge
        dash_resp = self.client.get('/dashboard')
        self.assertEqual(dash_resp.status_code, 200)
        dash_html = dash_resp.get_data(as_text=True)

        self.assertIn(f'id="job-row-{job_id}"', dash_html)
        self.assertIn(f'id="job-status-cell-{job_id}"', dash_html)
        self.assertIn('spinner-border', dash_html)
        self.assertIn('integration_test_webinar.mp4', dash_html)
        self.assertIn('2 recipients', dash_html)

if __name__ == '__main__':
    unittest.main()

