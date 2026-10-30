"""
Secure SMTP Email Delivery Service for WebinarAI.
Integrates standard Python smtplib and email modules to deliver generated
PDF summaries to validated student recipients with atomic status auditing,
individual message privacy, robust error handling, and duplicate prevention.
"""

import os
import re
import ssl
import smtplib
import socket
import logging
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Dict, Any, Optional, List, Tuple

from flask import current_app

logger = logging.getLogger(__name__)

# RFC-compliant basic email syntax validation
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


class SMTPDeliveryError(Exception):
    """Custom exception for sanitized SMTP delivery failures."""
    def __init__(self, message: str, code: str = 'SMTP_ERROR'):
        super().__init__(message)
        self.message = message
        self.code = code


def sanitize_error_message(error: Any) -> str:
    """
    Strips raw stack traces, file paths, and potential credential patterns
    from error strings before returning to users or storing in the database.
    """
    if not error:
        return "Unknown SMTP error occurred."
    
    text = str(error)
    # Strip Windows or Unix file paths
    text = re.sub(r'[A-Za-z]:\\[^:\n\r]+', '[path]', text)
    text = re.sub(r'/[^\s:]+/[^\s:]+', '[path]', text)
    # Mask potential password arguments
    text = re.sub(r'(?i)(password|secret|key|passwd)\s*[:=]\s*\S+', r'\1=[PROTECTED]', text)
    return text.strip()[:500]


