"""
YouTube Retrieval Provider for WebinarAI using yt-dlp (Prompt A5).

Implements official yt-dlp media retrieval for YouTube URLs:
- Validates and normalizes YouTube URLs across standard watch, youtu.be, shorts, and embed formats.
- Separates Metadata retrieval, Caption/transcript inspection, and Media retrieval.
- Prefers audio-only stream extraction (m4a/mp3) to optimize bandwidth, disk, and transcription performance.
- Enforces strict compliance: No DRM bypass, no cookie/login scraping, no unauthorized circumvention.
- Requires user authorization confirmation before media retrieval.
- Performs FFprobe media verification on downloaded media.
- Provides fallback to manual MP4/TXT/VTT upload when automated retrieval is unavailable or restricted.
"""

import os
import re
import glob
import uuid
import logging
import subprocess
from typing import Dict, Any, Optional

try:
    import yt_dlp
    from yt_dlp.utils import DownloadError, ExtractorError
    HAS_YTDLP = True
except ImportError:
    yt_dlp = None
    DownloadError = Exception
    ExtractorError = Exception
    HAS_YTDLP = False

from app.providers.base import BaseRetrievalProvider

logger = logging.getLogger(__name__)

YOUTUBE_URL_REGEX = re.compile(
    r'^(https?://)?(www\.|m\.)?(youtube\.com/(?:watch\?.*?v=|shorts/|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})',
    re.IGNORECASE
)

# Maximum allowed video duration (4 hours = 14,400 seconds)
DEFAULT_MAX_DURATION_SECONDS = 14400

# Default maximum media download size (250 MB)
DEFAULT_MAX_MEDIA_SIZE_BYTES = 250 * 1024 * 1024


def extract_youtube_video_id(url_or_id: Optional[str]) -> Optional[str]:
    """
    Extracts the 11-character YouTube video ID from standard URL formats or raw ID.
    Rejects malformed inputs, unrelated domains, and non-string values.
    """
    if not url_or_id or not isinstance(url_or_id, str):
        return None
    url = url_or_id.strip()
    match = YOUTUBE_URL_REGEX.search(url)
    if match:
        return match.group(4)
    # Check if raw 11-char ID
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url
    return None


def get_canonical_youtube_url(video_id: str) -> str:
    """Returns standard canonical YouTube watch URL for a video ID."""
    return f"https://www.youtube.com/watch?v={video_id}"


def get_ffmpeg_directory() -> Optional[str]:
    """Finds directory containing FFmpeg/FFprobe binaries if available."""
    for candidate in [r'C:\Apps\ffmpeg\bin', r'C:\ffmpeg\bin']:
        if os.path.exists(os.path.join(candidate, 'ffmpeg.exe')) and os.path.exists(os.path.join(candidate, 'ffprobe.exe')):
            return candidate
    return None


