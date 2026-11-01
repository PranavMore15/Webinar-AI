# Spec Delta

## Purpose

Provides authorized automated ingestion of webinar video and audio from direct URLs, YouTube, Google Drive, and local computer selections, enforcing strict security boundaries and feeding valid recordings into the summarization pipeline.

## ADDED Requirements

### Requirement: Multi-Source Dashboard Selection
The system SHALL present an intuitive "Webinar Content Source" selector supporting direct media URLs, YouTube links, Google Drive links, local computer files, local computer folders, and manual uploads while preserving existing manual options.

#### Scenario: User chooses direct media link input
- **WHEN** the user selects the Direct Media Link option on the dashboard
- **THEN** the system displays a URL input field configured for HTTP/HTTPS audio/video sources and hides unrelated source panels

#### Scenario: Existing manual upload remains accessible
- **WHEN** the user selects the Manual Upload option
- **THEN** the system presents the existing MP4 video, TXT transcript, and VTT transcript upload controls

### Requirement: Source Accessibility Pre-Flight Inspection
The system SHALL provide an explicit "Check Accessibility" action that validates source reachability, MIME type, file size limits, and authorization constraints without initiating a full download or processing job.

#### Scenario: Pre-flight check on valid public video URL
- **WHEN** the user submits a reachable direct MP4 URL for accessibility inspection
- **THEN** the system verifies HEAD/GET headers, reports "Retrieval Supported", and displays detected MIME type and content length

#### Scenario: Pre-flight check on inaccessible or private link
- **WHEN** the user submits a URL that returns HTTP 401, 403, or 404
- **THEN** the system reports the specific accessibility status ("Authentication Required" or "Source Unavailable") with recommended next steps

### Requirement: Safe Direct Media URL Retrieval with SSRF Protection
The system SHALL retrieve remote media files over HTTP/HTTPS while strictly enforcing Server-Side Request Forgery (SSRF) defenses, redirect safety, port restrictions, streaming size limits, and binary container verification.

#### Scenario: Block loopback and internal network addresses
- **WHEN** a user provides a URL resolving to localhost, 127.0.0.1, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, or cloud metadata endpoints
- **THEN** the system rejects the request immediately with an "Invalid Destination" error without initiating a remote connection

#### Scenario: Streaming size limit enforcement
- **WHEN** a remote media download exceeds the configured maximum allowed file size during streaming
- **THEN** the system terminates the connection, deletes any partial temporary file, and marks the retrieval status as "File Too Large"

### Requirement: Google Drive Official API Retrieval and OAuth Authorization
The system SHALL authenticate users via official Google OAuth 2.0 with minimum required scopes and download permitted media files through the official Google Drive API.

#### Scenario: Authorized file retrieval via Google Drive
- **WHEN** an authenticated user provides a valid Google Drive file link for which access has been granted
- **THEN** the system inspects file metadata via the Google Drive API, downloads the file stream safely, and saves it to local storage

#### Scenario: Unauthenticated or access denied file
- **WHEN** a user provides a private Google Drive link without having completed OAuth authorization
- **THEN** the system displays "Authentication Required" and prompts the user to initiate the official Google account authorization flow

### Requirement: YouTube Compliance and Caption Inspection
The system SHALL validate YouTube URLs, inspect metadata and caption availability via official API patterns, and strictly reject unauthorized video downloading or scraping tools.

#### Scenario: Captions available for public educational video
- **WHEN** a valid YouTube URL with official transcript/caption tracks is provided
- **THEN** the system retrieves the official caption text and routes it to the transcript processing pipeline without downloading video media

#### Scenario: Automated video retrieval restricted
- **WHEN** a YouTube URL has no permitted caption track or prohibits automated downloading
- **THEN** the system reports "Download Restricted: Automated media retrieval is not permitted" and offers the user manual upload options

### Requirement: Browser-Supported Local File and Folder Selection
The system SHALL support selecting local video/audio files or folders using standard browser selection dialogs, displaying discovered media files and transferring only the explicitly selected recording.

#### Scenario: Folder selection and recording choice
- **WHEN** a user selects a local folder containing multiple files via the browser folder picker
- **THEN** the system lists only supported audio and video files from the folder and waits for explicit user selection before uploading

### Requirement: Pipeline Integration and Processing Handoff
The system SHALL verify the integrity of retrieved media files and seamlessly pass valid recordings to audio extraction, Whisper transcription, Gemini summarization, ReportLab PDF, and SMTP distribution.

#### Scenario: Direct MP4 handoff to processing pipeline
- **WHEN** a direct MP4 file is successfully retrieved and verified
- **THEN** the system associates the file path with a ProcessingJob record, extracts audio via FFmpeg, and proceeds through AI summarization

#### Scenario: Audio-only file bypasses unnecessary extraction
- **WHEN** an audio file (e.g. MP3, WAV) is retrieved
- **THEN** the system bypasses video audio extraction and routes the audio directly to Whisper transcription

### Requirement: Retrieval Failure Isolation and Delivery Safeguards
The system SHALL ensure that any retrieval failure immediately halts downstream processing and strictly prevents summary email dispatch.

#### Scenario: Retrieval failure prevents email delivery
- **WHEN** a media retrieval operation fails due to network timeout or access rejection
- **THEN** the job overall status is set to "failed" with an explanatory message, and zero emails are sent to registered recipients

### Requirement: Idempotency and Selective Retry
The system SHALL prevent duplicate retrieval attempts and support retrying failed stages without re-downloading previously verified media.

#### Scenario: Browser refresh does not duplicate job
- **WHEN** a user refreshes the dashboard while a retrieval job is active
- **THEN** the system displays the current in-flight job progress without creating a duplicate job or initiating duplicate download requests

