"""
YouTube Retrieval Provider for WebinarAI (Prompt A5).

Complies strictly with platform terms and copyright rules:
- No unauthorized scraping, stream interception, or prohibited download tools (no yt-dlp, youtube-dl).
- Uses official YouTube Data API v3 for video metadata and caption inspection.
- When permitted captions are available, ingests transcript directly into pipeline without video downloading.
- If captions are not available or video download is restricted, returns clean rejection guiding user to manual upload.
"""

import os
import re
import uuid
import logging
from typing import Dict, Any, Optional

from app.providers.base import BaseRetrievalProvider

logger = logging.getLogger(__name__)

YOUTUBE_URL_REGEX = re.compile(
    r'^(https?://)?(www\.|m\.)?(youtube\.com/(?:watch\?.*?v=|shorts/|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})',
    re.IGNORECASE
)


def extract_youtube_video_id(url_or_id: str) -> Optional[str]:
    """Extracts the 11-character YouTube video ID from standard URL formats or raw ID."""
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


class YouTubeProvider(BaseRetrievalProvider):
    """
    Official YouTube integration provider for WebinarAI.
    """

    @property
    def provider_name(self) -> str:
        return 'youtube'

    def identify(self, source_reference: str) -> bool:
        """Determines if the given reference is a YouTube video URL."""
        if not source_reference or not isinstance(source_reference, str):
            return False
        ref = source_reference.strip().lower()
        if 'youtube.com' in ref or 'youtu.be' in ref:
            return extract_youtube_video_id(source_reference) is not None
        return False

    def build_service(self, api_key: Optional[str] = None):
        """Builds an official YouTube Data API v3 client."""
        key = api_key or os.environ.get('YOUTUBE_API_KEY')
        if not key:
            return None
        from googleapiclient.discovery import build
        return build('youtube', 'v3', developerKey=key, cache_discovery=False)

    def check_accessibility(
        self,
        source_reference: str,
        options: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Validates YouTube URL and inspects official metadata and caption tracks.
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

        service = opts.get('youtube_service')
        api_key = opts.get('api_key')

        if not service and api_key:
            try:
                service = self.build_service(api_key)
            except Exception as e:
                logger.error("Failed to build YouTube service: %s", str(e))

        # If official service is available, query video details and caption tracks
        if service:
            try:
                video_resp = service.videos().list(
                    part='snippet,contentDetails,status',
                    id=video_id
                ).execute()

                items = video_resp.get('items', [])
                if not items:
                    return {
                        'success': False,
                        'status': 'error',
                        'source_type': 'youtube',
                        'accessibility_status': 'Video Not Found',
                        'retrieval_eligible': False,
                        'message': 'YouTube video not found. Verify that the video is public or unlisted.'
                    }

                video_item = items[0]
                snippet = video_item.get('snippet', {})
                title = snippet.get('title', f"YouTube Video {video_id}")
                channel = snippet.get('channelTitle', '')

                # Query captions
                has_captions = False
                try:
                    captions_resp = service.captions().list(
                        part='snippet',
                        videoId=video_id
                    ).execute()
                    caption_items = captions_resp.get('items', [])
                    has_captions = len(caption_items) > 0
                except Exception as ce:
                    logger.info("Could not list caption tracks via API: %s", str(ce))
                    # Some YouTube channels restrict caption API; check snippet
                    has_captions = opts.get('mock_has_captions', False)

                if not has_captions and not opts.get('has_captions', False):
                    if opts.get('caption_content'):
                        return {
                            'success': True,
                            'source_type': 'youtube',
                            'source_reference': source_reference,
                            'video_id': video_id,
                            'title': title,
                            'channel': channel,
                            'accessibility_status': 'Transcript Attached',
                            'media_type': 'YouTube Video (User-Provided Transcript)',
                            'file_size': 'Transcript Stream',
                            'retrieval_eligible': True,
                            'requires_auth': False,
                            'explanation': f"YouTube video '{title}' verified with user-provided transcript."
                        }
                    return {
                        'success': False,
                        'status': 'error',
                        'source_type': 'youtube',
                        'source_reference': source_reference,
                        'video_id': video_id,
                        'title': title,
                        'accessibility_status': 'Download Restricted',
                        'retrieval_eligible': False,
                        'message': 'This YouTube recording does not have official public captions available. Automated video downloading from YouTube is prohibited by platform policies. Please attach a transcript (.vtt/.txt) or upload the recording manually.'
                    }

                return {
                    'success': True,
                    'source_type': 'youtube',
                    'source_reference': source_reference,
                    'video_id': video_id,
                    'title': title,
                    'channel': channel,
                    'accessibility_status': 'Retrieval Supported',
                    'media_type': 'YouTube Video (Official Captions)',
                    'file_size': 'Transcript Stream',
                    'retrieval_eligible': True,
                    'requires_auth': False,
                    'explanation': f"YouTube video '{title}' verified. Official captions are available for automated summarization."
                }

            except Exception as e:
                logger.error("YouTube API error for %s: %s", video_id, str(e))
                if opts.get('caption_content'):
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
                        'explanation': 'YouTube URL verified with user-provided transcript.'
                    }
                return {
                    'success': False,
                    'status': 'error',
                    'source_type': 'youtube',
                    'accessibility_status': 'API Error',
                    'retrieval_eligible': False,
                    'message': f"YouTube API query failed: {str(e)}"
                }

        # Fallback when API key or service is not configured
        if opts.get('caption_content'):
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
                'explanation': 'YouTube URL verified with user-provided transcript.'
            }

        return {
            'success': True,
            'source_type': 'youtube',
            'source_reference': source_reference,
            'video_id': video_id,
            'accessibility_status': 'Retrieval Supported',
            'media_type': 'YouTube Video (Official Captions)',
            'file_size': 'N/A (Stream / Captions)',
            'retrieval_eligible': True,
            'requires_auth': False,
            'explanation': 'YouTube URL format verified. Official captions will be inspected and routed directly to summarization without video downloading. An accompanying transcript can be attached below if captions are unavailable.'
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
        Retrieves official YouTube captions/transcript and saves as a VTT transcript file.
        Strict guardrail: Refuses unauthorized video binary downloading.
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

        # Strict guardrail: Check if user attempted to force video download
        if opts.get('force_video_download'):
            return {
                'success': False,
                'error': 'Automated video stream downloading from YouTube is strictly prohibited. Only official captions can be retrieved.',
                'code': 'DOWNLOAD_RESTRICTED'
            }

        caption_content = opts.get('caption_content')
        service = opts.get('youtube_service')
        api_key = opts.get('api_key') or os.environ.get('YOUTUBE_API_KEY')

        if not caption_content:
            if not service and api_key:
                try:
                    service = self.build_service(api_key)
                except Exception as e:
                    logger.warning("Could not build YouTube service in retrieve_media: %s", str(e))

            if service:
                try:
                    captions_resp = service.captions().list(part='snippet', videoId=video_id).execute()
                    items = captions_resp.get('items', [])
                    if items:
                        caption_id = items[0]['id']
                        # Download caption track
                        caption_stream = service.captions().download(id=caption_id, tfmt='vtt').execute()
                        caption_content = caption_stream.decode('utf-8') if isinstance(caption_stream, bytes) else str(caption_stream)
                except Exception as e:
                    logger.warning("Could not download caption track via API: %s", str(e))

        # If caption content is not available, enforce guardrail
        if not caption_content or not str(caption_content).strip():
            return {
                'success': False,
                'error': 'No permitted official captions or transcript tracks were found for this YouTube recording. Automated video downloading is not permitted. Please upload an MP4 recording or transcript manually.',
                'code': 'DOWNLOAD_RESTRICTED'
            }

        # Save caption content as a safe WebVTT transcript file
        os.makedirs(destination_dir, exist_ok=True)
        unique_prefix = uuid.uuid4().hex[:12]
        safe_filename = f"{unique_prefix}_youtube_{video_id}.vtt"
        destination_path = os.path.join(destination_dir, safe_filename)

        # Ensure valid VTT header and standardized line endings
        vtt_text = str(caption_content).strip().replace('\r\n', '\n').replace('\r', '\n')
        if not vtt_text.startswith('WEBVTT'):
            vtt_text = "WEBVTT\n\n" + vtt_text

        with open(destination_path, 'w', encoding='utf-8') as f:
            f.write(vtt_text)

        file_size = os.path.getsize(destination_path)

        return {
            'success': True,
            'source_type': 'youtube',
            'input_type': 'transcript',
            'original_filename': f"youtube_{video_id}_captions.vtt",
            'safe_filename': safe_filename,
            'storage_path': destination_path,
            'file_size': file_size,
            'file_extension': 'vtt',
            'source_url': source_reference,
            'video_id': video_id,
            'message': 'Official YouTube caption transcript retrieved and staged for AI summarization.'
        }

