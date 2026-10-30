# Proposal: PDF Summary Generation and Secure Download

## Why

Following the successful implementation of Gemini AI summarization (Prompt 5), the platform produces structured educational summaries stored as JSON files on the server. However, students and academic operators require a portable, professionally formatted offline study document rather than raw JSON or web text. 

Implementing Prompt 6 provides automated, publication-quality PDF generation using ReportLab, converting structured Gemini summaries into clean, multi-page, student-friendly revision briefs. It also delivers an authenticated, authorized, and path-traversal-resistant download mechanism directly within the existing Flask dashboard.

## What Changes

- **Dependency Addition**: Add `reportlab>=4.1.0` to active dependencies in `requirements.txt` and install into the project virtual environment.
- **Dedicated PDF Generation Service (`app/services/pdf_service.py`)**:
  - Build a modular ReportLab document generation engine with custom page templates, A4 sizing, consistent typographic hierarchy, and cohesive college-themed styling.
  - Implement dynamic multi-page numbering via a two-pass `NumberedCanvas` ("Page X of Y") with WebinarAI branding and AI-generated notes notice in headers and footers.
  - Map structured summary fields into distinct visual sections: Header/Branding, Webinar Overview & Metadata, Executive Summary, Important Topics / Key Points, Technical Takeaways, Discussion Points / Action Items, Technical Terminology (tabular or callout cards), and Conclusion.
  - Gracefully omit missing, null, or empty sections without printing empty headings, raw JSON, Python `None`, or error placeholders.
  - Safely handle Unicode, special characters, and long text wrapping to prevent clipping, overflow, or font-missing exceptions.
- **Pipeline & Storage Integration**:
  - Persist generated PDFs into `storage/pdfs/` using server-controlled unique filenames (e.g., `webinar_summary_job_<id>_<uuid>.pdf`).
  - Update `ProcessingJob.pdf_path` (storing relative path) and `ProcessingJob.pdf_status` (`'generating'`, `'completed'`, or `'failed'`).
  - Maintain idempotency: avoid regenerating identical PDFs if a valid, readable PDF for the current summary already exists on disk.
- **Secure Download Route & Authorization**:
  - Expose protected download route (`/dashboard/jobs/<int:job_id>/download-pdf` and API alias) requiring authentication and verifying strict job ownership (tenant isolation).
  - Enforce server-side path traversal safeguards ensuring resolved file paths remain strictly contained within `storage/pdfs/`.
  - Provide fallback error handling if a PDF file is missing, corrupt, or still in generation.
- **Dashboard UI Enhancements (`app/templates/dashboard.html`)**:
  - Update the Registered Processing Jobs table to include a dedicated action column with a "Download PDF" button when `pdf_status == 'completed'`.
  - Display informative badges when PDF generation is pending, in-progress, or failed.
- **Automated Verification Suite (`tests/test_pdf_generation.py`)**:
  - Comprehensive unit and integration tests covering PDF generation, formatting, Unicode safety, multi-page layout, missing section omission, idempotency, path traversal defenses, and tenant-isolated download permissions.

## Capabilities

### New Capabilities

- `pdf-generation`: Generates professional educational summary PDFs via ReportLab from structured Gemini summaries, manages server-side storage in `storage/pdfs/`, updates job statuses in MySQL, and provides authenticated, tenant-isolated PDF downloads.

### Modified Capabilities

*(None. No existing specification requirements are being changed; this introduces new downstream capabilities building upon Prompt 5 summarization.)*

## Impact

- **Dependencies**: `reportlab>=4.1.0` added to `requirements.txt`.
- **Database**: No schema changes required (`pdf_status` and `pdf_path` columns already exist in `ProcessingJob`).
- **Filesystem**: PDFs written to `storage/pdfs/` (folder already initialized in `app/__init__.py`).
- **Security**: Strict user ownership check and path traversal verification on download endpoints.
- **API & UI**: New GET endpoint for downloading PDFs and updated dashboard job actions.
