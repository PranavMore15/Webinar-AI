"""
Automated Pipeline Execution Service for WebinarAI.
Orchestrates sequential end-to-end execution of a ProcessingJob:
1. Transcript Ingestion / Speech-to-Text (transcript_service)
2. Gemini AI Structured Summarization (gemini_service)
3. ReportLab PDF Brief Compilation (pdf_service)
4. SMTP Summary Email Distribution (email_service)

Executes asynchronously in a daemon thread so API responses return immediately
and client-side dashboards receive real-time stage progress updates.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from flask import Flask

logger = logging.getLogger(__name__)


def run_job_pipeline(job_id: int, app: Flask) -> Dict[str, Any]:
    """
    Executes all processing and delivery stages sequentially for a given ProcessingJob.
    Updates stage statuses and overall_status in MySQL at each milestone.
    """
    from app.models import db, ProcessingJob
    from app.services import transcript_service, gemini_service, pdf_service, email_service

    with app.app_context():
        job = db.session.get(ProcessingJob, job_id)
        if not job:
            logger.error(f"[Pipeline] Job #{job_id} not found.")
            return {'success': False, 'error': f"Job #{job_id} not found."}

        logger.info(f"[Pipeline] Starting automated execution for Job #{job.id} ('{job.title}')...")

        # ---------------------------------------------------------------------
        # Stage 1: Transcript Ingestion / Transcription
        # ---------------------------------------------------------------------
        try:
            job.overall_status = 'transcribing'
            job.transcript_status = 'processing'
            job.error_message = None
            db.session.commit()

            logger.info(f"[Pipeline] Job #{job.id}: Processing webinar transcript ({job.input_type})...")
            transcript_res = transcript_service.process_webinar_to_transcript(
                job.input_type,
                job.input_file_path
            )
            transcript_text = transcript_res.get('transcript_text', '')

            job.transcript_status = 'completed'
            db.session.commit()
            logger.info(f"[Pipeline] Job #{job.id}: Transcript processing completed.")

        except Exception as e:
            db.session.rollback()
            err_msg = str(e)
            logger.error(f"[Pipeline] Job #{job.id}: Transcript processing failed: {err_msg}", exc_info=True)
            job = db.session.get(ProcessingJob, job_id)
            if job:
                job.transcript_status = 'failed'
                job.overall_status = 'failed'
                job.error_message = f"Transcript Ingestion Failed: {err_msg}"
                db.session.commit()
            return {'success': False, 'stage': 'transcript', 'error': err_msg}

        # ---------------------------------------------------------------------
        # Stage 2: Gemini AI Summarization
        # ---------------------------------------------------------------------
        try:
            job = db.session.get(ProcessingJob, job_id)
            job.overall_status = 'summarizing'
            job.summary_status = 'generating'
            db.session.commit()

            logger.info(f"[Pipeline] Job #{job.id}: Invoking Gemini AI summarization...")
            title_hint = job.title or job.input_file_name
            summary_result = gemini_service.summarize_transcript(
                transcript_text=transcript_text,
                title_hint=title_hint
            )
            gemini_service.save_job_summary(job.id, summary_result)

            job.summary_status = 'completed'
            db.session.commit()
            logger.info(f"[Pipeline] Job #{job.id}: Gemini summarization completed successfully.")

        except Exception as e:
            db.session.rollback()
            err_msg = str(e)
            logger.error(f"[Pipeline] Job #{job.id}: Summarization failed: {err_msg}", exc_info=True)
            job = db.session.get(ProcessingJob, job_id)
            if job:
                job.summary_status = 'failed'
                job.overall_status = 'failed'
                job.error_message = f"AI Summarization Failed: {err_msg}"
                db.session.commit()
            return {'success': False, 'stage': 'summary', 'error': err_msg}

        # ---------------------------------------------------------------------
        # Stage 3: PDF Document Compilation
        # ---------------------------------------------------------------------
        try:
            job = db.session.get(ProcessingJob, job_id)
            job.overall_status = 'generating_pdf'
            job.pdf_status = 'generating'
            db.session.commit()

            logger.info(f"[Pipeline] Job #{job.id}: Compiling PDF summary brief...")
            pdf_res = pdf_service.generate_job_pdf(job, force=True)

            job.pdf_status = 'completed'
            db.session.commit()
            logger.info(f"[Pipeline] Job #{job.id}: PDF generated successfully at {pdf_res.get('pdf_path')}.")

        except Exception as e:
            db.session.rollback()
            err_msg = str(e)
            logger.error(f"[Pipeline] Job #{job.id}: PDF generation failed: {err_msg}", exc_info=True)
            job = db.session.get(ProcessingJob, job_id)
            if job:
                job.pdf_status = 'failed'
                job.overall_status = 'failed'
                job.error_message = f"PDF Compilation Failed: {err_msg}"
                db.session.commit()
            return {'success': False, 'stage': 'pdf', 'error': err_msg}

        # ---------------------------------------------------------------------
        # Stage 4: SMTP Email Delivery
        # ---------------------------------------------------------------------
        try:
            job = db.session.get(ProcessingJob, job_id)
            total_recipients = job.recipients.count()

            if total_recipients > 0:
                job.overall_status = 'sending_emails'
                # Do NOT set job.email_status = 'sending' here because
                # email_service.send_webinar_summary_emails enforces a concurrency guard
                # verifying that email_status != 'sending' before atomically setting it.
                db.session.commit()

                logger.info(f"[Pipeline] Job #{job.id}: Delivering emails to {total_recipients} recipient(s)...")
                email_res = email_service.send_webinar_summary_emails(job.id, retry_failed_only=False)

                db.session.expire_all()
                job = db.session.get(ProcessingJob, job_id)
                sent_cnt = email_res.get('sent_count', 0)
                failed_cnt = email_res.get('failed_count', 0)

                # Ensure terminal statuses are reflected even if email_service was mocked or returned results
                if failed_cnt == 0 and sent_cnt > 0:
                    job.email_status = 'completed'
                    job.overall_status = 'completed'
                    job.completed_at = datetime.now(timezone.utc)
                elif sent_cnt > 0:
                    job.email_status = 'partially_sent'
                    job.overall_status = 'partially_sent'
                elif total_recipients > 0 and failed_cnt > 0:
                    job.email_status = 'failed'
                    job.overall_status = 'failed'

                job.error_message = None
                db.session.commit()

                logger.info(
                    f"[Pipeline] Job #{job.id}: Email delivery finished (sent={sent_cnt}, failed={failed_cnt}). "
                    f"Overall status: {job.overall_status}, Email status: {job.email_status}"
                )
            else:
                job.overall_status = 'completed'
                job.completed_at = datetime.now(timezone.utc)
                job.error_message = None
                db.session.commit()
                logger.info(f"[Pipeline] Job #{job.id}: No recipients registered; marked completed.")

            return {'success': True, 'job_id': job.id, 'overall_status': job.overall_status}

        except Exception as e:
            db.session.rollback()
            err_msg = str(e)
            logger.error(f"[Pipeline] Job #{job.id}: Email delivery failed: {err_msg}", exc_info=True)
            job = db.session.get(ProcessingJob, job_id)
            if job:
                job.email_status = 'failed'
                job.overall_status = 'failed'
                job.error_message = f"Email Delivery Failed: {err_msg}"
                db.session.commit()
            return {'success': False, 'stage': 'email', 'error': err_msg}


def start_job_pipeline_async(job_id: int, app: Flask) -> threading.Thread:
    """
    Spawns a background worker thread to execute the full pipeline asynchronously.
    Returns the started threading.Thread instance.
    """
    thread = threading.Thread(
        target=run_job_pipeline,
        args=(job_id, app),
        name=f"job-pipeline-worker-{job_id}",
        daemon=True
    )
    thread.start()
    logger.info(f"[Pipeline] Dispatched async background worker for Job #{job_id}.")
    return thread
