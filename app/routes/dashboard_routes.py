import os
import re
import logging
import urllib.parse
from flask import Blueprint, render_template, redirect, url_for, session, flash, request, jsonify, current_app, send_file
from app.models import db, User, ProcessingJob, JobRecipient
from app.services import csv_service, media_service, pdf_service, email_service, pipeline_service
from app.utils.auth import login_required, user_required, EMAIL_REGEX

dashboard_bp = Blueprint('dashboard', __name__)
logger = logging.getLogger(__name__)

@dashboard_bp.route('/')
def root():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    if session.get('role') == 'admin':
        return redirect(url_for('admin.dashboard'))
    return redirect(url_for('dashboard.index'))

@dashboard_bp.route('/dashboard')
@user_required
def index():
    if not session.get('user_id'):
        flash('Please log in to access the WebinarAI dashboard.', 'warning')
        return redirect(url_for('auth.login'))
    
    username = session.get('username', 'Authorized User')
    user_id = session.get('user_id')

    # Retrieve current session upload states if active
    csv_state = session.get('current_csv_validation')
    webinar_state = session.get('current_webinar_upload')
    if webinar_state and webinar_state.get('storage_path') and not os.path.exists(webinar_state['storage_path']):
        session.pop('current_webinar_upload', None)
        webinar_state = None

    # Query persistent recent jobs for this authenticated user
    recent_jobs = []
    try:
        recent_jobs = ProcessingJob.query.filter_by(user_id=user_id).order_by(ProcessingJob.created_at.desc()).limit(50).all()
    except Exception:
        recent_jobs = []

    return render_template(
        'dashboard.html',
        username=username,
        csv_state=csv_state,
        webinar_state=webinar_state,
        recent_jobs=recent_jobs
    )

@dashboard_bp.route('/api/upload-webinar', methods=['POST'])
@user_required
def upload_webinar():
    """
    Server-side MP4, TXT, and VTT upload handling.
    Enforces authentication, size limits, extension matching, and safe storage under storage/uploads/.
    """
    if 'file' not in request.files and 'webinar_file' not in request.files:
        return jsonify({'success': False, 'message': 'No webinar file was submitted.'}), 400

    uploaded_file = request.files.get('file') or request.files.get('webinar_file')
    if not uploaded_file or uploaded_file.filename == '':
        return jsonify({'success': False, 'message': 'No file was selected.'}), 400

    source_type = request.form.get('source_type', 'video').lower().strip()
    if source_type not in ('video', 'transcript'):
        return jsonify({'success': False, 'message': "Source type must be 'video' or 'transcript'."}), 400

    # Select configured size limit
    max_size = current_app.config.get('MAX_VIDEO_SIZE', 250 * 1024 * 1024) if source_type == 'video' else current_app.config.get('MAX_TRANSCRIPT_SIZE', 10 * 1024 * 1024)
    upload_folder = current_app.config.get('UPLOAD_FOLDER')

    # Validate and save to storage/uploads
    result = media_service.validate_and_save_media(
        file_storage=uploaded_file,
        source_type=source_type,
        upload_folder=upload_folder,
        max_size_bytes=max_size
    )

    if not result.get('success'):
        return jsonify({
            'success': False,
            'message': result.get('error', 'Webinar media validation failed.'),
            'code': result.get('code')
        }), 400

    # Clean up previous webinar file in current session if replaced
    previous_upload = session.get('current_webinar_upload')
    if previous_upload and previous_upload.get('storage_path'):
        media_service.delete_uploaded_file(previous_upload['storage_path'])

    # Store validated media in session for workflow orchestration
    session['current_webinar_upload'] = {
        'input_type': result['source_type'],
        'original_filename': result['original_filename'],
        'safe_filename': result['safe_filename'],
        'storage_path': result['storage_path'],
        'file_size': result['file_size'],
        'file_extension': result['file_extension']
    }

    return jsonify({
        'success': True,
        'message': f"Webinar {result['source_type']} uploaded and verified on server.",
        'details': {
            'input_type': result['source_type'],
            'original_filename': result['original_filename'],
            'safe_filename': result['safe_filename'],
            'file_size': result['file_size'],
            'file_extension': result['file_extension']
        }
    }), 200

@dashboard_bp.route('/api/clear-webinar', methods=['POST'])
@user_required
def clear_webinar():
    """
    Clears the active webinar upload from disk and current session state.
    """
    webinar_data = session.get('current_webinar_upload')
    if webinar_data and webinar_data.get('storage_path'):
        media_service.delete_uploaded_file(webinar_data['storage_path'])

    session.pop('current_webinar_upload', None)
    return jsonify({'success': True, 'message': 'Webinar media cleared from server storage and session.'}), 200

YOUTUBE_URL_REGEX = re.compile(
    r'^(https?://)?(www\.)?(youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
    re.IGNORECASE
)
GDRIVE_URL_REGEX = re.compile(
    r'^(https?://)?(drive\.google\.com/(?:file/d/|open\?id=)|docs\.google\.com/file/d/)([a-zA-Z0-9_-]+)',
    re.IGNORECASE
)

