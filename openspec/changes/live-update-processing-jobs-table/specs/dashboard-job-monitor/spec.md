# Spec Delta

## Purpose

Enables real-time tracking and dynamic rendering of registered processing jobs on the dashboard homepage table across all processing milestones, ensuring visibility persists even when the submission modal is closed.

## ADDED Requirements

### Requirement: Immediate table row insertion on job creation
The dashboard interface SHALL immediately render and prepend a job row in the Registered Processing Jobs table when a webinar processing job is initiated, without requiring a full page refresh.

#### Scenario: New job submitted while jobs already exist
- **WHEN** the user starts a processing job from the submission modal and the server responds with job creation success
- **THEN** the system immediately prepends a new table row displaying the job ID, media filename, recipient count, created timestamp, and an active stage indicator to the Registered Processing Jobs table and increments the total job count badge

#### Scenario: New job submitted when no prior jobs exist
- **WHEN** a processing job is initiated while the dashboard displays the empty state container
- **THEN** the system hides the empty state container and reveals the Registered Processing Jobs table containing the newly created job row

### Requirement: Persistent tracking during modal closure
The system SHALL continue updating job progress and stage status badges in the Registered Processing Jobs table when the submission modal is closed or dismissed while processing remains active.

#### Scenario: User closes modal during processing
- **WHEN** the user closes or dismisses the processing modal while video processing is in-progress
- **THEN** the job remains visible in the homepage table displaying its live stage status with animated indicators

#### Scenario: Stage transitions while modal is closed
- **WHEN** background processing advances through transcription, summarization, PDF generation, or email delivery while the submission modal is closed
- **THEN** the job row in the dashboard table automatically updates its status badge, PDF download links, email delivery actions, or error badges

### Requirement: Active statuses endpoint payload completeness
The active statuses API endpoint SHALL provide all metadata necessary to construct and dynamically synchronize complete job rows on the dashboard.

#### Scenario: Polling active job statuses
- **WHEN** an authenticated client requests `/api/jobs/active-statuses`
- **THEN** the server returns each job's identifier, media filename, input type, recipient total, creation timestamp, and stage statuses (`transcript_status`, `summary_status`, `pdf_status`, `email_status`, `overall_status`)

#### Scenario: Reconciliation of unrendered jobs
- **WHEN** client polling receives an active job that is not present in the DOM table
- **THEN** the client dynamically creates and prepends the corresponding job row into the table

### Requirement: Initial ready state active presentation
The system SHALL display newly created jobs in the `ready` or initial queued state with an active in-progress visual indicator on the dashboard.

#### Scenario: User reloads dashboard immediately after submission
- **WHEN** the dashboard page is refreshed while a job is in the initial `ready` status
- **THEN** the Registered Processing Jobs table renders the job status with an animated spinner and active processing styling

