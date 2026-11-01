"""
Automated Test Suite for Prompt A6: Retrieval & Processing Pipeline Integration.

Covers:
1. Schema verification: source_type, source_url, retrieval_status, retrieval_error on ProcessingJob.
2. Direct audio routing: Audio inputs (.mp3, .wav, .m4a) route directly to Whisper without FFmpeg video extraction.
3. Failure isolation: If media retrieval fails or input file is missing, pipeline halts before summarization and email delivery.
4. Idempotency guard: Completed jobs are not re-executed on redundant calls.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from app import create_app
from app.config import TestConfig
from app.models import db, User, ProcessingJob, JobRecipient
from app.services import pipeline_service, transcript_service


class TestPipelineIntegrationA6(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.upload_dir = os.path.join(self.temp_dir, 'uploads')
        os.makedirs(self.upload_dir, exist_ok=True)

        class A6TestConfig(TestConfig):
            UPLOAD_FOLDER = self.upload_dir
            TESTING = True

        self.app = create_app(A6TestConfig)
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Seed test user
        self.user = User(
            username='pipeline_user',
            email='pipeline_user@webinarai.edu',
            role='user',
            is_active=True
        )
        self.user.set_password('PipelineSecure123!')
        db.session.add(self.user)
        db.session.commit()
        self.user_id = self.user.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_schema_retrieval_columns_exist(self):
        """Verify ProcessingJob contains source_type, source_url, retrieval_status, retrieval_error."""
        job = ProcessingJob(
            user_id=self.user_id,
            title='Schema Test',
            input_type='video',
            input_file_name='test.mp4',
            input_file_path='/dummy/path/test.mp4',
            source_type='direct',
            source_url='https://example.com/test.mp4',
            retrieval_status='completed',
            retrieval_error=None
        )
        db.session.add(job)
        db.session.commit()

        queried = db.session.get(ProcessingJob, job.id)
        self.assertEqual(queried.source_type, 'direct')
        self.assertEqual(queried.source_url, 'https://example.com/test.mp4')
        self.assertEqual(queried.retrieval_status, 'completed')
        self.assertIsNone(queried.retrieval_error)

    @patch('app.services.transcription_service.transcribe_audio_chunks')
    @patch('app.services.audio_service.chunk_audio_if_needed')
    @patch('app.services.audio_service.extract_audio_from_video')
    def test_audio_only_input_skips_video_extraction(self, mock_extract, mock_chunk, mock_transcribe):
        """Verify audio inputs (MP3/WAV) bypass FFmpeg video extraction and route directly to Whisper."""
        mock_chunk.return_value = ['/dummy/audio.mp3']
        mock_transcribe.return_value = {
            'transcript_text': 'This is transcribed speech from an MP3 audio file.',
            'word_count': 9
        }

        fake_audio_path = os.path.join(self.upload_dir, 'seminar_audio.mp3')
        with open(fake_audio_path, 'wb') as f:
            f.write(b'ID3\x03\x00\x00\x00\x00\x00\x00\xff\xfb\x90' + b'\x00' * 50)

        result = transcript_service.process_webinar_to_transcript('audio', fake_audio_path)

        # Video extraction MUST NOT be called for audio input
        mock_extract.assert_not_called()
        # Audio chunking and Whisper transcription MUST be called
        mock_chunk.assert_called_once_with(fake_audio_path)
        mock_transcribe.assert_called_once()
        self.assertIn('transcribed speech', result['transcript_text'])

    @patch('app.services.gemini_service.summarize_transcript')
    @patch('app.services.email_service.send_webinar_summary_emails')
    def test_pipeline_failure_isolation_missing_media(self, mock_email, mock_gemini):
        """Verify pipeline immediately halts if media file does not exist, without calling Gemini or SMTP."""
        job = ProcessingJob(
            user_id=self.user_id,
            title='Missing Media Test',
            input_type='video',
            input_file_name='nonexistent.mp4',
            input_file_path=os.path.join(self.upload_dir, 'does_not_exist.mp4'),
            source_type='direct',
            overall_status='ready'
        )
        db.session.add(job)
        db.session.commit()

        res = pipeline_service.run_job_pipeline(job.id, self.app)

        self.assertFalse(res['success'])
        self.assertEqual(res['stage'], 'transcript')

        # Check job in DB
        db.session.expire_all()
        updated_job = db.session.get(ProcessingJob, job.id)
        self.assertEqual(updated_job.overall_status, 'failed')

        # Summarization and Email MUST NOT be invoked
        mock_gemini.assert_not_called()
        mock_email.assert_not_called()

    @patch('app.services.gemini_service.summarize_transcript')
    @patch('app.services.email_service.send_webinar_summary_emails')
    def test_pipeline_failure_isolation_retrieval_failed(self, mock_email, mock_gemini):
        """Verify pipeline halts before summarization if retrieval_status is 'failed'."""
        job = ProcessingJob(
            user_id=self.user_id,
            title='Retrieval Failed Test',
            input_type='video',
            input_file_name='failed_download.mp4',
            input_file_path=os.path.join(self.upload_dir, 'failed_download.mp4'),
            source_type='direct',
            retrieval_status='failed',
            retrieval_error='Connection refused by remote host',
            overall_status='ready'
        )
        db.session.add(job)
        db.session.commit()

        res = pipeline_service.run_job_pipeline(job.id, self.app)

        self.assertFalse(res['success'])
        self.assertEqual(res['stage'], 'retrieval')

        db.session.expire_all()
        updated_job = db.session.get(ProcessingJob, job.id)
        self.assertEqual(updated_job.overall_status, 'failed')
        self.assertIn('Connection refused', updated_job.error_message)

        mock_gemini.assert_not_called()
        mock_email.assert_not_called()

    @patch('app.services.transcript_service.process_webinar_to_transcript')
    def test_pipeline_idempotency_guard_completed_job(self, mock_transcript):
        """Verify pipeline skips execution for jobs already in 'completed' status."""
        job = ProcessingJob(
            user_id=self.user_id,
            title='Already Completed Job',
            input_type='transcript',
            input_file_name='sample.txt',
            input_file_path=os.path.join(self.upload_dir, 'sample.txt'),
            overall_status='completed'
        )
        db.session.add(job)
        db.session.commit()

        res = pipeline_service.run_job_pipeline(job.id, self.app)

        self.assertTrue(res['success'])
        self.assertEqual(res['overall_status'], 'completed')
        mock_transcript.assert_not_called()


if __name__ == '__main__':
    unittest.main()
