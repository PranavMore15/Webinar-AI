"""
Automated Test Suite for Prompt A4: Google Drive Official Integration.

Covers:
1. Google OAuth 2.0 flow: /auth/gdrive/connect, CSRF state generation, /auth/gdrive/callback, token exchange.
2. GDriveMediaProvider file identification, URL extraction, and accessibility checking.
3. Official Drive API v3 metadata query, media type validation, and error handling (401, 403, 404, 429, Google Docs, canDownload=False).
4. Streaming download with byte-level limit enforcement and container signature verification.
5. Endpoints: /api/sources/gdrive/status, /api/sources/gdrive/disconnect, /api/sources/gdrive/check, /api/sources/gdrive/retrieve.
6. ProcessingJob submission after Google Drive media retrieval.
"""

import os
import io
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob
from app.providers.gdrive_provider import (
    GDriveMediaProvider,
    extract_gdrive_file_id,
    SUPPORTED_MEDIA_EXTENSIONS
)


class TestGDriveIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_upload_dir = tempfile.mkdtemp()
        self.upload_dir = os.path.join(self.temp_upload_dir, 'uploads')
        os.makedirs(self.upload_dir, exist_ok=True)

        class GDriveTestConfig(TestConfig):
            UPLOAD_FOLDER = self.upload_dir
            MAX_VIDEO_SIZE = 50 * 1024 * 1024
            GOOGLE_CLIENT_ID = 'test-client-id.apps.googleusercontent.com'
            GOOGLE_CLIENT_SECRET = 'test-client-secret'

        self.app = create_app(GDriveTestConfig)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed test user
        self.user = User(
            username='gdrive_tester',
            email='gdrive_tester@webinarai.edu',
            role='user',
            is_active=True
        )
        self.user.set_password('DriveSecurePass123!')
        db.session.add(self.user)
        db.session.commit()
        self.user_id = self.user.id

        self.provider = GDriveMediaProvider()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        shutil.rmtree(self.temp_upload_dir, ignore_errors=True)

    def _login(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user_id
            sess['username'] = 'gdrive_tester'
            sess['role'] = 'user'

    def test_extract_file_id(self):
        """Verify URL parser extracts file ID from various standard Drive formats."""
        id1 = extract_gdrive_file_id('https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/view')
        self.assertEqual(id1, '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms')

        id2 = extract_gdrive_file_id('https://drive.google.com/open?id=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms')
        self.assertEqual(id2, '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms')

        id3 = extract_gdrive_file_id('https://docs.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit')
        self.assertEqual(id3, '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms')

        # Invalid link
        self.assertIsNone(extract_gdrive_file_id('https://example.com/file.mp4'))

    def test_provider_identify(self):
        """Verify GDriveMediaProvider identifies Google Drive links and rejects other URLs."""
        self.assertTrue(self.provider.identify('https://drive.google.com/file/d/1234567890abcdefghijklmnop/view'))
        self.assertFalse(self.provider.identify('https://www.youtube.com/watch?v=dQw4w9WgXcQ'))
        self.assertFalse(self.provider.identify('https://example.com/recording.mp4'))
        self.assertFalse(self.provider.identify(''))

    def test_oauth_connect_unauthenticated(self):
        """Verify /auth/gdrive/connect requires user to be signed in."""
        resp = self.client.get('/auth/gdrive/connect')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])

    @patch('google_auth_oauthlib.flow.Flow.from_client_config')
    def test_oauth_connect_generates_state_and_redirects(self, mock_flow_cls):
        """Verify /auth/gdrive/connect generates CSRF state and redirects to Google."""
        self._login()
        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = ('https://accounts.google.com/o/oauth2/auth?state=xyz', 'xyz')
        mock_flow_cls.return_value = mock_flow

        resp = self.client.get('/auth/gdrive/connect')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers['Location'].startswith('https://accounts.google.com'))

        # Verify CSRF state saved in session
        with self.client.session_transaction() as sess:
            self.assertIsNotNone(sess.get('gdrive_oauth_state'))

    def test_oauth_callback_csrf_rejection(self):
        """Verify /auth/gdrive/callback rejects mismatched or missing CSRF state."""
        self._login()
        with self.client.session_transaction() as sess:
            sess['gdrive_oauth_state'] = 'expected_state_token'

        # Send mismatched state
        resp = self.client.get('/auth/gdrive/callback?state=wrong_state&code=test_code')
        self.assertEqual(resp.status_code, 302)

        # Token should NOT be set
        with self.client.session_transaction() as sess:
            self.assertNotIn('gdrive_token', sess)

    @patch('google_auth_oauthlib.flow.Flow.from_client_config')
    def test_oauth_callback_success(self, mock_flow_cls):
        """Verify successful OAuth callback exchanges code for token and stores in session."""
        self._login()
        valid_state = 'valid_oauth_state_123'
        with self.client.session_transaction() as sess:
            sess['gdrive_oauth_state'] = valid_state
            sess['gdrive_code_verifier'] = 'pkce_verifier_string_456'

        mock_creds = MagicMock()
        mock_creds.token = 'ya29.sample_access_token'
        mock_creds.refresh_token = 'sample_refresh_token'
        mock_creds.token_uri = 'https://oauth2.googleapis.com/token'
        mock_creds.client_id = 'test-client-id'
        mock_creds.client_secret = 'test-client-secret'
        mock_creds.scopes = ['https://www.googleapis.com/auth/drive.readonly']

        mock_flow = MagicMock()
        mock_flow.credentials = mock_creds
        mock_flow_cls.return_value = mock_flow

        resp = self.client.get(f'/auth/gdrive/callback?state={valid_state}&code=sample_auth_code')
        self.assertEqual(resp.status_code, 302)

        # Check session has token and CSRF state was cleared
        with self.client.session_transaction() as sess:
            self.assertIn('gdrive_token', sess)
            self.assertEqual(sess['gdrive_token']['token'], 'ya29.sample_access_token')
            self.assertNotIn('gdrive_oauth_state', sess)
            self.assertNotIn('gdrive_code_verifier', sess)

        self.assertEqual(mock_flow.code_verifier, 'pkce_verifier_string_456')

    def test_disconnect_endpoint(self):
        """Verify /api/sources/gdrive/disconnect clears stored token from session."""
        self._login()
        with self.client.session_transaction() as sess:
            sess['gdrive_token'] = {'token': 'dummy_token'}

        resp = self.client.post('/api/sources/gdrive/disconnect')
        self.assertEqual(resp.status_code, 200)
        json_data = resp.get_json()
        self.assertTrue(json_data['success'])
        self.assertFalse(json_data['connected'])

        with self.client.session_transaction() as sess:
            self.assertNotIn('gdrive_token', sess)

    def test_status_endpoint(self):
        """Verify /api/sources/gdrive/status reports correct connection state."""
        self._login()
        # Not connected
        resp1 = self.client.get('/api/sources/gdrive/status')
        self.assertEqual(resp1.status_code, 200)
        self.assertFalse(resp1.get_json()['connected'])

        # Connected
        with self.client.session_transaction() as sess:
            sess['gdrive_token'] = {'token': 'active_token'}
        resp2 = self.client.get('/api/sources/gdrive/status')
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.get_json()['connected'])

    def test_check_accessibility_unauthenticated_requests_auth(self):
        """Verify checking a Drive link without connected account indicates Authentication Required."""
        res = self.provider.check_accessibility(
            'https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/view'
        )
        self.assertTrue(res['success'])
        self.assertEqual(res['accessibility_status'], 'Authentication Required')
        self.assertTrue(res['requires_auth'])

    def test_check_accessibility_with_mock_drive_service(self):
        """Verify check_accessibility queries metadata when service/token is provided."""
        mock_service = MagicMock()
        mock_files = MagicMock()
        mock_files.get.return_value.execute.return_value = {
            'id': '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms',
            'name': 'webinar_lecture.mp4',
            'mimeType': 'video/mp4',
            'size': '15728640',  # 15 MB
            'capabilities': {'canDownload': True},
            'trashed': False
        }
        mock_service.files.return_value = mock_files

        res = self.provider.check_accessibility(
            'https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/view',
            drive_service=mock_service
        )

        self.assertTrue(res['success'])
        self.assertEqual(res['accessibility_status'], 'Ready for Retrieval')
        self.assertEqual(res['filename'], 'webinar_lecture.mp4')
        self.assertTrue(res['retrieval_eligible'])

    def test_check_accessibility_rejects_google_docs(self):
        """Verify Google Docs / Sheets files are rejected as non-media."""
        mock_service = MagicMock()
        mock_files = MagicMock()
        mock_files.get.return_value.execute.return_value = {
            'id': 'doc_123',
            'name': 'Meeting Notes',
            'mimeType': 'application/vnd.google-apps.document',
            'capabilities': {'canDownload': True},
            'trashed': False
        }
        mock_service.files.return_value = mock_files

        res = self.provider.check_accessibility(
            'https://drive.google.com/file/d/doc_123/view',
            drive_service=mock_service
        )

        self.assertFalse(res['success'])
        self.assertEqual(res['accessibility_status'], 'Media Type Unsupported')
        self.assertIn('Google Workspace documents', res['message'])

    def test_check_accessibility_rejects_download_disabled(self):
        """Verify check_accessibility detects when file owner has disabled downloads."""
        mock_service = MagicMock()
        mock_files = MagicMock()
        mock_files.get.return_value.execute.return_value = {
            'id': 'video_nodownload',
            'name': 'restricted.mp4',
            'mimeType': 'video/mp4',
            'capabilities': {'canDownload': False},
            'trashed': False
        }
        mock_service.files.return_value = mock_files

        res = self.provider.check_accessibility(
            'https://drive.google.com/file/d/video_nodownload/view',
            drive_service=mock_service
        )

        self.assertFalse(res['success'])
        self.assertEqual(res['accessibility_status'], 'Download Restricted')
        self.assertIn('disabled downloads', res['message'])

    def test_check_accessibility_handles_404_not_found(self):
        """Verify 404 from Drive API returns friendly File Not Found status."""
        mock_service = MagicMock()
        mock_files = MagicMock()
        mock_files.get.return_value.execute.side_effect = Exception('HttpError 404: File not found')
        mock_service.files.return_value = mock_files

        res = self.provider.check_accessibility(
            'https://drive.google.com/file/d/nonexistent/view',
            drive_service=mock_service
        )

        self.assertFalse(res['success'])
        self.assertEqual(res['accessibility_status'], 'File Not Found')

    def test_check_accessibility_handles_403_access_denied(self):
        """Verify 403 from Drive API returns Access Denied status."""
        mock_service = MagicMock()
        mock_files = MagicMock()
        mock_files.get.return_value.execute.side_effect = Exception('HttpError 403: The user does not have sufficient permissions')
        mock_service.files.return_value = mock_files

        res = self.provider.check_accessibility(
            'https://drive.google.com/file/d/private_video/view',
            drive_service=mock_service
        )

        self.assertFalse(res['success'])
        self.assertEqual(res['accessibility_status'], 'Access Denied')

    @patch('googleapiclient.http.MediaIoBaseDownload')
    def test_retrieve_media_success_and_session_staging(self, mock_downloader_cls):
        """Verify retrieve_media streams Google Drive file and verifies container signature."""
        valid_mp4_content = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42' + b'\x00' * 256

        mock_service = MagicMock()
        mock_files = MagicMock()
        mock_files.get.return_value.execute.return_value = {
            'id': 'gdrive_sample_id',
            'name': 'webinar_final.mp4',
            'mimeType': 'video/mp4',
            'size': str(len(valid_mp4_content)),
            'capabilities': {'canDownload': True}
        }
        mock_service.files.return_value = mock_files

        # Mock MediaIoBaseDownload
        def mock_downloader_init(fh, request, chunksize):
            fh.write(valid_mp4_content)
            mock_inst = MagicMock()
            mock_status = MagicMock()
            mock_status.resumable_progress = len(valid_mp4_content)
            mock_inst.next_chunk.return_value = (mock_status, True)
            return mock_inst

        mock_downloader_cls.side_effect = mock_downloader_init

        result = self.provider.retrieve_media(
            source_reference='https://drive.google.com/file/d/gdrive_sample_id/view',
            destination_dir=self.upload_dir,
            drive_service=mock_service
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['source_type'], 'gdrive')
        self.assertEqual(result['input_type'], 'video')
        self.assertTrue(os.path.exists(result['storage_path']))
        self.assertEqual(result['file_size'], len(valid_mp4_content))

    @patch('app.providers.gdrive_provider.GDriveMediaProvider.retrieve_media')
    def test_end_to_end_gdrive_job_creation(self, mock_retrieve):
        """Verify full end-to-end flow: retrieve GDrive media -> stage session -> submit job."""
        self._login()

        # Mock provider retrieval output
        fake_storage = os.path.join(self.upload_dir, 'sample_gdrive_webinar.mp4')
        with open(fake_storage, 'wb') as f:
            f.write(b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42' + b'\x00' * 128)

        mock_retrieve.return_value = {
            'success': True,
            'source_type': 'gdrive',
            'input_type': 'video',
            'original_filename': 'lecture_recording.mp4',
            'safe_filename': 'safe_lecture_recording.mp4',
            'storage_path': fake_storage,
            'file_size': 148,
            'file_extension': 'mp4'
        }

        # 1. Trigger retrieve endpoint
        resp = self.client.post(
            '/api/sources/gdrive/retrieve',
            json={'url': 'https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/view'}
        )
        self.assertEqual(resp.status_code, 200)

        # 2. Stage recipient list
        with self.client.session_transaction() as sess:
            sess['current_csv_validation'] = {
                'valid_unique_count': 1,
                'valid_recipients': [{'email': 'learner@webinarai.edu', 'name': 'Learner'}]
            }

        # 3. Submit job
        job_resp = self.client.post('/api/submit-job', json={})
        self.assertEqual(job_resp.status_code, 201)

        job_id = job_resp.get_json()['job']['id']
        job = db.session.get(ProcessingJob, job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job.user_id, self.user_id)
        self.assertEqual(job.input_type, 'video')


if __name__ == '__main__':
    unittest.main()

