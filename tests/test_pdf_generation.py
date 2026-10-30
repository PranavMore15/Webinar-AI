import os
import json
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob
from app.services import pdf_service


class TestPdfGeneration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        
        class CustomTestConfig(TestConfig):
            PDF_FOLDER = os.path.join(self.temp_dir.name, 'pdfs')
            SUMMARY_FOLDER = os.path.join(self.temp_dir.name, 'summaries')

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

        # Provision Admin
        self.admin = User(username='admin_boss', email='admin@webinarai.edu', role='admin', is_active=True)
        self.admin.set_password('AdminPass123!')
        db.session.add(self.admin)

        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        self.temp_dir.cleanup()

    # --- Unit Tests: Sanitization & Helpers ---

    def test_sanitize_pdf_text_quotes_and_entities(self):
        """Verify text normalization correctly converts quotes, dashes, and escapes XML entities."""
        raw = 'Intro: “Advanced” AI & Machine Learning — Part 1 <Basics> with ‘quotes’…'
        cleaned = pdf_service.sanitize_pdf_text(raw)
        self.assertIn('&amp;', cleaned)
        self.assertIn('&lt;Basics&gt;', cleaned)
        self.assertIn('"Advanced"', cleaned)
        self.assertIn(" - ", cleaned)
        self.assertNotIn('“', cleaned)
        self.assertNotIn('”', cleaned)

    def test_sanitize_pdf_text_empty_and_none(self):
        """Verify None and empty strings return empty sanitized string without error."""
        self.assertEqual(pdf_service.sanitize_pdf_text(None), "")
        self.assertEqual(pdf_service.sanitize_pdf_text("   "), "")

    def test_resolve_pdf_full_path_security(self):
        """Verify resolve_pdf_full_path enforces strict containment within PDF_FOLDER and blocks traversal."""
        base_folder = self.app.config['PDF_FOLDER']
        
        # Valid relative paths
        valid_rel = "pdfs/test_doc.pdf"
        resolved = pdf_service.resolve_pdf_full_path(valid_rel)
        self.assertIsNotNone(resolved)
        self.assertTrue(os.path.abspath(resolved).startswith(os.path.abspath(base_folder)))

        # Directory traversal attempt
        traversal_attempt = "../../etc/passwd"
        self.assertIsNone(pdf_service.resolve_pdf_full_path(traversal_attempt))

        # Dot-dot traversal within path
        nested_traversal = "pdfs/../../../secret.txt"
        self.assertIsNone(pdf_service.resolve_pdf_full_path(nested_traversal))

    # --- Document Generation Tests ---

    def test_build_pdf_document_complete(self):
        """Verify compilation of a full educational summary into an A4 multi-page PDF."""
        summary_data = {
            'title': 'Autonomous Robotics: Perception and Motion Planning',
            'overview': 'This technical brief summarizes perception algorithms, Kalman filters, and motion planning for autonomous mobile platforms.',
            'key_points': [
                'Sensor fusion combines LiDAR and camera data.',
                'Extended Kalman Filters maintain state estimation during GPS outage.'
            ],
            'takeaways': [
                'Implement loop closure detection in SLAM.',
                'Use bounded velocity profiles to avoid actuator saturation.'
            ],
            'action_items': [
                'Configure ROS 2 node parameters for the real-time controller.'
            ],
            'terminology': [
                {
                    'term': 'SLAM',
                    'definition': 'Simultaneous Localization and Mapping algorithm.'
                },
                {
                    'term': 'EKF',
                    'definition': 'Extended Kalman Filter for nonlinear state estimation.'
                }
            ],
            'conclusion': 'Modular robotics architectures ensure testability and safety in field environments.'
        }
        metadata = {
            'job_id': 101,
            'input_type': 'video',
            'input_file_name': 'robotics_lecture.mp4'
        }

        out_path = os.path.join(self.app.config['PDF_FOLDER'], 'robotics_summary.pdf')
        result_path = pdf_service.build_pdf_document(summary_data, out_path, metadata)
        
        self.assertEqual(result_path, out_path)
        self.assertTrue(os.path.isfile(out_path))
        self.assertGreater(os.path.getsize(out_path), 1000)

        # Check standard PDF magic header
        with open(out_path, 'rb') as f:
            header = f.read(5)
            self.assertEqual(header, b'%PDF-')

    def test_build_pdf_document_sparse_and_unicode(self):
        """Verify document compiles gracefully when optional fields (action_items, terminology, conclusion) are absent."""
        sparse_summary = {
            'title': 'Quantum Computing: Qubits & Decoherence',
            'overview': 'Overview of superposition & entanglement with special symbols: α, β, ±, ≤, ≥, and non-ASCII dashes —.',
            'key_points': ['Superposition allows parallel state evaluation.'],
            'takeaways': ['Decoherence limits quantum gate fidelity.']
            # action_items, terminology, and conclusion are omitted
        }
        out_path = os.path.join(self.app.config['PDF_FOLDER'], 'sparse_summary.pdf')
        pdf_service.build_pdf_document(sparse_summary, out_path)

        self.assertTrue(os.path.isfile(out_path))
        self.assertGreater(os.path.getsize(out_path), 500)

    # --- Service Orchestration & Idempotency Tests ---

    def test_generate_job_pdf_success_and_idempotency(self):
        """Verify generate_job_pdf writes PDF, updates MySQL columns, and behaves idempotently on repeated calls."""
        job = ProcessingJob(
            user_id=self.user_a.id,
            title='Distributed Systems 101',
            input_type='transcript',
            input_file_name='dist_sys.txt',
            input_file_path='storage/uploads/fake_dist_sys.txt',
            summary_status='completed',
            overall_status='ready'
        )
        db.session.add(job)
        db.session.commit()

        mock_summary = {
            'title': 'Distributed Consensus & Raft Protocol',
            'overview': 'An overview of leader election, log replication, and Byzantine fault tolerance.',
            'key_points': ['Raft simplifies consensus compared to Paxos.'],
            'takeaways': ['Elect leaders with randomized election timers.'],
            'action_items': [],
            'terminology': [{'term': 'Heartbeat', 'definition': 'Periodic message sent by leader.'}],
            'conclusion': 'Strong leader consensus provides linearized state machine replication.'
        }

        with patch('app.services.gemini_service.load_job_summary', return_value=mock_summary):
            # First Generation Call
            res1 = pdf_service.generate_job_pdf(job.id)
            self.assertTrue(res1['success'])
            self.assertFalse(res1['idempotent'])
            self.assertEqual(job.pdf_status, 'completed')
            self.assertIsNotNone(job.pdf_path)

            first_full_path = res1['full_path']
            self.assertTrue(os.path.isfile(first_full_path))

            # Second Generation Call (Idempotent: should reuse file without recreating)
            res2 = pdf_service.generate_job_pdf(job.id, force=False)
            self.assertTrue(res2['success'])
            self.assertTrue(res2['idempotent'])
            self.assertEqual(res2['full_path'], first_full_path)

    def test_generate_job_pdf_fails_when_summary_missing(self):
        """Verify generate_job_pdf raises ValueError and updates pdf_status to 'failed' when summary is missing."""
        job = ProcessingJob(
            user_id=self.user_a.id,
            title='Missing Summary Job',
            input_type='transcript',
            input_file_name='missing.txt',
            input_file_path='storage/uploads/fake_missing.txt',
            summary_status='pending'
        )
        db.session.add(job)
        db.session.commit()

        with patch('app.services.gemini_service.load_job_summary', return_value=None):
            with self.assertRaises(ValueError):
                pdf_service.generate_job_pdf(job.id)

        # Reload from DB
        db.session.refresh(job)
        self.assertEqual(job.pdf_status, 'failed')
        self.assertIn('No AI summary file exists', job.error_message)

    # --- HTTP Download & Authorization Tests ---

    def test_download_pdf_unauthenticated_redirects(self):
        """Verify unauthenticated requests to download PDF are rejected with redirect or 401."""
        job = ProcessingJob(
            user_id=self.user_a.id,
            title='Sample Job',
            input_type='transcript',
            input_file_name='sample.txt',
            input_file_path='storage/uploads/sample.txt',
            summary_status='completed',
            pdf_status='completed',
            pdf_path='pdfs/sample.pdf'
        )
        db.session.add(job)
        db.session.commit()

        res = self.client.get(f'/dashboard/jobs/{job.id}/download-pdf')
        # Expect redirect to login page
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers['Location'])

    def test_download_pdf_authorized_job_owner(self):
        """Verify authorized owner can download their completed PDF successfully."""
        # Create physical dummy PDF
        filename = 'webinar_summary_job_test.pdf'
        full_pdf_path = os.path.join(self.app.config['PDF_FOLDER'], filename)
        with open(full_pdf_path, 'wb') as f:
            f.write(b'%PDF-1.4\nTest PDF Content for WebinarAI\n%%EOF')

        job = ProcessingJob(
            user_id=self.user_a.id,
            title='Cloud Architecture Seminar',
            input_type='transcript',
            input_file_name='cloud.txt',
            input_file_path='storage/uploads/cloud.txt',
            summary_status='completed',
            pdf_status='completed',
            pdf_path=f"pdfs/{filename}"
        )
        db.session.add(job)
        db.session.commit()

        # Simulate authenticated session for User A
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user_a.id
            sess['username'] = self.user_a.username
            sess['role'] = 'user'

        res = self.client.get(f'/dashboard/jobs/{job.id}/download-pdf')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('Content-Type'), 'application/pdf')
        self.assertIn(f"WebinarAI_Summary_Job_{job.id}.pdf", res.headers.get('Content-Disposition', ''))
        self.assertTrue(res.data.startswith(b'%PDF-'))

    def test_download_pdf_cross_tenant_forbidden(self):
        """Verify User B cannot download User A's generated PDF (tenant isolation)."""
        filename = 'user_a_secret_notes.pdf'
        full_pdf_path = os.path.join(self.app.config['PDF_FOLDER'], filename)
        with open(full_pdf_path, 'wb') as f:
            f.write(b'%PDF-1.4 User A Private Data')

        job_a = ProcessingJob(
            user_id=self.user_a.id,
            title='User A Sensitive Lecture',
            input_type='transcript',
            input_file_name='user_a.txt',
            input_file_path='storage/uploads/user_a.txt',
            summary_status='completed',
            pdf_status='completed',
            pdf_path=f"pdfs/{filename}"
        )
        db.session.add(job_a)
        db.session.commit()

        # Log in as User B
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user_b.id
            sess['username'] = self.user_b.username
            sess['role'] = 'user'

        res = self.client.get(f'/dashboard/jobs/{job_a.id}/download-pdf')
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertFalse(data['success'])
        self.assertIn('Access denied', data['message'])

    def test_download_pdf_not_ready_returns_400(self):
        """Verify download request for a job whose summary is still pending returns 400 Bad Request."""
        job = ProcessingJob(
            user_id=self.user_a.id,
            title='Incomplete Job',
            input_type='video',
            input_file_name='incomplete.mp4',
            input_file_path='storage/uploads/incomplete.mp4',
            summary_status='pending',
            pdf_status='pending'
        )
        db.session.add(job)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user_a.id
            sess['username'] = self.user_a.username
            sess['role'] = 'user'

        res = self.client.get(f'/dashboard/jobs/{job.id}/download-pdf')
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data['success'])
        self.assertIn('must be completed first', data['message'])

    def test_trigger_generate_pdf_api(self):
        """Verify POST /api/jobs/<id>/generate-pdf triggers generation successfully."""
        job = ProcessingJob(
            user_id=self.user_a.id,
            title='API Generation Trigger',
            input_type='transcript',
            input_file_name='api_lecture.txt',
            input_file_path='storage/uploads/api_lecture.txt',
            summary_status='completed',
            pdf_status='pending'
        )
        db.session.add(job)
        db.session.commit()

        mock_summary = {
            'title': 'API Design Best Practices',
            'overview': 'RESTful API principles and idempotency.',
            'key_points': ['Use standard HTTP verbs.'],
            'takeaways': ['Safe methods must be idempotent.']
        }

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user_a.id
            sess['username'] = self.user_a.username
            sess['role'] = 'user'

        with patch('app.services.gemini_service.load_job_summary', return_value=mock_summary):
            res = self.client.post(f'/api/jobs/{job.id}/generate-pdf', json={'force': True})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data['success'])
            self.assertEqual(data['pdf_status'], 'completed')
            self.assertIn('pdfs/', data['pdf_path'])

    def test_admin_inspect_includes_pdf_readiness(self):
        """Verify admin job details endpoint reports pdf_status and pdf_ready."""
        job = ProcessingJob(
            user_id=self.user_a.id,
            title='Admin Oversight Job',
            input_type='transcript',
            input_file_name='oversight.txt',
            input_file_path='storage/uploads/oversight.txt',
            summary_status='completed',
            pdf_status='completed',
            pdf_path='pdfs/oversight.pdf'
        )
        db.session.add(job)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id
            sess['username'] = self.admin.username
            sess['role'] = 'admin'

        res = self.client.get(f'/admin/api/jobs/{job.id}/details')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['job']['pdf_status'], 'completed')
        self.assertTrue(data['job']['pdf_ready'])
        self.assertEqual(data['job']['pdf_path'], 'pdfs/oversight.pdf')


if __name__ == '__main__':
    unittest.main()