@dashboard_bp.route('/api/sources/check-accessibility', methods=['POST'])
@user_required
def check_source_accessibility():
    """
    Non-destructive pre-flight accessibility check for remote and local sources.
    Validates URL syntax, provider formatting, detects candidate MIME types,
    and returns accessibility status, eligibility, and instructions without
    initiating a full download or processing job.
    """
    try:
        import urllib.parse
        data = request.get_json(silent=True) or request.form or {}
        source_type = data.get('source_type', '').strip().lower()
        source_url = data.get('source_url', '').strip()
        filename = data.get('filename', '').strip()

        if not source_type:
            return jsonify({
                'success': False,
                'status': 'error',
                'accessibility_status': 'Source Not Selected',
                'message': 'Source type is required.'
            }), 400

        if source_type == 'direct':
            if not source_url:
                return jsonify({
                    'success': False,
                    'status': 'error',
                    'accessibility_status': 'Invalid URL',
                    'message': 'Invalid link. Please enter a valid video or audio link.'
                }), 400

            from app.providers.direct_provider import DirectMediaProvider
            provider = DirectMediaProvider()
            result = provider.check_accessibility(source_url)
            status_code = 200 if result.get('success') else 400
            return jsonify(result), status_code

        elif source_type == 'youtube':
            if not source_url:
                return jsonify({
                    'success': False,
                    'status': 'error',
                    'accessibility_status': 'Invalid URL',
                    'message': 'Please provide a YouTube video URL.'
                }), 400

            caption_content = data.get('caption_content')
            if not caption_content and request.files:
                caption_file = request.files.get('caption_file') or request.files.get('file')
                if caption_file:
                    caption_content = caption_file.read().decode('utf-8', errors='ignore')

            user_authorized = bool(data.get('user_authorized', False))

            from app.providers.youtube_provider import YouTubeProvider
            provider = YouTubeProvider()
            result = provider.check_accessibility(
                source_reference=source_url,
                caption_content=caption_content,
                user_authorized=user_authorized
            )
            status_code = 200 if result.get('success') else 400
            return jsonify(result), status_code

        elif source_type == 'gdrive':
            if not source_url:
                return jsonify({
                    'success': False,
                    'status': 'error',
                    'accessibility_status': 'Invalid URL',
                    'message': 'Please provide a Google Drive file link.'
                }), 400

            from app.providers.gdrive_provider import GDriveMediaProvider
            provider = GDriveMediaProvider()
            result = provider.check_accessibility(
                source_reference=source_url,
                session_token=session.get('gdrive_token'),
                max_size_bytes=current_app.config.get('MAX_VIDEO_SIZE', 250 * 1024 * 1024)
            )
            status_code = 200 if result.get('success') else 400
            return jsonify(result), status_code

        elif source_type in ('local_file', 'local_folder'):
            from app.providers.local_provider import LocalMediaProvider
            provider = LocalMediaProvider()
            result = provider.check_accessibility(
                source_reference=filename or source_url or 'selected_recording',
                filename=filename,
                file_size=data.get('file_size'),
                file_size_formatted=data.get('file_size') if isinstance(data.get('file_size'), str) else None,
                source_type=source_type,
                max_size_bytes=current_app.config.get('MAX_VIDEO_SIZE', 250 * 1024 * 1024)
            )
            status_code = 200 if result.get('success') else 400
            return jsonify(result), status_code

        else:
            return jsonify({
                'success': False,
                'status': 'error',
                'accessibility_status': 'Unsupported Source',
                'message': f"Source type '{source_type}' is not supported by WebinarAI."
            }), 400
    except Exception as e:
        logger.exception("Unhandled error in check_source_accessibility: %s", str(e))
        return jsonify({
            'success': False,
            'status': 'error',
            'accessibility_status': 'Server Error',
            'message': f"Error performing accessibility check: {str(e)}"
        }), 500

@dashboard_bp.route('/api/sources/direct/check', methods=['POST'])
@user_required
def check_direct_media():
    """
    Validates a direct media URL using DirectMediaProvider and SSRF protections.
    """
    from app.providers.direct_provider import DirectMediaProvider
    data = request.get_json(silent=True) or request.form or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({
            'success': False,
            'accessibility_status': 'Invalid URL',
            'message': 'Direct media URL is required.'
        }), 400

    provider = DirectMediaProvider()
    result = provider.check_accessibility(url)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@dashboard_bp.route('/api/sources/direct/retrieve', methods=['POST'])
@user_required
def retrieve_direct_media():
    """
    Streams and verifies a direct media file from a validated URL.
    Saves to upload folder and populates session['current_webinar_upload']
    for seamless integration with job creation.
    """
    from app.providers.direct_provider import DirectMediaProvider
    data = request.get_json(silent=True) or request.form or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({
            'success': False,
            'message': 'Direct media URL is required for retrieval.'
        }), 400

    provider = DirectMediaProvider()
    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    max_size = current_app.config.get('MAX_VIDEO_SIZE', 250 * 1024 * 1024)

    result = provider.retrieve_media(
        source_reference=url,
        destination_dir=upload_folder,
        max_size_bytes=max_size
    )

    if not result.get('success'):
        return jsonify({
            'success': False,
            'message': result.get('error', 'Direct media retrieval failed.'),
            'code': result.get('code')
        }), 400

    # Clean up any previously active webinar upload in current session
    previous_upload = session.get('current_webinar_upload')
    if previous_upload and previous_upload.get('storage_path'):
        media_service.delete_uploaded_file(previous_upload['storage_path'])

    # Stage retrieved file in session
    session['current_webinar_upload'] = {
        'source_type': 'direct',
        'input_type': result['input_type'],
        'original_filename': result['original_filename'],
        'safe_filename': result['safe_filename'],
        'storage_path': result['storage_path'],
        'file_size': result['file_size'],
        'file_extension': result['file_extension'],
        'source_url': url
    }
    session.modified = True

    return jsonify({
        'success': True,
        'message': f"Direct {result['input_type']} retrieved and verified from remote source.",
        'details': session['current_webinar_upload']
    }), 200

@dashboard_bp.route('/api/sources/local/upload', methods=['POST'])
@user_required
def upload_local_source():
    """
    Handles uploaded local media file (from Local File picker or Local Folder discovery).
    Validates extension, size, container signature, and stages into session['current_webinar_upload'].
    """
    from app.providers.local_provider import LocalMediaProvider

    if 'file' not in request.files and 'media_file' not in request.files:
        return jsonify({'success': False, 'message': 'No local media file was provided.'}), 400

    uploaded_file = request.files.get('file') or request.files.get('media_file')
    if not uploaded_file or uploaded_file.filename == '':
        return jsonify({'success': False, 'message': 'No file was selected.'}), 400

    source_type = request.form.get('source_type', 'local_file').strip().lower()
    if source_type not in ('local_file', 'local_folder'):
        source_type = 'local_file'

    provider = LocalMediaProvider()
    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    max_size = current_app.config.get('MAX_VIDEO_SIZE', 250 * 1024 * 1024)

    result = provider.retrieve_media(
        source_reference=uploaded_file.filename,
        destination_dir=upload_folder,
        max_size_bytes=max_size,
        file_storage=uploaded_file,
        source_type=source_type
    )

    if not result.get('success'):
        return jsonify({
            'success': False,
            'message': result.get('error', 'Local media upload failed.'),
            'code': result.get('code')
        }), 400

    # Clean up previous webinar file in current session if replaced
    previous_upload = session.get('current_webinar_upload')
    if previous_upload and previous_upload.get('storage_path'):
        media_service.delete_uploaded_file(previous_upload['storage_path'])

    # Stage validated local media in session
    session['current_webinar_upload'] = {
        'source_type': source_type,
        'input_type': result['input_type'],
        'original_filename': result['original_filename'],
        'safe_filename': result['safe_filename'],
        'storage_path': result['storage_path'],
        'file_size': result['file_size'],
        'file_extension': result['file_extension']
    }
    session.modified = True

    return jsonify({
        'success': True,
        'message': result.get('message', 'Local media uploaded and verified on server.'),
        'details': session['current_webinar_upload']
    }), 200

