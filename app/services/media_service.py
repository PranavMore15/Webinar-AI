import os
import uuid
from werkzeug.utils import secure_filename

class MediaValidationError(Exception):
    """Exception raised when uploaded media fails validation."""
    pass

def validate_and_save_media(file_storage, source_type: str, upload_folder: str, max_size_bytes: int):
    """
    Safely validates and stores webinar media (MP4 video or TXT/VTT transcript).
    
    Validation checks:
    1. Source type must be 'video' or 'transcript'.
    2. Filename and extension matching source type.
    3. File size within configured limit.
    4. Non-empty file content.
    5. Content verification:
       - MP4: checks container header (e.g. ftyp box / valid binary).
       - TXT/VTT: checks decodeability and non-whitespace text; VTT checks header/cues.
    6. Safe storage under upload_folder with unique collision-resistant filename.
    
    Returns dict with success status, original_filename, storage_path, file_size, or error.
    """
    if not file_storage or not file_storage.filename:
        return {
            'success': False,
            'error': 'No file was provided for upload.',
            'code': 'NO_FILE'
        }

    raw_filename = file_storage.filename
    clean_name = secure_filename(raw_filename)
    if not clean_name:
        clean_name = "uploaded_file"

    ext = raw_filename.rsplit('.', 1)[-1].lower() if '.' in raw_filename else ''

    # Validate extension by source type
    if source_type == 'video':
        if ext != 'mp4':
            return {
                'success': False,
                'error': f"Invalid video file extension '.{ext}'. Only MP4 files (.mp4) are allowed.",
                'code': 'INVALID_EXTENSION'
            }
    elif source_type == 'transcript':
        if ext not in ('txt', 'vtt'):
            return {
                'success': False,
                'error': f"Invalid transcript file extension '.{ext}'. Only TXT (.txt) and WebVTT (.vtt) files are allowed.",
                'code': 'INVALID_EXTENSION'
            }
    else:
        return {
            'success': False,
            'error': f"Unknown webinar source type '{source_type}'. Must be 'video' or 'transcript'.",
            'code': 'INVALID_SOURCE_TYPE'
        }

    # Read bytes safely
    try:
        if hasattr(file_storage, 'seek'):
            file_storage.seek(0)
        file_bytes = file_storage.read()
    except Exception as e:
        return {
            'success': False,
            'error': f"Failed to read upload stream: {str(e)}",
            'code': 'READ_ERROR'
        }

    # Size check
    file_size = len(file_bytes)
    if file_size == 0:
        return {
            'success': False,
            'error': 'Uploaded file is empty (0 bytes).',
            'code': 'EMPTY_FILE'
        }

    if file_size > max_size_bytes:
        max_mb = max_size_bytes // (1024 * 1024)
        return {
            'success': False,
            'error': f"File size ({file_size // (1024 * 1024)}MB) exceeds allowable limit of {max_mb}MB.",
            'code': 'FILE_TOO_LARGE'
        }

    # Content signature verification
    if source_type == 'video':
        # Basic MP4 ISO box check: MP4 files contain 'ftyp' in bytes 4..8
        if len(file_bytes) < 8 or b'ftyp' not in file_bytes[:16]:
            return {
                'success': False,
                'error': 'File does not appear to be a valid MP4 video container.',
                'code': 'INVALID_VIDEO_HEADER'
            }
    elif source_type == 'transcript':
        # Text decoding check
        decoded_text = None
        for enc in ('utf-8', 'utf-8-sig', 'latin-1'):
            try:
                decoded_text = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if decoded_text is None:
            return {
                'success': False,
                'error': 'Transcript file is not valid readable text (encoding error).',
                'code': 'DECODE_ERROR'
            }

        stripped_content = decoded_text.strip()
        if len(stripped_content) == 0:
            return {
                'success': False,
                'error': 'Transcript file contains only whitespace and has no spoken content.',
                'code': 'EMPTY_CONTENT'
            }

        # If .vtt extension, verify WebVTT header or cue presence
        if ext == 'vtt':
            if not stripped_content.upper().startswith('WEBVTT') and '-->' not in stripped_content:
                return {
                    'success': False,
                    'error': "Malformed WebVTT file: Missing 'WEBVTT' header or timing cue markers ('-->').",
                    'code': 'MALFORMED_VTT'
                }

    # Safe storage write
    os.makedirs(upload_folder, exist_ok=True)
    unique_prefix = uuid.uuid4().hex[:12]
    safe_disk_filename = f"{unique_prefix}_{clean_name}"
    target_path = os.path.join(upload_folder, safe_disk_filename)

    try:
        with open(target_path, 'wb') as f:
            f.write(file_bytes)
    except Exception as e:
        # Clean up if partially written
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass
        return {
            'success': False,
            'error': f"Failed to save file to disk storage: {str(e)}",
            'code': 'WRITE_ERROR'
        }

    return {
        'success': True,
        'source_type': source_type,
        'original_filename': raw_filename,
        'safe_filename': safe_disk_filename,
        'storage_path': target_path,
        'file_size': file_size,
        'file_extension': ext
    }

def delete_uploaded_file(file_path: str) -> bool:
    """Safely removes an uploaded file from disk if it exists."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            return True
        except OSError:
            return False
    return False
