"""
Direct Media Provider for WebinarAI (Prompt A2).

Retrieves webinar video (MP4) and audio (MP3, WAV, M4A) directly over HTTP/HTTPS.
Enforces SSRF defense, redirect safety, size limits, and binary container header verification.
"""

import os
import uuid
import logging
import urllib.parse
from typing import Dict, Any, Optional, Tuple
from werkzeug.utils import secure_filename
from app.providers.base import BaseRetrievalProvider
from app.utils.ssrf import validate_url_ssrf, safe_request, safe_download_media_stream, SSRFSecurityError

logger = logging.getLogger(__name__)

SUPPORTED_MEDIA_EXTENSIONS = ('.mp4', '.mp3', '.wav', '.m4a')
SUPPORTED_MIME_TYPES = {
    'video/mp4': 'mp4',
    'video/quicktime': 'mp4',
    'audio/mpeg': 'mp3',
    'audio/mp3': 'mp3',
    'audio/wav': 'wav',
    'audio/x-wav': 'wav',
    'audio/mp4': 'm4a',
    'audio/x-m4a': 'm4a',
    'application/octet-stream': None  # Many servers serve media with generic binary octet-stream
}


def verify_media_container_signature(file_path: str, expected_extension: str) -> Tuple[bool, str]:
    """
    Inspects leading bytes of downloaded file to ensure it is genuine media
    and not an HTML error page, PHP script, or text document disguised with a media extension.
    """
    if not os.path.exists(file_path):
        return False, "Downloaded file is missing from disk."

    size = os.path.getsize(file_path)
    if size < 12:
        return False, "File is too small to contain a valid media header."

    with open(file_path, 'rb') as f:
        header = f.read(64)

    # HTML / Text check
    lower_header = header.lower()
    if b'<!doctype html' in lower_header or b'<html' in lower_header or b'<head' in lower_header or b'<?xml' in lower_header:
        return False, "The URL returned an HTML error webpage rather than a valid media stream."

    ext = expected_extension.lower().lstrip('.')

    # MP4 / M4A check: ISO base media file format contains 'ftyp' box
    if ext in ('mp4', 'm4a'):
        if b'ftyp' in header[:16]:
            return True, "Valid MP4/M4A ISO container"
        return False, "File does not contain a valid MP4/M4A 'ftyp' container signature."

    # WAV check: RIFF header with WAVE format
    elif ext == 'wav':
        if len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WAVE':
            return True, "Valid WAV RIFF container"
        return False, "File does not contain a valid RIFF/WAVE header."

    # MP3 check: ID3 tag or MPEG sync word (0xFF 0xFB/0xFA/0xF3)
    elif ext == 'mp3':
        if header[:3] == b'ID3':
            return True, "Valid MP3 with ID3 tag"
        if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
            return True, "Valid MP3 MPEG audio frame sync"
        return False, "File does not contain a valid MP3 ID3 header or MPEG sync word."

    # Fallback check: if 'ftyp' or 'RIFF' or 'ID3' exists
    if b'ftyp' in header[:16] or (header[:4] == b'RIFF' and header[8:12] == b'WAVE') or header[:3] == b'ID3':
        return True, "Valid media container"

    return False, f"Unsupported or unrecognizable binary format for extension '.{ext}'."


