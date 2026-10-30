# Spec Delta: Email Delivery

## Purpose

Provides secure SMTP dispatch of generated webinar summary PDFs to validated student recipients, tracking per-recipient delivery outcomes and preventing duplicate transmissions.

## ADDED Requirements

### Requirement: Configurable SMTP Transport
The system SHALL support configurable SMTP server parameters via environment variables (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `SMTP_USE_SSL`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`) and validate connection parameters with explicit socket timeouts before transmission.

#### Scenario: Valid TLS or SSL configuration connects successfully
- **WHEN** valid SMTP configuration is provided with STARTTLS (port 587) or SSL (port 465)
- **THEN** the system successfully authenticates and establishes a secure SMTP session within configured socket timeouts

#### Scenario: Missing or invalid credentials return actionable configuration error
- **WHEN** required SMTP host, port, or authentication credentials are missing or authentication fails
- **THEN** the system logs a sanitized error without exposing credentials and returns a clear configuration error to the user

#### Scenario: Incompatible TLS and SSL flags rejected
- **WHEN** both `SMTP_USE_TLS` and `SMTP_USE_SSL` are enabled simultaneously
- **THEN** the system rejects the configuration with a validation error indicating conflicting security settings

### Requirement: Professional Email Content and PDF Attachment
The system SHALL generate individual multipart MIME email messages containing a professional study brief notification and the verified ReportLab PDF summary as an attachment.

#### Scenario: Personalized greeting and safe PDF attachment
- **WHEN** an email is prepared for a recipient whose name was provided
- **THEN** the message body greets the student by name, includes the webinar title, and attaches the summary PDF using a safe filename and MIME type `application/pdf`

#### Scenario: Fallback greeting when recipient name is missing
- **WHEN** an email is prepared for a recipient with no name specified
- **THEN** the message body uses a neutral student greeting without displaying placeholder values or null labels

#### Scenario: Non-existent or inaccessible PDF rejects dispatch
- **WHEN** email delivery is initiated for a job whose summary PDF does not exist on disk or fails path traversal verification
- **THEN** dispatch is aborted with an error and no messages are transmitted

### Requirement: Individual Recipient Delivery and Privacy
The system SHALL send separate, isolated email messages to each valid student address, strictly avoiding header aggregation that could expose student email addresses to other recipients.

#### Scenario: Each recipient receives an isolated message
- **WHEN** a job with multiple student recipients is dispatched
- **THEN** each student receives a dedicated message where only their own address appears in the destination header

#### Scenario: One recipient failure does not abort remaining recipients
- **WHEN** transmission to one recipient fails due to a network or recipient rejection error
- **THEN** the system records the failure for that recipient and continues delivering to the remaining valid recipients

### Requirement: Explicit User-Controlled Sending and Pre-Flight Checks
The system SHALL initiate email delivery only upon explicit user confirmation from the dashboard or job details interface, enforcing server-side prerequisite checks.

#### Scenario: Dispatch triggered only on explicit user request
- **WHEN** an authorized user reviews job and recipient previews and explicitly clicks "Send PDF Summaries"
- **THEN** the system initiates the delivery workflow for eligible recipients

#### Scenario: Uploading CSV or media does not trigger sending
- **WHEN** a user uploads a webinar recording, transcript, or recipient CSV
- **THEN** the file is validated and previewed without sending any email

#### Scenario: Pending or unverified PDF rejects sending
- **WHEN** email delivery is requested for a job whose PDF is not yet compiled or marked completed
- **THEN** the request is rejected with a 400 Bad Request explaining that the PDF must be ready first

#### Scenario: Unauthenticated or non-owner user cannot initiate sending
- **WHEN** an unauthenticated client or a user who does not own the processing job requests email dispatch
- **THEN** the request is rejected with 401 Unauthorized or 403 Forbidden

### Requirement: Concurrency Protection and Duplicate Prevention
The system SHALL prevent concurrent duplicate delivery runs for the same job and avoid re-sending to recipients who have already received the summary.

#### Scenario: Concurrent sending requests rejected
- **WHEN** a delivery request is received while the job is already actively sending
- **THEN** the secondary request is rejected with a conflict error indicating a delivery is in progress

#### Scenario: Already sent recipients skipped on re-attempt
- **WHEN** a user triggers delivery or retry on a job where some recipients already have status `sent`
- **THEN** the system skips previously successful recipients and processes only pending or failed recipients

### Requirement: Delivery Status Tracking and Reporting
The system SHALL record per-recipient delivery outcomes in the database and provide a dashboard delivery report distinguishing SMTP server acceptance from delivery failure.

#### Scenario: SMTP server acceptance records timestamp and sent status
- **WHEN** the SMTP server accepts an individual recipient message
- **THEN** the system updates `JobRecipient.delivery_status` to `sent`, records `sent_at` timestamp, and increments `ProcessingJob.successful_emails`

#### Scenario: SMTP failure records sanitized error and failed status
- **WHEN** sending to a recipient fails
- **THEN** the system updates `JobRecipient.delivery_status` to `failed`, increments `attempt_count`, records a sanitized error message, and increments `ProcessingJob.failed_emails`

#### Scenario: User views delivery report with per-recipient status and retry option
- **WHEN** an authorized owner views the job details after delivery
- **THEN** the dashboard displays total counts, per-recipient statuses, and an actionable retry button if failed recipients exist
