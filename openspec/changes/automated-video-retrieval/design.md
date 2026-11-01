# Design: Automated Webinar Video Retrieval and Processing

## Context

WebinarAI currently ingests webinar content strictly through browser-uploaded MP4, TXT, or VTT files via POST `/api/upload-webinar`, storing validated files in `storage/uploads/`. A `ProcessingJob` record in MySQL tracks the job, and `pipeline_service.py` runs audio extraction (FFmpeg), speech-to-text (Whisper), AI summarization (Gemini), PDF generation (ReportLab), and email delivery (SMTP) in an asynchronous background daemon thread.

This change introduces automated remote and local retrieval across 5 new source types (Direct URLs, YouTube, Google Drive, Local Files, and Local Folders) while preserving manual uploads. See `proposal.md` for motivation and `specs/media-retrieval/spec.md` for normative requirements.

## Goals / Non-Goals

**Goals:**
- Provide a modular provider architecture (`BaseRetrievalProvider`) for source detection, access validation, and streaming retrieval.
- Implement an explicit pre-flight "Check Accessibility" capability prior to committing a processing job.
- Implement robust Server-Side Request Forgery (SSRF) defenses for direct URL ingestion (IP validation, DNS rebinding defense, redirect re-validation, port whitelisting, streaming size limits).
- Integrate official Google Drive API v3 and OAuth 2.0 authorization for cloud files.
- Implement YouTube Data API v3 integration for metadata and permitted captions, with explicit non-bypass compliance.
- Support browser-native local file and directory selection (`webkitdirectory`) without arbitrary host filesystem access.
- Seamlessly route retrieved media into the existing `pipeline_service.py` pipeline.
- Maintain 100% backward compatibility with existing tests and manual upload workflows.

**Non-Goals:**
- Unauthorized video scraping or downloading tools (`yt-dlp`, `youtube-dl`, headless browser DOM scrapers).
- Bypassing video DRM, subscriptions, paywalls, or platform login barriers.
- Server-side browsing of arbitrary client or host filesystem directories.
- Rewriting or altering existing Gemini summarization, ReportLab PDF, or SMTP email services.

## Decisions

### Decision 1: Modular Provider Interface (`BaseRetrievalProvider`)
We will create a clean abstraction in `app/providers/base.py`:
- `identify(source_reference: str) -> bool`: Identifies whether this provider handles the input.
- `check_accessibility(source_reference: str, options: dict) -> AccessibilityResult`: Verifies reachability, auth requirements, file size, MIME type.
- `retrieve_media(source_reference: str, destination_dir: str, options: dict) -> RetrievalResult`: Streams content to safe storage and verifies container signature.
- `cleanup(temp_paths: list)`: Safely removes temporary files on failure.

*Alternatives considered*:
- Putting retrieval logic directly in route handlers: Rejected as it tightly couples network transport with HTTP controller logic and prevents provider reusability.

### Decision 2: Two-Step Workflow (Check Accessibility vs Start Processing)
The UI separates checking from job creation:
1. `Check Accessibility`: Calls `/api/sources/check-accessibility`, returning metadata (title, size, MIME type, auth required, eligibility) without downloading the complete recording.
2. `Start Processing & Deliver Email`: User confirms rights/authorization and clicks the primary button, calling `/api/sources/submit-job` which performs retrieval and hands off to `pipeline_service.py`.

*Alternatives considered*:
- Auto-retrieving on URL paste: Rejected because it wastes bandwidth, triggers unnecessary remote requests, and could lead to accidental job creation.

### Decision 3: Server-Side SSRF Protection Engine (`app/utils/ssrf.py`)
All remote requests (direct URLs and redirects) pass through an SSRF validator:
1. Scheme restriction: `http` and `https` only.
2. Port restriction: Approved standard ports (80, 443) unless explicitly allowed.
3. DNS resolution and IP evaluation: Resolves host to IPv4/IPv6 and verifies against `ipaddress.is_private`, `is_loopback`, `is_reserved`, `is_link_local`, and cloud metadata addresses (`169.254.169.254`).
4. Redirect following with re-validation: Redirects must re-validate the target address against SSRF rules.
5. Streaming byte limits: Downloads are read in 64KB chunks up to `MAX_VIDEO_SIZE` (250MB); aborts immediately if exceeded.