class DirectMediaProvider(BaseRetrievalProvider):
    """Retrieves direct audio and video URLs safely."""

    @property
    def provider_name(self) -> str:
        return 'direct'

    def identify(self, source_reference: str) -> bool:
        """Returns True if reference is an HTTP/HTTPS URL not originating from YouTube or Google Drive."""
        if not source_reference or not isinstance(source_reference, str):
            return False
        ref = source_reference.strip().lower()
        if not (ref.startswith('http://') or ref.startswith('https://')):
            return False
        if 'youtube.com' in ref or 'youtu.be' in ref or 'drive.google.com' in ref:
            return False
        return True

    def check_accessibility(self, source_reference: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Pre-flight non-destructive check. Inspects SSRF safety, connects via HEAD/GET,
        and verifies Content-Type and Content-Length.
        """
        is_safe, ssrf_error, _ = validate_url_ssrf(source_reference)
        if not is_safe:
            return {
                'success': False,
                'source_type': 'direct',
                'accessibility_status': 'Retrieval Restricted',
                'retrieval_eligible': False,
                'error': ssrf_error or "Destination address is restricted.",
                'code': 'SSRF_RESTRICTED'
            }

        parsed = urllib.parse.urlparse(source_reference)
        path = parsed.path.lower()
        candidate_ext = ''
        for ext in SUPPORTED_MEDIA_EXTENSIONS:
            if path.endswith(ext):
                candidate_ext = ext
                break

        # Attempt safe HEAD request first; fallback to GET stream if server rejects HEAD
        try:
            response = safe_request(source_reference, method='HEAD', timeout=(10, 15))
            if response.status_code in (405, 501):  # Method not allowed
                response = safe_request(source_reference, method='GET', stream=True, timeout=(10, 15))
        except SSRFSecurityError as se:
            return {
                'success': False,
                'source_type': 'direct',
                'accessibility_status': 'Retrieval Restricted',
                'retrieval_eligible': False,
                'error': str(se),
                'code': 'SSRF_BLOCKED'
            }
        except Exception as e:
            return {
                'success': False,
                'source_type': 'direct',
                'accessibility_status': 'Source Unavailable',
                'retrieval_eligible': False,
                'error': f"Failed to connect to media host: {str(e)}",
                'code': 'UNREACHABLE'
            }

        if response.status_code == 401 or response.status_code == 403:
            return {
                'success': False,
                'source_type': 'direct',
                'accessibility_status': 'Authentication Required',
                'retrieval_eligible': False,
                'error': f"Media server requires credentials (HTTP {response.status_code}).",
                'code': 'AUTH_REQUIRED'
            }

        if response.status_code == 404:
            return {
                'success': False,
                'source_type': 'direct',
                'accessibility_status': 'Source Unavailable',
                'retrieval_eligible': False,
                'error': "Media file was not found on remote server (HTTP 404).",
                'code': 'NOT_FOUND'
            }

        if response.status_code != 200:
            return {
                'success': False,
                'source_type': 'direct',
                'accessibility_status': 'Source Unavailable',
                'retrieval_eligible': False,
                'error': f"Remote server returned unexpected HTTP status {response.status_code}.",
                'code': f'HTTP_{response.status_code}'
            }

        content_type = response.headers.get('Content-Type', '').split(';')[0].strip().lower()

        # Reject HTML webpages disguised with media extensions
        if 'text/html' in content_type:
            return {
                'success': False,
                'source_type': 'direct',
                'accessibility_status': 'Media Type Unsupported',
                'retrieval_eligible': False,
                'error': "The URL points to an HTML webpage rather than a direct downloadable media file.",
                'code': 'HTML_NOT_MEDIA'
            }

        content_length = response.headers.get('Content-Length')
        file_size_formatted = "Unknown size"
        if content_length and content_length.isdigit():
            size_bytes = int(content_length)
            file_size_formatted = f"{size_bytes // (1024 * 1024)} MB"

        return {
            'success': True,
            'source_type': 'direct',
            'source_reference': source_reference,
            'accessibility_status': 'Retrieval Supported',
            'media_type': content_type or (f"video/{candidate_ext.lstrip('.')}" if candidate_ext else "media/stream"),
            'file_size': file_size_formatted,
            'retrieval_eligible': True,
            'requires_auth': False,
            'explanation': "Direct media URL verified. File is reachable and ready for streaming retrieval."
        }

    def retrieve_media(
        self,
        source_reference: str,
        destination_dir: str,
        max_size_bytes: int,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Streams media safely to disk, verifies container signature,
        and returns validated file metadata.
        """
        # Determine candidate filename and extension
        parsed = urllib.parse.urlparse(source_reference)
        raw_name = os.path.basename(parsed.path) or 'recording.mp4'
        clean_name = secure_filename(raw_name) or 'recording.mp4'
        ext = clean_name.rsplit('.', 1)[-1].lower() if '.' in clean_name else 'mp4'
        if ext not in ('mp4', 'mp3', 'wav', 'm4a'):
            ext = 'mp4'

        safe_filename = f"{uuid.uuid4().hex[:12]}_{clean_name}"
        destination_path = os.path.join(destination_dir, safe_filename)

        # Execute safe streaming download
        download_res = safe_download_media_stream(
            url=source_reference,
            destination_path=destination_path,
            max_size_bytes=max_size_bytes
        )

        if not download_res.get('success'):
            return download_res

        actual_path = download_res.get('storage_path') or destination_path

        # Verify binary container signature
        valid_sig, sig_msg = verify_media_container_signature(actual_path, ext)
        if not valid_sig:
            if os.path.exists(actual_path):
                try:
                    os.remove(actual_path)
                except Exception:
                    pass
            return {
                'success': False,
                'error': f"Downloaded content failed media verification: {sig_msg}",
                'code': 'INVALID_MEDIA_HEADER'
            }

        input_type = 'audio' if ext in ('mp3', 'wav', 'm4a') else 'video'

        return {
            'success': True,
            'source_type': 'direct',
            'original_filename': clean_name,
            'safe_filename': os.path.basename(actual_path),
            'storage_path': actual_path,
            'file_size': download_res['file_size'],
            'file_extension': ext,
            'input_type': input_type,
            'content_type': download_res.get('content_type')
        }