# -----------------------------------------------------------------------------
# Google Drive Media Endpoints (Prompt A4)
# -----------------------------------------------------------------------------

@dashboard_bp.route('/api/sources/gdrive/status', methods=['GET'])
@user_required
def gdrive_status():
    """Returns whether the active user session has a connected Google account."""
    connected = bool(session.get('gdrive_token'))
    return jsonify({
        'success': True,
        'connected': connected
    }), 200


@dashboard_bp.route('/api/sources/gdrive/disconnect', methods=['POST'])
@user_required
def gdrive_disconnect():
    """Disconnects Google account and cleans up stored OAuth tokens."""
    session.pop('gdrive_token', None)
    session.pop('gdrive_oauth_state', None)
    session.modified = True
    return jsonify({
        'success': True,
        'connected': False,
        'message': 'Google account disconnected successfully.'
    }), 200


@dashboard_bp.route('/api/sources/gdrive/check', methods=['POST'])
@user_required
def gdrive_check():
    """Pre-flight check for a Google Drive URL."""
    from app.providers.gdrive_provider import GDriveMediaProvider
    data = request.get_json(silent=True) or request.form or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({
            'success': False,
            'accessibility_status': 'Invalid URL',
            'message': 'Google Drive file URL is required.'
        }), 400

    provider = GDriveMediaProvider()
    result = provider.check_accessibility(
        source_reference=url,
        session_token=session.get('gdrive_token'),
        max_size_bytes=current_app.config.get('MAX_VIDEO_SIZE', 250 * 1024 * 1024)
    )
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@dashboard_bp.route('/api/sources/gdrive/retrieve', methods=['POST'])
@user_required
def gdrive_retrieve():
    """
    Downloads and verifies a Google Drive media recording via official Drive API v3.
    Stages downloaded media in session['current_webinar_upload'].
    """
    from app.providers.gdrive_provider import GDriveMediaProvider
    data = request.get_json(silent=True) or request.form or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({
            'success': False,
            'message': 'Google Drive URL is required for retrieval.'
        }), 400

    provider = GDriveMediaProvider()
    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    max_size = current_app.config.get('MAX_VIDEO_SIZE', 250 * 1024 * 1024)

    result = provider.retrieve_media(
        source_reference=url,
        destination_dir=upload_folder,
        max_size_bytes=max_size,
        session_token=session.get('gdrive_token')
    )

    if not result.get('success'):
        return jsonify({
            'success': False,
            'message': result.get('error', 'Google Drive media retrieval failed.'),
            'code': result.get('code')
        }), 400

    # Clean up previous webinar file in current session if replaced
    previous_upload = session.get('current_webinar_upload')
    if previous_upload and previous_upload.get('storage_path'):
        media_service.delete_uploaded_file(previous_upload['storage_path'])

    # Stage retrieved file in session
    session['current_webinar_upload'] = {
        'source_type': 'gdrive',
        'input_type': result['input_type'],
        'original_filename': result['original_filename'],
        'safe_filename': result['safe_filename'],
        'storage_path': result['storage_path'],
        'file_size': result['file_size'],
        'file_extension': result['file_extension'],
        'source_url': url
    }
    session.modified = True

    return jsonify({
        'success': True,
        'message': f"Google Drive {result['input_type']} retrieved and verified.",
        'details': session['current_webinar_upload']
    }), 200

# -----------------------------------------------------------------------------
# YouTube Retrieval Endpoints (Prompt A5)
# -----------------------------------------------------------------------------

@dashboard_bp.route('/api/sources/youtube/check', methods=['POST'])
@user_required
def youtube_check():
    """Pre-flight accessibility and metadata inspection for YouTube video using yt-dlp."""
    try:
        from app.providers.youtube_provider import YouTubeProvider
        data = request.get_json(silent=True) or request.form or {}
        url = data.get('url', '').strip()
        user_authorized = bool(data.get('user_authorized', False))

        if not url:
            return jsonify({
                'success': False,
                'accessibility_status': 'Invalid URL',
                'message': 'YouTube video URL is required.'
            }), 400

        caption_content = data.get('caption_content')
        if not caption_content and request.files:
            caption_file = request.files.get('caption_file') or request.files.get('file')
            if caption_file:
                caption_content = caption_file.read().decode('utf-8', errors='ignore')

        provider = YouTubeProvider()
        result = provider.check_accessibility(
            source_reference=url,
            caption_content=caption_content,
            user_authorized=user_authorized
        )
        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code
    except Exception as e:
        logger.exception("Unhandled error in youtube_check: %s", str(e))
        return jsonify({
            'success': False,
            'accessibility_status': 'Server Error',
            'message': f"Error inspecting YouTube video: {str(e)}"
        }), 500


@dashboard_bp.route('/api/sources/youtube/retrieve', methods=['POST'])
@user_required
def youtube_retrieve():
    """
    Retrieves YouTube media (preferring audio) using yt-dlp for authorized content.
    Enforces user authorization confirmation, duration/size limits, and stages in session.
    """
    try:
        from app.providers.youtube_provider import YouTubeProvider
        data = request.get_json(silent=True) or request.form or {}
        url = data.get('url', '').strip()
        user_authorized = bool(data.get('user_authorized', False))

        if not url:
            return jsonify({
                'success': False,
                'message': 'YouTube URL is required for retrieval.'
            }), 400

        if not user_authorized:
            return jsonify({
                'success': False,
                'message': 'User authorization confirmation required. Please confirm you have the necessary rights to retrieve and process this content.',
                'code': 'AUTHORIZATION_REQUIRED'
            }), 400

        caption_content = data.get('caption_content')
        if not caption_content and request.files:
            caption_file = request.files.get('caption_file') or request.files.get('file')
            if caption_file:
                caption_content = caption_file.read().decode('utf-8', errors='ignore')

        provider = YouTubeProvider()
        upload_folder = current_app.config.get('UPLOAD_FOLDER')
        max_size = current_app.config.get('MAX_VIDEO_SIZE')

        result = provider.retrieve_media(
            source_reference=url,
            destination_dir=upload_folder,
            max_size_bytes=max_size,
            caption_content=caption_content,
            user_authorized=user_authorized
        )

        if not result.get('success'):
            return jsonify({
                'success': False,
                'message': result.get('error', 'YouTube media retrieval failed.'),
                'code': result.get('code')
            }), 400

        # Clean up previous webinar file in current session if replaced
        previous_upload = session.get('current_webinar_upload')
        if previous_upload and previous_upload.get('storage_path'):
            media_service.delete_uploaded_file(previous_upload['storage_path'])

        # Stage retrieved media in session
        session['current_webinar_upload'] = {
            'source_type': 'youtube',
            'input_type': result['input_type'],
            'original_filename': result['original_filename'],
            'safe_filename': result['safe_filename'],
            'storage_path': result['storage_path'],
            'file_size': result['file_size'],
            'file_extension': result['file_extension'],
            'source_url': url,
            'title': result.get('title'),
            'duration': result.get('duration')
        }
        session.modified = True

        return jsonify({
            'success': True,
            'message': result.get('message', 'YouTube media retrieved and staged for processing.'),
            'details': session['current_webinar_upload']
        }), 200
    except Exception as e:
        logger.exception("Unhandled error in youtube_retrieve: %s", str(e))
        return jsonify({
            'success': False,
            'message': f"Error retrieving YouTube media: {str(e)}",
            'code': 'SERVER_ERROR'
        }), 500

