# Tasks: PDF Summary Generation and Secure Download

## 1. Dependency & Storage Configuration

- [x] 1.1 Add `reportlab>=4.1.0` to active dependencies in `requirements.txt` and install into `.venv`; verify installation with `python -c "import reportlab; print(reportlab.__version__)"`.
- [x] 1.2 Verify `Config.PDF_FOLDER` storage path and directory initialization in `app/config.py` and `app/__init__.py`; verify directory existence.

## 2. ReportLab PDF Service Implementation

- [x] 2.1 Implement `NumberedCanvas` in `app/services/pdf_service.py` to record canvas operations and draw dynamic "Page X of Y" and AI-generated notes notice in running footers.
- [x] 2.2 Implement typography styling, color palette, and `sanitize_pdf_text` helper in `app/services/pdf_service.py` to normalize Unicode smart quotes, dashes, and symbols for crash-free encoding.
- [x] 2.3 Implement modular section flowable builders (Branding Header, Overview, Key Points, Technical Takeaways, Action Items, Technical Terminology table/cards, and Conclusion) with graceful omission of empty or missing sections.
- [x] 2.4 Implement `build_pdf_document(summary_data, output_path, metadata=None)` in `app/services/pdf_service.py` generating structured multi-page A4 PDFs; verify generation with sample summary data.
- [x] 2.5 Implement `generate_job_pdf(job, force=False)` with idempotency verification, server-controlled unique filename generation in `storage/pdfs/`, transactional database update of `ProcessingJob.pdf_path` and `ProcessingJob.pdf_status = 'completed'`, and error rollback to `'failed'`.
- [x] 2.6 Export `pdf_service` in `app/services/__init__.py` and verify clean module imports.

## 3. Routes & Security Enforcement

- [x] 3.1 Implement protected download routes `/dashboard/jobs/<int:job_id>/download-pdf` and `/api/jobs/<int:job_id>/download-pdf` in `app/routes/dashboard_routes.py` enforcing `@user_required`, strict job ownership, and path traversal resolution safeguards.
- [x] 3.2 Ensure admin diagnostic oversight in `app/routes/admin_routes.py` accurately reflects PDF status and file readiness without breaking role separation.

## 4. Dashboard UI Integration

- [x] 4.1 Update the Registered Processing Jobs table in `app/templates/dashboard.html` to add a PDF action column with an active "Download PDF" button when `pdf_status == 'completed'` and appropriate status badges when pending or failed.

## 5. Automated Verification & Regression Testing

- [x] 5.1 Create `tests/test_pdf_generation.py` containing automated unit and integration tests covering document generation, styling, Unicode normalization, missing section omission, idempotency, path traversal defenses, unauthenticated rejection, and multi-tenant isolation.
- [x] 5.2 Execute complete test suite across all test modules to verify zero regressions and complete pass status.
- [x] 5.3 Update `PROJECT_STATUS.md` documenting Prompt 6 completion, newly verified endpoints, and test results.
