# Design: Handle YouTube Retrieval Restricted and Caption Fallback

## Context

WebinarAI supports YouTube as an ingestion source under Prompt A5, with strict platform compliance: automated video binary downloading (`yt-dlp`, scraping) is prohibited, and processing must rely on captions/transcripts.

However, in practice:
1. `YouTubeProvider.check_accessibility` returns a false-positive `success: True, accessibility_status: 'Retrieval Supported'` when no `YOUTUBE_API_KEY` is configured or caption tracks cannot be verified, misleading users before job submission.
2. `YouTubeProvider.retrieve_media` only looks for `opts.get('youtube_service')` and ignores `api_key`, failing to instantiate the API client when an API key is present.
3. YouTube Data API v3 requires OAuth 2.0 channel owner authorization to download caption tracks via `captions().download()`, so 3rd party public videos cannot download caption binaries via the official API without owner credentials.
4. When `POST /api/sources/youtube/retrieve` fails during job submission modal confirmation, users are blocked with an error modal and no immediate recovery action.

## Goals / Non-Goals

**Goals:**
- Provide accurate pre-flight accessibility reporting: distinguish between verified public captions and unverified/restricted sources upfront.
- Enable inline transcript/caption fallback directly in the YouTube source panel (uploading `.vtt`/`.txt` or pasting text), keeping the YouTube URL and metadata attached to the processing job.
- Fix `YouTubeProvider.retrieve_media` service initialization and ensure user-provided `caption_content` is seamlessly formatted and saved as a valid WebVTT file.
- Add recovery actions to the job confirmation error modal (e.g., "Attach Transcript" and "Switch to Manual Upload") preserving validated recipient lists.
- Retain all compliance guardrails: zero video scraping or unauthorized streaming tools.

**Non-Goals:**
- Downloading video streams from YouTube via unofficial scrapers or reverse-engineered video extractors.
- Modifying the core downstream processing pipeline (which already supports `input_type: 'transcript'`).

## Decisions

### Decision 1: Pre-Flight Accuracy and Status Differentiation
- When `YOUTUBE_API_KEY` is not configured or caption tracks are not accessible via API, `check_accessibility` returns:
  - `accessibility_status: 'Captions Unavailable'`
  - `retrieval_eligible: false`
  - Clear message: `"Automated caption download is restricted for this YouTube recording. You can provide an accompanying transcript file (.vtt/.txt) or paste transcript text below to proceed."`
- When user provides caption content in the UI, `retrieval_eligible` becomes `true` and the status badge updates to `"Transcript Attached"`.
- *Alternative Considered*: Disallowing YouTube URLs entirely if API keys are absent. *Rejected* because educators frequently have YouTube webinar links and external transcript files from Zoom/Teams.

### Decision 2: Inline Fallback Transcript Input on YouTube Panel
- Add a collapsible or integrated "Transcript / Caption Fallback" card inside `#panelSourceYouTube` in `app/templates/dashboard.html`.
- Support two input methods:
  1. File input accepting `.vtt` and `.txt` files.
  2. Textarea for pasting transcript text directly.
- On file selection or text input, `dashboard.js` reads the content into `state.webinarUpload.caption_content` and updates the prerequisite state so the user can proceed to job confirmation.

### Decision 3: Service Building and Fallback Ingestion in `YouTubeProvider`
- In `YouTubeProvider.retrieve_media`:
  - First, check if `caption_content` was passed in `options` or `kwargs`. If present, validate and write directly as a WebVTT transcript file, skipping any external API calls.
  - If `caption_content` is absent, check for `youtube_service` OR build one using `opts.get('api_key') or os.environ.get('YOUTUBE_API_KEY')`.
  - If no captions can be retrieved, return `{ 'success': False, 'code': 'DOWNLOAD_RESTRICTED', 'error': ... }`.
- In `dashboard_routes.py`:
  - In `youtube_retrieve()`, forward `caption_content` from `request.get_json()`.

### Decision 4: Interactive Recovery in Job Confirmation Modal
- When `/api/sources/youtube/retrieve` returns `DOWNLOAD_RESTRICTED`, the confirmation modal displays:
  - Clear explanation: automated downloading is restricted and no caption track was found.
  - Action button: `"Attach Transcript"` (dismisses modal and focuses the YouTube panel's transcript upload control).
  - Action button: `"Switch to Manual Upload"` (activates manual tab without clearing CSV recipient data).

## Risks / Trade-offs

- **[Risk]** User enters unstructured text into the fallback transcript textarea.
  - → *Mitigation*: Ensure `YouTubeProvider.retrieve_media` normalizes raw text into valid WebVTT structure with a `WEBVTT` header and basic cue blocks if cues are not already present.
- **[Risk]** Existing unit tests break due to updated accessibility status response strings.
  - → *Mitigation*: Maintain compatibility with existing mock signatures and update assertions in `tests/test_youtube_integration.py` to cover both automated and fallback paths.