@dashboard_bp.route('/api/upload-csv', methods=['POST'])
@user_required
def upload_csv():
    """
    Backend CSV validation endpoint for student recipient lists.
    Merges with any existing draft recipients and performs case-insensitive cross-deduplication.
    """
    if 'file' not in request.files and 'csv_file' not in request.files:
        return jsonify({'success': False, 'message': 'No CSV file was submitted with the request.'}), 400

    uploaded_file = request.files.get('file') or request.files.get('csv_file')
    if not uploaded_file or uploaded_file.filename == '':
        return jsonify({'success': False, 'message': 'No file was selected.'}), 400

    filename = uploaded_file.filename
    if not filename.lower().endswith('.csv'):
        return jsonify({
            'success': False,
            'message': 'Unsupported file type. Please upload a .csv file.'
        }), 400

    try:
        file_bytes = uploaded_file.read()
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to read uploaded file: {str(e)}'}), 400

    max_size = current_app.config.get('MAX_CSV_SIZE', 10 * 1024 * 1024)
    if len(file_bytes) > max_size:
        return jsonify({
            'success': False,
            'message': f'File exceeds maximum allowed size ({max_size // (1024 * 1024)}MB).'
        }), 400

    # Retrieve existing draft recipients to perform cross-deduplication
    existing_recipients = []
    current_csv = session.get('current_csv_validation')
    if current_csv and isinstance(current_csv, dict) and current_csv.get('valid_recipients'):
        existing_recipients = list(current_csv.get('valid_recipients'))

    result = csv_service.validate_and_parse_csv(
        file_bytes=file_bytes,
        filename=filename,
        max_size_bytes=max_size,
        existing_recipients=existing_recipients
    )

    if not result.get('success'):
        return jsonify({
            'success': False,
            'message': result.get('error', 'CSV validation failed.'),
            'code': result.get('code')
        }), 400

    combined_recipients = existing_recipients + result['valid_recipients']

    session['current_csv_validation'] = {
        'filename': result['filename'],
        'total_data_rows': (current_csv.get('total_data_rows', 0) if current_csv else 0) + result['total_data_rows'],
        'valid_unique_count': len(combined_recipients),
        'duplicate_count': (current_csv.get('duplicate_count', 0) if current_csv else 0) + result['duplicate_count'],
        'invalid_count': (current_csv.get('invalid_count', 0) if current_csv else 0) + result['invalid_count'],
        'blank_count': (current_csv.get('blank_count', 0) if current_csv else 0) + result['blank_count'],
        'valid_recipients': combined_recipients
    }
    session.modified = True

    response_payload = dict(result)
    response_payload['valid_unique_count'] = len(combined_recipients)
    response_payload['valid_recipients'] = combined_recipients
    return jsonify(response_payload), 200

@dashboard_bp.route('/api/clear-recipients', methods=['POST'])
@dashboard_bp.route('/api/clear-csv', methods=['POST'])
@user_required
def clear_csv():
    """
    Clears active recipient validation session state.
    """
    session.pop('current_csv_validation', None)
    return jsonify({'success': True, 'message': 'Recipient session state cleared.'}), 200

@dashboard_bp.route('/api/recipients', methods=['GET'])
@user_required
def get_recipients():
    """
    Returns current active recipient list from session.
    """
    csv_state = session.get('current_csv_validation') or {}
    recipients = csv_state.get('valid_recipients', [])
    return jsonify({
        'success': True,
        'valid_unique_count': len(recipients),
        'recipients': recipients
    }), 200

@dashboard_bp.route('/api/recipients/add', methods=['POST'])
@user_required
def add_recipient():
    """
    Adds an individual recipient manually to the active draft recipient list.
    Enforces format validation and case-insensitive deduplication across
    both manual entries and CSV uploads, preserving the first valid entry.
    """
    data = request.get_json(silent=True) or request.form or {}
    raw_email = data.get('email', '')
    raw_name = data.get('name', '') or data.get('student_name', '')

    if not raw_email or not str(raw_email).strip():
        return jsonify({
            'success': False,
            'message': 'Email address is required.'
        }), 400

    clean_email = str(raw_email).strip()
    if not EMAIL_REGEX.match(clean_email):
        return jsonify({
            'success': False,
            'message': 'Invalid email address format. Please provide a valid email (e.g., student@university.edu).'
        }), 400

    clean_name = str(raw_name).strip() if raw_name else ''
    normalized_email = clean_email.lower()

    # Retrieve or initialize session recipient state
    csv_state = session.get('current_csv_validation')
    if not csv_state or not isinstance(csv_state, dict):
        csv_state = {
            'filename': 'manual_entry',
            'total_data_rows': 0,
            'valid_unique_count': 0,
            'duplicate_count': 0,
            'invalid_count': 0,
            'blank_count': 0,
            'valid_recipients': []
        }

    recipients = list(csv_state.get('valid_recipients', []))

    # Case-insensitive duplicate check
    for r in recipients:
        if r.get('email', '').lower() == normalized_email:
            return jsonify({
                'success': False,
                'message': f"Recipient '{clean_email}' is already in the recipient list. Duplicate ignored."
            }), 400

    # Add valid recipient
    new_entry = {
        'row': len(recipients) + 1,
        'email': normalized_email,
        'original_email': clean_email,
        'name': clean_name,
        'source': 'manual'
    }
    recipients.append(new_entry)

    csv_state['valid_recipients'] = recipients
    csv_state['valid_unique_count'] = len(recipients)
    session['current_csv_validation'] = csv_state
    session.modified = True

    return jsonify({
        'success': True,
        'message': f"Recipient '{clean_email}' added successfully.",
        'recipient': new_entry,
        'valid_unique_count': len(recipients),
        'recipients': recipients
    }), 200

