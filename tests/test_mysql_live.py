import os
import unittest
from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError
from app import create_app
from app.models import db, User, ProcessingJob, JobRecipient

# Load environment
load_dotenv()

class TestMySQLLiveIntegration(unittest.TestCase):
    """
    Live integration test suite testing directly against MySQL Community Server on localhost:3306.
    Verifies actual database schema, tables, persistence, and authentication.
    """
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    def test_1_mysql_tables_exist(self):
        """Verify that all three Prompt 2 tables exist in the live MySQL webinar_ai_db schema."""
        inspector = db.inspect(db.engine)
        tables = set(inspector.get_table_names())
        self.assertIn('users', tables)
        self.assertIn('processing_jobs', tables)
        self.assertIn('job_recipients', tables)

    def test_2_admin_user_persisted_with_scrypt_hash(self):
        """Verify that the authorized administrator account exists in MySQL with a salted scrypt hash."""
        admin_user = User.query.filter_by(username='admin').first()
        self.assertIsNotNone(admin_user, "Admin user should exist in MySQL users table.")
        self.assertTrue(admin_user.password_hash.startswith('scrypt:'), "Password hash must use scrypt.")
        
        # Verify against password loaded from .env
        env_password = os.getenv('ADMIN_PASSWORD')
        if env_password:
            self.assertTrue(admin_user.check_password(env_password))
            self.assertFalse(admin_user.check_password('DefinitelyWrongPassword!'))

        # Verify role and active state
        self.assertEqual(admin_user.role, 'admin')
        self.assertTrue(admin_user.is_active)
        self.assertTrue(admin_user.is_admin)

    def test_3_processing_job_persistence_and_lifecycle_in_mysql(self):
        """Verify creating, querying, and updating a ProcessingJob in the live MySQL database."""
        admin_user = User.query.filter_by(username='admin').first()
        self.assertIsNotNone(admin_user)

        # Create live job
        test_job = ProcessingJob(
            user_id=admin_user.id,
            input_type='transcript',
            input_file_name='live_test_webinar.vtt',
            input_file_path='storage/uploads/live_test.vtt',
            overall_status='ready',
            total_recipients=10
        )
        db.session.add(test_job)
        db.session.commit()
        job_id = test_job.id
        self.assertIsNotNone(job_id)

        # Retrieve and verify persistence
        retrieved_job = db.session.get(ProcessingJob, job_id)
        self.assertEqual(retrieved_job.input_file_name, 'live_test_webinar.vtt')
        self.assertEqual(retrieved_job.overall_status, 'ready')
        self.assertEqual(retrieved_job.total_recipients, 10)

        # Clean up test job
        db.session.delete(retrieved_job)
        db.session.commit()

        # Confirm deletion
        self.assertIsNone(db.session.get(ProcessingJob, job_id))

    def test_4_job_recipients_uniqueness_and_cascade_in_mysql(self):
        """Verify JobRecipient foreign key cascade and unique constraint in live MySQL."""
        admin_user = User.query.filter_by(username='admin').first()
        
        job = ProcessingJob(
            user_id=admin_user.id,
            input_type='video',
            input_file_name='test_vid.mp4',
            input_file_path='storage/uploads/test_vid.mp4'
        )
        db.session.add(job)
        db.session.commit()

        r1 = JobRecipient(job_id=job.id, email='student1@college.edu', student_name='Student 1')
        db.session.add(r1)
        db.session.commit()

        # Attempt to insert duplicate recipient in same job
        r_dup = JobRecipient(job_id=job.id, email='student1@college.edu', student_name='Student Dup')
        db.session.add(r_dup)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        # Delete job and verify cascade
        db.session.delete(job)
        db.session.commit()
        self.assertEqual(JobRecipient.query.filter_by(job_id=job.id).count(), 0)

    def test_5_live_login_authentication_with_mysql(self):
        """Test authentication against the live MySQL database via Flask test client."""
        admin_password = os.getenv('ADMIN_PASSWORD')
        if not admin_password:
            self.skipTest("ADMIN_PASSWORD not present in .env")

        # 1. Invalid password rejection
        res_fail = self.client.post('/login', data={'username': 'admin', 'password': 'WrongPassword123'}, follow_redirects=True)
        self.assertEqual(res_fail.status_code, 200)
        self.assertIn('Invalid credentials', res_fail.get_data(as_text=True))

        # 2. Admin attempting User Login is rejected
        res_user_rej = self.client.post('/login', data={'username': 'admin', 'password': admin_password, 'login_type': 'user'}, follow_redirects=True)
        self.assertEqual(res_user_rej.status_code, 200)
        self.assertIn('Administrator accounts must sign in via Admin Login', res_user_rej.get_data(as_text=True))

        # 3. Valid admin authentication via Admin Login
        res_success = self.client.post('/login', data={'username': 'admin', 'password': admin_password, 'login_type': 'admin'}, follow_redirects=True)
        self.assertEqual(res_success.status_code, 200)
        html = res_success.get_data(as_text=True)
        self.assertIn('System Administration Console', html)
        self.assertIn('Welcome back, Administrator admin!', html)

    def test_6_live_media_and_csv_upload_pipeline_with_mysql(self):
        """End-to-end live test verifying media upload, CSV validation, and job persistence in MySQL."""
        admin_password = os.getenv('ADMIN_PASSWORD')
        if not admin_password:
            self.skipTest("ADMIN_PASSWORD not present in .env")

        # 1. Authenticate with live admin user via admin login
        self.client.post('/login', data={'username': 'admin', 'password': admin_password, 'login_type': 'admin'})

        # Verify admin is strictly forbidden from accessing workspace processing APIs
        res_admin_forbidden = self.client.post('/api/upload-webinar', data={})
        self.assertEqual(res_admin_forbidden.status_code, 403)
        self.assertIn('Administrator accounts cannot access the processing workspace', res_admin_forbidden.get_json()['message'])

        # Log out admin session before operator login
        self.client.get('/logout')

        # 2. Provision or retrieve live regular user for workspace operations
        operator = User.query.filter_by(username='live_operator').first()
        if not operator:
            operator = User(username='live_operator', email='operator@college.edu', role='user', is_active=True)
            operator.set_password('OperatorSecret123!')
            db.session.add(operator)
            db.session.commit()

        # Log in as live regular operator via User Login
        self.client.post('/login', data={'username': 'live_operator', 'password': 'OperatorSecret123!', 'login_type': 'user'})

        # 3. Upload transcript media as regular user
        vtt_content = b"WEBVTT - Live Integration Test\n\n00:00:01.000 --> 00:00:03.000\nTesting MySQL persistence."
        import io
        res_media = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(vtt_content), 'live_test_rec.vtt'),
            'source_type': 'transcript'
        })
        self.assertEqual(res_media.status_code, 200)
        media_data = res_media.get_json()['details']
        storage_path = os.path.join(self.app.config['UPLOAD_FOLDER'], media_data['safe_filename'])

        # 4. Upload recipient CSV
        csv_content = b"email,name\nlive_student1@college.edu,Student One\nlive_student2@college.edu,Student Two\n"
        res_csv = self.client.post('/api/upload-csv', data={
            'file': (io.BytesIO(csv_content), 'live_students.csv')
        })
        self.assertEqual(res_csv.status_code, 200)

        # 5. Add a manual recipient to verify mixed list in live database
        res_manual = self.client.post('/api/recipients/add', json={
            'email': 'live_student3@college.edu',
            'name': 'Student Three Manual'
        })
        self.assertEqual(res_manual.status_code, 200)

        # 6. Pre-validation
        res_val = self.client.post('/api/validate-state', json={})
        self.assertEqual(res_val.status_code, 200)
        self.assertEqual(res_val.get_json()['details']['recipients_ready'], 3)

        # 7. Submit job
        res_job = self.client.post('/api/submit-job', json={'title': 'Live MySQL Test Job'})
        self.assertEqual(res_job.status_code, 201)
        job_id = res_job.get_json()['job']['id']

        # 8. Verify in MySQL
        live_job = db.session.get(ProcessingJob, job_id)
        self.assertIsNotNone(live_job)
        self.assertEqual(live_job.input_type, 'transcript')
        self.assertEqual(live_job.total_recipients, 3)
        self.assertEqual(live_job.overall_status, 'ready')

        recipients = JobRecipient.query.filter_by(job_id=job_id).all()
        self.assertEqual(len(recipients), 3)
        self.assertEqual(
            {r.email for r in recipients},
            {'live_student1@college.edu', 'live_student2@college.edu', 'live_student3@college.edu'}
        )

        # Clean up test rows and stored file from disk
        db.session.delete(live_job)
        if operator and operator.id != 2:
            db.session.delete(operator)
        db.session.commit()
        if os.path.exists(storage_path):
            try:
                os.remove(storage_path)
            except OSError:
                pass

if __name__ == '__main__':
    unittest.main()
