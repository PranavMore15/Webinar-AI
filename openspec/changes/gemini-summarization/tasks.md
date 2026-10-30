# Tasks: Gemini AI Summarization Implementation

## 1. Environment, Dependency & Configuration Setup

- [x] 1.1 Add `google-genai` to `requirements.txt` and install in `.venv`, verifying `from google import genai` succeeds
- [x] 1.2 Audit codebase for any Mistral references, imports, or dependencies to ensure zero lingering or conflicting Mistral components exist
- [x] 1.3 Add `GEMINI_API_KEY` and `GEMINI_MODEL` (defaulting to `gemini-2.5-flash`) to `app/config.py` and ensure `storage/summaries/` directory is created on application startup
- [x] 1.4 Update `.env.example` with placeholder entries for `GEMINI_API_KEY` and `GEMINI_MODEL`, verifying `.env` is never overwritten or secrets exposed

## 2. Gemini Summarization Core Service & Schema Validation

- [x] 2.1 Implement structured summary schema definition, data models, and strict output validation helper in `app/services/gemini_service.py`
- [x] 2.2 Implement Gemini API client integration and prompt builder in `app/services/gemini_service.py` enforcing structured JSON generation, system constraints against hallucination, and strict exclusion of student recipient/CSV data
- [x] 2.3 Implement error handling, timeout handling, and bounded exponential backoff for rate limits (HTTP 429 / resource exhausted) in `app/services/gemini_service.py`
- [x] 2.4 Implement long transcript chunking and hierarchical synthesis in `app/services/gemini_service.py` for transcripts exceeding single-pass context thresholds
- [x] 2.5 Create comprehensive unit tests in `tests/test_gemini_summarization.py` covering schema validation, single-pass summarization, long-transcript chunking, missing credentials, API rate limits, timeouts, and malformed responses with mocked Gemini responses

## 3. Pipeline Integration & Persistence

- [x] 3.1 Implement summarization pipeline integration connecting cleaned transcripts from MP4/Whisper audio extraction and TXT/VTT file parsing to `gemini_service.py`
- [x] 3.2 Persist validated structured summary JSON artifacts under `storage/summaries/<job_id>_summary.json` and update `ProcessingJob.summary_status` to `'completed'` or `'failed'` with error messages in the database
- [x] 3.3 Add pipeline integration tests in `tests/test_gemini_summarization.py` verifying both MP4 and TXT/VTT processing paths and transactional database status updates with mocked Gemini responses

## 4. End-to-End Verification & Documentation

- [x] 4.1 Run the complete test suite (`unittest discover -s tests`) to verify all 109 existing tests plus all new Gemini summarization tests pass with 0 failures and 0 errors
- [x] 4.2 Update `PROJECT_STATUS.md` documenting Prompt 5 completion, provider change to Google Gemini API, test counts, and pending approval before Prompt 6