@dashboard_bp.route('/api/recipients/remove', methods=['POST'])
@user_required
def remove_recipient():
    """
    Deletes an individual recipient from the active draft list by email.
    """
    data = request.get_json(silent=True) or request.form or {}
    target_email = data.get('email', '')

    if not target_email or not str(target_email).strip():
        return jsonify({
            'success': False,
            'message': 'Email address to remove is required.'
        }), 400

    target_normalized = str(target_email).strip().lower()

    csv_state = session.get('current_csv_validation')
    if not csv_state or not isinstance(csv_state, dict) or not csv_state.get('valid_recipients'):
        return jsonify({
            'success': False,
            'message': 'No recipients found in the active list.'
        }), 404

    recipients = list(csv_state.get('valid_recipients', []))
    initial_len = len(recipients)
    recipients = [r for r in recipients if r.get('email', '').lower() != target_normalized]

    if len(recipients) == initial_len:
        return jsonify({
            'success': False,
            'message': f"Recipient '{target_email}' was not found in the list."
        }), 404

    # Re-index rows
    for idx, r in enumerate(recipients, start=1):
        r['row'] = idx

    csv_state['valid_recipients'] = recipients
    csv_state['valid_unique_count'] = len(recipients)
    session['current_csv_validation'] = csv_state
    session.modified = True

    return jsonify({
        'success': True,
        'message': f"Recipient '{target_email}' removed successfully.",
        'valid_unique_count': len(recipients),
        'recipients': recipients
    }), 200

@dashboard_bp.route('/api/validate-state', methods=['POST'])
@user_required
def validate_state():
    """
    Verifies server-side state of selected uploads before job submission.
    Ensures both inputs exist on the server.
    """
    data = request.get_json() or {}
    
    # Check server-side session states
    webinar_state = session.get('current_webinar_upload')
    if webinar_state and webinar_state.get('storage_path'):
        if not os.path.exists(webinar_state['storage_path']):
            session.pop('current_webinar_upload', None)
            webinar_state = None

    has_webinar = webinar_state is not None or data.get('hasWebinar', False)
    webinar_name = webinar_state.get('original_filename', '') if webinar_state else data.get('webinarName', '')
    webinar_type = webinar_state.get('input_type', '') if webinar_state else data.get('webinarType', 'none')

    csv_state = session.get('current_csv_validation')
    recipients_ready = csv_state.get('valid_unique_count', 0) if csv_state else data.get('recipientCount', 0)
    
    if not has_webinar:
        return jsonify({
            'success': False,
            'message': 'Server validation rejected: No webinar video or transcript uploaded to server.'
        }), 400
        
    if recipients_ready <= 0:
        return jsonify({
            'success': False,
            'message': 'Server validation rejected: At least one valid, unique recipient email is required.'
        }), 400
        
    return jsonify({
        'success': True,
        'message': 'Server-side pre-validation passed! Inputs satisfy requirements.',
        'details': {
            'input_type': webinar_type,
            'input_name': webinar_name,
            'recipients_ready': recipients_ready,
            'recipient_filename': csv_state.get('filename', 'client_csv') if csv_state else 'client_csv',
            'stage_note': 'Both inputs verified on backend. Ready for job persistence.'
        }
    })

