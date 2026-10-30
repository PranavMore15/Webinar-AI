# Design: Gemini AI Summarization Architecture

## Context

WebinarAI has completed Prompts 1 through 4:
- Ingestion of MP4 videos and TXT/VTT transcripts.
- Audio extraction (FFmpeg) and Whisper speech-to-text transcription for MP4 files.
- Robust transcript cleaning, decoding, and normalization via `transcript_service.py`.
- MySQL persistence for `ProcessingJob` (`summary_status` field already present) and `JobRecipient`.
- Strict user vs. admin role separation and session management.

This design establishes the technical architecture for Prompt 5: AI-driven summarization using the official Google Gen AI Python SDK (`google-genai`) with Gemini as the sole active provider.

## Goals / Non-Goals

**Goals:**
- Implement a dedicated service module (`app/services/gemini_service.py`) encapsulating client instantiation, prompt generation, API calls, and retry logic.
- Enforce strict JSON schema validation for structured outputs (title, overview, key points, takeaways, action items, terminology, conclusion).
- Support long-transcript processing through intelligent text chunking and synthesis.
- Persist structured summaries as JSON documents in `storage/summaries/` keyed by job ID and update `ProcessingJob.summary_status`.
- Provide an integrated pipeline function that accepts either an MP4 job or a TXT/VTT job, coordinates transcript retrieval/cleaning, invokes Gemini, and saves results.
- Implement comprehensive automated test coverage with 100% mocked Gemini responses (no live external API calls during testing).

**Non-Goals:**
- PDF generation using ReportLab (scheduled for Prompt 6).
- SMTP delivery to student recipient lists (scheduled for Prompt 7).
- Adding background task workers (Celery, Redis) or message queues.
- Altering existing MySQL table schemas destructively or resetting the database.
- Any use of or coexistence with Mistral API.

## Decisions

### Decision 1: Use Official `google-genai` Python SDK
- **Choice**: Use the modern `google-genai` SDK (`from google import genai`) with `client = genai.Client(api_key=...)`.
- **Rationale**: This is Google's current, officially supported unified SDK for Gemini API models.
- **Alternatives Considered**: 
  - Legacy `google-generativeai`: Deprecated in favor of the new unified SDK.
  - Raw `requests`/HTTP calls: Lacks built-in serialization, typed error handling, and future model compatibility.

### Decision 2: Model Configuration via `GEMINI_MODEL`
- **Choice**: Read `GEMINI_MODEL` from environment, defaulting to `gemini-2.5-flash`.
- **Rationale**: `gemini-2.5-flash` offers state-of-the-art summarization quality, low latency, generous token rate limits, and a large context window suitable for long lecture transcripts.
- **Alternatives Considered**:
  - `gemini-1.5-pro`: Slower and more prone to rate limits for automated batch processing.

### Decision 3: Structured Schema Output via JSON Mode & Validation
- **Choice**: Request JSON output mode (`response_mime_type="application/json"`) with an explicit schema contract. Validate parsed JSON on the server using a Python validator before accepting it.
- **Rationale**: Guarantees deterministic structured attributes:
  - `title`: string
  - `overview`: string
  - `key_points`: list of strings
  - `takeaways`: list of strings
  - `action_items`: list of strings (empty if none supported by transcript)
  - `terminology`: list of objects (`{"term": "...", "definition": "..."}`)
  - `conclusion`: string
- **Alternatives Considered**: Plain Markdown text generation — rejected because downstream ReportLab PDF generator (Prompt 6) requires structured data sections.

### Decision 4: Hierarchical Chunking for Long Transcripts
- **Choice**: Set a configurable chunk threshold (e.g. 40,000 characters ~ 8,000 words). If transcript length is below threshold, perform single-pass summarization. If above threshold, segment along natural sentence/paragraph boundaries, summarize each chunk, and pass the concatenated intermediate summaries to a final synthesis prompt.
- **Rationale**: Ensures that long multi-hour webinars retain granular technical points without hitting single-turn output truncation or attention fading.

### Decision 5: File-Backed Persistence in `storage/summaries/`
- **Choice**: Store the complete validated summary JSON file in `storage/summaries/<job_id>_summary.json`. Update `ProcessingJob.summary_status` to `'completed'` (or `'failed'`) in MySQL.
- **Rationale**: Preserves the existing MySQL table structure without requiring risky table migrations or column additions, matching the design of `storage/uploads/` and `storage/audio/`.

### Decision 6: Complete Mocking Strategy for Automated Tests
- **Choice**: Patch `genai.Client` and its `models.generate_content` in `tests/test_gemini_summarization.py`.
- **Rationale**: Guarantees fast, deterministic, offline unit tests without leaking API keys or requiring paid quota.

## Risks / Trade-offs

- **[Risk: Rate Limiting / 429 Resource Exhausted]** → Implement bounded exponential backoff (up to 3 retries with jitter) inside `gemini_service.py`. If persistent, mark job `summary_status = 'failed'` and record clear diagnostic message in `ProcessingJob.error_message`.
- **[Risk: Hallucination / Fact Fabrication]** → Include explicit system constraints forbidding invention of speakers, technical claims, or unsourced action items.
- **[Risk: Accidental Credential Leakage]** → `GEMINI_API_KEY` is loaded solely in backend configuration, never logged, never exposed to client-side templates or JSON responses.
- **[Risk: Recipient Privacy Violation]** → The summarization service API accepts only transcript text; recipient emails and CSV records are strictly excluded from all AI payloads.

## Migration & Provider Verification

1. Inspect dependencies: confirm `mistralai` is not installed or referenced.
2. Add `google-genai` to `requirements.txt`.
3. Add `GEMINI_API_KEY` and `GEMINI_MODEL` to `app/config.py` and `.env.example`.
4. Ensure `storage/summaries/` directory is created on application startup.
