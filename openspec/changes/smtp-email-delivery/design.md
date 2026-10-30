# Technical Design: Secure SMTP Email Delivery of PDF Summaries

## Context

WebinarAI currently compiles AI-generated webinar summaries into multi-page ReportLab PDFs stored safely under `storage/pdfs/` and referenced by `ProcessingJob.pdf_path`. Recipient lists uploaded through CSV or entered manually are parsed, validated, deduplicated, and stored in MySQL as `JobRecipient` rows linked to a `ProcessingJob`.

The application now requires an email distribution service to dispatch the generated PDF summaries to validated student email addresses using SMTP. Per project constraints:
- Use standard Python `smtplib` and `email` modules without adding Celery, Redis, Docker, or paid email APIs.
- Respect strict role separation: regular users own and trigger delivery for their jobs; system administrators cannot access the user workspace.
- Provide user-controlled execution with pre-flight validation, failure resilience, concurrency protection, and detailed delivery reporting.

## Goals / Non-Goals

**Goals:**
- Provide a robust, configurable SMTP service (`app/services/email_service.py`) supporting standard ports, STARTTLS, and SSL.
- Create professional, personalized email notifications with safe MIME attachments of the ReportLab PDF summary.
- Enforce strict recipient privacy via isolated, individual message dispatch.
- Persist per-recipient delivery outcomes (`JobRecipient.delivery_status`, `attempt_count`, `sent_at`, `last_error`) and overall job metrics.
- Prevent duplicate deliveries and race conditions via server-side atomic state transitions.
- Implement an idempotent retry mechanism for failed or unattempted recipients.
- Integrate user controls and delivery reporting into the Bootstrap 5 dashboard.
- Provide comprehensive unit and integration tests mocking SMTP.

**Non-Goals:**
- Introducing external queuing infrastructure (Celery, Redis) or containerization (Docker).
- Implementing email delivery confirmation beyond SMTP server acceptance (inbox tracking is outside standard SMTP scope).
- Integrating proprietary email provider APIs (SendGrid, Mailgun, AWS SES) or OAuth2 authorization flows.
- Bulk `To`/`Cc`/`Bcc` batching (each recipient receives an individual message for privacy and per-recipient delivery verification).

## Decisions

### 1. SMTP Implementation via Standard Library (`smtplib` + `email.message.EmailMessage`)
- **Choice**: Use Python's built-in `smtplib.SMTP`, `smtplib.SMTP_SSL`, and `email.message.EmailMessage`.
- **Rationale**: Built into Python 3, zero external dependencies, robust TLS/SSL support, and straightforward MIME multipart construction.
- **Alternatives Considered**:
  - `Flask-Mail`: Abandoned and unmaintained for modern Flask versions.
  - `Flask-Mailman`: Adds third-party dependency with unnecessary abstraction.

### 2. Configuration & Validation Architecture
- **Choice**: Load settings from environment variables in `app/config.py`:
  - `SMTP_HOST` (default: `""` or `smtp.gmail.com`)
  - `SMTP_PORT` (default: `587`)
  - `SMTP_USERNAME` (default: `""`)
  - `SMTP_PASSWORD` (default: `""`)
  - `SMTP_USE_TLS` (default: `True`)
  - `SMTP_USE_SSL` (default: `False`)
  - `SMTP_FROM_EMAIL` (default: `""`)
  - `SMTP_FROM_NAME` (default: `"WebinarAI Platform"`)
  - `SMTP_TIMEOUT` (default: `15` seconds)
- **Validation**:
  - Require `SMTP_HOST`, `SMTP_PORT`, and `SMTP_FROM_EMAIL`.
  - Disallow conflicting `SMTP_USE_TLS=True` AND `SMTP_USE_SSL=True`.
  - Validate connection before dispatching batch with graceful, sanitized error reporting.