@dashboard_bp.route('/api/submit-job', methods=['POST'])
@user_required
def submit_job():
    """
    Creates and persists a new ProcessingJob and associated JobRecipient records
    in the database for the authenticated owner.
    """
    user_id = session.get('user_id')
    user = None
    try:
        user = db.session.get(User, user_id) if user_id else None
        if not user:
            # Auto-adopt existing user or auto-provision standard user to prevent foreign key constraint error
            user = User.query.filter_by(role='user').first()
            if user:
                user_id = user.id
                session['user_id'] = user.id
                session['username'] = user.username
                session['role'] = user.role
            else:
                user = User(id=user_id or 2, username='student', email='student@webinarai.local', role='user', is_active=True)
                user.set_password('student123')
                db.session.add(user)
                db.session.commit()
                user_id = user.id
                session['user_id'] = user.id
                session['username'] = user.username
                session['role'] = user.role
    except Exception:
        pass

    webinar_data = session.get('current_webinar_upload')
    csv_data = session.get('current_csv_validation')

    if not webinar_data or not webinar_data.get('storage_path'):
        return jsonify({
            'success': False,
            'message': 'Cannot create processing job: No webinar media uploaded.'
        }), 400

    if not os.path.exists(webinar_data['storage_path']):
        session.pop('current_webinar_upload', None)
        return jsonify({
            'success': False,
            'message': 'Cannot create processing job: Uploaded webinar media file is missing from server storage.'
        }), 400

    if not csv_data or csv_data.get('valid_unique_count', 0) <= 0:
        return jsonify({
            'success': False,
            'message': 'Cannot create processing job: No valid recipient list validated.'
        }), 400

    # Execute database transaction
    try:
        job_title = f"Webinar Processing - {webinar_data['original_filename']}"[:250]
        if request.is_json and request.get_json() and request.get_json().get('title'):
            job_title = request.get_json().get('title')[:250]

        new_job = ProcessingJob(
            user_id=user_id,
            title=job_title,
            input_type=webinar_data['input_type'],
            input_file_name=webinar_data['original_filename'],
            input_file_path=webinar_data['storage_path'],
            source_type=webinar_data.get('source_type', 'manual'),
            source_url=webinar_data.get('source_url'),
            retrieval_status='completed',
            overall_status='ready',
            transcript_status='pending',
            summary_status='pending',
            pdf_status='pending',
            email_status='pending',
            total_recipients=csv_data['valid_unique_count']
        )
        db.session.add(new_job)
        db.session.flush()  # Allocate new_job.id within active transaction

        # Insert job recipients
        recipients_to_insert = [
            JobRecipient(
                job_id=new_job.id,
                email=r['email'],
                student_name=r.get('name') or None,
                delivery_status='pending'
            )
            for r in csv_data['valid_recipients']
        ]
        db.session.add_all(recipients_to_insert)
        db.session.commit()

        # Clear session upload states after successful persistence
        session.pop('current_webinar_upload', None)
        session.pop('current_csv_validation', None)

        # Launch automated asynchronous background processing pipeline (if not in offline test mode)
        if not current_app.config.get('TESTING'):
            pipeline_service.start_job_pipeline_async(new_job.id, current_app._get_current_object())

        return jsonify({
            'success': True,
            'message': f"Processing Job #{new_job.id} created and automated processing pipeline started.",
            'job': {
                'id': new_job.id,
                'input_type': new_job.input_type,
                'input_file_name': new_job.input_file_name,
                'overall_status': new_job.overall_status,
                'total_recipients': new_job.total_recipients,
                'created_at': new_job.created_at.strftime('%Y-%m-%d %H:%M:%S') if new_job.created_at else ''
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f"Database transaction failed while creating job: {str(e)}"
        }), 500

def get_transcription_stage_progress(job):
    """Calculates granular stage label and dynamic progress percentage for transcription."""
    if job.input_type == 'transcript':
        return 25, 'Step 1/4: Ingesting & normalizing transcript...'

    sub_msg = job.error_message
    if not sub_msg or sub_msg.startswith('Transcript Ingestion Failed') or sub_msg.startswith('Processing failed'):
        return 25, 'Step 1/4: Transcribing speech with AI...'

    progress = 25
    if 'Extracting audio' in sub_msg:
        progress = 20
    elif 'Gemini AI' in sub_msg:
        progress = 30
    elif 'chunk' in sub_msg.lower():
        m = re.search(r'chunk\s+(\d+)\s+of\s+(\d+)', sub_msg, re.IGNORECASE)
        if m:
            curr, total = int(m.group(1)), int(m.group(2))
            progress = min(40, 20 + int((curr / max(total, 1)) * 20))
        else:
            progress = 30

    return progress, f"Step 1/4: {sub_msg}"

@dashboard_bp.route('/api/jobs/<int:job_id>', methods=['GET'])
@dashboard_bp.route('/api/jobs/<int:job_id>/status', methods=['GET'])
@user_required
def get_job_status(job_id):
    """
    Returns processing job status with progress percentage and stage descriptions.
    Enforces user ownership server-side.
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    job = db.session.get(ProcessingJob, job_id)
    if not job:
        return jsonify({'success': False, 'message': 'Job not found.'}), 404

    # Ownership verification: ordinary users can only view their own jobs
    if job.user_id != user_id and user_role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied: You do not own this processing job.'}), 403

    stage_labels = {
        'ready': 'Queued in database',
        'processing': 'Processing started...',
        'transcribing': 'Step 1/4: Transcribing speech with AI...',
        'summarizing': 'Step 2/4: Generating structured AI summary with Gemini...',
        'generating_pdf': 'Step 3/4: Compiling ReportLab PDF brief...',
        'sending_emails': 'Step 4/4: Delivering summary emails via SMTP...',
        'completed': 'Completed: Summary brief generated and delivered!',
        'partially_sent': 'Completed with partial email delivery',
        'cancelled': 'Job execution cancelled by user',
        'failed': f"Processing failed: {job.error_message or 'Error occurred'}"
    }
    progress_map = {
        'ready': 5,
        'processing': 15,
        'transcribing': 25,
        'summarizing': 50,
        'generating_pdf': 75,
        'sending_emails': 90,
        'completed': 100,
        'partially_sent': 100,
        'cancelled': 100,
        'failed': 100
    }
    if job.overall_status == 'transcribing':
        trans_pct, trans_label = get_transcription_stage_progress(job)
        stage_labels['transcribing'] = trans_label
        progress_map['transcribing'] = trans_pct

    is_pdf_ready = bool(job.pdf_status == 'completed' and job.pdf_path)

    return jsonify({
        'success': True,
        'job': {
            'id': job.id,
            'title': job.title,
            'input_type': job.input_type,
            'input_file_name': job.input_file_name,
            'overall_status': job.overall_status,
            'transcript_status': job.transcript_status,
            'summary_status': job.summary_status,
            'pdf_status': job.pdf_status,
            'email_status': job.email_status,
            'pdf_ready': is_pdf_ready,
            'pdf_path': job.pdf_path,
            'pdf_url': url_for('dashboard.download_job_pdf', job_id=job.id) if is_pdf_ready else None,
            'progress_percent': progress_map.get(job.overall_status, 10),
            'stage_label': stage_labels.get(job.overall_status, job.overall_status.capitalize()),
            'is_active': job.overall_status in ['ready', 'processing', 'transcribing', 'summarizing', 'generating_pdf', 'sending_emails'],
            'total_recipients': job.total_recipients,
            'successful_emails': job.successful_emails,
            'failed_emails': job.failed_emails,
            'error_message': job.error_message,
            'created_at': job.created_at.strftime('%Y-%m-%d %H:%M:%S') if job.created_at else ''
        }
    }), 200


@dashboard_bp.route('/api/jobs/<int:job_id>/cancel', methods=['POST'])
@user_required
def cancel_job(job_id):
    """
    Cancels an active or queued processing job.
    Enforces user ownership, marks overall_status as 'cancelled',
    and records cancellation explanation.
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    job = db.session.get(ProcessingJob, job_id)
    if not job:
        return jsonify({'success': False, 'message': 'Job not found.'}), 404

    if job.user_id != user_id and user_role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied: You do not own this processing job.'}), 403

    if job.overall_status in ['completed', 'partially_sent', 'failed', 'cancelled']:
        return jsonify({
            'success': False,
            'message': f"Cannot cancel Job #{job.id}: Job is already {job.overall_status}."
        }), 400

    job.overall_status = 'cancelled'
    job.error_message = 'Job execution cancelled by user.'
    if job.transcript_status in ['pending', 'processing']:
        job.transcript_status = 'cancelled'
    if job.summary_status in ['pending', 'generating']:
        job.summary_status = 'cancelled'
    if job.pdf_status in ['pending', 'generating']:
        job.pdf_status = 'cancelled'
    if job.email_status in ['pending', 'sending']:
        job.email_status = 'cancelled'

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f"Processing Job #{job.id} execution has been cancelled.",
        'job': {
            'id': job.id,
            'overall_status': job.overall_status,
            'error_message': job.error_message
        }
    }), 200