*Alternatives considered*:
- Standard `requests.get`: Vulnerable to SSRF, DNS rebinding, and memory exhaustion from infinite streams.

### Decision 4: Official Google OAuth 2.0 & Google Drive API v3
For Google Drive links:
- Uses `google-auth-oauthlib` and `google-api-python-client`.
- Minimal scope: `https://www.googleapis.com/auth/drive.readonly`.
- User clicks "Connect Google Drive", completes standard OAuth consent, and session stores the token securely (or in encrypted user settings).
- Downloads binary files using `drive_service.files().get_media()`.
- Rejects non-media Google Workspace native formats (Docs, Sheets) with a descriptive error.

*Alternatives considered*:
- Parsing public download links (`drive.google.com/uc?export=download`): Unreliable, violates Google rate limits, and fails for files larger than 100MB due to virus scan warning interstitials.

### Decision 5: YouTube API Metadata & Caption Ingestion Only
In accordance with user requirements and terms of service:
- Accepts standard YouTube URLs (`watch?v=`, `youtu.be/`, `/shorts/`).
- Safely extracts the 11-character video ID.
- Uses official YouTube Data API v3 to fetch video title, description, and caption tracks.
- When captions are available, retrieves the authorized transcript and directly feeds it to `transcript_service.py` (bypassing video extraction and Whisper).
- When automated video retrieval or captions are restricted, clearly explains the limitation and prompts the user to upload a local recording or transcript.
- Absolutely zero integration of `yt-dlp` or scraping workarounds.

*Alternatives considered*:
- Bundling `yt-dlp`: Strictly forbidden by user guidelines due to terms of service, DRM, and platform stability risks.

### Decision 6: Browser-Supported Local File and Folder Selection
For local files and folders:
- Uses HTML5 standard `<input type="file">` for files.
- Uses `<input type="file" webkitdirectory>` (and File System Access API where supported) for folder selection.
- Browser inspects the folder, filters for supported media formats (`.mp4`, `.mp3`, `.wav`, `.m4a`), and displays a file selection list inside the dashboard.
- The user selects the intended recording, and only that file is transferred to the server via existing `validate_and_save_media`.
- Completely avoids arbitrary server-side filesystem scanning.

### Decision 7: Backward-Compatible Database Schema Extension
In `app/models/schema.py`:
- `ProcessingJob` gains nullable columns:
  - `source_type = db.Column(db.String(50), default='manual_upload', nullable=False)`
  - `source_url = db.Column(db.String(500), nullable=True)`
  - `retrieval_status = db.Column(db.String(50), default='completed', nullable=False)`
  - `retrieval_error = db.Column(db.Text, nullable=True)`
- Existing jobs continue working with defaults.
- Schema initialization runs `init_db.py` or safe `ALTER TABLE` if columns are absent.

## Risks / Trade-offs

- **[Risk] Direct download timeout on slow external servers**  
  → *Mitigation*: Enforce configurable connection timeout (15s) and streaming read timeout (60s). Track partial progress and clean up on timeout.
- **[Risk] DNS Rebinding attack in direct media URL retrieval**  
  → *Mitigation*: Pin the resolved IP address when opening the HTTP connection or verify IP on each DNS resolution step before data transfer.
- **[Risk] YouTube video has no captions and automated video retrieval is forbidden**  
  → *Mitigation*: Detect absence of official captions during "Check Accessibility", report status clearly as "Download Restricted / Captions Unavailable", and guide the user to manual upload.
- **[Risk] Google Drive OAuth token expiration or quota limits**  
  → *Mitigation*: Catch `HttpError` 401/403/429 specifically; attempt token refresh using refresh token; return actionable user-facing messages.
- **[Risk] Browser does not support `webkitdirectory`**  
  → *Mitigation*: Feature-detect browser capability; display a polite notice advising the user to select files directly or use a compatible modern browser.

## Migration Plan

1. Create migration script / helper to check and add new columns to `processing_jobs` table in MySQL (`source_type`, `source_url`, `retrieval_status`, `retrieval_error`).
2. Add providers under `app/providers/` without touching existing upload endpoints.
3. Update `app/services/pipeline_service.py` to handle retrieved media inputs and audio-only formats.
4. Update dashboard UI to provide the new "Webinar Content Source" controls alongside existing manual upload controls.
5. Ensure all existing 162 tests pass continuously.

