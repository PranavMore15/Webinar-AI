# Tasks

## 1. Gemini Speech-to-Text Transcription Service

- [x] 1.1 Implement `transcribe_audio_with_gemini(audio_path, model_name=None)` in `app/services/transcription_service.py` using `google-genai` File API and verify it extracts full transcripts with punctuation and cleans up remote Google Cloud files via `client.files.delete()`.
- [x] 1.2 Implement prompt instructions and text extraction parser in `gemini_service.py` / `transcription_service.py` tailored for verbatim webinar transcripts, and verify parser handles raw text and JSON-wrapped transcripts.
- [x] 1.3 Add unit tests in `tests/test_media_audio_processing.py` mocking Gemini audio upload and response to verify successful transcript parsing and remote file deletion.

## 2. Hybrid Transcription Engine & Fallback Mechanism

- [x] 2.1 Implement `transcribe_audio_hybrid(audio_path, progress_callback=None)` in `app/services/transcription_service.py` that prioritizes Gemini audio transcription when `GEMINI_API_KEY` is present and automatically falls back to local Whisper upon API error or offline mode.
- [x] 2.2 Wire progress callback notifications into `transcribe_audio_chunks` in `transcription_service.py` to emit live progress updates (e.g., chunk X of Y, percentage) during CPU Whisper inference.
- [x] 2.3 Add unit tests in `tests/test_media_audio_processing.py` verifying seamless fallback from Gemini API error to local Whisper without raising fatal exceptions.

## 3. Audio Extraction Optimization & Lifecycle

- [x] 3.1 Optimize `extract_audio_from_video` in `app/services/audio_service.py` to extract 16kHz mono audio efficiently and report audio extraction duration and byte size.
- [x] 3.2 Implement reliable detection and immediate failure reporting for MP4 files lacking an audio stream, verifying tests catch empty audio streams.
- [x] 3.3 Ensure robust deletion of intermediate audio files and chunk files in `finally` blocks in `audio_service.py` and `transcript_service.py`.

## 4. Pipeline Orchestration & Real-Time Job Status Updates

- [x] 4.1 Update `process_webinar_to_transcript` in `app/services/transcript_service.py` to accept an optional `progress_callback` and route video/audio jobs through `transcribe_audio_hybrid`.
- [x] 4.2 Update `run_job_pipeline` in `app/services/pipeline_service.py` to pass a database-backed progress callback that updates `job.error_message` with detailed status descriptions (e.g., "Extracting audio track...", "Transcribing speech via Gemini AI...", "Whisper CPU: Chunk 1/2...") and persists active progress.
- [x] 4.3 Update `/api/jobs/<job_id>/status` in `app/routes/dashboard_routes.py` to return the granular transcription status and dynamic progress percentage in the JSON payload.

## 5. Dashboard UI Live Progress Feedback

- [x] 5.1 Update active job polling logic in `app/static/js/dashboard.js` to render the detailed transcribing sub-step message and smooth progress bar transitions during the transcription stage.
- [x] 5.2 Verify in browser or via route tests that `/api/jobs/<job_id>/status` reflects changing sub-stage labels without freezing at static 25%.

## 6. End-to-End Pipeline Verification

- [x] 6.1 Run test suite (`pytest tests/test_media_audio_processing.py` and `pytest tests/test_pipeline_and_status.py`) and verify all tests pass without errors.
- [x] 6.2 Test manual video upload and direct video link processing flow end-to-end to confirm transcription completes in seconds via Gemini and status updates smoothly.

