import unittest
from unittest.mock import patch
from app import create_app
from app.config import TestConfig
from app.models import db, User

class TestSourceSelectionUI(unittest.TestCase):
    """
    Automated test suite for Prompt A1: Dashboard Source Selection UI & Accessibility Checking.
    Verifies 6-option source rendering, pre-flight accessibility checks,
    and input validation across direct links, YouTube, Google Drive, and local media.
    """
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app.config['SECRET_KEY'] = 'test-source-selection-secret'
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.create_all()
        # Provision test operator
        self.user = User(username='source_tester', email='sourcetester@webinarai.edu', role='user', is_active=True)
        self.user.set_password('SecureTestPass123!')
        db.session.add(self.user)
        db.session.commit()
        self.user_id = self.user.id

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _login_client(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user_id
            sess['username'] = 'source_tester'
            sess['role'] = 'user'

    def test_dashboard_renders_all_six_source_options(self):
        """Verify dashboard HTML contains all 6 Webinar Content Source selector options."""
        self._login_client()
        response = self.client.get('/dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('Section A: Webinar Content Source', html)
        self.assertIn('modeManual', html)
        self.assertIn('Manual Upload', html)
        self.assertIn('modeDirect', html)
        self.assertIn('Direct Link', html)
        self.assertIn('modeYouTube', html)
        self.assertIn('YouTube', html)
        self.assertIn('modeGDrive', html)
        self.assertIn('Google Drive', html)
        self.assertIn('modeLocalFile', html)
        self.assertIn('Local File', html)
        self.assertIn('modeLocalFolder', html)
        self.assertIn('Local Folder', html)
        self.assertIn('Check Accessibility', html)
        self.assertIn('accessibilityReportCard', html)

    def test_check_accessibility_unauthenticated_redirects(self):
        """Verify unauthenticated requests to check-accessibility are rejected with redirect or 401."""
        response = self.client.post('/api/sources/check-accessibility', json={
            'source_type': 'direct',
            'source_url': 'https://example.com/video.mp4'
        })
        self.assertIn(response.status_code, (302, 401))

    def test_check_accessibility_missing_source_type_rejected(self):
        """Verify missing source_type is rejected with 400 Bad Request."""
        self._login_client()
        response = self.client.post('/api/sources/check-accessibility', json={
            'source_url': 'https://example.com/video.mp4'
        })
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['accessibility_status'], 'Source Not Selected')

    @patch('app.providers.direct_provider.DirectMediaProvider.check_accessibility')
    def test_check_accessibility_direct_valid_url(self, mock_check):
        """Verify valid direct MP4 URL returns 200 with Retrieval Supported and detected MIME type."""
        self._login_client()
        mock_check.return_value = {
            'success': True,
            'source_type': 'direct',
            'source_reference': 'https://example.com/recordings/webinar.mp4',
            'accessibility_status': 'Retrieval Supported',
            'media_type': 'video/mp4',
            'file_size': '12 MB',
            'retrieval_eligible': True,
            'requires_auth': False,
            'explanation': 'Direct media URL verified.'
        }
        response = self.client.post('/api/sources/check-accessibility', json={
            'source_type': 'direct',
            'source_url': 'https://example.com/recordings/webinar.mp4'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['source_type'], 'direct')
        self.assertEqual(data['accessibility_status'], 'Retrieval Supported')
        self.assertEqual(data['media_type'], 'video/mp4')
        self.assertTrue(data['retrieval_eligible'])

    @patch('app.providers.direct_provider.DirectMediaProvider.check_accessibility')
    def test_check_accessibility_direct_valid_audio_url(self, mock_check):
        """Verify direct audio URL (.mp3, .wav) detects audio MIME type."""
        self._login_client()
        mock_check.return_value = {
            'success': True,
            'source_type': 'direct',
            'source_reference': 'https://example.com/audio/podcast.mp3',
            'accessibility_status': 'Retrieval Supported',
            'media_type': 'audio/mpeg',
            'file_size': '5 MB',
            'retrieval_eligible': True,
            'requires_auth': False,
            'explanation': 'Direct media URL verified.'
        }
        response = self.client.post('/api/sources/check-accessibility', json={
            'source_type': 'direct',
            'source_url': 'https://example.com/audio/podcast.mp3'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['media_type'], 'audio/mpeg')

    def test_check_accessibility_direct_invalid_protocol(self):
        """Verify non-HTTP protocols (e.g. ftp://) are rejected."""
        self._login_client()
        response = self.client.post('/api/sources/check-accessibility', json={
            'source_type': 'direct',
            'source_url': 'ftp://example.com/video.mp4'
        })
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertIn(data['accessibility_status'], ('Invalid URL', 'Retrieval Restricted'))

    def test_check_accessibility_direct_missing_url(self):
        """Verify empty URL for direct source is rejected."""
        self._login_client()
        response = self.client.post('/api/sources/check-accessibility', json={
            'source_type': 'direct',
            'source_url': ''
        })
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['accessibility_status'], 'Invalid URL')

    def test_check_accessibility_youtube_valid_urls(self):
        """Verify standard watch, youtu.be, and shorts URLs are parsed with video ID."""
        self._login_client()
        urls = [
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'https://youtu.be/dQw4w9WgXcQ',
            'https://www.youtube.com/shorts/dQw4w9WgXcQ'
        ]
        for url in urls:
            response = self.client.post('/api/sources/check-accessibility', json={
                'source_type': 'youtube',
                'source_url': url
            })
            self.assertEqual(response.status_code, 200, f"Failed for {url}")
            data = response.get_json()
            self.assertTrue(data['success'])
            self.assertEqual(data['source_type'], 'youtube')
            self.assertEqual(data['video_id'], 'dQw4w9WgXcQ')
            self.assertEqual(data['accessibility_status'], 'Retrieval Supported')

    def test_check_accessibility_youtube_invalid_url(self):
        """Verify non-YouTube URLs submitted as YouTube are rejected."""
        self._login_client()
        response = self.client.post('/api/sources/check-accessibility', json={
            'source_type': 'youtube',
            'source_url': 'https://vimeo.com/12345678'
        })
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['accessibility_status'], 'Invalid URL')

    def test_check_accessibility_gdrive_valid_link_unauthenticated(self):
        """Verify valid Google Drive link indicates Authentication Required when no OAuth token is stored."""
        self._login_client()
        response = self.client.post('/api/sources/check-accessibility', json={
            'source_type': 'gdrive',
            'source_url': 'https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/view'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['source_type'], 'gdrive')
        self.assertEqual(data['file_id'], '1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms')
        self.assertEqual(data['accessibility_status'], 'Authentication Required')
        self.assertTrue(data['requires_auth'])

    def test_check_accessibility_gdrive_invalid_link(self):
        """Verify non-Drive links submitted as Google Drive are rejected."""
        self._login_client()
        response = self.client.post('/api/sources/check-accessibility', json={
            'source_type': 'gdrive',
            'source_url': 'https://dropbox.com/s/123456/recording.mp4'
        })
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['accessibility_status'], 'Invalid URL')

    def test_check_accessibility_local_file_supported(self):
        """Verify local file with supported extension (.mp4, .mp3, .wav, .m4a) passes."""
        self._login_client()
        response = self.client.post('/api/sources/check-accessibility', json={
            'source_type': 'local_file',
            'filename': 'physics_lecture.mp4'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['media_type'], 'video/mp4')
        self.assertEqual(data['accessibility_status'], 'Retrieval Supported')

    def test_check_accessibility_local_file_unsupported_format(self):
        """Verify local file with unsupported extension (.pdf, .exe) is rejected."""
        self._login_client()
        response = self.client.post('/api/sources/check-accessibility', json={
            'source_type': 'local_file',
            'filename': 'lecture_notes.pdf'
        })
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['accessibility_status'], 'Media Type Unsupported')

    def test_check_accessibility_unknown_source_type_rejected(self):
        """Verify unknown source type is rejected."""
        self._login_client()
        response = self.client.post('/api/sources/check-accessibility', json={
            'source_type': 'torrent',
            'source_url': 'magnet:?xt=urn:btih:...'
        })
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['accessibility_status'], 'Unsupported Source')


if __name__ == '__main__':
    unittest.main()

