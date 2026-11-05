# Spec Delta

## Purpose

Enables high-performance speech-to-text transcription for webinar video and audio media, providing sub-minute cloud AI transcription, offline local Whisper fallback, and granular real-time stage progress reporting.

## ADDED Requirements

### Requirement: Fast-Path Audio Transcription via Gemini AI
The system SHALL transcribe extracted audio from uploaded videos or direct video links using Google Gemini multimodal audio processing when a Gemini API key is configured.

#### Scenario: Successful fast transcription of webinar video
- **WHEN** a processing job with video or audio input executes and a valid Gemini API key is configured
- **THEN** the system SHALL send the audio to the Gemini API, obtain the complete transcript, clean and normalize the text, and complete the transcription stage without running local CPU Whisper inference.

#### Scenario: Gemini API error triggers automated fallback
- **WHEN** the Gemini API transcription call encounters a network failure, rate limit, or service error
- **THEN** the system SHALL log the error, record an informative transitional progress update, and automatically fall back to local Whisper speech-to-text processing without failing the job.

### Requirement: Local Whisper Speech-to-Text Fallback
The system SHALL transcribe audio using the local OpenAI Whisper model whenever Gemini AI is unconfigured, disabled, or unavailable, ensuring offline resilience.

#### Scenario: Offline or unconfigured Gemini fallback execution
- **WHEN** a processing job executes and no Gemini API key is configured
- **THEN** the system SHALL transcribe the extracted audio chunks using the configured local Whisper model on the host device.

#### Scenario: Lightweight greedy CPU inference parameters
- **WHEN** the local Whisper engine transcribes audio on a CPU device
- **THEN** the system SHALL apply greedy search decoding (`beam_size=1`, `best_of=1`, `temperature=0.0`) and optimal CPU thread limits to minimize inference latency.

### Requirement: Granular Real-Time Stage Progress Updates
The system SHALL record and expose granular sub-stage progress labels and dynamic completion percentages throughout audio extraction and transcription.

#### Scenario: Audio extraction progress notification
- **WHEN** the pipeline begins extracting audio from a webinar video
- **THEN** the system SHALL update the job status with an audio extraction milestone message and an active progress indicator before transcription begins.

#### Scenario: Live transcription progress updates
- **WHEN** speech-to-text processing is actively running (whether via Gemini API or multi-chunk Whisper inference)
- **THEN** the system SHALL update the job status to reflect active sub-stage status (such as cloud transcription progress or chunk X of Y progress) so the user interface does not appear frozen.

### Requirement: Audio Track Extraction and Optimization
The system SHALL extract audio from video media using FFmpeg into a 16kHz single-channel mono audio format optimized for both cloud upload efficiency and local Whisper execution.

#### Scenario: Standard MP4 video audio extraction
- **WHEN** a valid MP4 video is provided to the pipeline
- **THEN** the system SHALL execute FFmpeg to produce a mono 16kHz audio track, calculate its duration, and clean up temporary audio files upon completion.

#### Scenario: Detection of video files without audio
- **WHEN** an uploaded video contains no audio stream or results in an empty audio file
- **THEN** the system SHALL halt transcription immediately and mark the job stage as failed with a clear descriptive message indicating that the video contains no audio stream.

