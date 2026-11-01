import unittest
from datetime import datetime, timezone
from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob

class TestDashboardRoutes(unittest.TestCase):
    """
    Unit tests for dashboard API endpoints including active job statuses.
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

if __name__ == '__main__':
    unittest.main()

