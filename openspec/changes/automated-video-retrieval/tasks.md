# Tasks

## 1. Dashboard Source Selection UI (Prompt A1)

- [x] 1.1 Extend `app/templates/dashboard.html` Section A with a 6-option "Webinar Content Source" selector (Direct Link, YouTube, Google Drive, Local File, Local Folder, Manual Upload) while preserving manual MP4/TXT/VTT inputs; verify UI renders properly in browser
- [x] 1.2 Implement client-side dynamic source panels and input validation in `app/static/js/dashboard.js`; verify switching between modes activates appropriate input controls
- [x] 1.3 Add "Check Accessibility" trigger and status display card showing source type, reachability, media size, and eligibility; verify visual states for loading, success, warning, and error
- [x] 1.4 Add unit/integration tests for dashboard template rendering and accessibility status endpoints in `tests/test_source_selection_ui.py`; verify tests pass

## 2. Direct Media URL Retrieval & SSRF Protection (Prompt A2)

- [x] 2.1 Implement `app/utils/ssrf.py` with DNS resolution validation, private/loopback/cloud IP blocking (RFC 1918, RFC 3927), safe port filtering, and redirect re-validation; verify with unit tests
- [x] 2.2 Implement `DirectMediaProvider` in `app/providers/direct_provider.py` supporting streaming downloads up to `MAX_VIDEO_SIZE`, connection timeouts, and binary container header verification (`ftyp` for MP4, audio headers for MP3/WAV); verify provider tests pass
- [x] 2.3 Implement POST `/api/sources/direct/check` and `/api/sources/direct/retrieve` endpoints in `app/routes/dashboard_routes.py`; verify end-to-end retrieval with mock HTTP server tests

## 3. Local Computer File and Folder Selection (Prompt A3)

- [x] 3.1 Implement browser-supported local file selection and folder selection (`webkitdirectory` / File System Access API) in `app/static/js/dashboard.js` with client-side media filtering (`.mp4`, `.mp3`, `.wav`, `.m4a`); verify selection in browser
- [x] 3.2 Display selected folder contents in the UI, allowing the user to inspect discovered media and pick the target recording; verify only selected file transfers to backend
- [x] 3.3 Add fallback messaging for browsers lacking directory picker support; verify graceful fallback rendering
- [x] 3.4 Implement backend upload handling for selected local files in `app/providers/local_provider.py` and write tests in `tests/test_local_selection.py`; verify tests pass

## 4. Google Drive Official Integration (Prompt A4)

- [x] 4.1 Implement Google OAuth 2.0 flow (`app/routes/auth_routes.py` and `app/providers/gdrive_provider.py`) with `drive.readonly` scope, CSRF state verification, and encrypted token session storage; verify OAuth routes
- [x] 4.2 Implement Google Drive file metadata inspection, access verification, and streaming binary download via official `google-api-python-client`; verify unit tests with mocked Google Drive API
- [x] 4.3 Handle Google Drive specific errors (401 unauthenticated, 403 access denied/download disabled, 404 not found, 429 quota exceeded, non-media Workspace docs); verify sanitized error reporting
- [x] 4.4 Add secure Google account disconnection endpoint (`/api/sources/gdrive/disconnect`) and verify session cleanup

## 5. YouTube Compliance & Official Caption Integration (Prompt A5)

- [x] 5.1 Implement YouTube URL parser in `app/providers/youtube_provider.py` supporting `youtube.com/watch?v=`, `youtu.be/`, and `/shorts/` formats; verify URL extraction tests
- [x] 5.2 Implement official YouTube Data API v3 client for video metadata (title, channel, duration, caption tracks) and verify metadata retrieval
- [x] 5.3 Implement official caption/transcript ingestion when permitted, routing transcript directly to `transcript_service.py` without video downloading; verify transcript parsing
- [x] 5.4 Implement strict non-bypass guardrails: when video has no captions or automated retrieval is restricted, return "Download Restricted" and guide user to manual upload; verify tests pass

## 6. Retrieval & Processing Pipeline Integration (Prompt A6)

- [x] 6.1 Extend MySQL `ProcessingJob` model in `app/models/schema.py` with `source_type`, `source_url`, `retrieval_status`, and `retrieval_error` columns with database migration script; verify schema update
- [x] 6.2 Update `app/services/pipeline_service.py` and `transcript_service.py` to accept audio-only inputs (MP3, WAV, M4A) by skipping video audio extraction and feeding audio directly to Whisper; verify pipeline tests
- [x] 6.3 Connect successful media retrievals directly to `pipeline_service.start_job_pipeline_async()`, ensuring retrieval failures halt the pipeline before any summarization or email delivery attempts; verify failure isolation tests
- [x] 6.4 Implement idempotency guards preventing duplicate downloads or duplicate email dispatches on page refresh or retry; verify idempotency tests

## 7. Comprehensive Testing, Security Verification & Documentation (Prompt A7)

- [x] 7.1 Execute full test matrix covering 26 verification scenarios (direct MP4/audio, invalid links, SSRF attempts, YouTube metadata/captions/restrictions, Google Drive public/private/error flows, local files/folders, failure isolation, retry idempotency, and manual upload preservation)
- [x] 7.2 Verify that all existing 162 unit and integration tests continue to pass without regression
- [x] 7.3 Update `README.md` with API credential configuration, supported sources, security boundaries, and user guide
- [x] 7.4 Update `PROJECT_STATUS.md` with final test execution results and operational metrics

