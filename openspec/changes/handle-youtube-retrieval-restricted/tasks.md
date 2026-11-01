# Tasks

## 1. Backend Provider & Route Enhancements

- [x] 1.1 Update `YouTubeProvider.check_accessibility` in `app/providers/youtube_provider.py` to accurately report caption track availability and return "Captions Unavailable" / "Download Restricted" when captions cannot be fetched, verifying via unit test.
- [x] 1.2 Update `YouTubeProvider.retrieve_media` in `app/providers/youtube_provider.py` to initialize the API service from `api_key` and format user-supplied `caption_content` into a validated WebVTT file, verifying via unit test.
- [x] 1.3 Update `POST /api/sources/youtube/retrieve` in `app/routes/dashboard_routes.py` to accept and forward `caption_content` from request JSON/form to `provider.retrieve_media`, verifying via endpoint tests.

## 2. Frontend UI & Fallback Experience

- [x] 2.1 Add an inline fallback transcript section (file input for `.vtt`/`.txt` and pasteable textarea) to `#panelSourceYouTube` in `app/templates/dashboard.html` and verify markup renders properly.
- [x] 2.2 Update `app/static/js/dashboard.js` to read fallback transcript file/text, update prerequisite readiness, and send `caption_content` with `/api/sources/youtube/retrieve`, verifying client-side state handling.
- [x] 2.3 Enhance the job confirmation modal error handling in `app/static/js/dashboard.js` to provide "Attach Transcript" and "Switch to Manual Upload" recovery actions when YouTube retrieval is restricted, verifying modal recovery behavior.

## 3. Integration Testing & Full Verification

- [x] 3.1 Update and expand `tests/test_youtube_integration.py` to cover pre-flight caption detection, user-supplied caption ingestion, and end-to-end job creation with YouTube transcripts, verifying with `python -m unittest tests/test_youtube_integration.py`.
- [x] 3.2 Execute the entire application test suite to ensure all retrieval providers and pipeline integration tests continue passing without regression.