def get_configured_smtp_settings(config_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extracts SMTP settings from Flask current_app config or override dict.
    Supports standard names and legacy fallback keys.
    """
    cfg = config_override or {}
    if not config_override and current_app:
        cfg = current_app.config

    host = str(cfg.get('SMTP_HOST', '')).strip()
    port_val = cfg.get('SMTP_PORT', 587)
    try:
        port = int(port_val)
    except (ValueError, TypeError):
        port = 587

    username = str(cfg.get('SMTP_USERNAME') or cfg.get('SMTP_USER') or '').strip()
    password = str(cfg.get('SMTP_PASSWORD') or '').strip()

    use_tls = cfg.get('SMTP_USE_TLS', True)
    if isinstance(use_tls, str):
        use_tls = use_tls.lower() in ('true', '1', 'yes')

    use_ssl = cfg.get('SMTP_USE_SSL', False)
    if isinstance(use_ssl, str):
        use_ssl = use_ssl.lower() in ('true', '1', 'yes')

    from_email = str(cfg.get('SMTP_FROM_EMAIL') or cfg.get('SMTP_SENDER_EMAIL') or '').strip()
    from_name = str(cfg.get('SMTP_FROM_NAME') or 'WebinarAI Platform').strip()

    timeout_val = cfg.get('SMTP_TIMEOUT', 15)
    try:
        timeout = int(timeout_val)
    except (ValueError, TypeError):
        timeout = 15

    return {
        'host': host,
        'port': port,
        'username': username,
        'password': password,
        'use_tls': bool(use_tls),
        'use_ssl': bool(use_ssl),
        'from_email': from_email,
        'from_name': from_name,
        'timeout': timeout
    }


def validate_smtp_config(config_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Validates that SMTP settings are properly configured:
    1. Checks required host and port.
    2. Rejects mutually exclusive USE_TLS and USE_SSL flags enabled simultaneously.
    3. Validates from_email syntax.
    4. Ensures actionable instructions are provided without exposing credentials.
    """
    settings = get_configured_smtp_settings(config_override)

    if not settings['host']:
        return {
            'valid': False,
            'error': 'SMTP host is not configured. Please set SMTP_HOST in your environment or .env file.',
            'code': 'MISSING_HOST'
        }

    if settings['port'] < 1 or settings['port'] > 65535:
        return {
            'valid': False,
            'error': f"Invalid SMTP port '{settings['port']}'. Port must be between 1 and 65535.",
            'code': 'INVALID_PORT'
        }

    # Incompatible TLS and SSL combinations check
    if settings['use_tls'] and settings['use_ssl']:
        return {
            'valid': False,
            'error': 'Incompatible SMTP configuration: SMTP_USE_TLS and SMTP_USE_SSL cannot both be enabled. '
                     'Use TLS (port 587) or SSL (port 465).',
            'code': 'INCOMPATIBLE_SECURITY'
        }

    if not settings['from_email']:
        return {
            'valid': False,
            'error': 'SMTP sender email is not configured. Please set SMTP_FROM_EMAIL in your environment or .env file.',
            'code': 'MISSING_FROM_EMAIL'
        }

    if not EMAIL_REGEX.match(settings['from_email']):
        return {
            'valid': False,
            'error': f"Invalid sender email address '{settings['from_email']}'. Must follow standard email format.",
            'code': 'INVALID_FROM_EMAIL'
        }

    return {
        'valid': True,
        'settings': settings
    }


def build_summary_email(
    recipient_email: str,
    recipient_name: Optional[str],
    webinar_title: Optional[str],
    pdf_path: str,
    config_override: Optional[Dict[str, Any]] = None
) -> EmailMessage:
    """
    Constructs an individual RFC 5322 multipart MIME email message with:
    - Personalized or fallback greeting
    - Webinar details in both plain text and HTML
    - Attached ReportLab PDF summary brief
    - Isolated single recipient in 'To' header (no recipient leakage)
    """
    from app.services.pdf_service import resolve_pdf_full_path

    if not recipient_email or not EMAIL_REGEX.match(recipient_email.strip()):
        raise ValueError(f"Invalid recipient email address: '{recipient_email}'")

    clean_email = recipient_email.strip().lower()
    clean_name = recipient_name.strip() if recipient_name and str(recipient_name).strip() else None
    clean_title = webinar_title.strip() if webinar_title and str(webinar_title).strip() else "Webinar Knowledge Brief"

    # Verify and load PDF attachment safely
    full_pdf_path = resolve_pdf_full_path(pdf_path)
    if not full_pdf_path or not os.path.isfile(full_pdf_path):
        raise FileNotFoundError(f"PDF summary file not found on server or failed security path validation.")

    with open(full_pdf_path, 'rb') as f:
        pdf_bytes = f.read()

    if not pdf_bytes or len(pdf_bytes) == 0:
        raise ValueError("PDF summary file exists but is empty (0 bytes).")

    settings = get_configured_smtp_settings(config_override)
    from_header = f"{settings['from_name']} <{settings['from_email']}>" if settings['from_name'] else settings['from_email']

    msg = EmailMessage()
    msg['Subject'] = f"Webinar Summary: {clean_title}"
    msg['From'] = from_header
    msg['To'] = clean_email

    greeting = f"Dear {clean_name}," if clean_name else "Dear Student,"

    # Plain text version
    text_content = (
        f"{greeting}\n\n"
        f"Attached to this email is your AI-generated summary brief for \"{clean_title}\".\n\n"
        f"This study brief includes:\n"
        f"  - Executive Overview & Metadata\n"
        f"  - Key Technical Takeaways & Concepts\n"
        f"  - Action Items & Discussion Highlights\n"
        f"  - Core Technical Terminology & Definitions\n\n"
        f"Please review the attached PDF at your convenience.\n\n"
        f"Best regards,\n"
        f"WebinarAI Knowledge Distribution Platform\n"
    )

    # Clean, professional HTML version
    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Webinar Summary Brief</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #0f172a; line-height: 1.6; max-width: 620px; margin: 0 auto; padding: 20px; background-color: #f8fafc;">
  <div style="background: linear-gradient(135deg, #1e3a8a 0%, #0284c7 100%); padding: 24px; border-radius: 12px 12px 0 0; color: #ffffff;">
    <h2 style="margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.5px;">WebinarAI</h2>
    <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.9;">AI-Powered Educational Knowledge Distribution</p>
  </div>
  <div style="border: 1px solid #e2e8f0; border-top: none; padding: 28px; border-radius: 0 0 12px 12px; background-color: #ffffff; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
    <p style="font-size: 16px; margin-top: 0;"><strong>{greeting}</strong></p>
    <p style="color: #334155;">
      Your AI-generated summary brief for <strong>{clean_title}</strong> is ready and attached to this email.
    </p>
    <div style="background-color: #f1f5f9; border-left: 4px solid #0284c7; padding: 14px 18px; border-radius: 4px; margin: 20px 0;">
      <div style="font-weight: 600; font-size: 14px; color: #1e3a8a; margin-bottom: 6px;">What's Inside Your Study Brief:</div>
      <ul style="margin: 0; padding-left: 20px; color: #475569; font-size: 13px;">
        <li>Executive Overview &amp; Session Highlights</li>
        <li>Key Discussion Points &amp; Technical Takeaways</li>
        <li>Action Items &amp; Next Steps</li>
        <li>Technical Terminology &amp; Clear Definitions</li>
      </ul>
    </div>
    <p style="color: #475569; font-size: 14px;">
      Please find the complete multi-page document attached as a PDF: <em>WebinarAI_Summary.pdf</em>.
    </p>
    <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 28px 0 20px 0;">
    <p style="font-size: 12px; color: #64748b; margin: 0;">
      This email was generated and delivered automatically by <strong>WebinarAI</strong>. Please do not reply directly to this automated notification.
    </p>
  </div>
</body>
</html>"""

    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype='html')

    # Safe attachment filename
    safe_attachment_name = "WebinarAI_Summary_Notes.pdf"
    msg.add_attachment(
        pdf_bytes,
        maintype='application',
        subtype='pdf',
        filename=safe_attachment_name
    )

    return msg


def get_smtp_client(config_override: Optional[Dict[str, Any]] = None) -> smtplib.SMTP:
    """
    Establishes and returns an authenticated, secure SMTP connection client
    based on validated configuration.
    Supports STARTTLS (port 587) and implicit SSL (port 465).
    """
    validation = validate_smtp_config(config_override)
    if not validation['valid']:
        raise SMTPDeliveryError(validation['error'], code=validation['code'])

    settings = validation['settings']
    host = settings['host']
    port = settings['port']
    timeout = settings['timeout']
    username = settings['username']
    password = settings['password']

    try:
        if settings['use_ssl']:
            context = ssl.create_default_context()
            client = smtplib.SMTP_SSL(host=host, port=port, timeout=timeout, context=context)
        else:
            client = smtplib.SMTP(host=host, port=port, timeout=timeout)
            client.ehlo()
            if settings['use_tls']:
                context = ssl.create_default_context()
                client.starttls(context=context)
                client.ehlo()

        # Perform authentication if credentials are provided
        if username and password:
            client.login(username, password)
        elif username and not password:
            raise SMTPDeliveryError(
                "SMTP username is provided without a password. Please check your credentials.",
                code="MISSING_PASSWORD"
            )

        return client

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP Authentication Failure: {sanitize_error_message(e)}")
        raise SMTPDeliveryError(
            "SMTP authentication failed: Invalid username or password. If using Gmail, "
            "ensure you have enabled 2-Step Verification and are using a generated Google App Password.",
            code="AUTH_FAILED"
        )
    except (socket.timeout, TimeoutError) as e:
        logger.error(f"SMTP Connection Timeout to {host}:{port}: {sanitize_error_message(e)}")
        raise SMTPDeliveryError(
            f"SMTP connection timed out connecting to {host}:{port}. Please check network and firewall settings.",
            code="TIMEOUT"
        )
    except (smtplib.SMTPConnectError, ConnectionRefusedError, socket.gaierror) as e:
        logger.error(f"SMTP Connection Error to {host}:{port}: {sanitize_error_message(e)}")
        raise SMTPDeliveryError(
            f"Could not connect to SMTP server at {host}:{port}: {sanitize_error_message(e)}",
            code="CONNECT_FAILED"
        )
    except SMTPDeliveryError:
        raise
    except Exception as e:
        logger.error(f"Unexpected SMTP Transport Error: {sanitize_error_message(e)}")
        raise SMTPDeliveryError(
            f"SMTP transport initialization error: {sanitize_error_message(e)}",
            code="TRANSPORT_ERROR"
        )


def send_webinar_summary_emails(
    job_id: int,
    retry_failed_only: bool = False,
    config_override: Optional[Dict[str, Any]] = None,
    smtp_client_override: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Orchestrates the complete email delivery workflow for a ProcessingJob:
    1. Validates job existence, ownership, and PDF readiness.
    2. Concurrency protection: enforces atomic email_status != 'sending'.
    3. Filters eligible recipients (skips previously successful recipients).
    4. Connects to SMTP server and transmits individual messages.
    5. Updates per-recipient delivery_status, attempt_count, last_error, and sent_at.
    6. Commits per-recipient updates to persist delivery audit even on partial failure.
    7. Updates ProcessingJob overall statistics.
    """
    from app.models import db, ProcessingJob, JobRecipient
    from app.services.pdf_service import resolve_pdf_full_path

    job = db.session.get(ProcessingJob, job_id)
    if not job:
        raise ValueError(f"ProcessingJob #{job_id} not found.")

    # PDF Readiness Check
    if job.pdf_status != 'completed' or not job.pdf_path:
        raise ValueError(f"Cannot deliver emails for Job #{job.id}: PDF summary has not been generated or completed.")

    full_pdf_path = resolve_pdf_full_path(job.pdf_path)
    if not full_pdf_path or not os.path.isfile(full_pdf_path):
        raise FileNotFoundError(f"Cannot deliver emails: Verified PDF summary file does not exist on disk.")

    # Concurrency Protection Check
    if job.email_status == 'sending':
        raise SMTPDeliveryError(
            f"Job #{job.id} email delivery is already currently in progress. Please wait for the current run to complete.",
            code="ALREADY_SENDING"
        )

    # Gather eligible recipients
    if retry_failed_only:
        eligible_recipients = (
            job.recipients
            .filter(JobRecipient.delivery_status.in_(['failed', 'pending']))
            .order_by(JobRecipient.id.asc())
            .all()
        )
    else:
        eligible_recipients = (
            job.recipients
            .filter(JobRecipient.delivery_status != 'sent')
            .order_by(JobRecipient.id.asc())
            .all()
        )

    if not eligible_recipients:
        # Check if all recipients were already sent
        all_recipients = job.recipients.all()
        already_sent_count = sum(1 for r in all_recipients if r.delivery_status == 'sent')
        return {
            'success': True,
            'job_id': job.id,
            'message': 'No pending recipients to deliver to. All eligible recipients have already been sent the summary PDF.',
            'total_recipients': len(all_recipients),
            'sent_count': 0,
            'failed_count': 0,
            'skipped_count': already_sent_count,
            'status': job.email_status
        }

    # Set atomic in-flight sending state
    job.email_status = 'sending'
    db.session.commit()

    smtp_client = smtp_client_override
    owns_client = False

    sent_count = 0
    failed_count = 0
    now = datetime.now(timezone.utc)

    try:
        if smtp_client is None:
            smtp_client = get_smtp_client(config_override)
            owns_client = True

        for recipient in eligible_recipients:
            try:
                # Build isolated message for recipient
                msg = build_summary_email(
                    recipient_email=recipient.email,
                    recipient_name=recipient.student_name,
                    webinar_title=job.title or job.input_file_name,
                    pdf_path=job.pdf_path,
                    config_override=config_override
                )

                # Send message
                smtp_client.send_message(msg)

                # Record per-recipient success
                recipient.delivery_status = 'sent'
                recipient.sent_at = datetime.now(timezone.utc)
                recipient.last_error = None
                job.successful_emails += 1
                sent_count += 1

            except Exception as item_err:
                sanitized_msg = sanitize_error_message(item_err)
                logger.warning(f"Failed to email recipient {recipient.email} for Job #{job.id}: {sanitized_msg}")
                recipient.delivery_status = 'failed'
                recipient.attempt_count += 1
                recipient.last_error = sanitized_msg
                job.failed_emails += 1
                failed_count += 1

            # Commit per recipient to guarantee persistent auditing
            db.session.commit()

    except Exception as batch_err:
        logger.error(f"Fatal error during SMTP batch processing for Job #{job.id}: {sanitize_error_message(batch_err)}")
        # If client initialization or fatal batch error occurred, mark remaining recipients if not already marked
        for recipient in eligible_recipients:
            if recipient.delivery_status == 'pending':
                recipient.delivery_status = 'failed'
                recipient.attempt_count += 1
                recipient.last_error = sanitize_error_message(batch_err)
                job.failed_emails += 1
                failed_count += 1
        db.session.commit()

    finally:
        if owns_client and smtp_client is not None:
            try:
                smtp_client.quit()
            except Exception:
                try:
                    smtp_client.close()
                except Exception:
                    pass

    # Finalize job statuses
    all_recipients = job.recipients.all()
    total_count = len(all_recipients)
    total_successful = sum(1 for r in all_recipients if r.delivery_status == 'sent')
    total_failed = sum(1 for r in all_recipients if r.delivery_status == 'failed')
    total_pending = sum(1 for r in all_recipients if r.delivery_status == 'pending')

    job.successful_emails = total_successful
    job.failed_emails = total_failed

    if total_pending == 0 and total_failed == 0:
        job.email_status = 'completed'
        job.overall_status = 'completed'
        job.completed_at = datetime.now(timezone.utc)
    elif total_successful > 0:
        job.email_status = 'partially_sent'
        job.overall_status = 'partially_completed'
    else:
        job.email_status = 'failed'
        job.overall_status = 'failed'

    db.session.commit()

    return {
        'success': True,
        'job_id': job.id,
        'total_recipients': total_count,
        'sent_count': sent_count,
        'failed_count': failed_count,
        'total_successful': total_successful,
        'total_failed': total_failed,
        'email_status': job.email_status,
        'overall_status': job.overall_status
    }
