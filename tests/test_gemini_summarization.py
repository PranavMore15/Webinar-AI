"""
Unit tests for Gemini AI Summarization Service (Prompt 5).
Validates schema compliance, long-transcript chunking, rate limiting,
error handling, and secret/privacy protection with 100% mocked Gemini API calls.
"""

import os
import json
import unittest
from unittest.mock import MagicMock, patch, call

from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob
from app.services.gemini_service import (
    validate_summary_data,
    chunk_transcript,
    summarize_transcript,
    call_gemini_generate,
    parse_and_validate_json_response,
    sanitize_text,
    process_job_summarization,
    load_job_summary,
    get_summary_path,
    GeminiConfigError,
    GeminiValidationError,
    GeminiAPIError,
    DEFAULT_GEMINI_MODEL
)
from google.genai import errors as genai_errors


class TestGeminiSummarizationUnit(unittest.TestCase):
    """Unit tests for the Gemini summarization service."""

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.app = create_app(TestConfig)
        self.app.config['SUMMARY_FOLDER'] = os.path.join(self.temp_dir, 'summaries')
        os.makedirs(self.app.config['SUMMARY_FOLDER'], exist_ok=True)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        self.valid_sample_summary = {
            "title": "Introduction to Distributed Microservices Architecture",
            "overview": "An engineering lecture detailing decoupled microservices, API gateway routing, and event streams.",
            "key_points": [
                "Microservices allow independent deployment and horizontal scalability.",
                "Event-driven architecture decouples producers from consumers using message brokers."
            ],
            "takeaways": [
                "Always design for partial network failure and implement circuit breakers.",
                "Distributed transactions require saga patterns instead of two-phase locking."
            ],
            "action_items": [
                "Review the API gateway configuration before next sprint.",
                "Run chaos engineering latency tests on the checkout service."
            ],
            "terminology": [
                {
                    "term": "Circuit Breaker",
                    "definition": "A design pattern used to detect failures and prevent cascading disruptions."
                },
                {
                    "term": "Idempotency",
                    "definition": "An operation that produces the same state regardless of repeated executions."
                }
            ],
            "conclusion": "Microservices offer resilience and scaling benefits when operational tooling is properly invested in."
        }

    def tearDown(self):
        import shutil
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Schema Validation Tests
    # -------------------------------------------------------------------------

    def test_schema_validation_success(self):
        """Valid summary dictionary passes validation and preserves fields."""
        validated = validate_summary_data(self.valid_sample_summary)
        self.assertEqual(validated['title'], self.valid_sample_summary['title'])
        self.assertEqual(len(validated['key_points']), 2)
        self.assertEqual(len(validated['takeaways']), 2)
        self.assertEqual(len(validated['action_items']), 2)
        self.assertEqual(len(validated['terminology']), 2)
        self.assertEqual(validated['terminology'][0]['term'], "Circuit Breaker")

    def test_schema_validation_missing_required_keys(self):
        """Missing required fields raises GeminiValidationError."""
        for field in ['title', 'overview', 'key_points', 'takeaways', 'conclusion']:
            with self.subTest(missing_field=field):
                invalid_data = dict(self.valid_sample_summary)
                del invalid_data[field]
                with self.assertRaises(GeminiValidationError) as ctx:
                    validate_summary_data(invalid_data)
                self.assertIn("missing required fields", str(ctx.exception))

    def test_schema_validation_empty_lists(self):
        """Empty key_points or takeaways raises GeminiValidationError."""
        invalid_data = dict(self.valid_sample_summary)
        invalid_data['key_points'] = []
        with self.assertRaises(GeminiValidationError) as ctx:
            validate_summary_data(invalid_data)
        self.assertIn("key_points", str(ctx.exception))

        invalid_data = dict(self.valid_sample_summary)
        invalid_data['takeaways'] = []
        with self.assertRaises(GeminiValidationError) as ctx:
            validate_summary_data(invalid_data)
        self.assertIn("takeaways", str(ctx.exception))

    def test_schema_validation_non_dict_input(self):
        """Non-dict model output raises GeminiValidationError."""
        with self.assertRaises(GeminiValidationError):
            validate_summary_data(["not", "a", "dict"])
        with self.assertRaises(GeminiValidationError):
            validate_summary_data("plain text")

    def test_schema_validation_string_terminology_normalization(self):
        """Colon-delimited terminology strings are normalized to dicts."""
        data = dict(self.valid_sample_summary)
        data['terminology'] = ["RPC: Remote Procedure Call protocol"]
        validated = validate_summary_data(data)
        self.assertEqual(validated['terminology'][0]['term'], "RPC")
        self.assertEqual(validated['terminology'][0]['definition'], "Remote Procedure Call protocol")

    # -------------------------------------------------------------------------
    # 2. Long Transcript Chunking Tests
    # -------------------------------------------------------------------------

    def test_chunk_transcript_short_text(self):
        """Short transcript below threshold returns a single chunk."""
        text = "This is a short transcript about system architecture."
        chunks = chunk_transcript(text, max_chars=1000)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_chunk_transcript_splits_along_boundaries(self):
        """Transcript exceeding max_chars splits along natural boundaries with overlap."""
        paragraphs = [
            f"Paragraph {i}. " + ("Technical engineering discussion about distributed consensus and Paxos algorithms. " * 10)
            for i in range(1, 10)
        ]
        full_text = "\n\n".join(paragraphs)
        self.assertGreater(len(full_text), 3000)

        chunks = chunk_transcript(full_text, max_chars=1200, overlap_chars=200)
        self.assertGreater(len(chunks), 1)
        # Every chunk should be within bounded character limit
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 1400)
            self.assertTrue(len(chunk.strip()) > 0)

    # -------------------------------------------------------------------------
    # 3. Input Validation & Missing Credentials
    # -------------------------------------------------------------------------

    def test_missing_api_key_raises_config_error(self):
        """Missing GEMINI_API_KEY raises GeminiConfigError."""
        with patch.dict(os.environ, {}, clear=True):
            self.app.config['GEMINI_API_KEY'] = ''
            with self.assertRaises(GeminiConfigError) as ctx:
                summarize_transcript("Valid transcript text for engineering lecture.")
            self.assertIn("GEMINI_API_KEY is not configured", str(ctx.exception))

    def test_empty_transcript_raises_validation_error(self):
        """Empty or whitespace transcript raises GeminiValidationError."""
        with self.assertRaises(GeminiValidationError):
            summarize_transcript("")
        with self.assertRaises(GeminiValidationError):
            summarize_transcript("   \n\t  ")

    def test_insufficient_words_raises_validation_error(self):
        """Transcript with fewer than 5 words raises GeminiValidationError."""
        with self.assertRaises(GeminiValidationError) as ctx:
            summarize_transcript("Too short transcript")
        self.assertIn("insufficient spoken text", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 4. Mocked API Execution & Output Parsing
    # -------------------------------------------------------------------------

    @patch('app.services.gemini_service.get_gemini_api_key', return_value='fake-test-api-key')
    def test_single_pass_summarization_success_mocked(self, mock_key):
        """Mocked Gemini client successfully produces validated summary."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(self.valid_sample_summary)
        mock_client.models.generate_content.return_value = mock_response

        transcript = (
            "Welcome everyone to our webinar on distributed systems. Today we will cover microservices, "
            "event streams, API gateways, circuit breakers, and idempotency in enterprise engineering."
        )

        result = summarize_transcript(
            transcript_text=transcript,
            title_hint="Distributed Architecture",
            client=mock_client
        )

        self.assertEqual(result['title'], self.valid_sample_summary['title'])
        self.assertEqual(result['overview'], self.valid_sample_summary['overview'])
        self.assertEqual(len(result['key_points']), 2)
        self.assertEqual(len(result['takeaways']), 2)
        mock_client.models.generate_content.assert_called_once()

    @patch('app.services.gemini_service.get_gemini_api_key', return_value='fake-test-api-key')
    def test_markdown_wrapped_json_response_parsing(self, mock_key):
        """Model response wrapped in markdown ```json ... ``` code fence is parsed cleanly."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = f"```json\n{json.dumps(self.valid_sample_summary)}\n```"
        mock_client.models.generate_content.return_value = mock_response

        transcript = "A comprehensive lecture on database indexing and B-tree optimization."
        result = summarize_transcript(transcript_text=transcript, client=mock_client)
        self.assertEqual(result['title'], self.valid_sample_summary['title'])

    @patch('app.services.gemini_service.get_gemini_api_key', return_value='fake-test-api-key')
    def test_malformed_json_response_raises_validation_error(self, mock_key):
        """Non-JSON model response raises GeminiValidationError."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Sorry, as an AI I cannot generate valid JSON right now."
        mock_client.models.generate_content.return_value = mock_response

        transcript = "A comprehensive lecture on database indexing and B-tree optimization."
        with self.assertRaises(GeminiValidationError) as ctx:
            summarize_transcript(transcript_text=transcript, client=mock_client)
        self.assertIn("Failed to parse Gemini output as JSON", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 5. Rate Limiting, Retries & Error Handling
    # -------------------------------------------------------------------------

    @patch('time.sleep')
    @patch('app.services.gemini_service.get_gemini_api_key', return_value='fake-test-api-key')
    def test_rate_limit_429_retry_success(self, mock_key, mock_sleep):
        """Transient 429 rate limit errors trigger backoff and succeed on subsequent attempt."""
        mock_client = MagicMock()
        
        # Create mock 429 APIError
        err_429 = genai_errors.APIError(429, {"error": {"message": "RESOURCE_EXHAUSTED: Rate limit exceeded."}})
        valid_response = MagicMock(text=json.dumps(self.valid_sample_summary))
        
        # Fail twice with 429, succeed on 3rd call
        mock_client.models.generate_content.side_effect = [err_429, err_429, valid_response]

        transcript = "A lecture discussing message brokers, Kafka partitions, and consumer groups."
        result = summarize_transcript(transcript_text=transcript, client=mock_client)

        self.assertEqual(result['title'], self.valid_sample_summary['title'])
        self.assertEqual(mock_client.models.generate_content.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('time.sleep')
    @patch('app.services.gemini_service.get_gemini_api_key', return_value='fake-test-api-key')
    def test_rate_limit_retries_exhausted_raises_api_error(self, mock_key, mock_sleep):
        """Exhausting retry attempts on persistent 429 raises GeminiAPIError."""
        mock_client = MagicMock()
        err_429 = genai_errors.APIError(429, {"error": {"message": "RESOURCE_EXHAUSTED: Rate limit exceeded."}})
        mock_client.models.generate_content.side_effect = err_429

        transcript = "A lecture discussing message brokers, Kafka partitions, and consumer groups."
        with self.assertRaises(GeminiAPIError) as ctx:
            summarize_transcript(transcript_text=transcript, client=mock_client)
        self.assertIn("Gemini API call failed (HTTP 429)", str(ctx.exception))
        self.assertEqual(mock_client.models.generate_content.call_count, 3)

    # -------------------------------------------------------------------------
    # 6. Multi-Chunk Long Transcript Synthesis
    # -------------------------------------------------------------------------

    @patch('app.services.gemini_service.get_gemini_api_key', return_value='fake-test-api-key')
    def test_long_transcript_multi_chunk_synthesis(self, mock_key):
        """Long transcript invokes multiple section calls and a final synthesis call."""
        mock_client = MagicMock()
        
        chunk_response = MagicMock(text=json.dumps(self.valid_sample_summary))
        synthesis_summary = dict(self.valid_sample_summary)
        synthesis_summary['title'] = "Synthesized Master Course on Systems Engineering"
        synthesis_response = MagicMock(text=json.dumps(synthesis_summary))

        # 2 chunks of text with max_chars=1200
        long_transcript = "Section One discussion about networking.\n\n" * 20 + "Section Two discussion about databases.\n\n" * 20
        
        # 2 chunk calls + 1 synthesis call = 3 total calls
        mock_client.models.generate_content.side_effect = [
            chunk_response,
            chunk_response,
            synthesis_response
        ]
        
        result = summarize_transcript(
            transcript_text=long_transcript,
            title_hint="Systems Masterclass",
            client=mock_client,
            chunk_char_limit=1200  # Threshold to trigger exactly 2 chunks
        )

        self.assertEqual(result['title'], "Synthesized Master Course on Systems Engineering")
        self.assertEqual(mock_client.models.generate_content.call_count, 3)

    # -------------------------------------------------------------------------
    # 7. Privacy & Secret Sanitization
    # -------------------------------------------------------------------------

    def test_secret_sanitization(self):
        """Sensitive API key is masked in error strings."""
        raw_error = "Error from https://generativelanguage.googleapis.com?key=AIzaSySecretApiKey123: invalid token"
        sanitized = sanitize_text(raw_error, "AIzaSySecretApiKey123")
        self.assertNotIn("AIzaSySecretApiKey123", sanitized)
        self.assertIn("[REDACTED_API_KEY]", sanitized)

    @patch('app.services.gemini_service.get_gemini_api_key', return_value='fake-test-api-key')
    def test_zero_recipient_data_transmitted(self, mock_key):
        """Verify prompt generated for Gemini never includes recipient emails or personal data."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(text=json.dumps(self.valid_sample_summary))

        transcript = "Cleaned lecture transcript covering cryptographic algorithms."
        summarize_transcript(transcript_text=transcript, client=mock_client)

        prompt_sent = mock_client.models.generate_content.call_args[1]['contents']
        self.assertIn("cryptographic algorithms", prompt_sent)
        self.assertNotIn("@", prompt_sent)
        self.assertNotIn("student", prompt_sent.lower())

    # -------------------------------------------------------------------------
    # 8. Pipeline Integration & Database Status Persistence
    # -------------------------------------------------------------------------

    @patch('app.services.gemini_service.get_gemini_api_key', return_value='fake-test-api-key')
    def test_process_job_summarization_with_txt_transcript(self, mock_key):
        """Pipeline processes a TXT transcript job, updates statuses, and saves JSON artifact."""
        # Provision test user and job
        user = User(username='testoperator', role='user', is_active=True)
        user.set_password('Secret123!')
        db.session.add(user)
        db.session.commit()

        # Create sample transcript file
        sample_txt_path = os.path.join(self.temp_dir, 'sample_lecture.txt')
        with open(sample_txt_path, 'w', encoding='utf-8') as f:
            f.write(
                "Webinar Title: Cloud Native Architecture\n"
                "Speaker: Martin Fowler\n"
                "Microservices require automated continuous integration and observable metrics. "
                "Event-driven messaging and circuit breakers prevent cascading failures across services."
            )

        job = ProcessingJob(
            user_id=user.id,
            title="Cloud Native Architecture",
            input_type="transcript",
            input_file_name="sample_lecture.txt",
            input_file_path=sample_txt_path,
            transcript_status="pending",
            summary_status="pending"
        )
        db.session.add(job)
        db.session.commit()

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(text=json.dumps(self.valid_sample_summary))

        result = process_job_summarization(job=job, client=mock_client)

        self.assertTrue(result['success'])
        self.assertEqual(result['job_id'], job.id)
        self.assertEqual(job.transcript_status, 'completed')
        self.assertEqual(job.summary_status, 'completed')
        self.assertIsNone(job.error_message)

        # Verify summary JSON file exists on disk and can be loaded
        loaded_summary = load_job_summary(job.id)
        self.assertIsNotNone(loaded_summary)
        self.assertEqual(loaded_summary['title'], self.valid_sample_summary['title'])

    @patch('app.services.transcript_service.process_webinar_to_transcript')
    @patch('app.services.gemini_service.get_gemini_api_key', return_value='fake-test-api-key')
    def test_process_job_summarization_with_video_input(self, mock_key, mock_transcript_step):
        """Pipeline handles video jobs by invoking transcript extraction then Gemini summarization."""
        user = User(username='videooperator', role='user', is_active=True)
        user.set_password('Secret123!')
        db.session.add(user)
        db.session.commit()

        job = ProcessingJob(
            user_id=user.id,
            title="Video Lecture on Neural Networks",
            input_type="video",
            input_file_name="lecture.mp4",
            input_file_path=os.path.join(self.temp_dir, "lecture.mp4"),
            transcript_status="pending",
            summary_status="pending"
        )
        db.session.add(job)
        db.session.commit()

        mock_transcript_step.return_value = {
            'success': True,
            'transcript_text': "Transcribed audio from video recording discussing convolutional layers and gradient descent optimization."
        }

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = MagicMock(text=json.dumps(self.valid_sample_summary))

        result = process_job_summarization(job=job, client=mock_client)

        self.assertTrue(result['success'])
        self.assertEqual(job.transcript_status, 'completed')
        self.assertEqual(job.summary_status, 'completed')
        mock_transcript_step.assert_called_once_with('video', job.input_file_path)

    @patch('app.services.gemini_service.get_gemini_api_key', return_value='fake-test-api-key')
    def test_process_job_summarization_failure_records_error_in_db(self, mock_key):
        """Errors during summarization set summary_status='failed' and record diagnostic message."""
        user = User(username='failoperator', role='user', is_active=True)
        user.set_password('Secret123!')
        db.session.add(user)
        db.session.commit()

        sample_txt = os.path.join(self.temp_dir, 'fail_lecture.txt')
        with open(sample_txt, 'w', encoding='utf-8') as f:
            f.write("Valid text for lecture that will encounter model generation failure.")

        job = ProcessingJob(
            user_id=user.id,
            title="Failure Case Lecture",
            input_type="transcript",
            input_file_name="fail_lecture.txt",
            input_file_path=sample_txt,
            transcript_status="pending",
            summary_status="pending"
        )
        db.session.add(job)
        db.session.commit()

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("Google API Network Timeout")

        with self.assertRaises(Exception):
            process_job_summarization(job=job, client=mock_client)

        self.assertEqual(job.summary_status, 'failed')
        self.assertIn("AI Summarization Failed", job.error_message)


if __name__ == '__main__':
    unittest.main()
