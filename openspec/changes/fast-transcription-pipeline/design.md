# Design

## Context

Webinar processing currently incurs a severe performance bottleneck during manual video uploads and direct video link retrieval. Specifically:
- `audio_service.extract_audio_from_video` extracts audio into uncompressed 16kHz WAV format and slices it into 10-minute (600s) chunks.
- `transcription_service.transcribe_audio_chunks` executes standard PyTorch OpenAI Whisper (`base` checkpoint) sequentially across chunks strictly on the host CPU.
- Standard Whisper on CPU executes at roughly 0.8x to 1.2x real-time speed. Consequently, a 15-20 minute webinar requires 15 to 20 minutes of CPU inference.
- Throughout this execution window, `job.overall_status` is static at `'transcribing'` (25%), giving the user the impression that the background task is hung or stuck.
- The project environment already contains `google-genai` and a verified `GEMINI_API_KEY` in `.env`, which is utilized for summarization in `gemini_service.py`, but has not yet been utilized for audio transcription.

## Goals / Non-Goals

**Goals:**
- Dramatically reduce transcription time from 15-20 minutes to under 25 seconds for video and audio inputs by leveraging Gemini Multimodal Audio transcription.
- Implement an automated hybrid architecture: primary high-speed Gemini STT with seamless fallback to local CPU Whisper if the Gemini API key is absent, offline, or rate-limited.
- Provide real-time granular progress tracking in `ProcessingJob` during audio extraction and transcription milestones so the frontend and database continuously reflect active progress.
- Optimize audio extraction to produce compact, high-quality audio files that minimize upload latency and disk footprint.
- Automatically clean up temporary audio files locally and on Gemini Files storage upon completion or error.

**Non-Goals:**
- Completely removing local Whisper (it is retained as a zero-dependency offline fallback).
- Modifying downstream stages (Gemini structured educational summarization, ReportLab PDF compilation, or SMTP email distribution).
- Modifying YouTube transcript handling (YouTube videos with official captions already use the ~1-second instant subtitle fast-path).

## Decisions

### 1. Gemini Multimodal Audio API for Speech-to-Text
- **Decision**: In `transcription_service.py`, add `transcribe_audio_with_gemini(audio_path: str) -> dict`. For audio files, use `client.files.upload` (or inline bytes for files under 10MB) via `google-genai` and prompt Gemini to produce a complete, verbatim transcript with normalized punctuation and speaker indicators.
- **Rationale**: Gemini 1.5/2.0/Flash processes audio natively up to several hours long with exceptional speed (5-15 seconds) and high transcription accuracy.
- **Alternatives Considered**:
  - *faster-whisper (CTranslate2)*: Improves CPU speed 3x to 4x, but still requires 3-5 minutes on CPU for a 20-minute video.
  - *Third-party speech services (Deepgram/Whisper Cloud)*: Would require new API keys, external accounts, and new SDK dependencies, whereas Gemini is already configured and paid/active.

### 2. Hybrid Transcription Dispatcher with Automatic Fallback
- **Decision**: Introduce `transcribe_audio_hybrid(audio_path: str, progress_callback=None) -> dict` in `transcription_service.py`.
  1. If `GEMINI_API_KEY` is present and not running in offline test mode:
     - Invoke `progress_callback("Transcribing speech with Gemini AI...")`
     - Attempt `transcribe_audio_with_gemini(audio_path)`
     - If successful, clean and normalize transcript and return.
  2. If Gemini API call fails (network timeout, quota limit 429, or invalid key) or `GEMINI_API_KEY` is empty:
     - Log warning and invoke `progress_callback("Gemini unavailable. Switching to local Whisper speech-to-text...")`
     - Chunk audio if needed and run `transcribe_audio_chunks(chunks, progress_callback)`
- **Rationale**: Guarantees fast path for all users with API access while ensuring 100% offline and development reliability when running without network access or during offline test suites.

### 3. Granular Real-Time Stage Progress Tracking
- **Decision**: In `pipeline_service.py`, define a progress callback function that updates `job.error_message` with detailed status messages (e.g., `"Extracting audio track..."`, `"Transcribing speech via Gemini AI..."`, or `"Whisper CPU: transcribing chunk 1 of 2 (50%)..."`) and increments progress percentages dynamically, committing changes to the database at each milestone.
- **Rationale**: Eliminates the frozen 25% UI state. Dashboard users see dynamic stage updates in real time via polling `/api/jobs/<job_id>/status`.

### 4. Audio Extraction Format and Cleanup
- **Decision**: Keep audio extraction in `audio_service.py` at 16kHz mono PCM WAV or 64kbps MP3 for optimal compatibility with both Gemini API and local Whisper. Ensure Gemini File resources are immediately deleted via `client.files.delete(name=uploaded_file.name)` in a `finally` block once the transcript is received.
- **Rationale**: Prevents temporary file accumulation on disk and maintains a clean remote storage state in Google Cloud.

## Risks / Trade-offs

- **[Risk]**: Temporary Gemini Files accumulation in Google Cloud.  
  → **Mitigation**: Wrap Gemini API file uploads in `try...finally` blocks to explicitly call `client.files.delete()` as soon as inference completes or fails.
- **[Risk]**: Gemini API quota limits (429 Too Many Requests) on free tier keys.  
  → **Mitigation**: Automatic graceful catch and fall-through to local Whisper inference, ensuring jobs never fail due to API rate limits.
- **[Risk]**: Whisper CPU inference latency for offline fallback.  
  → **Mitigation**: Fast CPU inference parameters (`beam_size=1`, `best_of=1`, optimal thread count) and live chunk progress reporting so progress is continuously visible.

## Migration Plan

1. Implement `transcribe_audio_with_gemini` and `transcribe_audio_hybrid` in `transcription_service.py`.
2. Enhance `audio_service.py` to ensure robust duration detection and clean temporary audio handling.
3. Update `transcript_service.py` to route audio transcription through the hybrid dispatcher with progress callbacks.
4. Update `pipeline_service.py` to emit live progress milestones during audio extraction and transcription stages.
5. Update `dashboard_routes.py` to expose detailed transcribing status and sub-step messages.
6. Validate all changes with unit and integration tests (mocking Gemini API and Whisper appropriately).

