# Design: ReportLab PDF Summary Generation and Secure Download

## Context

In Prompt 5, the Google Gemini AI summarization pipeline was completed, outputting structured JSON summaries saved under `storage/summaries/job_<job_id>_summary.json`. 

The `ProcessingJob` database model already has `pdf_status` (default `'pending'`) and `pdf_path` (nullable string) columns, and `Config.PDF_FOLDER` (`storage/pdfs`) is initialized on application startup. However, ReportLab is not yet installed in `.venv`, no PDF compilation service exists, and the dashboard has no PDF download endpoints or actions.

See [proposal.md](file:///d:/WebinarAI/openspec/changes/pdf-summary-generation/proposal.md) for problem motivation and scope boundaries.

## Goals / Non-Goals

**Goals:**
- Add `reportlab>=4.1.0` to `requirements.txt` and install into the project virtual environment.
- Create a dedicated, modular `app/services/pdf_service.py` to compile structured JSON summaries into professional A4 educational briefs.
- Implement a two-pass `NumberedCanvas` rendering dynamic "Page X of Y" page counts, running headers with WebinarAI branding, and footers with AI-generation disclaimers.
- Gracefully format and organize summary sections (Header, Overview, Key Points, Technical Takeaways, Action Items, Terminology, Conclusion) while cleanly omitting missing/empty sections.
- Safely handle Unicode, smart quotes, mathematical symbols, and wrapping to prevent clipping or font encoding crashes.
- Persist PDFs in `storage/pdfs/` with server-controlled unique filenames and update `ProcessingJob.pdf_path` and `ProcessingJob.pdf_status` in MySQL.
- Support idempotent generation so repeated requests do not duplicate files.
- Expose an authenticated, tenant-isolated download route `/dashboard/jobs/<int:job_id>/download-pdf` (and `/api/jobs/<int:job_id>/download-pdf`) with strict path traversal verification.
- Update `dashboard.html` to display a "Download PDF" button in the registered jobs table when `pdf_status == 'completed'`.
- Deliver automated unit and integration tests verifying styling, layout, Unicode safety, missing section handling, tenant isolation, and traversal defenses.

**Non-Goals:**
- Email distribution (reserved for Prompt 7: SMTP Email Delivery).
- Asynchronous task queuing / Celery (reserved for Prompt 8: Job Orchestration).
- Altering the MySQL database schema or dropping existing tables.
- Modifying the Gemini prompt engineering or transcript parsing from previous prompts.

## Decisions

### Decision 1: ReportLab SimpleDocTemplate with Flowables
**Choice**: Use ReportLab's `SimpleDocTemplate` with flowable elements (`Paragraph`, `Spacer`, `Table`, `KeepTogether`, `HRFlowable`) and standard `getSampleStyleSheet()`.
**Rationale**: High-level flowables manage automatic page breaking, margins, and text wrapping cleanly, avoiding fragile manual canvas coordinate arithmetic.
**Alternatives Considered**: 
- Low-level `canvas.Canvas` drawing: Required calculating every line break and Y-offset manually, high risk of text clipping and page overflow.
- WeasyPrint / pdfkit: Requires heavy external C-libraries (Pango/Cairo or wkhtmltopdf) not installed or suitable for standard Python environments on Windows.

### Decision 2: Two-Pass NumberedCanvas for Dynamic Page Numbering
**Choice**: Subclass `reportlab.pdfgen.canvas.Canvas` to intercept `showPage()` and defer footer rendering until `save()`, allowing dynamic computation of total page count ("Page X of Y").
**Rationale**: ReportLab's flowable pipeline does not know the total page count on page 1. The standard two-pass canvas pattern allows exact "Page X of Y" numbering without guessing or running duplicate compilation passes.
**Alternatives Considered**:
- Single-pass "Page X" (without total): Looks less professional for academic study notes.
- Pre-compiling the document twice: Doubled CPU and memory usage.

### Decision 3: Character Normalization & Unicode Defense
**Choice**: Implement a text cleaning helper (`sanitize_pdf_text`) that normalizes Unicode punctuation (e.g., smart quotes `“` `”` to `"`, apostrophes `’` to `'`, em/en-dashes `—` `–` to `-`, bullets `•` to `*`, and non-breaking spaces) before feeding text into ReportLab Paragraphs.
**Rationale**: Built-in Helvetica fonts in ReportLab raise `UnicodeEncodeError` when encountering characters outside the Latin-1 / WinAnsiEncoding scope. Normalization guarantees zero-crash rendering across diverse webinar transcripts without requiring external TTF font packaging.
**Alternatives Considered**:
- Bundling external TrueType fonts: Adds binary font dependencies and path management complexity across development environments.

### Decision 4: Idempotent Server-Side Persistence
**Choice**: Store relative paths (`pdfs/webinar_summary_job_<id>_<uuid>.pdf`) in `ProcessingJob.pdf_path` and save actual files under `storage/pdfs/`. If a job already has a valid, readable PDF file at that path matching the current summary, re-use it instead of re-generating.
**Rationale**: Avoids redundant file generation on page reloads, prevents disk bloat, and aligns with the idempotent processing guidelines in the project specification.

### Decision 5: Multi-Tenant Authorization and Traversal Defense
**Choice**: Download endpoints verify `session.get('user_id')`, load the job, verify `job.user_id == session['user_id']` (or user is admin), resolve the filesystem path against `Config.PDF_FOLDER`, and assert using `os.path.commonpath` or `startswith` that the file resides strictly within the configured PDF directory before calling `send_file`.
**Rationale**: Strictly prevents unauthorized cross-tenant data leakage and defends against path traversal (`../`) attacks.

## Risks / Trade-offs

- **[Risk]** Long technical terms or unbroken strings in transcripts causing table cell overflow.  
  → **Mitigation**: Wrap all table cell contents in `Paragraph` flowables with explicit column widths and automatic word wrapping.
- **[Risk]** Summary JSON missing optional sections (e.g., action items or terminology).  
  → **Mitigation**: Implement strict section conditional checks. If a list or string is empty or None, omit the heading and content entirely without visual gaps.
- **[Risk]** PDF generation crashes due to sudden filesystem permission error or disk full.  
  → **Mitigation**: Wrap generation in try-except; on failure, update `job.pdf_status = 'failed'` with a sanitized error message and clean up partial files.
