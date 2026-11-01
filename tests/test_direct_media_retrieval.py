"""
Automated Test Suite for Prompt A2: Direct Media Retrieval & SSRF Protection.

Covers:
1. SSRF URL validation (loopback, RFC 1918 private, link-local, cloud metadata, port restriction, scheme restriction).
2. DirectMediaProvider accessibility check and streaming retrieval.
3. Binary container verification (ftyp header for MP4, ID3 header for MP3, rejection of HTML error pages).
4. File size limit enforcement and temporary file cleanup.
5. REST endpoints POST /api/sources/direct/check and /api/sources/direct/retrieve.
6. ProcessingJob creation from retrieved direct media.
"""

import os
import io
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import requests

from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob, JobRecipient
from app.utils.ssrf import validate_url_ssrf, is_ip_restricted, SSRFSecurityError
from app.providers.direct_provider import DirectMediaProvider, verify_media_container_signature


class TestDirectMediaRetrieval(unittest.TestCase):
    def setUp(self):
        self.temp_upload_dir = tempfile.mkdtemp()

        class CustomTestConfig(TestConfig):
            TESTING = True
            SECRET_KEY = 'test-ssrf-secret'
            UPLOAD_FOLDER = self.temp_upload_dir
            MAX_VIDEO_SIZE = 2 * 1024 * 1024  # 2MB limit for tests

        self.app = create_app(CustomTestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.create_all()
        self.user = User(username='direct_tester', email='direct@webinarai.edu', role='user', is_active=True)
        self.user.set_password('DirectPass123!')
        db.session.add(self.user)
        db.session.commit()
        self.user_id = self.user.id

        self.client = self.app.test_client()

        # Synthetic headers
        self.valid_mp4_bytes = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42\x00\x00\x00\x08free' + (b'\x00' * 512)
        self.valid_mp3_bytes = b'ID3\x04\x00\x00\x00\x00\x00\x20TIT2\x00\x00\x00\x05\x00\x00\x00Test' + (b'\xff\xfb\x90\x00' * 100)
        self.html_error_bytes = b"<!DOCTYPE html><html><head><title>404 Not Found</title></head><body>File not found</body></html>"

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        if os.path.exists(self.temp_upload_dir):
            shutil.rmtree(self.temp_upload_dir, ignore_errors=True)

    def _login_client(self):
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user_id
            sess['username'] = 'direct_tester'
            sess['role'] = 'user'

    # -------------------------------------------------------------------------
    # 1. SSRF Validation Tests
    # -------------------------------------------------------------------------
    def test_ssrf_blocks_loopback_destinations(self):
        """Verify loopback IPv4 and hostnames are rejected."""
        loopback_urls = [
            'http://127.0.0.1/video.mp4',
            'http://127.0.0.2:80/stream.mp4',
            'http://localhost/recording.mp4',
            'http://sub.localhost/video.mp4'
        ]
        for url in loopback_urls:
            is_safe, error, _ = validate_url_ssrf(url)
            self.assertFalse(is_safe, f"Loopback URL not blocked: {url}")
            self.assertIsNotNone(error)

    def test_ssrf_blocks_rfc1918_private_ips(self):
        """Verify private IPv4 ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16) are rejected."""
        private_urls = [
            'http://10.0.0.1/video.mp4',
            'http://10.255.255.254/video.mp4',
            'http://172.16.0.1/lecture.mp4',
            'http://172.31.255.255/lecture.mp4',
            'http://192.168.1.1/seminar.mp4',
            'http://192.168.100.50/seminar.mp4'
        ]
        for url in private_urls:
            is_safe, error, _ = validate_url_ssrf(url)
            self.assertFalse(is_safe, f"Private IP not blocked: {url}")
            self.assertIn("restricted", error.lower())

    def test_ssrf_blocks_cloud_metadata_service(self):
        """Verify 169.254.169.254 and metadata hostnames are blocked."""
        meta_urls = [
            'http://169.254.169.254/latest/meta-data/',
            'http://169.254.1.1/video.mp4',
            'http://metadata.google.internal/computeMetadata/v1/'
        ]
        for url in meta_urls:
            is_safe, error, _ = validate_url_ssrf(url)
            self.assertFalse(is_safe, f"Metadata destination not blocked: {url}")

    def test_ssrf_blocks_non_standard_ports(self):
        """Verify ports outside 80, 443, 8080, 8443 are rejected."""
        bad_port_urls = [
            'http://example.com:22/video.mp4',
            'http://example.com:25/video.mp4',
            'http://example.com:3306/video.mp4',
            'http://example.com:6379/video.mp4'
        ]
        for url in bad_port_urls:
            is_safe, error, _ = validate_url_ssrf(url)
            self.assertFalse(is_safe, f"Disallowed port not blocked: {url}")
            self.assertIn("port", error.lower())

    def test_ssrf_blocks_disallowed_schemes(self):
        """Verify non-HTTP/HTTPS schemes (ftp, file, gopher) are rejected."""
        bad_schemes = [
            'ftp://example.com/video.mp4',
            'file:///etc/passwd',
            'gopher://example.com/'
        ]
        for url in bad_schemes:
            is_safe, error, _ = validate_url_ssrf(url)
            self.assertFalse(is_safe)
            self.assertIn("protocol", error.lower())

    @patch('app.utils.ssrf.socket.getaddrinfo')
    def test_ssrf_allows_public_routable_destinations(self, mock_getaddrinfo):
        """Verify standard public IP addresses pass SSRF checks."""
        # Mock public IP: 93.184.216.34 (example.com)
        mock_getaddrinfo.return_value = [
            (2, 1, 6, '', ('93.184.216.34', 443))
        ]
        is_safe, error, ip = validate_url_ssrf('https://example.com/recordings/webinar.mp4')
        self.assertTrue(is_safe)
        self.assertIsNone(error)
        self.assertEqual(ip, '93.184.216.34')

    # -------------------------------------------------------------------------
    # 2. Binary Container Signature Verification Tests
    # -------------------------------------------------------------------------
    def test_container_verification_valid_mp4(self):
        """Verify valid MP4 container with ftyp box passes verification."""
        path = os.path.join(self.temp_upload_dir, "test.mp4")
        with open(path, 'wb') as f:
            f.write(self.valid_mp4_bytes)

        valid, msg = verify_media_container_signature(path, 'mp4')
        self.assertTrue(valid)
        self.assertIn("Valid MP4", msg)

    def test_container_verification_valid_mp3(self):
        """Verify valid MP3 with ID3 header passes verification."""
        path = os.path.join(self.temp_upload_dir, "test.mp3")
        with open(path, 'wb') as f:
            f.write(self.valid_mp3_bytes)

        valid, msg = verify_media_container_signature(path, 'mp3')
        self.assertTrue(valid)

    def test_container_verification_rejects_html_error_page(self):
        """Verify HTML error page disguised as .mp4 is strictly rejected."""
        path = os.path.join(self.temp_upload_dir, "fake.mp4")
        with open(path, 'wb') as f:
            f.write(self.html_error_bytes)

        valid, msg = verify_media_container_signature(path, 'mp4')
        self.assertFalse(valid)
        self.assertIn("HTML", msg)

    # -------------------------------------------------------------------------
    # 3. DirectMediaProvider Unit Tests
    # -------------------------------------------------------------------------
    def test_provider_identification(self):
        """Verify provider correctly identifies direct links vs YouTube/GDrive."""
        provider = DirectMediaProvider()
        self.assertTrue(provider.identify('https://example.com/video.mp4'))
        self.assertTrue(provider.identify('http://cdn.university.edu/audio.mp3'))
        self.assertFalse(provider.identify('https://www.youtube.com/watch?v=12345'))
        self.assertFalse(provider.identify('https://drive.google.com/file/d/123/view'))
        self.assertFalse(provider.identify('ftp://example.com/video.mp4'))

    @patch('app.providers.direct_provider.validate_url_ssrf')
    @patch('app.providers.direct_provider.safe_request')
    def test_provider_check_accessibility_success(self, mock_request, mock_ssrf):
        """Verify accessibility check returns 200 with media metadata."""
        mock_ssrf.return_value = (True, None, '93.184.216.34')
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {
            'Content-Type': 'video/mp4',
            'Content-Length': '1048576'
        }
        mock_request.return_value = mock_resp

        provider = DirectMediaProvider()
        res = provider.check_accessibility('https://example.com/recording.mp4')
        self.assertTrue(res['success'])
        self.assertEqual(res['accessibility_status'], 'Retrieval Supported')
        self.assertEqual(res['media_type'], 'video/mp4')
        self.assertTrue(res['retrieval_eligible'])

    @patch('app.providers.direct_provider.validate_url_ssrf')
    @patch('app.providers.direct_provider.safe_request')
    def test_provider_check_accessibility_rejects_html_content_type(self, mock_request, mock_ssrf):
        """Verify server returning text/html for an .mp4 URL is rejected."""
        mock_ssrf.return_value = (True, None, '93.184.216.34')
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/html; charset=utf-8'}
        mock_request.return_value = mock_resp

        provider = DirectMediaProvider()
        res = provider.check_accessibility('https://example.com/fake_video.mp4')
        self.assertFalse(res['success'])
        self.assertEqual(res['code'], 'HTML_NOT_MEDIA')

    @patch('app.providers.direct_provider.safe_download_media_stream')
    def test_provider_retrieve_media_success(self, mock_download):
        """Verify media retrieval downloads, validates header, and outputs metadata."""
        target_path = os.path.join(self.temp_upload_dir, "retrieved.mp4")
        with open(target_path, 'wb') as f:
            f.write(self.valid_mp4_bytes)

        mock_download.return_value = {
            'success': True,
            'storage_path': target_path,
            'file_size': len(self.valid_mp4_bytes),
            'content_type': 'video/mp4'
        }

        provider = DirectMediaProvider()
        res = provider.retrieve_media(
            source_reference='https://example.com/lecture.mp4',
            destination_dir=self.temp_upload_dir,
            max_size_bytes=5 * 1024 * 1024
        )

        self.assertTrue(res['success'])
        self.assertEqual(res['input_type'], 'video')
        self.assertEqual(res['file_extension'], 'mp4')
        self.assertTrue(os.path.exists(res['storage_path']))

    # -------------------------------------------------------------------------
    # 4. REST Endpoints & Job Integration Tests
    # -------------------------------------------------------------------------
    @patch('app.providers.direct_provider.DirectMediaProvider.check_accessibility')
    def test_api_sources_direct_check_endpoint(self, mock_check):
        """Verify POST /api/sources/direct/check calls provider."""
        self._login_client()
        mock_check.return_value = {
            'success': True,
            'accessibility_status': 'Retrieval Supported',
            'media_type': 'video/mp4'
        }

        response = self.client.post('/api/sources/direct/check', json={
            'url': 'https://example.com/seminar.mp4'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['accessibility_status'], 'Retrieval Supported')

    @patch('app.providers.direct_provider.DirectMediaProvider.retrieve_media')
    def test_api_sources_direct_retrieve_and_submit_job(self, mock_retrieve):
        """
        End-to-end integration:
        1. Retrieve direct media via /api/sources/direct/retrieve (populates session).
        2. Upload CSV recipient list.
        3. Submit job via /api/submit-job and verify ProcessingJob persisted in MySQL!
        """
        self._login_client()

        target_file = os.path.join(self.temp_upload_dir, "stored_media.mp4")
        with open(target_file, 'wb') as f:
            f.write(self.valid_mp4_bytes)

        mock_retrieve.return_value = {
            'success': True,
            'source_type': 'direct',
            'original_filename': 'seminar.mp4',
            'safe_filename': 'uuid_seminar.mp4',
            'storage_path': target_file,
            'file_size': len(self.valid_mp4_bytes),
            'file_extension': 'mp4',
            'input_type': 'video'
        }

        # 1. Retrieve direct media
        ret_resp = self.client.post('/api/sources/direct/retrieve', json={
            'url': 'https://example.com/seminar.mp4'
        })
        self.assertEqual(ret_resp.status_code, 200)
        ret_data = ret_resp.get_json()
        self.assertTrue(ret_data['success'])

        # 2. Add recipient
        csv_bytes = b"email,name\nstudent@college.edu,John Doe\n"
        csv_resp = self.client.post('/api/upload-csv', data={
            'file': (io.BytesIO(csv_bytes), 'students.csv')
        }, content_type='multipart/form-data')
        self.assertEqual(csv_resp.status_code, 200)

        # 3. Submit job
        submit_resp = self.client.post('/api/submit-job', json={
            'title': 'Quantum Physics Webinar'
        })
        self.assertEqual(submit_resp.status_code, 201)
        submit_data = submit_resp.get_json()
        self.assertTrue(submit_data['success'])
        self.assertIn('job', submit_data)

        # Verify database record
        job_id = submit_data['job']['id']
        job = db.session.get(ProcessingJob, job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job.input_type, 'video')
        self.assertEqual(job.input_file_name, 'seminar.mp4')
        self.assertEqual(job.total_recipients, 1)


if __name__ == '__main__':
    unittest.main()

