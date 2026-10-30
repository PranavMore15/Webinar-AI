# Proposal: Gemini AI Summarization for WebinarAI

## Why

WebinarAI currently extracts or parses spoken transcripts from MP4 video or TXT/VTT uploads, but lacks automated, high-quality technical summarization to produce digestible student learning materials. By integrating Google's Gemini API via the official `google-genai` Python SDK, WebinarAI will automatically generate structured, factual educational summaries from transcripts while preventing hallucination, managing long transcripts, and establishing a single active AI provider.

## What Changes

- **Single Active AI Provider (Google Gemini)**: Adopt Google Gemini API through the official `google-genai` Python SDK as the dedicated AI summarization engine. Remove or prevent any conflicting Mistral configuration or dependencies.
- **Structured Educational Summarization**: Prompt and validate structured model output containing webinar title, overview, key points, important takeaways, action items (where supported by transcript), important terminology, and conclusion.
- **Long Transcript Handling**: Support long transcript inputs with context-aware chunking or recursive hierarchical summarization that preserves technical concepts without truncation or hallucination.
- **Robust Error Handling**: Handle missing credentials (`GEMINI_API_KEY`), API network errors, rate limits (HTTP 429), timeouts, empty transcripts, and malformed JSON responses with clean error diagnostics.
- **Dedicated Service Layer**: Encapsulate all Gemini interactions in a dedicated service module (`app/services/gemini_service.py` / `summarization_service.py`), ensuring API keys and recipient personal information are never exposed to frontend code, logs, or external API payloads.
- **Configuration & Environment**: Add `GEMINI_API_KEY` and configurable `GEMINI_MODEL` (e.g. `gemini-2.5-flash`) to `app/config.py` and `.env.example` (placeholders only; never overwriting `.env`). Add `google-genai` to `requirements.txt`.
- **Database & Pipeline Integration**: Connect summarization to existing Prompt 3/4 pipelines (MP4 → Whisper audio extraction → transcript → Gemini summary; TXT/VTT → transcript cleaning → Gemini summary), updating job lifecycle statuses (`summary_status` and persisted summary files in `storage/summaries/`).
- **Comprehensive Mocked Test Suite**: Implement extensive unit and integration tests mocking Gemini responses without external network dependencies, verifying successful parsing, validation, chunking, missing credentials, API failures, and pipeline flow.

## Capabilities

### New Capabilities

- `summarization`: AI-powered webinar summarization service that accepts cleaned transcripts from MP4/Whisper or TXT/VTT sources, sends them to Google Gemini via the `google-genai` SDK, and outputs validated structured JSON summaries adhering to educational schema requirements.

### Modified Capabilities

*(None. No previous capability specs exist in the repository.)*

## Impact

- **Dependencies**: Add `google-genai` to `requirements.txt` and `.venv`.
- **Configuration**: Extend `app/config.py` with `GEMINI_API_KEY` and `GEMINI_MODEL`. Update `.env.example`.
- **Services**: Introduce `app/services/gemini_service.py` (and pipeline helper in `app/services/summary_service.py` or similar).
- **Storage**: Maintain summary artifacts in `storage/summaries/` associated with `processing_jobs.id`.
- **Database**: Update `processing_jobs.summary_status` and error handling without schema recreation or dropping data.
- **Security**: Strict isolation of student/recipient data and API keys away from Gemini prompt payloads and logs.
- **Tests**: Add comprehensive automated test suite in `tests/test_gemini_summarization.py` mocking all API interactions.
