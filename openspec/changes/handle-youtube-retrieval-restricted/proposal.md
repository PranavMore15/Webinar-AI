# Proposal: Handle YouTube Retrieval Restricted and Caption Fallback

## Why

When users attempt to create a processing job using a YouTube URL where automated video downloading is prohibited and official caption tracks cannot be downloaded automatically (e.g., videos lacking official caption tracks, YouTube Data API quota/OAuth restrictions on 3rd party caption downloads, or missing API keys), the job submission abruptly fails during modal confirmation with:
`"YouTube Retrieval Restricted: No permitted official captions or transcript tracks were found for this YouTube recording. Automated video downloading is not permitted. Please upload an MP4 recording or transcript manually."`

This failure occurs late in the workflow after the user has already configured recipient lists because the pre-flight accessibility check previously returned a misleading "Retrieval Supported" status without verifying retrievability. Furthermore, the dashboard provides no inline fallback to supply transcript text or a caption file alongside the YouTube video URL, leaving the user blocked.

## What Changes

- **Accurate Pre-Flight Accessibility Inspection**: Update `YouTubeProvider.check_accessibility` and the pre-flight check endpoint to accurately determine caption availability and API readiness, returning "Captions Unavailable" or "Download Restricted" upfront instead of a false "Retrieval Supported".
- **Inline Transcript / Caption Fallback for YouTube**: When official captions cannot be downloaded automatically, enable users to provide a transcript directly within the YouTube source panel (by uploading a `.vtt` / `.txt` file or entering transcript text), allowing job creation to proceed with `source_type: 'youtube'` and the original video URL linked to the job.
- **Provider API Service Initialization**: Fix `YouTubeProvider.retrieve_media` to correctly initialize the YouTube Data API v3 service from `api_key` or environment configuration when available, rather than requiring an explicit pre-built service instance in options.
- **Dashboard Submission and Error Recovery UX**: Update `app/static/js/dashboard.js` and `app/templates/dashboard.html` to pass user-provided caption content during retrieval and provide immediate actionable recovery (such as one-click switching to manual upload or inline transcript entry) when automated caption retrieval is restricted.
- **Preserve Compliance Guardrails**: Maintain strict compliance with platform terms prohibiting automated video stream ripping or scraping tools (`yt-dlp`), ensuring that all ingestion occurs either via permitted caption retrieval or authorized user-provided transcripts.

## Capabilities

### New Capabilities
- `media-retrieval`: Resilient YouTube accessibility inspection, restricted caption detection, and inline transcript fallback ingestion for automated webinar processing.

### Modified Capabilities
<!-- None. No existing specs in openspec/specs/. -->

## Impact

- **Backend**:
  - `app/providers/youtube_provider.py`: Build service from `api_key` in `retrieve_media`, validate caption availability accurately in `check_accessibility`.
  - `app/routes/dashboard_routes.py`: Forward caption content payload from frontend in `/api/sources/youtube/retrieve`.
- **Frontend**:
  - `app/templates/dashboard.html`: Add optional/fallback transcript input or file upload in YouTube source panel.
  - `app/static/js/dashboard.js`: Capture fallback transcript/caption file, submit it with retrieval request, and provide seamless recovery actions in the job submission modal.
- **Testing**:
  - `tests/test_youtube_integration.py`: Add test cases for restricted retrieval warning during accessibility check, fallback caption retrieval, and service instantiation.

