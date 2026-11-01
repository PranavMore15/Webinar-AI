"""
Google Drive Retrieval Provider for WebinarAI (Prompt A4).

Ingests webinar recordings stored in Google Drive via official Google Drive API v3.
Enforces OAuth 2.0 authorization, read-only scope, access permission checks,
download permission verification, rate-limit/quota handling, size limits,
and binary container signature validation.
"""

import os
import io
import re
import uuid
import logging
from typing import Dict, Any, Optional, Tuple
from werkzeug.utils import secure_filename

from app.providers.base import BaseRetrievalProvider
from app.providers.direct_provider import verify_media_container_signature

logger = logging.getLogger(__name__)

GDRIVE_FILE_ID_PATTERN = re.compile(
    r'(?:drive\.google\.com/(?:file/d/|open\?id=)|docs\.google\.com/file/d/)([a-zA-Z0-9_-]+)',
    re.IGNORECASE
)

SUPPORTED_MEDIA_EXTENSIONS = ('.mp4', '.mp3', '.wav', '.m4a')
SUPPORTED_MEDIA_MIME_TYPES = {
    'video/mp4': 'mp4',
    'video/quicktime': 'mp4',
    'audio/mpeg': 'mp3',
    'audio/mp3': 'mp3',
    'audio/wav': 'wav',
    'audio/x-wav': 'wav',
    'audio/mp4': 'm4a',
    'audio/x-m4a': 'm4a',
    'application/octet-stream': None
}

GOOGLE_DOCS_MIME_TYPES = (
    'application/vnd.google-apps.document',
    'application/vnd.google-apps.spreadsheet',
    'application/vnd.google-apps.presentation',
    'application/vnd.google-apps.folder',
    'application/vnd.google-apps.form'
)


def extract_gdrive_file_id(url_or_id: str) -> Optional[str]:
    """Extracts the Google Drive file ID from a URL or raw ID string."""
    if not url_or_id or not isinstance(url_or_id, str):
        return None
    url = url_or_id.strip()
    match = GDRIVE_FILE_ID_PATTERN.search(url)
    if match:
        return match.group(1)
    # Check if raw alphanumeric string of standard ID length (around 25-45 chars)
    if re.match(r'^[a-zA-Z0-9_-]{25,50}$', url):
        return url
    return None


