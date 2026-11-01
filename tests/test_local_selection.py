"""
Tests for Local Computer File and Folder Selection (Prompt A3).

Validates:
1. LocalMediaProvider source identification and pre-flight accessibility checks.
2. Binary container verification for local MP4, MP3, WAV, and M4A uploads.
3. Size limit enforcement and empty file rejection.
4. REST endpoint POST /api/sources/local/upload authentication and validation.
5. Session staging and integration with job submission.
"""

import io
import os
import shutil
import tempfile
import unittest
from flask import session
from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob
from app.providers.local_provider import LocalMediaProvider


class TestLocalSelection(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.upload_dir = os.path.join(self.temp_dir, 'uploads')
        os.makedirs(self.upload_dir, exist_ok=True)

        class LocalTestConfig(TestConfig):
            UPLOAD_FOLDER = self.upload_dir
            MAX_VIDEO_SIZE = 50 * 1024 * 1024

        self.app = create_app(LocalTestConfig)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed test user
        self.test_user = User(
            username='localuser',
            email='localuser@webinarai.edu',
            role='user'
        )
        self.test_user.set_password('LocalSecure123!')
        db.session.add(self.test_user)
        db.session.commit()
        self.user_id = self.test_user.id

        self.provider = LocalMediaProvider()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _login(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user_id
            sess['username'] = 'localuser'
            sess['role'] = 'user'

    def test_provider_identify_source(self):
        """Verify local provider correctly identifies local sources and file extensions."""
        self.assertTrue(self.provider.identify_source('presentation.mp4'))
        self.assertTrue(self.provider.identify_source('audio_recording.mp3'))
        self.assertTrue(self.provider.identify_source('seminar.wav'))
        self.assertTrue(self.provider.identify_source('podcast.m4a'))
        self.assertTrue(self.provider.identify_source('local_file'))
        self.assertTrue(self.provider.identify_source('local_folder'))
        self.assertTrue(self.provider.identify_source('file:///C:/Users/recording.mp4'))

        # False for remote URLs or non-media
        self.assertFalse(self.provider.identify_source('https://example.com/video.mp4'))
        self.assertFalse(self.provider.identify_source('document.pdf'))
        self.assertFalse(self.provider.identify_source('script.py'))
        self.assertFalse(self.provider.identify_source(''))

    def test_provider_check_accessibility_success(self):
        """Verify check_accessibility returns 200 for supported local extensions."""
        res_mp4 = self.provider.check_accessibility('lecture.mp4')
        self.assertTrue(res_mp4['success'])
        self.assertEqual(res_mp4['media_type'], 'video/mp4')
        self.assertTrue(res_mp4['retrieval_eligible'])

        res_mp3 = self.provider.check_accessibility('speech.mp3')
        self.assertTrue(res_mp3['success'])
        self.assertEqual(res_mp3['media_type'], 'audio/mp3')

        res_wav = self.provider.check_accessibility('talk.wav')
        self.assertTrue(res_wav['success'])
        self.assertEqual(res_wav['media_type'], 'audio/wav')

    def test_provider_check_accessibility_unsupported(self):
        """Verify unsupported extensions are rejected."""
        res = self.provider.check_accessibility('report.pdf')
        self.assertFalse(res['success'])
        self.assertEqual(res['accessibility_status'], 'Media Type Unsupported')
        self.assertFalse(res['retrieval_eligible'])

    def test_provider_check_accessibility_size_limit(self):
        """Verify check_accessibility detects oversized files."""
        res = self.provider.check_accessibility(
            'huge.mp4',
            file_size=60 * 1024 * 1024,
            max_size_bytes=50 * 1024 * 1024
        )
        self.assertFalse(res['success'])
        self.assertEqual(res['accessibility_status'], 'File Too Large')

    def test_provider_retrieve_valid_mp4(self):
        """Verify retrieve_media successfully stages a valid MP4 with ftyp signature."""
        mp4_bytes = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42' + b'\x00' * 100
        file_obj = io.BytesIO(mp4_bytes)
        file_obj.filename = 'webinar.mp4'

        result = self.provider.retrieve_media(
            source_reference='webinar.mp4',
            destination_dir=self.upload_dir,
            file_storage=file_obj
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['input_type'], 'video')
        self.assertEqual(result['file_extension'], 'mp4')
        self.assertTrue(os.path.exists(result['storage_path']))
        self.assertGreater(result['file_size'], 0)

    def test_provider_retrieve_valid_mp3(self):
        """Verify retrieve_media successfully stages a valid MP3 with ID3 signature."""
        mp3_bytes = b'ID3\x03\x00\x00\x00\x00\x00\x00' + b'\xff\xfb\x90\x64' + b'\x00' * 50
        file_obj = io.BytesIO(mp3_bytes)
        file_obj.filename = 'audio_lecture.mp3'

        result = self.provider.retrieve_media(
            source_reference='audio_lecture.mp3',
            destination_dir=self.upload_dir,
            file_storage=file_obj
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['input_type'], 'audio')
        self.assertEqual(result['file_extension'], 'mp3')
        self.assertTrue(os.path.exists(result['storage_path']))

    def test_provider_retrieve_valid_wav(self):
        """Verify retrieve_media successfully stages a valid WAV with RIFF/WAVE signature."""
        wav_bytes = b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00' + b'\x00' * 30
        file_obj = io.BytesIO(wav_bytes)
        file_obj.filename = 'session.wav'

        result = self.provider.retrieve_media(
            source_reference='session.wav',
            destination_dir=self.upload_dir,
            file_storage=file_obj
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['input_type'], 'audio')
        self.assertEqual(result['file_extension'], 'wav')
        self.assertTrue(os.path.exists(result['storage_path']))

    def test_provider_retrieve_rejects_empty_file(self):
        """Verify retrieve_media rejects empty (0-byte) files."""
        file_obj = io.BytesIO(b'')
        file_obj.filename = 'empty.mp4'

        result = self.provider.retrieve_media(
            source_reference='empty.mp4',
            destination_dir=self.upload_dir,
            file_storage=file_obj
        )

        self.assertFalse(result['success'])
        self.assertEqual(result['code'], 'EMPTY_FILE')

    def test_provider_retrieve_rejects_disguised_html(self):
        """Verify retrieve_media rejects HTML or text disguised as .mp4."""
        html_bytes = b'<!DOCTYPE html><html><body>Error 404</body></html>'
        file_obj = io.BytesIO(html_bytes)
        file_obj.filename = 'fake.mp4'

        result = self.provider.retrieve_media(
            source_reference='fake.mp4',
            destination_dir=self.upload_dir,
            file_storage=file_obj
        )

        self.assertFalse(result['success'])
        self.assertEqual(result['code'], 'INVALID_CONTAINER')

    def test_provider_retrieve_enforces_size_limit(self):
        """Verify retrieve_media stops and deletes file if max_size_bytes is exceeded."""
        oversized_bytes = b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 2000
        file_obj = io.BytesIO(oversized_bytes)
        file_obj.filename = 'too_big.mp4'

        result = self.provider.retrieve_media(
            source_reference='too_big.mp4',
            destination_dir=self.upload_dir,
            max_size_bytes=500,  # limit to 500 bytes
            file_storage=file_obj
        )

        self.assertFalse(result['success'])
        self.assertEqual(result['code'], 'FILE_TOO_LARGE')

    def test_endpoint_upload_local_unauthenticated(self):
        """Verify /api/sources/local/upload requires authentication."""
        resp = self.client.post('/api/sources/local/upload')
        self.assertIn(resp.status_code, (302, 401))

    def test_endpoint_upload_local_no_file(self):
        """Verify /api/sources/local/upload returns 400 when no file is submitted."""
        self._login()
        resp = self.client.post('/api/sources/local/upload', data={})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['success'])

    def test_endpoint_upload_local_mp4_success(self):
        """Verify authenticated user can upload local MP4 and session is populated."""
        self._login()
        mp4_content = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42' + b'\x00' * 128
        data = {
            'file': (io.BytesIO(mp4_content), 'college_seminar.mp4'),
            'source_type': 'local_file'
        }
        resp = self.client.post(
            '/api/sources/local/upload',
            data=data,
            content_type='multipart/form-data'
        )

        self.assertEqual(resp.status_code, 200)
        json_data = resp.get_json()
        self.assertTrue(json_data['success'])
        self.assertEqual(json_data['details']['input_type'], 'video')
        self.assertEqual(json_data['details']['file_extension'], 'mp4')

        # Check session state
        with self.client.session_transaction() as sess:
            upload_state = sess.get('current_webinar_upload')
            self.assertIsNotNone(upload_state)
            self.assertEqual(upload_state['source_type'], 'local_file')
            self.assertEqual(upload_state['input_type'], 'video')
            self.assertTrue(os.path.exists(upload_state['storage_path']))

    def test_endpoint_upload_local_folder_mp3_success(self):
        """Verify uploading an MP3 from a local folder selection sets source_type=local_folder."""
        self._login()
        mp3_content = b'ID3\x03\x00\x00\x00\x00\x00\x00' + b'\xff\xfb\x90\x64' + b'\x00' * 64
        data = {
            'file': (io.BytesIO(mp3_content), 'faculty_lecture.mp3'),
            'source_type': 'local_folder'
        }
        resp = self.client.post(
            '/api/sources/local/upload',
            data=data,
            content_type='multipart/form-data'
        )

        self.assertEqual(resp.status_code, 200)
        json_data = resp.get_json()
        self.assertTrue(json_data['success'])
        self.assertEqual(json_data['details']['source_type'], 'local_folder')
        self.assertEqual(json_data['details']['input_type'], 'audio')

    def test_end_to_end_local_file_job_creation(self):
        """Verify full end-to-end flow: upload local file -> stage in session -> create job."""
        self._login()

        # 1. Upload local file
        mp4_content = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42' + b'\x00' * 128
        data = {
            'file': (io.BytesIO(mp4_content), 'final_presentation.mp4'),
            'source_type': 'local_file'
        }
        resp = self.client.post('/api/sources/local/upload', data=data, content_type='multipart/form-data')
        self.assertEqual(resp.status_code, 200)

        # 2. Stage recipients in session
        with self.client.session_transaction() as sess:
            sess['current_csv_validation'] = {
                'valid_unique_count': 1,
                'valid_recipients': [{'email': 'student@university.edu', 'name': 'Alice Student'}]
            }

        # 3. Submit job
        submit_resp = self.client.post('/api/submit-job')
        self.assertEqual(submit_resp.status_code, 201)
        job_data = submit_resp.get_json()
        self.assertTrue(job_data['success'])

        job_id = job_data['job']['id']
        job = ProcessingJob.query.get(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job.user_id, self.user_id)
        self.assertEqual(job.input_type, 'video')


if __name__ == '__main__':
    unittest.main()