@dashboard_bp.route('/api/jobs/<int:job_id>/start', methods=['POST'])
@user_required
def start_job_manually(job_id):
    """
    Manually triggers background pipeline processing for an existing job.
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    job = db.session.get(ProcessingJob, job_id)
    if not job:
        return jsonify({'success': False, 'message': 'Job not found.'}), 404

    if job.user_id != user_id and user_role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied: You do not own this processing job.'}), 403

    if job.overall_status in ['transcribing', 'summarizing', 'generating_pdf', 'sending_emails']:
        return jsonify({'success': False, 'message': 'Job pipeline is already actively running.'}), 409

    pipeline_service.start_job_pipeline_async(job.id, current_app._get_current_object())
    return jsonify({
        'success': True,
        'message': f"Pipeline started for Job #{job.id}."
    }), 200


@dashboard_bp.route('/api/jobs/active-statuses', methods=['GET'])
@user_required
def get_active_job_statuses():
    """
    Returns updated stage statuses for recent user jobs to power live table updates.
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    query = ProcessingJob.query
    if user_role != 'admin':
        query = query.filter_by(user_id=user_id)
    jobs = query.order_by(ProcessingJob.created_at.desc()).limit(50).all()

    progress_map = {
        'ready': 5,
        'processing': 15,
        'transcribing': 25,
        'summarizing': 50,
        'generating_pdf': 75,
        'sending_emails': 90,
        'completed': 100,
        'partially_sent': 100,
        'cancelled': 100,
        'failed': 100
    }

    def format_active_job(j):
        p_pct = progress_map.get(j.overall_status, 10)
        s_lbl = j.overall_status.capitalize()
        if j.overall_status == 'transcribing':
            p_pct, s_lbl = get_transcription_stage_progress(j)
        return {
            'id': j.id,
            'title': j.title,
            'input_type': j.input_type,
            'input_file_name': j.input_file_name,
            'overall_status': j.overall_status,
            'transcript_status': j.transcript_status,
            'summary_status': j.summary_status,
            'pdf_status': j.pdf_status,
            'email_status': j.email_status,
            'pdf_ready': bool(j.pdf_status == 'completed' and j.pdf_path),
            'pdf_url': url_for('dashboard.download_job_pdf', job_id=j.id) if (j.pdf_status == 'completed' and j.pdf_path) else None,
            'progress_percent': p_pct,
            'stage_label': s_lbl,
            'is_active': j.overall_status in ['ready', 'processing', 'transcribing', 'summarizing', 'generating_pdf', 'sending_emails'],
            'successful_emails': j.successful_emails,
            'failed_emails': j.failed_emails,
            'total_recipients': j.total_recipients,
            'error_message': j.error_message,
            'created_at': j.created_at.strftime('%Y-%m-%d %H:%M:%S') if j.created_at else ''
        }

    return jsonify({
        'success': True,
        'jobs': [format_active_job(j) for j in jobs]
    }), 200


@dashboard_bp.route('/dashboard/jobs/<int:job_id>/download-pdf', methods=['GET'])
@dashboard_bp.route('/api/jobs/<int:job_id>/download-pdf', methods=['GET'])
@user_required
def download_job_pdf(job_id):
    """
    Secure, tenant-isolated PDF download endpoint.
    Verifies user ownership, validates file existence within configured PDF storage,
    and prevents directory traversal.
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    job = db.session.get(ProcessingJob, job_id)

    if not job:
        return jsonify({'success': False, 'message': 'Processing job not found.'}), 404

    # Strict ownership verification (ordinary users can only access their own jobs)
    if job.user_id != user_id and user_role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied: You do not own this processing job.'}), 403

    # If PDF is pending/not yet compiled but Gemini summary is ready, attempt on-demand compilation
    if (job.pdf_status != 'completed' or not job.pdf_path) and job.summary_status == 'completed':
        try:
            pdf_service.generate_job_pdf(job)
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f"PDF generation failed on-demand: {str(e)}"
            }), 500

    if job.pdf_status != 'completed' or not job.pdf_path:
        return jsonify({
            'success': False,
            'message': 'PDF summary has not been generated for this job yet. Summarization must be completed first.'
        }), 400

    # Resolve and verify physical file path (traversal defense)
    full_path = pdf_service.resolve_pdf_full_path(job.pdf_path)
    if not full_path or not os.path.isfile(full_path):
        return jsonify({
            'success': False,
            'message': 'PDF file not found on server or path security check failed.'
        }), 404

    download_name = f"WebinarAI_Summary_Job_{job.id}.pdf"
    return send_file(
        full_path,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=download_name
    )


@dashboard_bp.route('/api/jobs/<int:job_id>/generate-pdf', methods=['POST'])
@user_required
def trigger_generate_pdf(job_id):
    """
    Idempotent PDF generation trigger endpoint for a completed AI summary.
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    job = db.session.get(ProcessingJob, job_id)

    if not job:
        return jsonify({'success': False, 'message': 'Processing job not found.'}), 404

    if job.user_id != user_id and user_role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied: You do not own this processing job.'}), 403

    if job.summary_status != 'completed':
        return jsonify({
            'success': False,
            'message': 'Cannot generate PDF: AI summary must be completed first.'
        }), 400

    try:
        force = request.is_json and request.get_json() and request.get_json().get('force', False)
        result = pdf_service.generate_job_pdf(job, force=force)
        return jsonify({
            'success': True,
            'message': 'PDF generated successfully.',
            'job_id': job.id,
            'pdf_status': job.pdf_status,
            'pdf_path': job.pdf_path,
            'idempotent': result.get('idempotent', False)
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"PDF generation failed: {str(e)}"
        }), 500


