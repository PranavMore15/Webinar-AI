import os
import io
import shutil
import tempfile
import unittest
from unittest.mock import patch
from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob, JobRecipient

class TestMediaUploadPipeline(unittest.TestCase):
    """
    Automated test suite for Prompt 3: Media Upload Pipeline.
    Verifies MP4/TXT/VTT validation, safe storage, path traversal protection,
    disk cleanup, independent upload workflows, and ProcessingJob database persistence.
    """
    def setUp(self):
        # Create unique temp upload directory
        self.temp_upload_dir = tempfile.mkdtemp()

        class CustomTestConfig(TestConfig):
            TESTING = True
            SECRET_KEY = 'media-test-secret'
            UPLOAD_FOLDER = self.temp_upload_dir
            MAX_VIDEO_SIZE = 5 * 1024 * 1024       # 5MB for quick testing
            MAX_TRANSCRIPT_SIZE = 1 * 1024 * 1024  # 1MB for quick testing
            MAX_CSV_SIZE = 1 * 1024 * 1024

        self.app = create_app(CustomTestConfig)
        self.client = self.app.test_client()

        # Initialize in-memory database
        with self.app.app_context():
            db.create_all()
            # Provision test user
            self.test_user = User(username='test_operator', email='operator@college.edu')
            self.test_user.set_password('SecretPass123!')
            db.session.add(self.test_user)
            db.session.commit()
            self.test_user_id = self.test_user.id

        # Synthetic valid file contents
        # Minimal valid MP4 header containing 'ftyp' in bytes 4..8
        self.valid_mp4_bytes = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42\x00\x00\x00\x08free'
        self.valid_txt_bytes = b"Webinar Title: Quantum Computing Overview\nSpeaker: Dr. Richard Feynman\nTakeaways: Superposition and entanglement."
        self.valid_vtt_bytes = b"WEBVTT - Quantum Webinar\n\n00:00:01.000 --> 00:00:04.000\nWelcome to Quantum Computing 101."
        self.valid_csv_bytes = b"email,name\nalice@college.edu,Alice Smith\nbob@college.edu,Bob Jones\n"

    def tearDown(self):
        # Clean up database
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            if hasattr(db.engine, 'dispose'):
                db.engine.dispose()

        # Clean up temp upload directory
        if os.path.exists(self.temp_upload_dir):
            shutil.rmtree(self.temp_upload_dir, ignore_errors=True)

    def _login_session(self):
        """Helper to establish authenticated session."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.test_user_id
            sess['username'] = 'test_operator'

    # -------------------------------------------------------------------------
    # Authentication & Route Protection Tests
    # -------------------------------------------------------------------------
    def test_unauthenticated_upload_webinar_returns_401(self):
        res = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_mp4_bytes), 'webinar.mp4'),
            'source_type': 'video'
        })
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data['success'])

    def test_unauthenticated_clear_webinar_returns_401(self):
        res = self.client.post('/api/clear-webinar')
        self.assertEqual(res.status_code, 401)

    def test_unauthenticated_submit_job_returns_401(self):
        res = self.client.post('/api/submit-job', json={})
        self.assertEqual(res.status_code, 401)

    # -------------------------------------------------------------------------
    # Validation & Rejection Tests
    # -------------------------------------------------------------------------
    def test_upload_webinar_no_file_rejected(self):
        self._login_session()
        res = self.client.post('/api/upload-webinar', data={'source_type': 'video'})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data['success'])
        self.assertIn('No webinar file was submitted', data['message'])

    def test_upload_webinar_invalid_source_type_rejected(self):
        self._login_session()
        res = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_mp4_bytes), 'webinar.mp4'),
            'source_type': 'audio'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data['success'])
        self.assertIn("Source type must be 'video' or 'transcript'", data['message'])

    def test_video_mode_rejects_non_mp4_extensions(self):
        self._login_session()
        for bad_name in ['video.txt', 'video.avi', 'malware.exe', 'presentation.pdf']:
            res = self.client.post('/api/upload-webinar', data={
                'file': (io.BytesIO(self.valid_mp4_bytes), bad_name),
                'source_type': 'video'
            })
            self.assertEqual(res.status_code, 400)
            data = res.get_json()
            self.assertEqual(data.get('code'), 'INVALID_EXTENSION')

    def test_transcript_mode_rejects_non_txt_vtt_extensions(self):
        self._login_session()
        for bad_name in ['recording.mp4', 'notes.docx', 'data.json', 'script.py']:
            res = self.client.post('/api/upload-webinar', data={
                'file': (io.BytesIO(self.valid_txt_bytes), bad_name),
                'source_type': 'transcript'
            })
            self.assertEqual(res.status_code, 400)
            data = res.get_json()
            self.assertEqual(data.get('code'), 'INVALID_EXTENSION')

    def test_empty_file_rejected_0_bytes(self):
        self._login_session()
        res = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(b''), 'empty.mp4'),
            'source_type': 'video'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data.get('code'), 'EMPTY_FILE')

    def test_oversized_video_file_rejected(self):
        self._login_session()
        # Configured max is 5MB; create 6MB stream
        large_bytes = b'\x00\x00\x00\x18ftyp' + (b'x' * (6 * 1024 * 1024))
        res = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(large_bytes), 'huge_video.mp4'),
            'source_type': 'video'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data.get('code'), 'FILE_TOO_LARGE')

    def test_corrupt_mp4_rejected_missing_ftyp_header(self):
        self._login_session()
        fake_mp4 = b'NOT_A_REAL_MP4_FILE_JUST_RANDOM_TEXT_DATA'
        res = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(fake_mp4), 'corrupt.mp4'),
            'source_type': 'video'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data.get('code'), 'INVALID_VIDEO_HEADER')

    def test_whitespace_only_transcript_rejected(self):
        self._login_session()
        blank_txt = b"   \n\t  \r\n   "
        res = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(blank_txt), 'blank.txt'),
            'source_type': 'transcript'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data.get('code'), 'EMPTY_CONTENT')

    def test_malformed_vtt_rejected(self):
        self._login_session()
        # VTT file lacking WEBVTT header and cue markers
        bad_vtt = b"Random notes without WebVTT signature or timing markers."
        res = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(bad_vtt), 'bad.vtt'),
            'source_type': 'transcript'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data.get('code'), 'MALFORMED_VTT')

    # -------------------------------------------------------------------------
    # Valid Uploads & Storage Tests
    # -------------------------------------------------------------------------
    def test_valid_mp4_upload_success_and_storage(self):
        self._login_session()
        res = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_mp4_bytes), 'lecture_intro.mp4'),
            'source_type': 'video'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['details']['input_type'], 'video')
        self.assertEqual(data['details']['original_filename'], 'lecture_intro.mp4')
        self.assertTrue(data['details']['safe_filename'].endswith('lecture_intro.mp4'))

        # Check file was stored on disk in UPLOAD_FOLDER
        stored_files = os.listdir(self.temp_upload_dir)
        self.assertEqual(len(stored_files), 1)
        self.assertEqual(stored_files[0], data['details']['safe_filename'])

        # Check session contains upload info
        with self.client.session_transaction() as sess:
            self.assertIn('current_webinar_upload', sess)
            self.assertEqual(sess['current_webinar_upload']['original_filename'], 'lecture_intro.mp4')

    def test_valid_txt_upload_success(self):
        self._login_session()
        res = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_txt_bytes), 'lecture_transcript.txt'),
            'source_type': 'transcript'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['details']['input_type'], 'transcript')
        self.assertEqual(data['details']['file_extension'], 'txt')

    def test_valid_vtt_upload_success(self):
        self._login_session()
        res = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_vtt_bytes), 'recording_captions.vtt'),
            'source_type': 'transcript'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['details']['file_extension'], 'vtt')

    def test_path_traversal_sanitized(self):
        self._login_session()
        malicious_filename = '../../../../etc/passwd.mp4'
        res = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_mp4_bytes), malicious_filename),
            'source_type': 'video'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        safe_name = data['details']['safe_filename']

        # Ensure stored strictly inside temp_upload_dir, no traversal
        target_path = os.path.join(self.temp_upload_dir, safe_name)
        self.assertTrue(os.path.exists(target_path))
        self.assertNotIn('..', safe_name)

    # -------------------------------------------------------------------------
    # Disk Cleanup Tests
    # -------------------------------------------------------------------------
    def test_replace_webinar_deletes_previous_file_from_disk(self):
        self._login_session()
        # Upload first file
        res1 = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_mp4_bytes), 'first_recording.mp4'),
            'source_type': 'video'
        })
        file1_path = os.path.join(self.temp_upload_dir, res1.get_json()['details']['safe_filename'])
        self.assertTrue(os.path.exists(file1_path))

        # Upload second file (replacing first)
        res2 = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_txt_bytes), 'second_notes.txt'),
            'source_type': 'transcript'
        })
        file2_path = os.path.join(self.temp_upload_dir, res2.get_json()['details']['safe_filename'])
        self.assertTrue(os.path.exists(file2_path))

        # First file must be deleted from disk
        self.assertFalse(os.path.exists(file1_path))
        self.assertEqual(len(os.listdir(self.temp_upload_dir)), 1)

    def test_clear_webinar_deletes_file_and_clears_session(self):
        self._login_session()
        res = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_mp4_bytes), 'to_remove.mp4'),
            'source_type': 'video'
        })
        file_path = os.path.join(self.temp_upload_dir, res.get_json()['details']['safe_filename'])
        self.assertTrue(os.path.exists(file_path))

        # Call clear endpoint
        res_clear = self.client.post('/api/clear-webinar')
        self.assertEqual(res_clear.status_code, 200)

        # File must be removed from disk
        self.assertFalse(os.path.exists(file_path))
        self.assertEqual(len(os.listdir(self.temp_upload_dir)), 0)

        # Session must not contain webinar
        with self.client.session_transaction() as sess:
            self.assertNotIn('current_webinar_upload', sess)

    # -------------------------------------------------------------------------
    # Independent Upload Flows & Job Persistence Tests
    # -------------------------------------------------------------------------
    def test_independent_order_webinar_first_then_csv(self):
        """Verifies webinar upload first, then CSV upload, followed by successful job creation."""
        self._login_session()

        # Step 1: Upload Webinar
        res_web = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_mp4_bytes), 'session1.mp4'),
            'source_type': 'video'
        })
        self.assertEqual(res_web.status_code, 200)

        # Step 2: Upload CSV
        res_csv = self.client.post('/api/upload-csv', data={
            'file': (io.BytesIO(self.valid_csv_bytes), 'students.csv')
        })
        self.assertEqual(res_csv.status_code, 200)

        # Step 3: Validate state
        res_val = self.client.post('/api/validate-state', json={})
        self.assertEqual(res_val.status_code, 200)
        self.assertEqual(res_val.get_json()['details']['recipients_ready'], 2)

        # Step 4: Submit job
        res_job = self.client.post('/api/submit-job', json={})
        self.assertEqual(res_job.status_code, 201)
        job_id = res_job.get_json()['job']['id']

        # Verify DB persistence
        with self.app.app_context():
            job = db.session.get(ProcessingJob, job_id)
            self.assertIsNotNone(job)
            self.assertEqual(job.user_id, self.test_user_id)
            self.assertEqual(job.input_type, 'video')
            self.assertEqual(job.input_file_name, 'session1.mp4')
            self.assertEqual(job.overall_status, 'ready')
            self.assertEqual(job.total_recipients, 2)

            recipients = JobRecipient.query.filter_by(job_id=job.id).all()
            self.assertEqual(len(recipients), 2)
            emails = {r.email for r in recipients}
            self.assertEqual(emails, {'alice@college.edu', 'bob@college.edu'})

    def test_independent_order_csv_first_then_webinar(self):
        """Verifies CSV upload first, then webinar upload, followed by successful job creation."""
        self._login_session()

        # Step 1: Upload CSV
        res_csv = self.client.post('/api/upload-csv', data={
            'file': (io.BytesIO(self.valid_csv_bytes), 'students_first.csv')
        })
        self.assertEqual(res_csv.status_code, 200)

        # Step 2: Upload Webinar (VTT Transcript)
        res_web = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_vtt_bytes), 'transcript_second.vtt'),
            'source_type': 'transcript'
        })
        self.assertEqual(res_web.status_code, 200)

        # Step 3: Validate state
        res_val = self.client.post('/api/validate-state', json={})
        self.assertEqual(res_val.status_code, 200)

        # Step 4: Submit job
        res_job = self.client.post('/api/submit-job', json={})
        self.assertEqual(res_job.status_code, 201)
        job_id = res_job.get_json()['job']['id']

        with self.app.app_context():
            job = db.session.get(ProcessingJob, job_id)
            self.assertIsNotNone(job)
            self.assertEqual(job.input_type, 'transcript')
            self.assertEqual(job.input_file_name, 'transcript_second.vtt')
            self.assertEqual(job.total_recipients, 2)

    def test_submit_job_fails_when_webinar_missing(self):
        self._login_session()
        # Upload CSV only
        self.client.post('/api/upload-csv', data={
            'file': (io.BytesIO(self.valid_csv_bytes), 'students.csv')
        })
        res = self.client.post('/api/submit-job', json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn('No webinar media uploaded', res.get_json()['message'])

    def test_submit_job_fails_when_csv_missing(self):
        self._login_session()
        # Upload Webinar only
        self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_mp4_bytes), 'webinar.mp4'),
            'source_type': 'video'
        })
        res = self.client.post('/api/submit-job', json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn('No valid recipient list validated', res.get_json()['message'])

    def test_submit_job_fails_if_stored_file_missing_from_disk(self):
        self._login_session()
        # Upload both
        res_web = self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_mp4_bytes), 'webinar.mp4'),
            'source_type': 'video'
        })
        self.client.post('/api/upload-csv', data={
            'file': (io.BytesIO(self.valid_csv_bytes), 'students.csv')
        })

        # Manually delete the stored file from disk
        safe_name = res_web.get_json()['details']['safe_filename']
        target_path = os.path.join(self.temp_upload_dir, safe_name)
        if os.path.exists(target_path):
            os.remove(target_path)

        res = self.client.post('/api/submit-job', json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn('missing from server storage', res.get_json()['message'])

    def test_submit_job_session_cleared_after_success(self):
        self._login_session()
        self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_mp4_bytes), 'webinar.mp4'),
            'source_type': 'video'
        })
        self.client.post('/api/upload-csv', data={
            'file': (io.BytesIO(self.valid_csv_bytes), 'students.csv')
        })

        res_job = self.client.post('/api/submit-job', json={})
        self.assertEqual(res_job.status_code, 201)

        # Verify session states were cleared to prevent accidental re-submission
        with self.client.session_transaction() as sess:
            self.assertNotIn('current_webinar_upload', sess)
            self.assertNotIn('current_csv_validation', sess)

    def test_submit_job_rollback_on_database_error(self):
        self._login_session()
        self.client.post('/api/upload-webinar', data={
            'file': (io.BytesIO(self.valid_mp4_bytes), 'webinar.mp4'),
            'source_type': 'video'
        })
        self.client.post('/api/upload-csv', data={
            'file': (io.BytesIO(self.valid_csv_bytes), 'students.csv')
        })

        # Simulate database failure during commit
        with patch('app.routes.dashboard_routes.db.session.commit', side_effect=Exception('Simulated DB Lockout')):
            res = self.client.post('/api/submit-job', json={})
            self.assertEqual(res.status_code, 500)
            self.assertIn('Database transaction failed', res.get_json()['message'])

        # Verify no orphaned records were persisted
        with self.app.app_context():
            job_count = ProcessingJob.query.count()
            recipient_count = JobRecipient.query.count()
            self.assertEqual(job_count, 0)
            self.assertEqual(recipient_count, 0)

if __name__ == '__main__':
    unittest.main()