### 3. Message Formatting & PDF Attachment Resolution
- **Choice**: Construct `EmailMessage` with both text and HTML alternatives:
  - Subject: `Webinar Summary: <Webinar Title>` (fallback: `Webinar Summary: Notes & Key Takeaways`)
  - Body: Personalized greeting (`Dear <Student Name>,` or `Dear Student,`), description of attached summary brief, and WebinarAI signature.
  - Attachment: Read binary bytes from `pdf_service.resolve_pdf_full_path(job.pdf_path)`. Set `maintype='application'`, `subtype='pdf'`, filename=`WebinarAI_Summary_Job_<job_id>.pdf`.
- **Privacy Enforcement**: Each message has exactly one recipient in the `To` header. Loop through recipients individually.

### 4. Dispatch Lifecycle & Concurrency Protection
- **Choice**: Server-side state transitions on `ProcessingJob` and `JobRecipient`:
  - State check: Job must have `pdf_status == 'completed'`, verified PDF file on disk, and `email_status != 'sending'`.
  - Set `job.email_status = 'sending'`, commit to database.
  - Iterate through eligible recipients (`delivery_status in ('pending', 'failed')`):
    - Connect to SMTP server (reuse connection across batch or reconnect on error).
    - Send individual message.
    - On success: `recipient.delivery_status = 'sent'`, `recipient.sent_at = utc_now()`, increment `job.successful_emails`.
    - On failure: `recipient.delivery_status = 'failed'`, `recipient.attempt_count += 1`, `recipient.last_error = sanitized_error`, increment `job.failed_emails`.
    - Commit per-recipient updates to persist progress even if batch is aborted.
  - Finalize:
    - If `failed_emails == 0`: `job.email_status = 'completed'`, `job.overall_status = 'completed'`
    - If `failed_emails > 0` and `successful_emails > 0`: `job.email_status = 'partially_sent'`, `job.overall_status = 'completed_with_errors'`
    - If all failed: `job.email_status = 'failed'`, `job.overall_status = 'failed'`
    - Record `job.completed_at = utc_now()` and commit.

### 5. Retry Handling
- **Choice**: Dedicated retry action `/api/jobs/<job_id>/retry-emails` query filters only `delivery_status != 'sent'`.
- **Rationale**: Prevents accidental spamming of students who already received the document, while providing instant recovery for transient network or mailbox failures.

### 6. User Interface & Delivery Reporting
- **Choice**: Add "Send PDF Summaries" action button in the Dashboard table and job details view. Clicking opens a pre-flight confirmation modal detailing:
  - Webinar title & input source.
  - Verified PDF readiness.
  - Count of pending recipients.
- After sending, a Delivery Report modal displays:
  - Summary badges: Total, Accepted, Failed, Skipped.
  - Table of recipients with timestamp and status badge.
  - "Retry Failed Recipients" button if any recipients failed.

## Risks / Trade-offs

- **[Risk: Slow synchronous loop for large recipient lists]** → *Mitigation*: Set tight 10-15s socket timeouts. Per-recipient database commits ensure progress is never lost. Re-use active SMTP connection for consecutive messages within the batch.
- **[Risk: Sensitive credentials leak in error messages or logs]** → *Mitigation*: Mask all credentials; wrap SMTP exceptions with generic sanitized messages (e.g. "SMTP Authentication Failed" rather than dumping credentials or raw traceback).
- **[Risk: Stale or forged attachment path]** → *Mitigation*: Resolve path exclusively through `pdf_service.resolve_pdf_full_path()`; reject any path traversal or missing file attempts.
- **[Risk: Double submission race condition]** → *Mitigation*: Check `job.email_status == 'sending'` inside an active transaction before beginning transmission.

## Migration Plan

1. Schema already supports all required fields in `processing_jobs` and `job_recipients` from Prompt 2 (no destructive schema changes or manual migrations needed).
2. Update `.env.example` with documented SMTP settings.
3. Add `email_service.py` and register endpoints in `dashboard_routes.py`.
4. Update `dashboard.html` with Send and Report UI components.
5. Verify complete automated test suite in offline mode (using mock SMTP).
