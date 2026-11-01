# Spec Delta

## Purpose

Provides resilient YouTube video accessibility verification, restricted retrieval handling, and inline transcript fallback ingestion for automated webinar processing.

## ADDED Requirements

### Requirement: Accurate YouTube Pre-Flight Accessibility Inspection
The system SHALL inspect YouTube video URLs during pre-flight accessibility checks to verify whether official caption tracks are retrievable, immediately reporting restricted or missing caption tracks rather than claiming unverified retrieval readiness.

#### Scenario: Public video without accessible caption tracks
- **WHEN** a user requests an accessibility check for a YouTube video that lacks downloadable official caption tracks
- **THEN** the system reports an accessibility status of "Captions Unavailable" or "Download Restricted" with retrieval eligibility set to false and guides the user to provide an accompanying transcript

#### Scenario: Public video with verified accessible captions
- **WHEN** a user requests an accessibility check for a YouTube video that has downloadable official captions available
- **THEN** the system reports "Retrieval Supported" with retrieval eligibility set to true and indicates caption stream ingestion is available

### Requirement: Inline Transcript and Caption Fallback for YouTube Source
The system SHALL allow users to provide an accompanying transcript file or text directly within the YouTube source panel when automated caption download is restricted or unavailable.

#### Scenario: User provides transcript file alongside YouTube URL
- **WHEN** a user enters a YouTube URL and uploads a supporting .vtt or .txt transcript file in the YouTube panel
- **THEN** the system validates the transcript, links it with the YouTube video metadata, and enables job submission without requiring automated video download

#### Scenario: User pastes transcript text alongside YouTube URL
- **WHEN** a user enters a YouTube URL and pastes transcript text into the YouTube fallback transcript field
- **THEN** the system converts the input into a validated transcript file associated with the YouTube source reference

### Requirement: Resilient YouTube Retrieval and Recovery in Job Confirmation
The system SHALL handle caption retrieval failures gracefully during job confirmation, forwarding any user-supplied caption payload and presenting actionable recovery options instead of dead-end errors.

#### Scenario: Job confirmation with user-supplied fallback caption
- **WHEN** a user confirms job processing for a YouTube source accompanied by user-supplied caption content
- **THEN** the system stores the caption transcript in local storage, sets the job input type to transcript, and advances to summarization without downloading video media

#### Scenario: Job confirmation when caption retrieval is restricted
- **WHEN** automated caption retrieval fails during job confirmation and no fallback transcript was supplied
- **THEN** the confirmation modal displays the restriction reason and presents immediate recovery options to upload a transcript or switch to manual upload while preserving validated recipients

