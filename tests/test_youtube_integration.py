"""
Automated Test Suite for Prompt A5: YouTube Compliance & Official Caption Integration.

Covers:
1. URL parsing across watch, youtu.be, shorts, and embed formats.
2. Metadata query via YouTube Data API v3 (title, channel, video existence, error handling).
3. Official caption track inspection and ingestion directly into pipeline without video downloading.
4. Strict non-bypass guardrails: Download Restricted when captions unavailable, rejection of scraping/video downloads.
5. Endpoints: POST /api/sources/youtube/check and POST /api/sources/youtube/retrieve.
6. Job submission integration with input_type='transcript'.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob
from app.providers.youtube_provider import YouTubeProvider, extract_youtube_video_id


class TestYouTubeIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_upload_dir = tempfile.mkdtemp()
        self.upload_dir = os.path.join(self.temp_upload_dir, 'uploads')
        os.makedirs(self.upload_dir, exist_ok=True)

        class YouTubeTestConfig(TestConfig):
            UPLOAD_FOLDER = self.upload_dir
            MAX_VIDEO_SIZE = 50 * 1024 * 1024
            YOUTUBE_API_KEY = 'test_youtube_api_key_123'

        self.app = create_app(YouTubeTestConfig)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed test user
        self.user = User(
            username='yt_student',
            email='yt_student@webinarai.edu',
            role='user',
            is_active=True
        )
        self.user.set_password('YouTubeSecure123!')
        db.session.add(self.user)
        db.session.commit()
        self.user_id = self.user.id

        self.provider = YouTubeProvider()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        shutil.rmtree(self.temp_upload_dir, ignore_errors=True)

    def _login(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user_id
            sess['username'] = 'yt_student'
            sess['role'] = 'user'

    def test_extract_video_id_formats(self):
        """Verify URL extractor handles all standard YouTube URL variations."""
        id1 = extract_youtube_video_id('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        self.assertEqual(id1, 'dQw4w9WgXcQ')

        id2 = extract_youtube_video_id('https://youtu.be/dQw4w9WgXcQ')
        self.assertEqual(id2, 'dQw4w9WgXcQ')

        id3 = extract_youtube_video_id('https://www.youtube.com/shorts/dQw4w9WgXcQ')
        self.assertEqual(id3, 'dQw4w9WgXcQ')

        id4 = extract_youtube_video_id('https://www.youtube.com/embed/dQw4w9WgXcQ')
        self.assertEqual(id4, 'dQw4w9WgXcQ')

        id5 = extract_youtube_video_id('https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=10s')
        self.assertEqual(id5, 'dQw4w9WgXcQ')

        # Raw 11-char ID
        id6 = extract_youtube_video_id('dQw4w9WgXcQ')
        self.assertEqual(id6, 'dQw4w9WgXcQ')

        # Invalid URL
        self.assertIsNone(extract_youtube_video_id('https://example.com/video.mp4'))
        self.assertIsNone(extract_youtube_video_id(''))

    def test_provider_identify(self):
        """Verify YouTubeProvider identifies YouTube URLs and rejects other providers."""
        self.assertTrue(self.provider.identify('https://www.youtube.com/watch?v=dQw4w9WgXcQ'))
        self.assertTrue(self.provider.identify('https://youtu.be/dQw4w9WgXcQ'))
        self.assertFalse(self.provider.identify('https://drive.google.com/file/d/123/view'))
        self.assertFalse(self.provider.identify('https://example.com/recording.mp4'))

    def test_check_accessibility_invalid_url(self):
        """Verify check_accessibility returns 400 for invalid YouTube link."""
        res = self.provider.check_accessibility('https://notyoutube.com/watch')
        self.assertFalse(res['success'])
        self.assertEqual(res['accessibility_status'], 'Invalid URL')

    def test_check_accessibility_video_not_found(self):
        """Verify check_accessibility reports Video Not Found when API returns empty items."""
        mock_service = MagicMock()
        mock_videos = MagicMock()
        mock_videos.list.return_value.execute.return_value = {'items': []}
        mock_service.videos.return_value = mock_videos

        res = self.provider.check_accessibility(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            youtube_service=mock_service
        )

        self.assertFalse(res['success'])
        self.assertEqual(res['accessibility_status'], 'Video Not Found')

    def test_check_accessibility_with_captions_supported(self):
        """Verify check_accessibility succeeds when official captions are detected."""
        mock_service = MagicMock()
        mock_videos = MagicMock()
        mock_videos.list.return_value.execute.return_value = {
            'items': [{
                'id': 'dQw4w9WgXcQ',
                'snippet': {
                    'title': 'AI Webinar Lecture',
                    'channelTitle': 'Computer Science Dept'
                }
            }]
        }
        mock_captions = MagicMock()
        mock_captions.list.return_value.execute.return_value = {
            'items': [{'id': 'caption_track_en', 'snippet': {'language': 'en'}}]
        }
        mock_service.videos.return_value = mock_videos
        mock_service.captions.return_value = mock_captions

        res = self.provider.check_accessibility(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            youtube_service=mock_service
        )

        self.assertTrue(res['success'])
        self.assertEqual(res['accessibility_status'], 'Retrieval Supported')
        self.assertEqual(res['title'], 'AI Webinar Lecture')
        self.assertEqual(res['channel'], 'Computer Science Dept')
        self.assertTrue(res['retrieval_eligible'])

    def test_check_accessibility_without_captions_restricted(self):
        """Verify check_accessibility reports Download Restricted when no captions exist."""
        mock_service = MagicMock()
        mock_videos = MagicMock()
        mock_videos.list.return_value.execute.return_value = {
            'items': [{
                'id': 'dQw4w9WgXcQ',
                'snippet': {
                    'title': 'Silent Seminar',
                    'channelTitle': 'Faculty Group'
                }
            }]
        }
        mock_captions = MagicMock()
        mock_captions.list.return_value.execute.return_value = {'items': []}
        mock_service.videos.return_value = mock_videos
        mock_service.captions.return_value = mock_captions

        res = self.provider.check_accessibility(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            youtube_service=mock_service
        )

        self.assertFalse(res['success'])
        self.assertEqual(res['accessibility_status'], 'Download Restricted')
        self.assertFalse(res['retrieval_eligible'])
        self.assertIn('prohibited', res['message'])

    def test_retrieve_media_strict_guardrail_rejects_video_download(self):
        """Verify retrieve_media strictly rejects any attempt to download video stream."""
        result = self.provider.retrieve_media(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            destination_dir=self.upload_dir,
            force_video_download=True
        )

        self.assertFalse(result['success'])
        self.assertEqual(result['code'], 'DOWNLOAD_RESTRICTED')
        self.assertIn('strictly prohibited', result['error'])

    def test_retrieve_media_success_with_captions(self):
        """Verify retrieve_media writes WebVTT captions directly without video downloading."""
        sample_vtt = (
            "WEBVTT\n\n"
            "00:00:01.000 --> 00:00:04.000\n"
            "Welcome to the artificial intelligence webinar.\n\n"
            "00:00:05.000 --> 00:00:08.000\n"
            "Today we will cover deep neural networks.\n"
        )

        result = self.provider.retrieve_media(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            destination_dir=self.upload_dir,
            caption_content=sample_vtt
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['source_type'], 'youtube')
        self.assertEqual(result['input_type'], 'transcript')
        self.assertEqual(result['file_extension'], 'vtt')
        self.assertTrue(os.path.exists(result['storage_path']))

        with open(result['storage_path'], 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertTrue(content.startswith('WEBVTT'))
        self.assertIn('deep neural networks', content)

    @patch('googleapiclient.discovery.build')
    def test_endpoint_youtube_check(self, mock_build):
        """Verify POST /api/sources/youtube/check endpoint returns metadata."""
        self._login()
        mock_service = MagicMock()
        mock_videos = MagicMock()
        mock_videos.list.return_value.execute.return_value = {
            'items': [{
                'id': 'dQw4w9WgXcQ',
                'snippet': {'title': 'Sample AI Video', 'channelTitle': 'AI Channel'}
            }]
        }
        mock_captions = MagicMock()
        mock_captions.list.return_value.execute.return_value = {
            'items': [{'id': 'c1'}]
        }
        mock_service.videos.return_value = mock_videos
        mock_service.captions.return_value = mock_captions
        mock_build.return_value = mock_service

        resp = self.client.post(
            '/api/sources/youtube/check',
            json={'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['video_id'], 'dQw4w9WgXcQ')
        self.assertEqual(data['accessibility_status'], 'Retrieval Supported')

    def test_endpoint_youtube_retrieve_restricted(self):
        """Verify POST /api/sources/youtube/retrieve rejects when no captions are available."""
        self._login()
        resp = self.client.post(
            '/api/sources/youtube/retrieve',
            json={'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'}
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['code'], 'DOWNLOAD_RESTRICTED')

    def test_end_to_end_youtube_job_creation(self):
        """Verify full flow: retrieve captions -> stage in session -> create processing job."""
        self._login()

        sample_vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nKey machine learning takeaways.\n"

        # 1. Retrieve official captions
        resp = self.client.post(
            '/api/sources/youtube/retrieve',
            json={
                'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                'caption_content': sample_vtt
            }
        )
        self.assertEqual(resp.status_code, 200)
        ret_data = resp.get_json()
        self.assertTrue(ret_data['success'])
        self.assertEqual(ret_data['details']['input_type'], 'transcript')

        # 2. Stage recipient list
        with self.client.session_transaction() as sess:
            sess['current_csv_validation'] = {
                'valid_unique_count': 1,
                'valid_recipients': [{'email': 'student@webinarai.edu', 'name': 'Bob Student'}]
            }

        # 3. Submit job
        job_resp = self.client.post('/api/submit-job', json={})
        self.assertEqual(job_resp.status_code, 201)

        job_id = job_resp.get_json()['job']['id']
        job = db.session.get(ProcessingJob, job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job.user_id, self.user_id)
        self.assertEqual(job.input_type, 'transcript')

    def test_check_accessibility_without_service_fallback_supported(self):
        """Verify check_accessibility returns Retrieval Supported with transcript guidance when no service is configured."""
        res = self.provider.check_accessibility('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        self.assertTrue(res['success'])
        self.assertEqual(res['accessibility_status'], 'Retrieval Supported')
        self.assertTrue(res['retrieval_eligible'])
        self.assertIn('transcript', res['explanation'].lower())

    def test_check_accessibility_with_user_supplied_caption_content(self):
        """Verify check_accessibility returns Transcript Attached when user supplies caption content."""
        res = self.provider.check_accessibility(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            caption_content='WEBVTT\n\n00:00:00.000 --> 00:01:00.000\nHello and welcome.'
        )
        self.assertTrue(res['success'])
        self.assertEqual(res['accessibility_status'], 'Transcript Attached')
        self.assertTrue(res['retrieval_eligible'])
        self.assertEqual(res['source_type'], 'youtube')

    def test_endpoint_youtube_check_with_caption_content(self):
        """Verify POST /api/sources/youtube/check succeeds with Transcript Attached when caption_content is sent."""
        self._login()
        resp = self.client.post(
            '/api/sources/youtube/check',
            json={
                'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                'caption_content': 'WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nLecture text.'
            }
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['accessibility_status'], 'Transcript Attached')

    @patch('app.providers.youtube_provider.YouTubeProvider.build_service')
    def test_retrieve_media_builds_service_from_api_key(self, mock_build_service):
        """Verify retrieve_media instantiates YouTube service when api_key is supplied."""
        mock_service = MagicMock()
        mock_captions = MagicMock()
        mock_captions.list.return_value.execute.return_value = {'items': []}
        mock_service.captions.return_value = mock_captions
        mock_build_service.return_value = mock_service

        res = self.provider.retrieve_media(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            destination_dir=self.upload_dir,
            api_key='custom_test_api_key'
        )

        mock_build_service.assert_called_with('custom_test_api_key')
        self.assertFalse(res['success'])
        self.assertEqual(res['code'], 'DOWNLOAD_RESTRICTED')

    def test_retrieve_media_formats_plain_text_to_vtt(self):
        """Verify retrieve_media automatically prepends WEBVTT header to plain text caption input."""
        res = self.provider.retrieve_media(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            destination_dir=self.upload_dir,
            caption_content='This is a plain transcript without WEBVTT header.'
        )

        self.assertTrue(res['success'])
        with open(res['storage_path'], 'r', encoding='utf-8') as f:
            saved_content = f.read()
        self.assertTrue(saved_content.startswith('WEBVTT\n\n'))
        self.assertIn('This is a plain transcript without WEBVTT header.', saved_content)


if __name__ == '__main__':
    unittest.main()
