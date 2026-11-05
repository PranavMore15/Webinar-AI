# Proposal

## Why

When users process webinars via direct video links or manual video uploads, processing takes 15 to 20+ minutes and appears completely frozen at the transcribing stage (progress pinned at 25%). This severe bottleneck and perception of being stuck stems from two issues:
1. Video inputs currently extract audio into uncompressed 10-minute WAV chunks and execute dense, unquantized OpenAI Whisper (`base`) inference strictly on the CPU, running near 1:1 real-time speed (e.g., a 15-minute video takes ~15 minutes).
2. During this entire CPU inference window, no granular database progress updates are written, leaving the user with a static status label ("Step 1/4: Transcribing speech with Whisper AI (running on CPU)...") for up to 20 minutes with zero feedback.

Meanwhile, WebinarAI already has Google Gemini API integrated (`google-genai` SDK and active `GEMINI_API_KEY`), which is capable of processing multi-minute audio streams and returning full, highly accurate transcripts in approximately 5 to 15 seconds. Implementing an accelerated hybrid transcription engine with real-time stage progress reporting will reduce video processing time from 15-20 minutes to under 30 seconds while eliminating perceived pipeline stalls.

## What Changes

- **Gemini Audio Speech-to-Text Fast-Path**: Introduce direct audio transcription via Google Gemini Multimodal Audio API (`google-genai`), generating structured verbatim transcripts in seconds for uploaded videos and direct video links.
- **Intelligent Hybrid Transcription Strategy**: Implement an automatic fallback dispatcher in `transcription_service`:
  - Primary: High-speed Google Gemini audio transcription when `GEMINI_API_KEY` is configured.
  - Fallback: Local Whisper transcription when offline, in test mode, or if Gemini API quota/network errors occur.
- **Optimized Local Whisper Fallback**: Optimize local Whisper CPU execution with configurable lightweight models (`tiny`/`base`), greedy search parameters, and thread allocation.
- **Granular Real-Time Stage Progress Updates**: Emit continuous sub-step progress updates to `ProcessingJob` and the database during the transcription phase (e.g., "Extracting audio track...", "Transcribing audio via Gemini AI...", or "Transcribing chunk X of Y via Whisper CPU (Z%)..."), preventing the dashboard from appearing frozen at 25%.
- **Efficient Audio Extraction**: Enhance `audio_service` to extract compact, Whisper/Gemini-optimized audio streams, minimizing disk I/O and payload overhead.

## Capabilities

### New Capabilities
- `media-transcription`: High-performance webinar audio and video transcription supporting Gemini AI multimodal audio fast-path, local Whisper fallback, and granular stage progress tracking.

### Modified Capabilities
<!-- None: No existing specs exist in openspec/specs/. -->

## Impact

- **Affected Services**:
  - `app/services/transcription_service.py`: Add Gemini audio transcription integration, hybrid fallback dispatcher, and progress callback hooks.
  - `app/services/audio_service.py`: Optimize audio extraction format, duration handling, and temporary file lifecycle.
  - `app/services/pipeline_service.py`: Integrate granular progress reporting into the background pipeline thread for transcription milestones.
- **Affected Routes & UI**:
  - `app/routes/dashboard_routes.py`: Expose granular transcription sub-stage messages and dynamic progress percentages in `/api/jobs/<job_id>/status`.
  - `app/static/js/dashboard.js`: Render live transcription sub-step labels in the active jobs table and progress bar.
- **Dependencies & Environment**:
  - Uses existing `google-genai` SDK and `openai-whisper`. No mandatory new external packages.
- **Tests**:
  - Add test coverage for Gemini audio transcription, hybrid fallback on error, and progress callback invocation.

