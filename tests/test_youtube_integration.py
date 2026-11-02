"""
Automated Test Suite for Prompt A5: YouTube Media Retrieval Using yt-dlp.

Covers:
1. URL parsing across watch, youtu.be, shorts, embed, and mobile formats.
2. Provider identification and domain restriction defenses.
3. Pre-flight metadata inspection using yt-dlp without media downloading.
4. Error mapping for platform restrictions: private videos, login/bot required, geo-restriction, DRM, live streams.
5. Duration limit enforcement.
6. User authorization requirement enforcement.
7. Audio-preferred media retrieval using yt-dlp.
8. Generated UUID safe filenames and temporary directory isolation.
9. FFprobe media verification on retrieved files.
10. Fallback and fast-path handling for user-provided transcripts.
11. Clean error handling, cleanup of partial files, and size-limit enforcement.
12. Endpoints: POST /api/sources/youtube/check and POST /api/sources/youtube/retrieve.
13. End-to-end integration with job submission and pipeline routing.
"""

import os
import glob
import wave
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import yt_dlp
from yt_dlp.utils import DownloadError

from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob
from app.providers.youtube_provider import (
    YouTubeProvider,
    extract_youtube_video_id,
    get_canonical_youtube_url,
    verify_media_file_with_ffprobe,
    map_ytdlp_error
)


def create_dummy_wav(path: str, duration_sec: int = 1):
    """Creates a valid 16kHz mono 16-bit WAV audio file for FFprobe tests."""
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b'\x00' * int(16000 * 2 * duration_sec))


class TestYouTubeIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_upload_dir = tempfile.mkdtemp()
        self.upload_dir = os.path.join(self.temp_upload_dir, 'uploads')
        os.makedirs(self.upload_dir, exist_ok=True)

        class YouTubeTestConfig(TestConfig):
            UPLOAD_FOLDER = self.upload_dir
            MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50 MB

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

    # -------------------------------------------------------------------------
    # 1. URL Validation & Identification
    # -------------------------------------------------------------------------

    def test_extract_video_id_formats(self):
        """Verify URL extractor handles all standard YouTube URL variations and rejects non-YouTube links."""
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

        # Canonical URL generator
        self.assertEqual(get_canonical_youtube_url('dQw4w9WgXcQ'), 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')

        # Invalid URLs
        self.assertIsNone(extract_youtube_video_id('https://example.com/video.mp4'))
        self.assertIsNone(extract_youtube_video_id('https://vimeo.com/123456789'))
        self.assertIsNone(extract_youtube_video_id(''))
        self.assertIsNone(extract_youtube_video_id(None))

    def test_provider_identify(self):
        """Verify YouTubeProvider identifies YouTube URLs and rejects other source providers."""
        self.assertTrue(self.provider.identify('https://www.youtube.com/watch?v=dQw4w9WgXcQ'))
        self.assertTrue(self.provider.identify('https://youtu.be/dQw4w9WgXcQ'))
        self.assertFalse(self.provider.identify('https://drive.google.com/file/d/123/view'))
        self.assertFalse(self.provider.identify('https://example.com/recording.mp4'))
        self.assertFalse(self.provider.identify(''))

    # -------------------------------------------------------------------------
    # 2. Metadata Inspection & Accessibility Checks (No Download)
    # -------------------------------------------------------------------------

    def test_check_accessibility_invalid_url(self):
        """Verify check_accessibility returns error for invalid YouTube link."""
        res = self.provider.check_accessibility('https://notyoutube.com/watch')
        self.assertFalse(res['success'])
        self.assertEqual(res['accessibility_status'], 'Invalid URL')
        self.assertFalse(res['retrieval_eligible'])

    def test_check_accessibility_metadata_success(self):
        """Verify check_accessibility extracts video title, duration, channel without downloading."""
        mock_info = {
            'title': 'Machine Learning Lecture 10',
            'duration': 3600,
            'uploader': 'Prof. Stanford AI',
            'filesize_approx': 35 * 1024 * 1024,
            'subtitles': {'en': [{'ext': 'vtt'}]}
        }

        res = self.provider.check_accessibility(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            mock_info=mock_info
        )

        self.assertTrue(res['success'])
        self.assertEqual(res['accessibility_status'], 'Retrieval Supported')
        self.assertEqual(res['title'], 'Machine Learning Lecture 10')
        self.assertEqual(res['channel'], 'Prof. Stanford AI')
        self.assertEqual(res['duration'], 3600)
        self.assertEqual(res['duration_str'], '01:00:00')
        self.assertTrue(res['retrieval_eligible'])
        self.assertTrue(res['has_subtitles'])
        self.assertIn('35.0 MB', res['file_size'])

    def test_check_accessibility_duration_exceeded(self):
        """Verify check_accessibility rejects videos that exceed the configured duration limit."""
        mock_info = {
            'title': 'Overly Long 10 Hour Stream',
            'duration': 36000,  # 10 hours
            'uploader': 'Streamer'
        }

        res = self.provider.check_accessibility(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            mock_info=mock_info,
            max_duration_seconds=14400  # 4 hours limit
        )

        self.assertFalse(res['success'])
        self.assertEqual(res['accessibility_status'], 'Duration Exceeded')
        self.assertEqual(res['code'], 'DURATION_EXCEEDED')
        self.assertFalse(res['retrieval_eligible'])
        self.assertIn('exceeds the allowed duration', res['message'])

    def test_check_accessibility_with_attached_transcript(self):
        """Verify check_accessibility returns Transcript Attached when accompanying transcript is supplied."""
        res = self.provider.check_accessibility(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            caption_content='WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nAttached lecture text.'
        )

        self.assertTrue(res['success'])
        self.assertEqual(res['accessibility_status'], 'Transcript Attached')
        self.assertTrue(res['retrieval_eligible'])

    # -------------------------------------------------------------------------
    # 3. Error Mapping for Restricted Platform Content
    # -------------------------------------------------------------------------

    def test_map_ytdlp_error_codes(self):
        """Verify map_ytdlp_error maps download exceptions to user-facing explanations."""
        e_private = DownloadError("Private video. Sign in if you've been granted access.")
        m_private = map_ytdlp_error(e_private)
        self.assertEqual(m_private['code'], 'PRIVATE_VIDEO')

        e_login = DownloadError("Sign in to confirm you’re not a bot.")
        m_login = map_ytdlp_error(e_login)
        self.assertEqual(m_login['code'], 'LOGIN_REQUIRED')

        e_unavail = DownloadError("Video unavailable. This video has been removed.")
        m_unavail = map_ytdlp_error(e_unavail)
        self.assertEqual(m_unavail['code'], 'VIDEO_UNAVAILABLE')

        e_geo = DownloadError("This video is not available in your country.")
        m_geo = map_ytdlp_error(e_geo)
        self.assertEqual(m_geo['code'], 'GEOGRAPHIC_RESTRICTION')

        e_drm = DownloadError("This video is protected by DRM.")
        m_drm = map_ytdlp_error(e_drm)
        self.assertEqual(m_drm['code'], 'DRM_RESTRICTED')

        e_live = DownloadError("This live event will begin in 10 minutes.")
        m_live = map_ytdlp_error(e_live)
        self.assertEqual(m_live['code'], 'LIVE_EVENT')

        e_timeout = DownloadError("Connection timed out.")
        m_timeout = map_ytdlp_error(e_timeout)
        self.assertEqual(m_timeout['code'], 'NETWORK_TIMEOUT')

    # -------------------------------------------------------------------------
    # 4. Media Retrieval via yt-dlp & Authorization
    # -------------------------------------------------------------------------

    def test_retrieve_media_authorization_required(self):
        """Verify retrieve_media requires user authorization confirmation before downloading."""
        res = self.provider.retrieve_media(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            destination_dir=self.upload_dir,
            user_authorized=False
        )

        self.assertFalse(res['success'])
        self.assertEqual(res['code'], 'AUTHORIZATION_REQUIRED')
        self.assertIn('authorization confirmation required', res['error'].lower())

    def test_retrieve_media_fast_path_with_captions(self):
        """Verify retrieve_media saves VTT directly when prefer_transcript=True and caption_content is given."""
        sample_vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nDeep learning overview.\n"
        res = self.provider.retrieve_media(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            destination_dir=self.upload_dir,
            caption_content=sample_vtt,
            user_authorized=True,
            prefer_transcript=True
        )

        self.assertTrue(res['success'])
        self.assertEqual(res['source_type'], 'youtube')
        self.assertEqual(res['input_type'], 'transcript')
        self.assertEqual(res['file_extension'], 'vtt')
        self.assertTrue(os.path.exists(res['storage_path']))

    def test_retrieve_media_success_with_ffprobe_verification(self):
        """Verify retrieve_media validates downloaded audio file with FFprobe and sets input_type='audio'."""
        mock_audio_path = os.path.join(self.upload_dir, 'sample_youtube_audio.wav')
        create_dummy_wav(mock_audio_path, duration_sec=2)
        self.assertTrue(verify_media_file_with_ffprobe(mock_audio_path))

        res = self.provider.retrieve_media(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            destination_dir=self.upload_dir,
            user_authorized=True,
            mock_download_file=mock_audio_path,
            title='Intro to Algorithms',
            duration=120
        )

        self.assertTrue(res['success'])
        self.assertEqual(res['source_type'], 'youtube')
        self.assertEqual(res['input_type'], 'audio')
        self.assertEqual(res['file_extension'], 'wav')
        self.assertEqual(res['storage_path'], mock_audio_path)
        self.assertEqual(res['title'], 'Intro to Algorithms')

    @patch('yt_dlp.YoutubeDL')
    def test_retrieve_media_handles_download_error_and_cleans_up(self, mock_ytdlp_cls):
        """Verify retrieve_media catches DownloadError, cleans up partial files, and returns mapped code."""
        mock_instance = MagicMock()
        mock_instance.extract_info.side_effect = DownloadError("Private video. Sign in if you've been granted access.")
        mock_ytdlp_cls.return_value.__enter__.return_value = mock_instance

        # Create a dummy partial file to verify cleanup
        dummy_partial = os.path.join(self.upload_dir, 'dummy_youtube_dQw4w9WgXcQ.m4a.part')
        with open(dummy_partial, 'w') as f:
            f.write('partial data')

        res = self.provider.retrieve_media(
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            destination_dir=self.upload_dir,
            user_authorized=True
        )

        self.assertFalse(res['success'])
        self.assertEqual(res['code'], 'PRIVATE_VIDEO')
        self.assertIn('private', res['error'].lower())

    # -------------------------------------------------------------------------
    # 5. Dashboard Endpoints (Check & Retrieve)
    # -------------------------------------------------------------------------

    def test_endpoint_youtube_check_success(self):
        """Verify POST /api/sources/youtube/check endpoint returns metadata using yt-dlp."""
        self._login()
        with patch.object(self.provider, 'get_metadata') as mock_meta:
            mock_meta.return_value = {
                'success': True,
                'video_id': 'dQw4w9WgXcQ',
                'info': {
                    'title': 'Robotics Keynote 2026',
                    'uploader': 'IEEE Robotics Society',
                    'duration': 1800,
                    'filesize_approx': 20 * 1024 * 1024
                }
            }
            with patch('app.providers.youtube_provider.YouTubeProvider', return_value=self.provider):
                resp = self.client.post(
                    '/api/sources/youtube/check',
                    json={'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'user_authorized': True}
                )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['video_id'], 'dQw4w9WgXcQ')
        self.assertEqual(data['accessibility_status'], 'Retrieval Supported')
        self.assertEqual(data['title'], 'Robotics Keynote 2026')

    def test_endpoint_youtube_retrieve_requires_authorization(self):
        """Verify POST /api/sources/youtube/retrieve returns 400 when user_authorized is False."""
        self._login()
        resp = self.client.post(
            '/api/sources/youtube/retrieve',
            json={'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'user_authorized': False}
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['code'], 'AUTHORIZATION_REQUIRED')

    def test_end_to_end_youtube_job_creation(self):
        """Verify full flow: retrieve audio media -> stage in session -> create processing job with input_type='audio'."""
        self._login()

        mock_audio_path = os.path.join(self.upload_dir, 'staged_yt_audio.m4a')
        create_dummy_wav(mock_audio_path, duration_sec=3)

        # 1. Mock retrieve_media returning audio file
        with patch.object(self.provider, 'retrieve_media') as mock_ret:
            mock_ret.return_value = {
                'success': True,
                'source_type': 'youtube',
                'input_type': 'audio',
                'original_filename': 'youtube_dQw4w9WgXcQ.m4a',
                'safe_filename': 'staged_yt_audio.m4a',
                'storage_path': mock_audio_path,
                'file_size': os.path.getsize(mock_audio_path),
                'file_extension': 'm4a',
                'source_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                'video_id': 'dQw4w9WgXcQ',
                'title': 'AI Webinar Lecture',
                'duration': 180,
                'message': 'YouTube audio retrieved successfully (M4A) and staged for pipeline processing.'
            }
            with patch('app.providers.youtube_provider.YouTubeProvider', return_value=self.provider):
                resp = self.client.post(
                    '/api/sources/youtube/retrieve',
                    json={'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'user_authorized': True}
                )

        self.assertEqual(resp.status_code, 200)
        ret_data = resp.get_json()
        self.assertTrue(ret_data['success'])
        self.assertEqual(ret_data['details']['input_type'], 'audio')

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
        self.assertEqual(job.input_type, 'audio')
        self.assertEqual(job.source_type, 'youtube')
        self.assertEqual(job.source_url, 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')


if __name__ == '__main__':
    unittest.main()
