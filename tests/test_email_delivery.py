"""
Automated Unit and Integration Tests for SMTP Email Delivery (Prompt 7).
Tests configuration validation, message construction, individual recipient privacy,
mocked SMTP delivery, partial failure handling, retry semantics, and multi-tenant security.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob, JobRecipient
from app.services import email_service, pdf_service


class TestEmailDelivery(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pdf_folder = os.path.join(self.temp_dir.name, 'pdfs')
        os.makedirs(self.pdf_folder, exist_ok=True)

        class CustomTestConfig(TestConfig):
            PDF_FOLDER = self.pdf_folder
            SMTP_HOST = 'smtp.testmail.edu'
            SMTP_PORT = 587
            SMTP_USERNAME = 'mailer@testmail.edu'
            SMTP_PASSWORD = 'app_secret_password'
            SMTP_USE_TLS = True
            SMTP_USE_SSL = False
            SMTP_FROM_EMAIL = 'webinar-noreply@testmail.edu'
            SMTP_FROM_NAME = 'WebinarAI Platform'
            SMTP_TIMEOUT = 5

        self.app = create_app(CustomTestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()

        db.create_all()

        # Provision User A (Job Owner)
        self.user_a = User(username='student_alice', email='alice@university.edu', role='user', is_active=True)
        self.user_a.set_password('Password123!')
        db.session.add(self.user_a)

        # Provision User B (Other Tenant)
        self.user_b = User(username='student_bob', email='bob@university.edu', role='user', is_active=True)
        self.user_b.set_password('Password123!')
        db.session.add(self.user_b)

        db.session.commit()
        self.client = self.app.test_client()

        # Create a dummy valid PDF file in test storage
        self.sample_pdf_filename = "test_summary.pdf"
        self.sample_pdf_full_path = os.path.join(self.pdf_folder, self.sample_pdf_filename)
        with open(self.sample_pdf_full_path, "wb") as f:
            f.write(b"%PDF-1.4 mock binary pdf stream for testing")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. SMTP Configuration Validation Tests
    # -------------------------------------------------------------------------

    def test_validate_smtp_config_valid(self):
        """Verify that valid configuration passes validation."""
        val = email_service.validate_smtp_config()
        self.assertTrue(val['valid'])
        self.assertEqual(val['settings']['host'], 'smtp.testmail.edu')
        self.assertEqual(val['settings']['port'], 587)
        self.assertTrue(val['settings']['use_tls'])
        self.assertFalse(val['settings']['use_ssl'])

    def test_validate_smtp_config_missing_host(self):
        """Verify that missing SMTP_HOST returns an actionable error."""
        val = email_service.validate_smtp_config({'SMTP_HOST': ''})
        self.assertFalse(val['valid'])
        self.assertEqual(val['code'], 'MISSING_HOST')

    def test_validate_smtp_config_invalid_port(self):
        """Verify that out-of-range port numbers are rejected."""
        val = email_service.validate_smtp_config({'SMTP_HOST': 'smtp.example.com', 'SMTP_PORT': 99999})
        self.assertFalse(val['valid'])
        self.assertEqual(val['code'], 'INVALID_PORT')

    def test_validate_smtp_config_incompatible_security(self):
        """Verify that enabling both TLS and SSL simultaneously is rejected."""
        val = email_service.validate_smtp_config({
            'SMTP_HOST': 'smtp.example.com',
            'SMTP_PORT': 587,
            'SMTP_USE_TLS': True,
            'SMTP_USE_SSL': True,
            'SMTP_FROM_EMAIL': 'test@example.com'
        })
        self.assertFalse(val['valid'])
        self.assertEqual(val['code'], 'INCOMPATIBLE_SECURITY')

    def test_validate_smtp_config_invalid_from_email(self):
        """Verify that invalid or missing sender email is rejected."""
        val1 = email_service.validate_smtp_config({'SMTP_HOST': 'smtp.example.com', 'SMTP_FROM_EMAIL': ''})
        self.assertFalse(val1['valid'])
        self.assertEqual(val1['code'], 'MISSING_FROM_EMAIL')

        val2 = email_service.validate_smtp_config({'SMTP_HOST': 'smtp.example.com', 'SMTP_FROM_EMAIL': 'not-an-email'})
        self.assertFalse(val2['valid'])
        self.assertEqual(val2['code'], 'INVALID_FROM_EMAIL')

    # -------------------------------------------------------------------------
    # 2. Email Formatting & Attachment Construction Tests
    # -------------------------------------------------------------------------

    def test_build_summary_email_personalized_with_attachment(self):
        """Verify MIME structure, personalized greeting, webinar title, and PDF attachment."""
        msg = email_service.build_summary_email(
            recipient_email='student1@university.edu',
            recipient_name='Charlie Brown',
            webinar_title='Quantum Computing 101',
            pdf_path=f"pdfs/{self.sample_pdf_filename}"
        )

        self.assertEqual(msg['To'], 'student1@university.edu')
        self.assertIn('Webinar Summary: Quantum Computing 101', msg['Subject'])
        self.assertIn('WebinarAI Platform', msg['From'])

        # Verify body contains personalized greeting
        body_content = msg.get_body(preferencelist=('plain', 'html')).get_content()
        self.assertIn('Dear Charlie Brown,', body_content)
        self.assertIn('Quantum Computing 101', body_content)

        # Verify attachment
        attachments = list(msg.iter_attachments())
        self.assertEqual(len(attachments), 1)
        att = attachments[0]
        self.assertEqual(att.get_content_type(), 'application/pdf')
        self.assertEqual(att.get_filename(), 'WebinarAI_Summary_Notes.pdf')
        self.assertTrue(att.get_content().startswith(b'%PDF-1.4'))

    def test_build_summary_email_fallback_greeting(self):
        """Verify neutral fallback greeting when student name is absent."""
        msg = email_service.build_summary_email(
            recipient_email='student2@university.edu',
            recipient_name='',
            webinar_title='',
            pdf_path=f"pdfs/{self.sample_pdf_filename}"
        )
        body_content = msg.get_body(preferencelist=('plain', 'html')).get_content()
        self.assertIn('Dear Student,', body_content)
        self.assertNotIn('None', body_content)

    def test_build_summary_email_missing_pdf_fails(self):
        """Verify that referencing a non-existent or invalid PDF raises an error."""
        with self.assertRaises((FileNotFoundError, ValueError)):
            email_service.build_summary_email(
                recipient_email='student@example.com',
                recipient_name='Test',
                webinar_title='Test',
                pdf_path='pdfs/non_existent_file.pdf'
            )

    # -------------------------------------------------------------------------
    # 3. SMTP Client Initialization & Mocked Dispatch
    # -------------------------------------------------------------------------

    @patch('smtplib.SMTP')
    def test_get_smtp_client_starttls(self, mock_smtp_class):
        """Verify STARTTLS client initializes with ehlo, starttls, and login."""
        mock_instance = MagicMock()
        mock_smtp_class.return_value = mock_instance

        client = email_service.get_smtp_client()
        mock_smtp_class.assert_called_once_with(host='smtp.testmail.edu', port=587, timeout=5)
        mock_instance.starttls.assert_called_once()
        mock_instance.login.assert_called_once_with('mailer@testmail.edu', 'app_secret_password')

    @patch('smtplib.SMTP_SSL')
    def test_get_smtp_client_ssl(self, mock_smtp_ssl_class):
        """Verify implicit SSL client initializes when USE_SSL is enabled."""
        mock_instance = MagicMock()
        mock_smtp_ssl_class.return_value = mock_instance

        ssl_config = {
            'SMTP_HOST': 'smtp.testmail.edu',
            'SMTP_PORT': 465,
            'SMTP_USE_TLS': False,
            'SMTP_USE_SSL': True,
            'SMTP_USERNAME': 'mailer@testmail.edu',
            'SMTP_PASSWORD': 'password',
            'SMTP_FROM_EMAIL': 'noreply@testmail.edu',
            'SMTP_TIMEOUT': 5
        }
        client = email_service.get_smtp_client(ssl_config)
        mock_smtp_ssl_class.assert_called_once()
        mock_instance.login.assert_called_once_with('mailer@testmail.edu', 'password')

    # -------------------------------------------------------------------------
    # 4. End-to-End Mocked Email Delivery Workflow
    # -------------------------------------------------------------------------

    def _create_sample_job(self, recipient_emails):
        """Helper to create a persisted job with multiple JobRecipient records."""
        job = ProcessingJob(
            user_id=self.user_a.id,
            title='Advanced Data Structures',
            input_type='transcript',
            input_file_name='lecture.txt',
            input_file_path='storage/uploads/lecture.txt',
            overall_status='ready',
            summary_status='completed',
            pdf_status='completed',
            pdf_path=f"pdfs/{self.sample_pdf_filename}",
            email_status='pending',
            total_recipients=len(recipient_emails)
        )
        db.session.add(job)
        db.session.flush()

        for idx, email_addr in enumerate(recipient_emails, start=1):
            recipient = JobRecipient(
                job_id=job.id,
                email=email_addr,
                student_name=f"Student {idx}",
                delivery_status='pending'
            )
            db.session.add(recipient)

        db.session.commit()
        return job

    def test_send_summary_emails_full_success(self):
        """Verify full success delivery updates all recipients and job summary statistics."""
        recipients = ['student1@univ.edu', 'student2@univ.edu', 'student3@univ.edu']
        job = self._create_sample_job(recipients)

        mock_smtp_client = MagicMock()

        result = email_service.send_webinar_summary_emails(
            job_id=job.id,
            smtp_client_override=mock_smtp_client
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['sent_count'], 3)
        self.assertEqual(result['failed_count'], 0)
        self.assertEqual(result['email_status'], 'completed')

        # Verify mock received 3 isolated send_message calls
        self.assertEqual(mock_smtp_client.send_message.call_count, 3)

        # Inspect database records
        db.session.refresh(job)
        self.assertEqual(job.successful_emails, 3)
        self.assertEqual(job.failed_emails, 0)
        self.assertEqual(job.email_status, 'completed')
        self.assertIsNotNone(job.completed_at)

        for r in job.recipients.all():
            self.assertEqual(r.delivery_status, 'sent')
            self.assertIsNotNone(r.sent_at)
            self.assertIsNone(r.last_error)

    def test_send_summary_emails_partial_failure_resilience(self):
        """Verify that a failure on one recipient does not stop delivery to others."""
        recipients = ['valid1@univ.edu', 'fail@univ.edu', 'valid2@univ.edu']
        job = self._create_sample_job(recipients)

        mock_smtp_client = MagicMock()

        # Side effect: fail on the second email
        def side_effect(msg):
            if 'fail@univ.edu' in msg['To']:
                raise Exception("SMTP 550 Mailbox does not exist")
            return {}

        mock_smtp_client.send_message.side_effect = side_effect

        result = email_service.send_webinar_summary_emails(
            job_id=job.id,
            smtp_client_override=mock_smtp_client
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['sent_count'], 2)
        self.assertEqual(result['failed_count'], 1)
        self.assertEqual(result['email_status'], 'partially_sent')

        db.session.refresh(job)
        self.assertEqual(job.successful_emails, 2)
        self.assertEqual(job.failed_emails, 1)
        self.assertEqual(job.email_status, 'partially_sent')

        # Check per-recipient status
        fail_rec = job.recipients.filter_by(email='fail@univ.edu').first()
        self.assertEqual(fail_rec.delivery_status, 'failed')
        self.assertEqual(fail_rec.attempt_count, 1)
        self.assertIn('550 Mailbox does not exist', fail_rec.last_error)

        valid_rec = job.recipients.filter_by(email='valid1@univ.edu').first()
        self.assertEqual(valid_rec.delivery_status, 'sent')

    def test_retry_emails_only_targets_failed_or_pending(self):
        """Verify that retrying delivery re-attempts failed recipients without re-sending to sent recipients."""
        recipients = ['already_sent@univ.edu', 'needs_retry@univ.edu']
        job = self._create_sample_job(recipients)

        # Manually mark first recipient as already sent
        r1 = job.recipients.filter_by(email='already_sent@univ.edu').first()
        r1.delivery_status = 'sent'
        r2 = job.recipients.filter_by(email='needs_retry@univ.edu').first()
        r2.delivery_status = 'failed'
        r2.attempt_count = 1
        job.successful_emails = 1
        job.failed_emails = 1
        job.email_status = 'partially_sent'
        db.session.commit()

        mock_smtp_client = MagicMock()

        result = email_service.send_webinar_summary_emails(
            job_id=job.id,
            retry_failed_only=True,
            smtp_client_override=mock_smtp_client
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['sent_count'], 1)  # Only 1 email sent (r2)
        self.assertEqual(mock_smtp_client.send_message.call_count, 1)

        db.session.refresh(job)
        self.assertEqual(job.successful_emails, 2)
        self.assertEqual(job.failed_emails, 0)
        self.assertEqual(job.email_status, 'completed')

    def test_concurrency_guard_rejects_simultaneous_send(self):
        """Verify that concurrent dispatch request is rejected if job.email_status == 'sending'."""
        job = self._create_sample_job(['student@univ.edu'])
        job.email_status = 'sending'
        db.session.commit()

        with self.assertRaises(email_service.SMTPDeliveryError) as ctx:
            email_service.send_webinar_summary_emails(job_id=job.id)

        self.assertEqual(ctx.exception.code, 'ALREADY_SENDING')

    # -------------------------------------------------------------------------
    # 5. Dashboard API Endpoints & Multi-Tenant Access Control Tests
    # -------------------------------------------------------------------------

    def _login_as(self, user):
        """Helper to establish an authenticated session."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id
            sess['username'] = user.username
            sess['role'] = user.role

    def test_api_email_preview_authorized(self):
        """Verify job owner can view pre-flight email preview."""
        self._login_as(self.user_a)
        job = self._create_sample_job(['s1@edu.com', 's2@edu.com'])

        resp = self.client.get(f"/api/jobs/{job.id}/email-preview")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertTrue(data['pdf_ready'])
        self.assertTrue(data['smtp_ready'])
        self.assertEqual(data['counts']['total'], 2)
        self.assertEqual(len(data['preview_recipients']), 2)

    def test_api_cross_user_access_rejected(self):
        """Verify that User B cannot preview, send, or view delivery report for User A's job."""
        self._login_as(self.user_b)  # Logged in as User B
        job = self._create_sample_job(['s1@edu.com'])  # Owned by User A

        # Preview
        resp1 = self.client.get(f"/api/jobs/{job.id}/email-preview")
        self.assertEqual(resp1.status_code, 403)

        # Send
        resp2 = self.client.post(f"/api/jobs/{job.id}/send-emails")
        self.assertEqual(resp2.status_code, 403)

        # Delivery Report
        resp3 = self.client.get(f"/api/jobs/{job.id}/delivery-report")
        self.assertEqual(resp3.status_code, 403)

    def test_api_send_rejected_when_pdf_not_ready(self):
        """Verify that /send-emails rejects jobs whose PDF has not been generated."""
        self._login_as(self.user_a)
        job = self._create_sample_job(['s1@edu.com'])
        job.pdf_status = 'pending'
        job.pdf_path = None
        db.session.commit()

        resp = self.client.post(f"/api/jobs/{job.id}/send-emails")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('PDF', data['message'])

    @patch('app.services.email_service.get_smtp_client')
    def test_api_send_emails_success(self, mock_get_client):
        """Verify successful user-triggered /send-emails via API."""
        self._login_as(self.user_a)
        job = self._create_sample_job(['student@univ.edu'])

        mock_smtp = MagicMock()
        mock_get_client.return_value = mock_smtp

        resp = self.client.post(f"/api/jobs/{job.id}/send-emails")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['details']['sent_count'], 1)

    def test_api_delivery_report_endpoint(self):
        """Verify delivery report endpoint returns structured audit details."""
        self._login_as(self.user_a)
        job = self._create_sample_job(['alice@univ.edu', 'bob@univ.edu'])

        resp = self.client.get(f"/api/jobs/{job.id}/delivery-report")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['counts']['total'], 2)
        self.assertEqual(len(data['recipients']), 2)


if __name__ == '__main__':
    unittest.main()