class GDriveMediaProvider(BaseRetrievalProvider):
    """
    Retrieval provider for Google Drive media files using the official Drive API v3.
    """

    @property
    def provider_name(self) -> str:
        return 'gdrive'

    def identify(self, source_reference: str) -> bool:
        """Determines if the given URL is a Google Drive file link."""
        if not source_reference or not isinstance(source_reference, str):
            return False
        ref = source_reference.strip().lower()
        if 'drive.google.com' in ref or 'docs.google.com' in ref:
            return extract_gdrive_file_id(source_reference) is not None
        return False

    def build_service(self, token_info: Optional[Dict[str, Any]] = None):
        """
        Builds and returns an authorized Google Drive v3 service client.
        """
        if not token_info:
            return None

        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        credentials = Credentials(
            token=token_info.get('token') or token_info.get('access_token'),
            refresh_token=token_info.get('refresh_token'),
            token_uri=token_info.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=token_info.get('client_id'),
            client_secret=token_info.get('client_secret'),
            scopes=token_info.get('scopes', ['https://www.googleapis.com/auth/drive.readonly'])
        )
        return build('drive', 'v3', credentials=credentials, cache_discovery=False)

    def check_accessibility(
        self,
        source_reference: str,
        options: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Inspects Google Drive file metadata without downloading media.
        Verifies link format, checks account connection, verifies file existence,
        permissions, mimeType, and size limits.
        """
        opts = dict(options or {})
        opts.update(kwargs)

        file_id = extract_gdrive_file_id(source_reference)
        if not file_id:
            return {
                'success': False,
                'status': 'error',
                'source_type': 'gdrive',
                'accessibility_status': 'Invalid URL',
                'retrieval_eligible': False,
                'message': 'Invalid Google Drive link. Please provide a standard file sharing URL.'
            }

        token_info = opts.get('token_info') or opts.get('session_token')
        service = opts.get('drive_service')

        # If user has not connected Google Account yet, report Authentication Required
        if not service and not token_info:
            return {
                'success': True,
                'source_type': 'gdrive',
                'source_reference': source_reference,
                'file_id': file_id,
                'accessibility_status': 'Authentication Required',
                'media_type': 'Google Drive Media File',
                'file_size': 'Pending account connection',
                'retrieval_eligible': True,
                'requires_auth': True,
                'explanation': 'Google Drive link recognized. Connect an authorized Google account to inspect and retrieve file.'
            }

        # User is authenticated: query file metadata via official API
        try:
            if not service:
                service = self.build_service(token_info)

            file_metadata = service.files().get(
                fileId=file_id,
                fields='id, name, mimeType, size, capabilities, trashed'
            ).execute()

        except Exception as e:
            err_str = str(e).lower()
            logger.warning("Google Drive API error for file %s: %s", file_id, str(e))
            if '404' in err_str or 'not found' in err_str:
                return {
                    'success': False,
                    'status': 'error',
                    'source_type': 'gdrive',
                    'accessibility_status': 'File Not Found',
                    'retrieval_eligible': False,
                    'message': 'The specified Google Drive file was not found. Verify the link and file permissions.'
                }
            elif '403' in err_str or 'permission' in err_str or 'access denied' in err_str:
                return {
                    'success': False,
                    'status': 'error',
                    'source_type': 'gdrive',
                    'accessibility_status': 'Access Denied',
                    'retrieval_eligible': False,
                    'message': 'Access to this Google Drive file was denied. Ensure your connected Google account has read access.'
                }
            elif '401' in err_str or 'invalid_grant' in err_str:
                return {
                    'success': False,
                    'status': 'error',
                    'source_type': 'gdrive',
                    'accessibility_status': 'Authentication Expired',
                    'retrieval_eligible': False,
                    'requires_auth': True,
                    'message': 'Google Drive session has expired. Please reconnect your Google account.'
                }
            elif '429' in err_str or 'rate' in err_str or 'quota' in err_str:
                return {
                    'success': False,
                    'status': 'error',
                    'source_type': 'gdrive',
                    'accessibility_status': 'Rate Limit Exceeded',
                    'retrieval_eligible': False,
                    'message': 'Google Drive API rate limit or quota exceeded. Please try again shortly.'
                }
            return {
                'success': False,
                'status': 'error',
                'source_type': 'gdrive',
                'accessibility_status': 'API Error',
                'retrieval_eligible': False,
                'message': f"Google Drive API error: {str(e)}"
            }

        if file_metadata.get('trashed'):
            return {
                'success': False,
                'status': 'error',
                'source_type': 'gdrive',
                'accessibility_status': 'File Trashed',
                'retrieval_eligible': False,
                'message': 'The requested file is currently in Google Drive trash.'
            }

        filename = file_metadata.get('name', 'drive_recording')
        mime_type = file_metadata.get('mimeType', '')

        # Check for proprietary Google Docs / Sheets / Slides / Folders
        if mime_type in GOOGLE_DOCS_MIME_TYPES:
            return {
                'success': False,
                'status': 'error',
                'source_type': 'gdrive',
                'accessibility_status': 'Media Type Unsupported',
                'retrieval_eligible': False,
                'message': f"Google Workspace documents ({mime_type}) are not webinar video/audio recordings."
            }

        # Check download capability
        capabilities = file_metadata.get('capabilities', {})
        if not capabilities.get('canDownload', True):
            return {
                'success': False,
                'status': 'error',
                'source_type': 'gdrive',
                'accessibility_status': 'Download Restricted',
                'retrieval_eligible': False,
                'message': 'File owner has disabled downloads for this recording. Automated retrieval is not permitted.'
            }

        # Validate media type by mime or filename extension
        ext = os.path.splitext(filename)[1].lower()
        is_supported = (
            ext in SUPPORTED_MEDIA_EXTENSIONS or
            mime_type in SUPPORTED_MEDIA_MIME_TYPES
        )

        if not is_supported and mime_type != 'application/octet-stream':
            return {
                'success': False,
                'status': 'error',
                'source_type': 'gdrive',
                'accessibility_status': 'Media Type Unsupported',
                'retrieval_eligible': False,
                'message': f"Unsupported media type '{mime_type}' ({ext}). Supported formats: .mp4, .mp3, .wav, .m4a."
            }

        # File size check
        size_bytes = int(file_metadata.get('size', 0))
        max_size = opts.get('max_size_bytes', 250 * 1024 * 1024)
        if size_bytes > max_size:
            max_mb = max_size // (1024 * 1024)
            size_mb = size_bytes // (1024 * 1024)
            return {
                'success': False,
                'status': 'error',
                'source_type': 'gdrive',
                'accessibility_status': 'File Too Large',
                'retrieval_eligible': False,
                'message': f"Google Drive file size ({size_mb} MB) exceeds maximum allowable limit of {max_mb} MB."
            }

        media_category = 'audio' if (ext in ('.mp3', '.wav', '.m4a') or 'audio' in mime_type) else 'video'
        file_size_formatted = f"{size_bytes / (1024 * 1024):.1f} MB" if size_bytes > 0 else 'Unknown'

        return {
            'success': True,
            'source_type': 'gdrive',
            'source_reference': source_reference,
            'file_id': file_id,
            'filename': filename,
            'accessibility_status': 'Ready for Retrieval',
            'media_type': mime_type or f"{media_category}/{ext.lstrip('.')}",
            'file_size': file_size_formatted,
            'file_size_bytes': size_bytes,
            'retrieval_eligible': True,
            'requires_auth': False,
            'explanation': f"Google Drive {media_category} recording verified and eligible for automated processing."
        }

    def retrieve_media(
        self,
        source_reference: str,
        destination_dir: str,
        max_size_bytes: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Downloads media file from Google Drive via official API v3 get_media.
        Streams in chunks to enforce max_size_bytes and validates container signature.
        """
        if max_size_bytes is None:
            max_size_bytes = 250 * 1024 * 1024

        opts = dict(options or {})
        opts.update(kwargs)

        file_id = extract_gdrive_file_id(source_reference)
        if not file_id:
            return {
                'success': False,
                'error': 'Invalid Google Drive link or file ID.',
                'code': 'INVALID_URL'
            }

        token_info = opts.get('token_info') or opts.get('session_token')
        service = opts.get('drive_service')

        if not service and not token_info:
            return {
                'success': False,
                'error': 'Google account authentication required for Drive retrieval.',
                'code': 'AUTH_REQUIRED'
            }

        try:
            if not service:
                service = self.build_service(token_info)

            # Pre-fetch metadata
            meta = service.files().get(
                fileId=file_id,
                fields='id, name, mimeType, size, capabilities'
            ).execute()

        except Exception as e:
            logger.error("Drive metadata error during retrieval for %s: %s", file_id, str(e))
            return {
                'success': False,
                'error': f"Failed to access Google Drive file: {str(e)}",
                'code': 'API_ERROR'
            }

        # Check download capability
        if not meta.get('capabilities', {}).get('canDownload', True):
            return {
                'success': False,
                'error': 'File owner has disabled downloads for this recording.',
                'code': 'DOWNLOAD_RESTRICTED'
            }

        raw_filename = meta.get('name', f"gdrive_{file_id}.mp4")
        clean_name = secure_filename(raw_filename) or f"gdrive_{file_id}.mp4"
        ext = os.path.splitext(clean_name)[1].lower()
        if not ext:
            mime = meta.get('mimeType', '')
            ext = f".{SUPPORTED_MEDIA_MIME_TYPES.get(mime, 'mp4')}"
            clean_name += ext

        if ext not in SUPPORTED_MEDIA_EXTENSIONS:
            return {
                'success': False,
                'error': f"Unsupported Google Drive media format '{ext}'.",
                'code': 'INVALID_EXTENSION'
            }

        os.makedirs(destination_dir, exist_ok=True)
        unique_prefix = uuid.uuid4().hex[:12]
        safe_filename = f"{unique_prefix}_{clean_name}"
        destination_path = os.path.join(destination_dir, safe_filename)

        # Stream download via official Drive API
        try:
            from googleapiclient.http import MediaIoBaseDownload

            request = service.files().get_media(fileId=file_id)
            bytes_written = 0

            with open(destination_path, 'wb') as dest_f:
                downloader = MediaIoBaseDownload(dest_f, request, chunksize=1024 * 1024)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        bytes_written = status.resumable_progress
                        if bytes_written > max_size_bytes:
                            dest_f.close()
                            if os.path.exists(destination_path):
                                os.remove(destination_path)
                            max_mb = max_size_bytes // (1024 * 1024)
                            return {
                                'success': False,
                                'error': f"File exceeded maximum download limit ({max_mb} MB).",
                                'code': 'FILE_TOO_LARGE'
                            }

            if not os.path.exists(destination_path) or os.path.getsize(destination_path) == 0:
                if os.path.exists(destination_path):
                    os.remove(destination_path)
                return {
                    'success': False,
                    'error': 'Downloaded Google Drive file was empty (0 bytes).',
                    'code': 'EMPTY_FILE'
                }

            actual_size = os.path.getsize(destination_path)

        except Exception as e:
            if os.path.exists(destination_path):
                os.remove(destination_path)
            logger.error("Failed downloading Google Drive file %s: %s", file_id, str(e))
            return {
                'success': False,
                'error': f"Failed to download file from Google Drive: {str(e)}",
                'code': 'DOWNLOAD_FAILED'
            }

        # Verify container signature
        valid_container, container_msg = verify_media_container_signature(destination_path, ext)
        if not valid_container:
            if os.path.exists(destination_path):
                os.remove(destination_path)
            return {
                'success': False,
                'error': f"Downloaded file failed container verification: {container_msg}",
                'code': 'INVALID_CONTAINER'
            }

        input_type = 'video' if ext == '.mp4' else 'audio'
        return {
            'success': True,
            'source_type': 'gdrive',
            'input_type': input_type,
            'original_filename': raw_filename,
            'safe_filename': safe_filename,
            'storage_path': destination_path,
            'file_size': actual_size,
            'file_extension': ext.lstrip('.'),
            'source_url': source_reference,
            'message': f"Google Drive {input_type} ({ext}) retrieved and verified successfully."
        }

