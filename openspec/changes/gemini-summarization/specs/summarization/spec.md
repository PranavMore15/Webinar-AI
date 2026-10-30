# Spec Delta: Gemini Summarization Capability

## Purpose

Provides automated, AI-driven educational summarization of webinar transcripts using Google Gemini API (`google-genai` SDK), producing validated structured summaries while ensuring fault tolerance, long-transcript synthesis, and strict recipient privacy.

## ADDED Requirements

### Requirement: Google Gemini Provider Configuration
The system SHALL use the Google Gemini API via the official `google-genai` Python SDK as the single active AI summarization provider, configured through `GEMINI_API_KEY` and `GEMINI_MODEL` environment variables.

#### Scenario: Valid Gemini configuration
- **WHEN** valid `GEMINI_API_KEY` and `GEMINI_MODEL` are configured and summarization is invoked
- **THEN** the system initializes the Google GenAI client and communicates with the configured Gemini model

#### Scenario: Missing API key configuration
- **WHEN** `GEMINI_API_KEY` is missing or empty when summarization is triggered
- **THEN** the system SHALL reject the request with a descriptive credential error and record the failure on the job without crashing

### Requirement: Validated Structured Educational Summary Schema
The system SHALL require Gemini to output a structured summary adhering to a strict schema containing webinar title, overview, key points, important takeaways, action items (when supported by transcript), important terminology (where relevant), and conclusion.

#### Scenario: Successful structured summary extraction
- **WHEN** a valid transcript is submitted to the summarization service
- **THEN** the system returns a validated structured dictionary containing title, overview, key points, takeaways, action items, terminology, and conclusion

#### Scenario: Malformed or incomplete model response
- **WHEN** the Gemini model returns invalid JSON or output missing required summary sections
- **THEN** the system SHALL detect schema validation failure, record diagnostic details, and fail gracefully without storing corrupted summary data

### Requirement: Processing Pipeline Integration
The system SHALL integrate Gemini summarization into both existing webinar ingestion pipelines: MP4 audio extraction and Whisper transcription, and TXT/VTT transcript parsing and cleaning.

#### Scenario: Video workflow integration
- **WHEN** an MP4 video is transcribed via Whisper and cleaned
- **THEN** the resulting cleaned transcript is routed directly to Gemini summarization and the job's `summary_status` is updated to 'completed'

#### Scenario: Direct transcript workflow integration
- **WHEN** a TXT or VTT file is parsed and cleaned
- **THEN** the cleaned transcript bypasses Whisper and is routed directly to Gemini summarization, updating `summary_status` to 'completed'

### Requirement: Long Transcript Chunking and Synthesis
The system SHALL detect transcripts that exceed configured single-pass character or token thresholds, split content into coherent logical chunks, extract intermediate section summaries, and synthesize a coherent, non-redundant final summary.

#### Scenario: Transcript exceeding chunking threshold
- **WHEN** a transcript exceeds the configured single-chunk size limit
- **THEN** the system splits the transcript into ordered chunks, summarizes each chunk with Gemini, combines intermediate results, and synthesizes the unified final structured summary

### Requirement: API Resilience and Error Handling
The system SHALL handle Gemini API rate limits (HTTP 429 / resource exhausted), network timeouts, server errors, and empty transcripts with bounded exponential backoff retries and clear error recording.

#### Scenario: Rate limit encountered with retry
- **WHEN** Gemini API responds with a 429 rate limit or quota exhaustion error
- **THEN** the system retries with bounded exponential backoff before failing and setting `summary_status` to 'failed' if retries are exhausted

#### Scenario: Empty or insufficient transcript
- **WHEN** a transcript is empty or contains fewer words than required for meaningful summarization
- **THEN** the system SHALL reject the summarization attempt immediately without invoking the external Gemini API

### Requirement: Data Privacy and Secret Protection
The system SHALL never transmit student recipient emails, names, or CSV metadata to the Gemini API, and SHALL never log, display in UI, or expose the `GEMINI_API_KEY` in error messages or client responses.

#### Scenario: Recipient isolation in API payload
- **WHEN** a job containing associated student email recipients is processed for summarization
- **THEN** the prompt payload sent to Gemini contains exclusively the cleaned transcript text and system instructions, with zero recipient information

#### Scenario: API key protection in error logs
- **WHEN** a Gemini API call encounters an exception or authentication error
- **THEN** the system logs and returns sanitized error messages that do not reveal the raw API key