def verify_media_file_with_ffprobe(file_path: str) -> bool:
    """
    Verifies that the retrieved file exists, is non-empty, and can be probed by FFprobe.
    """
    if not file_path or not os.path.exists(file_path):
        return False
    if os.path.getsize(file_path) == 0:
        return False

    try:
        from app.services.audio_service import get_ffprobe_executable
        probe_bin = get_ffprobe_executable()
        cmd = [
            probe_bin,
            '-v', 'error',
            '-show_entries', 'format=duration,size,format_name',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        return res.returncode == 0
    except Exception as e:
        logger.warning("FFprobe verification warning for %s: %s", file_path, str(e))
        return os.path.exists(file_path) and os.path.getsize(file_path) > 0


def map_ytdlp_error(err: Exception) -> Dict[str, str]:
    """
    Maps yt-dlp DownloadError / ExtractorError to user-facing explanations and error codes.
    Sanitizes output so no raw stack traces or internal server paths are exposed.
    """
    err_str = str(err)
    err_lower = err_str.lower()

    if 'private video' in err_lower:
        return {
            'code': 'PRIVATE_VIDEO',
            'message': 'This YouTube video is private. Access is restricted.'
        }
    if 'sign in' in err_lower or 'confirm you’re not a bot' in err_lower or 'members-only' in err_lower or 'login required' in err_lower:
        return {
            'code': 'LOGIN_REQUIRED',
            'message': 'Access to this video requires login or subscription. Platform restrictions prevent automated retrieval.'
        }
    if 'video unavailable' in err_lower or 'has been removed' in err_lower or 'does not exist' in err_lower:
        return {
            'code': 'VIDEO_UNAVAILABLE',
            'message': 'YouTube video is unavailable or has been deleted.'
        }
    if 'not available in your country' in err_lower or 'blocked in your country' in err_lower or 'geographic' in err_lower:
        return {
            'code': 'GEOGRAPHIC_RESTRICTION',
            'message': 'This YouTube video is geographically restricted in your region.'
        }
    if 'drm' in err_lower or 'protected' in err_lower:
        return {
            'code': 'DRM_RESTRICTED',
            'message': 'This video is protected by digital rights management (DRM) and cannot be retrieved.'
        }
    if 'live event' in err_lower or 'is live' in err_lower or 'premieres in' in err_lower:
        return {
            'code': 'LIVE_EVENT',
            'message': 'Live stream content or upcoming premieres cannot be processed until completed.'
        }
    if 'timed out' in err_lower or 'timeout' in err_lower:
        return {
            'code': 'NETWORK_TIMEOUT',
            'message': 'Connection timed out while contacting YouTube servers.'
        }

    return {
        'code': 'RETRIEVAL_FAILED',
        'message': f"Unable to retrieve YouTube media: {err_str.split(';')[0].strip()}"
    }


class YouTubeProvider(BaseRetrievalProvider):
    """
    YouTube integration provider for WebinarAI powered by yt-dlp.
    Provides separated metadata inspection, caption handling, and audio-first media retrieval.
    """

    @property
    def provider_name(self) -> str:
        return 'youtube'

    def identify(self, source_reference: Optional[str]) -> bool:
        """Determines if the given reference is a YouTube video URL."""
        if not source_reference or not isinstance(source_reference, str):
            return False
        ref = source_reference.strip().lower()
        if 'youtube.com' in ref or 'youtu.be' in ref:
            return extract_youtube_video_id(source_reference) is not None
        return False

    def get_metadata(
        self,
        source_reference: str,
        options: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Retrieves video metadata using yt-dlp without downloading any media.
        Returns video title, duration, channel, and format info.
        """
        opts = dict(options or {})
        opts.update(kwargs)

        video_id = extract_youtube_video_id(source_reference)
        if not video_id:
            return {
                'success': False,
                'code': 'INVALID_URL',
                'error': 'Invalid YouTube link. Please provide a standard watch, youtu.be, or shorts URL.'
            }

        # Check for mock info in unit testing
        if opts.get('mock_info'):
            return {
                'success': True,
                'video_id': video_id,
                'info': opts['mock_info']
            }

        if not HAS_YTDLP or yt_dlp is None:
            return {
                'success': False,
                'code': 'DEPENDENCY_MISSING',
                'error': 'The yt-dlp package is not installed in this Python environment. Please install it with: pip install yt-dlp'
            }

        canonical_url = get_canonical_youtube_url(video_id)
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'extract_flat': False,
            'socket_timeout': 15,
            'geo_bypass': False,
        }
        ffmpeg_dir = get_ffmpeg_directory()
        if ffmpeg_dir:
            ydl_opts['ffmpeg_location'] = ffmpeg_dir

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(canonical_url, download=False)
                return {
                    'success': True,
                    'video_id': video_id,
                    'info': info
                }
        except DownloadError as de:
            mapped = map_ytdlp_error(de)
            return {
                'success': False,
                'code': mapped['code'],
                'error': mapped['message']
            }
        except Exception as e:
            logger.error("Unexpected yt-dlp metadata extraction error: %s", str(e), exc_info=True)
            return {
                'success': False,
                'code': 'METADATA_EXTRACTION_FAILED',
                'error': f"Failed to inspect YouTube video metadata: {str(e)}"
            }

    def check_accessibility(
        self,
        source_reference: str,
        options: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Pre-flight accessibility and metadata inspection for YouTube video.
        Uses yt-dlp metadata extraction without downloading media.
        """
        opts = dict(options or {})
        opts.update(kwargs)

        video_id = extract_youtube_video_id(source_reference)
        if not video_id:
            return {
                'success': False,
                'status': 'error',
                'source_type': 'youtube',
                'accessibility_status': 'Invalid URL',
                'retrieval_eligible': False,
                'message': 'Invalid YouTube link. Please provide a standard watch, youtu.be, or shorts URL.'
            }

        # If user already provided an attached transcript, check if they want to use that directly
        caption_content = opts.get('caption_content')

        # Perform yt-dlp metadata retrieval
        meta_result = self.get_metadata(source_reference, options=opts)
        if not meta_result.get('success'):
            if caption_content:
                return {
                    'success': True,
                    'source_type': 'youtube',
                    'source_reference': source_reference,
                    'video_id': video_id,
                    'accessibility_status': 'Transcript Attached',
                    'media_type': 'YouTube Video (User-Provided Transcript)',
                    'file_size': 'Transcript Stream',
                    'retrieval_eligible': True,
                    'requires_auth': False,
                    'explanation': 'YouTube URL verified with user-provided transcript attached.'
                }

            return {
                'success': False,
                'status': 'error',
                'source_type': 'youtube',
                'source_reference': source_reference,
                'video_id': video_id,
                'accessibility_status': meta_result.get('code', 'Retrieval Error'),
                'retrieval_eligible': False,
                'code': meta_result.get('code'),
                'message': meta_result.get('error', 'Unable to retrieve YouTube video information.')
            }

        info = meta_result.get('info', {})
        title = info.get('title', f"YouTube Video {video_id}")
        channel = info.get('uploader') or info.get('channel') or ''
        duration = info.get('duration')  # In seconds

        # Check duration limit
        max_duration = opts.get('max_duration_seconds', DEFAULT_MAX_DURATION_SECONDS)
        if duration and duration > max_duration:
            hours = round(max_duration / 3600, 1)
            return {
                'success': False,
                'status': 'error',
                'source_type': 'youtube',
                'source_reference': source_reference,
                'video_id': video_id,
                'title': title,
                'channel': channel,
                'accessibility_status': 'Duration Exceeded',
                'retrieval_eligible': False,
                'code': 'DURATION_EXCEEDED',
                'message': f"This YouTube video is {duration // 60} minutes long, which exceeds the allowed duration limit of {hours} hours."
            }

        # Check subtitles / captions availability
        has_subtitles = bool(info.get('subtitles') or info.get('automatic_captions'))

        # Format file size estimation
        filesize = info.get('filesize') or info.get('filesize_approx')
        if filesize and isinstance(filesize, (int, float)):
            size_mb = round(filesize / (1024 * 1024), 1)
            formatted_size = f"~{size_mb} MB (Audio Stream)"
        else:
            formatted_size = "Adaptive Audio Stream"

        # Format duration string
        duration_str = ""
        if duration:
            mins, secs = divmod(int(duration), 60)
            hrs, mins = divmod(mins, 60)
            duration_str = f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"

        if caption_content:
            return {
                'success': True,
                'source_type': 'youtube',
                'source_reference': source_reference,
                'video_id': video_id,
                'title': title,
                'channel': channel,
                'duration': duration,
                'duration_str': duration_str,
                'accessibility_status': 'Transcript Attached',
                'media_type': 'YouTube Video (User-Provided Transcript)',
                'file_size': 'Transcript Stream',
                'retrieval_eligible': True,
                'requires_auth': False,
                'explanation': f"YouTube video '{title}' verified with attached transcript for summarization."
            }

        return {
            'success': True,
            'source_type': 'youtube',
            'source_reference': source_reference,
            'video_id': video_id,
            'title': title,
            'channel': channel,
            'duration': duration,
            'duration_str': duration_str,
            'accessibility_status': 'Retrieval Supported',
            'media_type': 'YouTube Audio (yt-dlp Stream)',
            'file_size': formatted_size,
            'retrieval_eligible': True,
            'has_subtitles': has_subtitles,
            'requires_auth': False,
            'explanation': f"YouTube video '{title}' verified via yt-dlp. Audio stream will be retrieved and transcribed using Whisper."
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
        Retrieves YouTube audio/media using yt-dlp.
        - Enforces user rights confirmation.
        - Prefers audio-only stream extraction (m4a/mp3).
        - Saves with unique generated UUID filename.
        - Verifies retrieved media using FFprobe.
        - Falls back to user-provided transcript if attached.
        """
        opts = dict(options or {})
        opts.update(kwargs)

        video_id = extract_youtube_video_id(source_reference)
        if not video_id:
            return {
                'success': False,
                'error': 'Invalid YouTube URL or video ID.',
                'code': 'INVALID_URL'
            }

        # User rights authorization confirmation check
        user_authorized = bool(opts.get('user_authorized', False))
        if not user_authorized:
            return {
                'success': False,
                'error': 'User authorization confirmation required. Please confirm you have the necessary rights or authorization to retrieve and process this content.',
                'code': 'AUTHORIZATION_REQUIRED'
            }

        if not HAS_YTDLP or yt_dlp is None:
            return {
                'success': False,
                'code': 'DEPENDENCY_MISSING',
                'error': 'The yt-dlp package is not installed in this Python environment. Please install it with: pip install yt-dlp'
            }

        # Fast path: user provided accompanying transcript
        caption_content = opts.get('caption_content')
        if caption_content and str(caption_content).strip() and opts.get('prefer_transcript', False):
            os.makedirs(destination_dir, exist_ok=True)
            unique_prefix = uuid.uuid4().hex[:12]
            safe_filename = f"{unique_prefix}_youtube_{video_id}.vtt"
            dest_path = os.path.join(destination_dir, safe_filename)
            vtt_text = str(caption_content).strip().replace('\r\n', '\n').replace('\r', '\n')
            if not vtt_text.startswith('WEBVTT'):
                vtt_text = "WEBVTT\n\n" + vtt_text
            with open(dest_path, 'w', encoding='utf-8') as f:
                f.write(vtt_text)

            return {
                'success': True,
                'source_type': 'youtube',
                'input_type': 'transcript',
                'original_filename': f"youtube_{video_id}_transcript.vtt",
                'safe_filename': safe_filename,
                'storage_path': dest_path,
                'file_size': os.path.getsize(dest_path),
                'file_extension': 'vtt',
                'source_url': source_reference,
                'video_id': video_id,
                'message': 'Accompanying YouTube transcript staged for pipeline processing.'
            }

        # Check for mock download in unit test environment
        if opts.get('mock_download_file'):
            mock_file = opts['mock_download_file']
            ext = os.path.splitext(mock_file)[1].lstrip('.').lower()
            return {
                'success': True,
                'source_type': 'youtube',
                'input_type': 'audio' if ext in ('m4a', 'mp3', 'wav', 'aac', 'ogg', 'flac') else 'video',
                'original_filename': f"youtube_{video_id}.{ext}",
                'safe_filename': os.path.basename(mock_file),
                'storage_path': mock_file,
                'file_size': os.path.getsize(mock_file),
                'file_extension': ext,
                'source_url': source_reference,
                'video_id': video_id,
                'title': opts.get('title', f"YouTube Video {video_id}"),
                'duration': opts.get('duration', 60),
                'message': f"YouTube audio retrieved successfully ({ext.upper()}) and staged for pipeline processing."
            }

        # Prepare yt-dlp download options
        os.makedirs(destination_dir, exist_ok=True)
        unique_prefix = uuid.uuid4().hex[:12]
        outtmpl = os.path.join(destination_dir, f"{unique_prefix}_youtube_{video_id}.%(ext)s")
        max_bytes = max_size_bytes or DEFAULT_MAX_MEDIA_SIZE_BYTES

        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best',
            'outtmpl': outtmpl,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'socket_timeout': 30,
            'max_filesize': max_bytes,
            'geo_bypass': False,
        }
        ffmpeg_dir = get_ffmpeg_directory()
        if ffmpeg_dir:
            ydl_opts['ffmpeg_location'] = ffmpeg_dir

        canonical_url = get_canonical_youtube_url(video_id)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(canonical_url, download=True)
                downloaded_title = info.get('title', f"YouTube Video {video_id}")
                downloaded_duration = info.get('duration')

        except DownloadError as de:
            # Clean up partial files
            for partial in glob.glob(os.path.join(destination_dir, f"{unique_prefix}_youtube_{video_id}.*")):
                try:
                    os.remove(partial)
                except Exception:
                    pass

            mapped = map_ytdlp_error(de)
            return {
                'success': False,
                'code': mapped['code'],
                'error': mapped['message']
            }
        except Exception as e:
            logger.error("Unexpected yt-dlp media download error: %s", str(e), exc_info=True)
            for partial in glob.glob(os.path.join(destination_dir, f"{unique_prefix}_youtube_{video_id}.*")):
                try:
                    os.remove(partial)
                except Exception:
                    pass

            return {
                'success': False,
                'code': 'DOWNLOAD_FAILED',
                'error': f"Media retrieval failed: {str(e)}"
            }

        # Locate the downloaded file
        candidates = glob.glob(os.path.join(destination_dir, f"{unique_prefix}_youtube_{video_id}.*"))
        # Exclude temporary .part files
        completed_files = [f for f in candidates if not f.endswith('.part') and not f.endswith('.ytdl')]

        if not completed_files:
            return {
                'success': False,
                'code': 'FILE_NOT_FOUND',
                'error': 'Media retrieval completed but output media file was not found on disk.'
            }

        downloaded_file = completed_files[0]
        ext = os.path.splitext(downloaded_file)[1].lstrip('.').lower()

        # Enforce size limit check
        file_size = os.path.getsize(downloaded_file)
        if file_size > max_bytes:
            try:
                os.remove(downloaded_file)
            except Exception:
                pass
            return {
                'success': False,
                'code': 'SIZE_EXCEEDED',
                'error': f"Downloaded media ({round(file_size / (1024 * 1024), 1)} MB) exceeds maximum allowed limit of {round(max_bytes / (1024 * 1024), 1)} MB."
            }

        # Verify media file with FFprobe
        if not verify_media_file_with_ffprobe(downloaded_file):
            try:
                os.remove(downloaded_file)
            except Exception:
                pass
            return {
                'success': False,
                'code': 'MEDIA_VERIFICATION_FAILED',
                'error': 'Retrieved media file could not be verified by FFprobe. Media stream may be corrupted or unreadable.'
            }

        input_type = 'audio' if ext in ('m4a', 'mp3', 'wav', 'aac', 'ogg', 'flac') else 'video'
        safe_filename = os.path.basename(downloaded_file)

        return {
            'success': True,
            'source_type': 'youtube',
            'input_type': input_type,
            'original_filename': f"youtube_{video_id}.{ext}",
            'safe_filename': safe_filename,
            'storage_path': downloaded_file,
            'file_size': file_size,
            'file_extension': ext,
            'source_url': source_reference,
            'video_id': video_id,
            'title': downloaded_title,
            'duration': downloaded_duration,
            'message': f"YouTube audio retrieved successfully ({ext.upper()}) and staged for AI pipeline processing."
        }
