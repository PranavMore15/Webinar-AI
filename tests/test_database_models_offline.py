import unittest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob, JobRecipient

class TestDatabaseModelsOffline(unittest.TestCase):
    """
    Offline unit tests for database models, relationships, and constraints.
    Runs entirely in-memory using SQLite without connecting to MySQL.
    """
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_user_password_hashing_and_verification(self):
        """Verify that User passwords are encrypted with salted hashes, not stored in plaintext."""
        user = User(username='testadmin', email='admin@test.edu')
        user.set_password('SecretPass123!')
        db.session.add(user)
        db.session.commit()

        # Verify password is not stored plaintext
        self.assertNotEqual(user.password_hash, 'SecretPass123!')
        self.assertTrue(user.password_hash.startswith('scrypt:') or len(user.password_hash) > 50)

        # Verify validation
        self.assertTrue(user.check_password('SecretPass123!'))
        self.assertFalse(user.check_password('WrongPassword'))
        self.assertFalse(user.check_password(''))

    def test_user_username_uniqueness(self):
        """Verify that duplicate usernames trigger database uniqueness constraints."""
        user1 = User(username='unique_user')
        user1.set_password('pass1')
        db.session.add(user1)
        db.session.commit()

        user2 = User(username='unique_user')
        user2.set_password('pass2')
        db.session.add(user2)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_user_role_defaults_and_admin_property(self):
        """Verify role default is 'user', is_active default is True, and is_admin property."""
        user = User(username='standard_user')
        user.set_password('pass')
        admin = User(username='admin_user', role='admin')
        admin.set_password('pass')
        db.session.add_all([user, admin])
        db.session.commit()

        self.assertEqual(user.role, 'user')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_admin)

        self.assertEqual(admin.role, 'admin')
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_admin)

    def test_processing_job_creation_and_defaults(self):
        """Verify ProcessingJob default milestone statuses and user foreign key binding."""
        user = User(username='operator')
        user.set_password('pass')
        db.session.add(user)
        db.session.commit()

        job = ProcessingJob(
            user_id=user.id,
            input_type='transcript',
            input_file_name='lecture.vtt',
            input_file_path='storage/uploads/lecture_abc123.vtt',
            total_recipients=5
        )
        db.session.add(job)
        db.session.commit()

        # Check default statuses
        self.assertEqual(job.overall_status, 'ready')
        self.assertEqual(job.transcript_status, 'pending')
        self.assertEqual(job.summary_status, 'pending')
        self.assertEqual(job.pdf_status, 'pending')
        self.assertEqual(job.email_status, 'pending')
        self.assertEqual(job.successful_emails, 0)
        self.assertEqual(job.failed_emails, 0)
        self.assertEqual(job.owner.username, 'operator')

    def test_job_recipients_cascade_deletion(self):
        """Verify that deleting a ProcessingJob automatically deletes associated JobRecipients."""
        user = User(username='cascade_user')
        user.set_password('pass')
        db.session.add(user)
        db.session.commit()

        job = ProcessingJob(
            user_id=user.id,
            input_type='video',
            input_file_name='recording.mp4',
            input_file_path='storage/uploads/rec.mp4'
        )
        db.session.add(job)
        db.session.commit()

        recipient1 = JobRecipient(job_id=job.id, email='student1@test.edu', student_name='Student 1')
        recipient2 = JobRecipient(job_id=job.id, email='student2@test.edu', student_name='Student 2')
        db.session.add_all([recipient1, recipient2])
        db.session.commit()

        self.assertEqual(JobRecipient.query.filter_by(job_id=job.id).count(), 2)

        # Delete job
        db.session.delete(job)
        db.session.commit()

        # Verify recipients were cascade deleted
        self.assertEqual(JobRecipient.query.filter_by(job_id=job.id).count(), 0)

    def test_recipient_uniqueness_within_single_job(self):
        """Verify that duplicate email entries in the same job trigger unique constraint uq_job_recipient_email."""
        user = User(username='dup_user')
        user.set_password('pass')
        db.session.add(user)
        db.session.commit()

        job = ProcessingJob(
            user_id=user.id,
            input_type='transcript',
            input_file_name='notes.txt',
            input_file_path='storage/uploads/notes.txt'
        )
        db.session.add(job)
        db.session.commit()

        r1 = JobRecipient(job_id=job.id, email='same@test.edu')
        db.session.add(r1)
        db.session.commit()

        r2 = JobRecipient(job_id=job.id, email='same@test.edu')
        db.session.add(r2)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_job_tenant_isolation(self):
        """Verify user ownership queries prevent cross-tenant job access."""
        u1 = User(username='user_a')
        u1.set_password('pass')
        u2 = User(username='user_b')
        u2.set_password('pass')
        db.session.add_all([u1, u2])
        db.session.commit()

        job_a = ProcessingJob(user_id=u1.id, input_type='video', input_file_name='a.mp4', input_file_path='path/a')
        job_b = ProcessingJob(user_id=u2.id, input_type='video', input_file_name='b.mp4', input_file_path='path/b')
        db.session.add_all([job_a, job_b])
        db.session.commit()

        # User A querying their own jobs
        user_a_jobs = ProcessingJob.query.filter_by(user_id=u1.id).all()
        self.assertEqual(len(user_a_jobs), 1)
        self.assertEqual(user_a_jobs[0].input_file_name, 'a.mp4')

        # User A attempting to query User B's job ID with ownership filter
        inaccessible_job = ProcessingJob.query.filter_by(id=job_b.id, user_id=u1.id).first()
        self.assertIsNone(inaccessible_job)

if __name__ == '__main__':
    unittest.main()