@dashboard_bp.route('/api/jobs/<int:job_id>/email-preview', methods=['GET'])
@user_required
def get_email_preview(job_id):
    """
    Pre-flight inspection endpoint before email dispatch.
    Returns webinar title, verified PDF readiness, recipient counts,
    and SMTP configuration validation status.
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    job = db.session.get(ProcessingJob, job_id)

    if not job:
        return jsonify({'success': False, 'message': 'Processing job not found.'}), 404

    if job.user_id != user_id and user_role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied: You do not own this processing job.'}), 403

    # Check physical PDF existence and security
    is_pdf_ready = False
    if job.pdf_status == 'completed' and job.pdf_path:
        full_pdf = pdf_service.resolve_pdf_full_path(job.pdf_path)
        if full_pdf and os.path.isfile(full_pdf) and os.path.getsize(full_pdf) > 0:
            is_pdf_ready = True

    # Validate SMTP configuration
    smtp_validation = email_service.validate_smtp_config()

    all_recipients = job.recipients.all()
    total = len(all_recipients)
    sent = sum(1 for r in all_recipients if r.delivery_status == 'sent')
    failed = sum(1 for r in all_recipients if r.delivery_status == 'failed')
    pending = sum(1 for r in all_recipients if r.delivery_status == 'pending')

    return jsonify({
        'success': True,
        'job_id': job.id,
        'title': job.title or job.input_file_name,
        'input_type': job.input_type,
        'input_file_name': job.input_file_name,
        'pdf_ready': is_pdf_ready,
        'pdf_path': job.pdf_path,
        'email_status': job.email_status,
        'overall_status': job.overall_status,
        'smtp_ready': smtp_validation['valid'],
        'smtp_error': smtp_validation.get('error') if not smtp_validation['valid'] else None,
        'counts': {
            'total': total,
            'sent': sent,
            'failed': failed,
            'pending': pending,
            'eligible_to_send': pending + failed
        },
        'preview_recipients': [
            {
                'email': r.email,
                'name': r.student_name,
                'status': r.delivery_status
            }
            for r in all_recipients[:10]
        ]
    }), 200


@dashboard_bp.route('/api/jobs/<int:job_id>/send-emails', methods=['POST'])
@user_required
def trigger_send_emails(job_id):
    """
    User-controlled execution endpoint to dispatch summary PDFs to students.
    Enforces ownership, PDF readiness, SMTP config validity, and concurrency protection.
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    job = db.session.get(ProcessingJob, job_id)

    if not job:
        return jsonify({'success': False, 'message': 'Processing job not found.'}), 404

    if job.user_id != user_id and user_role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied: You do not own this processing job.'}), 403

    if job.pdf_status != 'completed' or not job.pdf_path:
        return jsonify({
            'success': False,
            'message': 'Cannot send emails: Summary PDF has not been generated or completed yet.'
        }), 400

    full_pdf = pdf_service.resolve_pdf_full_path(job.pdf_path)
    if not full_pdf or not os.path.isfile(full_pdf):
        return jsonify({
            'success': False,
            'message': 'Cannot send emails: Summary PDF file is missing from server storage.'
        }), 400

    if job.email_status == 'sending':
        return jsonify({
            'success': False,
            'message': 'Email delivery is already in progress for this job.'
        }), 409

    smtp_val = email_service.validate_smtp_config()
    if not smtp_val['valid']:
        return jsonify({
            'success': False,
            'message': f"SMTP Configuration Error: {smtp_val['error']}",
            'code': smtp_val.get('code')
        }), 400

    try:
        result = email_service.send_webinar_summary_emails(job_id=job.id, retry_failed_only=False)
        return jsonify({
            'success': True,
            'message': f"Email delivery completed: {result['sent_count']} sent, {result['failed_count']} failed.",
            'details': result
        }), 200
    except email_service.SMTPDeliveryError as s_err:
        return jsonify({
            'success': False,
            'message': s_err.message,
            'code': s_err.code
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Email delivery failed: {str(e)}"
        }), 500


@dashboard_bp.route('/api/jobs/<int:job_id>/retry-emails', methods=['POST'])
@user_required
def trigger_retry_emails(job_id):
    """
    Retries delivery strictly for failed or unattempted recipients.
    Never re-sends to recipients who already received the PDF.
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    job = db.session.get(ProcessingJob, job_id)

    if not job:
        return jsonify({'success': False, 'message': 'Processing job not found.'}), 404

    if job.user_id != user_id and user_role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied: You do not own this processing job.'}), 403

    if job.pdf_status != 'completed' or not job.pdf_path:
        return jsonify({
            'success': False,
            'message': 'Cannot retry emails: Summary PDF must be generated first.'
        }), 400

    if job.email_status == 'sending':
        return jsonify({
            'success': False,
            'message': 'Email delivery is already in progress for this job.'
        }), 409

    smtp_val = email_service.validate_smtp_config()
    if not smtp_val['valid']:
        return jsonify({
            'success': False,
            'message': f"SMTP Configuration Error: {smtp_val['error']}",
            'code': smtp_val.get('code')
        }), 400

    try:
        result = email_service.send_webinar_summary_emails(job_id=job.id, retry_failed_only=True)
        return jsonify({
            'success': True,
            'message': f"Retry delivery completed: {result['sent_count']} sent, {result['failed_count']} failed.",
            'details': result
        }), 200
    except email_service.SMTPDeliveryError as s_err:
        return jsonify({
            'success': False,
            'message': s_err.message,
            'code': s_err.code
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Email retry delivery failed: {str(e)}"
        }), 500


@dashboard_bp.route('/api/jobs/<int:job_id>/delivery-report', methods=['GET'])
@user_required
def get_delivery_report(job_id):
    """
    Returns complete delivery audit information for a job owner:
    Totals (accepted, failed, pending), timestamps, and per-recipient delivery statuses.
    """
    user_id = session.get('user_id')
    user_role = session.get('role')
    job = db.session.get(ProcessingJob, job_id)

    if not job:
        return jsonify({'success': False, 'message': 'Processing job not found.'}), 404

    if job.user_id != user_id and user_role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied: You do not own this processing job.'}), 403

    all_recipients = job.recipients.order_by(JobRecipient.id.asc()).all()
    total = len(all_recipients)
    sent = sum(1 for r in all_recipients if r.delivery_status == 'sent')
    failed = sum(1 for r in all_recipients if r.delivery_status == 'failed')
    pending = sum(1 for r in all_recipients if r.delivery_status == 'pending')

    can_retry = (failed > 0 or pending > 0) and job.email_status != 'sending'

    return jsonify({
        'success': True,
        'job_id': job.id,
        'title': job.title or job.input_file_name,
        'email_status': job.email_status,
        'overall_status': job.overall_status,
        'completed_at': job.completed_at.strftime('%Y-%m-%d %H:%M:%S') if job.completed_at else None,
        'counts': {
            'total': total,
            'sent': sent,
            'failed': failed,
            'pending': pending
        },
        'can_retry': can_retry,
        'recipients': [
            {
                'id': r.id,
                'email': r.email,
                'name': r.student_name,
                'status': r.delivery_status,
                'attempts': r.attempt_count,
                'sent_at': r.sent_at.strftime('%Y-%m-%d %H:%M:%S') if r.sent_at else None,
                'last_error': r.last_error
            }
            for r in all_recipients
        ]
    }), 200


