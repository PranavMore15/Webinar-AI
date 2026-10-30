# Proposal: Secure SMTP Email Delivery of PDF Summaries

## Why

WebinarAI successfully processes webinar recordings/transcripts, generates structured educational summaries with Google Gemini, and compiles publication-quality ReportLab PDFs. However, the application currently lacks an automated knowledge distribution mechanism to deliver these PDF summaries to students. 

Implementing secure, explicit, and audited SMTP email delivery closes the post-webinar pipeline loop, allowing educators to distribute generated PDF briefs directly to validated student email addresses imported via CSV or manual entry.

## What Changes

- **SMTP Configuration & Service Integration**:
  - Create `app/services/email_service.py` utilizing Python's built-in `smtplib` and `email` packages.
  - Support configurable environment variables: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `SMTP_USE_SSL`, `SMTP_FROM_EMAIL`, and `SMTP_FROM_NAME`.
  - Support standard SMTP ports (587 for STARTTLS, 465 for SSL, 25/2525 for non-TLS test servers) with validation against incompatible TLS/SSL combinations and explicit socket/connection timeouts (e.g., 10-15s).
  - Gracefully handle authentication errors, connection timeouts, network disconnects, and SMTP transaction exceptions without leaking credentials or stack traces.
  - Document Google App Password configuration requirements (2-Step Verification) for Gmail SMTP.

- **Email Content & PDF Attachment Formatting**:
  - Construct clean, professional multipart MIME messages (`multipart/mixed` with `multipart/alternative` or clean text/html body).
  - Include personalized greetings when student names are available (neutral fallback when absent).
  - Attach the verified ReportLab PDF summary resolved via `pdf_service.resolve_pdf_full_path` with safe attachment filenames (`WebinarAI_Summary_<Job_ID>.pdf`).
  - Dispatch messages individually to each student (one email per recipient; never group students into `To` or `Cc` headers) to protect student privacy.

- **Explicit User-Controlled Dispatch**:
  - Provide a clear, explicit action on the dashboard and job details interface (e.g., "Send PDF Summaries").
  - Enforce strict pre-flight validation: require an authenticated job owner, a completed PDF summary on disk, and at least one valid pending recipient.
  - Prevent sending on mere file/CSV upload or when summarization/PDF generation is pending or failed.
  - Prevent concurrent duplicate deliveries using atomic server-side state checks (`email_status = 'sending'`).

- **Delivery Auditing & Retry Mechanism**:
  - Track per-recipient delivery status in the existing `JobRecipient` model (`delivery_status` in `'pending'`, `'sent'`, `'failed'`, `attempt_count`, `sent_at`, `last_error`).
  - Update `ProcessingJob` summary statistics (`successful_emails`, `failed_emails`, `email_status`, `overall_status`).
  - Distinguish between SMTP server acceptance and confirmed inbox delivery.
  - Provide a safe retry endpoint and action that resends exclusively to failed or unattempted recipients without re-sending to previously successful recipients.

- **Dashboard Integration & Delivery Reporting**:
  - Integrate a delivery report modal/view in the Bootstrap 5 dashboard showing total recipients, accepted messages, failures, per-recipient statuses, and retry options.
  - Update `.env.example` with placeholder settings and document configuration steps.

## Capabilities

### New Capabilities

- `email-delivery`: SMTP transport configuration, MIME message construction with ReportLab PDF attachment, individual recipient delivery, atomic status tracking, concurrency protection, and failure retry handling.

### Modified Capabilities

None. (Existing capabilities are unchanged; previous Prompt 5 and Prompt 6 features remain fully intact.)

## Impact

- **Configuration**: Updates `app/config.py` and `.env.example` with SMTP settings.
- **Backend Services**: Adds `app/services/email_service.py` and exports it in `app/services/__init__.py`.
- **Routes & APIs**: Adds `/api/jobs/<job_id>/send-emails`, `/api/jobs/<job_id>/delivery-report`, and `/api/jobs/<job_id>/retry-emails` in `app/routes/dashboard_routes.py`.
- **Frontend Templates**: Enhances `app/templates/dashboard.html` with Send action triggers, pre-flight confirmation modal, and delivery status reporting.
- **Database**: Reuses existing `ProcessingJob` and `JobRecipient` schema columns without destructive changes.
- **Dependencies**: Uses Python standard library (`smtplib`, `email`, `ssl`); no new external package required.
- **Testing**: Adds comprehensive automated test suite in `tests/test_email_delivery.py` mocking SMTP connections.
