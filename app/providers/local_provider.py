"""
Local Computer File and Folder Media Provider for WebinarAI (Prompt A3).

Handles browser-authorized local computer video and audio selection.
Supports MP4 video, and MP3, WAV, and M4A audio.
Enforces size limits, extension validation, binary container verification,
and collision-resistant storage staging.
"""

import os
import uuid
import logging
from typing import Dict, Any, Optional
from werkzeug.utils import secure_filename
from app.providers.base import BaseRetrievalProvider
from app.providers.direct_provider import verify_media_container_signature

logger = logging.getLogger(__name__)

SUPPORTED_LOCAL_EXTENSIONS = ('.mp4', '.mp3', '.wav', '.m4a')


class LocalMediaProvider(BaseRetrievalProvider):
    """
    Provider for local computer files and folder-selected media files.
    """

    @property
    def provider_name(self) -> str:
        return 'local'

    def identify(self, source_reference: str) -> bool:
        """Determines if this provider can handle the given local reference."""
        return self.identify_source(source_reference)

    def identify_source(self, source_reference: str) -> bool:
        """
        Determines whether the given reference represents a local file or local folder source.
        """
        if not source_reference:
            return False
        ref = source_reference.strip().lower()
        if ref.startswith(('http://', 'https://')):
            return False
        if ref.startswith(('local:', 'file://', 'local_file', 'local_folder')):
            return True
        return ref.endswith(SUPPORTED_LOCAL_EXTENSIONS)

    def check_accessibility(
        self,
        source_reference: str,
        options: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Non-destructive pre-flight check for a local file selection.
        Validates media extension, checks file size against configured limit,
        and returns eligibility status.
        """
        opts = dict(options or {})
        opts.update(kwargs)

        filename = opts.get('filename') or source_reference or 'selected_media'
        # Extract filename from path if path-like
        clean_filename = os.path.basename(filename)
        ext = os.path.splitext(clean_filename)[1].lower()

        if ext not in SUPPORTED_LOCAL_EXTENSIONS:
            return {
                'success': False,
                'status': 'error',
                'accessibility_status': 'Media Type Unsupported',
                'source_type': opts.get('source_type', 'local_file'),
                'source_reference': clean_filename,
                'retrieval_eligible': False,
                'message': f"Unsupported media extension '{ext}'. Supported formats: .mp4, .mp3, .wav, .m4a."
            }

        max_size = opts.get('max_size_bytes', 250 * 1024 * 1024)
        raw_size = opts.get('file_size')
        if isinstance(raw_size, (int, float)) and raw_size > max_size:
            max_mb = max_size // (1024 * 1024)
            return {
                'success': False,
                'status': 'error',
                'accessibility_status': 'File Too Large',
                'source_type': opts.get('source_type', 'local_file'),
                'source_reference': clean_filename,
                'retrieval_eligible': False,
                'message': f"Local file size exceeds allowable limit of {max_mb} MB."
            }

        media_type = 'video/mp4' if ext == '.mp4' else f'audio/{ext.lstrip(".")}'
        return {
            'success': True,
            'source_type': opts.get('source_type', 'local_file'),
            'source_reference': clean_filename,
            'accessibility_status': 'Retrieval Supported',
            'media_type': media_type,
            'file_size': opts.get('file_size_formatted', 'Local File'),
            'retrieval_eligible': True,
            'requires_auth': False,
            'explanation': 'Local media file verified. File can be transferred to the processing pipeline.'
        }

    def retrieve_media(
        self,
        source_reference: str,
        destination_dir: str,
        max_size_bytes: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
        file_storage: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Stages a local computer media file into destination_dir.
        Enforces extension matching, byte limits, container verification,
        and safe unique naming.
        """
        if max_size_bytes is None:
            max_size_bytes = 250 * 1024 * 1024

        opts = dict(options or {})
        opts.update(kwargs)

        source_type = opts.get('source_type', 'local_file')
        actual_file_storage = file_storage or opts.get('file_storage')

        if not actual_file_storage and not (source_reference and os.path.exists(source_reference)):
            return {
                'success': False,
                'error': 'No local file stream or valid source file path was provided.',
                'code': 'NO_FILE'
            }

        raw_filename = getattr(actual_file_storage, 'filename', None) or os.path.basename(source_reference)
        clean_name = secure_filename(raw_filename)
        if not clean_name:
            clean_name = "local_media"

        ext = os.path.splitext(raw_filename)[1].lower()
        if ext not in SUPPORTED_LOCAL_EXTENSIONS:
            return {
                'success': False,
                'error': f"Invalid local media extension '{ext}'. Supported formats: .mp4, .mp3, .wav, .m4a.",
                'code': 'INVALID_EXTENSION'
            }

        os.makedirs(destination_dir, exist_ok=True)
        unique_prefix = uuid.uuid4().hex[:12]
        safe_filename = f"{unique_prefix}_{clean_name}"
        destination_path = os.path.join(destination_dir, safe_filename)

        # Write content in controlled chunks to enforce size limit
        bytes_written = 0
        try:
            with open(destination_path, 'wb') as dest_f:
                if actual_file_storage:
                    if hasattr(actual_file_storage, 'seek'):
                        actual_file_storage.seek(0)
                    while True:
                        chunk = actual_file_storage.read(65536)
                        if not chunk:
                            break
                        bytes_written += len(chunk)
                        if bytes_written > max_size_bytes:
                            dest_f.close()
                            if os.path.exists(destination_path):
                                os.remove(destination_path)
                            max_mb = max_size_bytes // (1024 * 1024)
                            return {
                                'success': False,
                                'error': f"File size exceeds maximum allowable limit of {max_mb} MB.",
                                'code': 'FILE_TOO_LARGE'
                            }
                        dest_f.write(chunk)
                else:
                    with open(source_reference, 'rb') as src_f:
                        while True:
                            chunk = src_f.read(65536)
                            if not chunk:
                                break
                            bytes_written += len(chunk)
                            if bytes_written > max_size_bytes:
                                dest_f.close()
                                if os.path.exists(destination_path):
                                    os.remove(destination_path)
                                max_mb = max_size_bytes // (1024 * 1024)
                                return {
                                    'success': False,
                                    'error': f"File size exceeds maximum allowable limit of {max_mb} MB.",
                                    'code': 'FILE_TOO_LARGE'
                                }
                            dest_f.write(chunk)
        except Exception as e:
            if os.path.exists(destination_path):
                os.remove(destination_path)
            logger.error("Failed to write local media file %s: %s", raw_filename, str(e))
            return {
                'success': False,
                'error': f"Failed to save local media file: {str(e)}",
                'code': 'WRITE_ERROR'
            }

        if bytes_written == 0:
            if os.path.exists(destination_path):
                os.remove(destination_path)
            return {
                'success': False,
                'error': 'Uploaded local file is empty (0 bytes).',
                'code': 'EMPTY_FILE'
            }

        # Verify container signature (MP4/M4A ftyp, MP3 ID3/MPEG, WAV RIFF)
        valid_container, container_msg = verify_media_container_signature(destination_path, ext)
        if not valid_container:
            if os.path.exists(destination_path):
                os.remove(destination_path)
            return {
                'success': False,
                'error': f"File failed media container validation: {container_msg}",
                'code': 'INVALID_CONTAINER'
            }

        input_type = 'video' if ext == '.mp4' else 'audio'
        return {
            'success': True,
            'source_type': source_type,
            'input_type': input_type,
            'original_filename': raw_filename,
            'safe_filename': safe_filename,
            'storage_path': destination_path,
            'file_size': bytes_written,
            'file_extension': ext.lstrip('.'),
            'message': f"Local {input_type} ({ext}) verified and ready for processing."
        }
