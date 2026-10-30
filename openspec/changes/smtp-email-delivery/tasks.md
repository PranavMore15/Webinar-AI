# Tasks: Secure SMTP Email Delivery of PDF Summaries

## 1. Configuration & SMTP Service Foundation

- [x] 1.1 Add SMTP configuration keys (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `SMTP_USE_SSL`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`, `SMTP_TIMEOUT`) to `app/config.py` and update `.env.example` with documented placeholders and Gmail App Password instructions; verify configuration loads cleanly.
- [x] 1.2 Implement configuration validation function `validate_smtp_config()` in `app/services/email_service.py` to enforce required parameters, reject conflicting `SMTP_USE_TLS` and `SMTP_USE_SSL` flags, and return clear actionable errors without leaking credentials; verify with unit tests.

## 2. Email Formatting & Transport Implementation

- [x] 2.1 Implement `build_summary_email()` in `app/services/email_service.py` to construct individual multipart MIME messages (`EmailMessage`) with personalized student greetings (neutral fallback when name absent), contextual webinar title, and ReportLab PDF attachment resolved safely via `pdf_service.resolve_pdf_full_path()`; verify MIME structure and attachment headers.
- [x] 2.2 Implement SMTP client connection manager `get_smtp_client()` supporting STARTTLS (port 587) and SSL (port 465) with explicit socket timeouts, credential authentication, and sanitized error mapping.
- [x] 2.3 Implement `send_webinar_summary_emails(job_id, retry_failed_only=False)` in `app/services/email_service.py` to orchestrate batch dispatch: enforce atomic `email_status = 'sending'`, send individual messages, update `JobRecipient` status (`sent`, `failed`, `sent_at`, `attempt_count`, `last_error`) per iteration with transactional commits, and update `ProcessingJob` summary statistics (`successful_emails`, `failed_emails`, `email_status`, `overall_status`, `completed_at`).
- [x] 2.4 Export `email_service` in `app/services/__init__.py`.

## 3. Dashboard API Endpoints & Access Control

- [x] 3.1 Implement pre-flight check endpoint `GET /api/jobs/<int:job_id>/email-preview` in `app/routes/dashboard_routes.py` with `@user_required` and strict job ownership enforcement, returning webinar metadata, valid recipient count, and verified PDF readiness.
- [x] 3.2 Implement user-controlled dispatch endpoint `POST /api/jobs/<int:job_id>/send-emails` in `app/routes/dashboard_routes.py` enforcing ownership, PDF readiness, pre-flight validation, and concurrency guarding against concurrent requests; verify rejection of unauthorized or pending states.
- [x] 3.3 Implement retry endpoint `POST /api/jobs/<int:job_id>/retry-emails` in `app/routes/dashboard_routes.py` targeting strictly eligible failed or unattempted recipients, preventing re-sending to previously successful recipients.
- [x] 3.4 Implement delivery report endpoint `GET /api/jobs/<int:job_id>/delivery-report` in `app/routes/dashboard_routes.py` returning per-recipient delivery statuses and aggregate counts for the job owner.

## 4. Frontend Dashboard Integration & Delivery Reporting

- [x] 4.1 Update Registered Processing Jobs table in `app/templates/dashboard.html` to add Email Delivery status column and contextual action triggers ("Send Summaries", "View Report", "Retry Failed").
- [x] 4.2 Create Pre-Flight Confirmation Modal in `app/templates/dashboard.html` displaying webinar title, recipient count, PDF verification indicator, and explicit "Confirm & Send" button.
- [x] 4.3 Create Delivery Report Modal in `app/templates/dashboard.html` displaying aggregate stat badges (Total, Accepted, Failed, Skipped), per-recipient status table, and "Retry Failed Recipients" action.
- [x] 4.4 Add frontend JavaScript controller functions in `app/templates/dashboard.html` to wire up pre-flight verification, dispatch API calls, loading indicators, and delivery report modal rendering.

## 5. Automated Testing & Verification

- [x] 5.1 Create comprehensive test suite in `tests/test_email_delivery.py` covering:
  - Configuration loading, missing credential rejection, and conflicting TLS/SSL rejection.
  - Non-existent PDF rejection and traversal defense.
  - Message construction: personalized vs fallback greeting, webinar title, and MIME PDF attachment.
  - Individual recipient privacy (strict single-recipient `To` header, no `Cc`/`Bcc` leakage).
  - Mocked SMTP dispatch: 100% success, partial failure resilience (one failure doesn't abort others), and total network failure.
  - Duplicate dispatch prevention (concurrent send returns 409 conflict).
  - Selective retry behavior (only failed/pending recipients re-attempted; previously sent recipients skipped).
  - Multi-tenant security (cross-user send rejection with 403, unauthenticated rejection with 302/401).
- [x] 5.2 Execute complete test suite (`unittest discover -s tests -v`) verifying that all existing tests and new email delivery tests pass with 0 failures and 0 errors.
- [x] 5.3 Update `PROJECT_STATUS.md` with Prompt 7 implementation status, created/modified files, test results, and Gmail SMTP setup documentation.
