# Spec Delta: pdf-generation

## Purpose

Enables automated compilation of structured Gemini AI summaries into publication-quality educational PDF study briefs, manages safe server-side storage, updates processing job milestones, and provides secure, tenant-isolated downloads for authorized students and operators.

## ADDED Requirements

### Requirement: Professional Educational Summary PDF Generation
The system SHALL compile structured summary data into an A4 PDF document formatted with clear visual hierarchy, professional typography, consistent margins, and educational study note styling.

#### Scenario: Complete summary generation
- **WHEN** a valid processing job summary containing title, overview, key points, takeaways, action items, terminology, and conclusion is provided
- **THEN** the system generates a multi-page A4 PDF containing distinct sections for Header, Overview, Key Points, Technical Takeaways, Action Items, Technical Terminology, and Conclusion.

#### Scenario: Graceful omission of optional or missing sections
- **WHEN** a summary data structure has null, empty, or missing optional fields such as action items, terminology, or conclusion
- **THEN** the system omits those sections cleanly without printing empty headings, raw JSON representations, Python None literals, or error placeholders.

#### Scenario: Unicode and special character rendering
- **WHEN** the summary text contains Unicode punctuation, mathematical symbols, accented characters, or non-ASCII quotes
- **THEN** the PDF compiler formats and renders the text without character clipping, text overlapping, or unhandled encoding exceptions.

### Requirement: Document Branding and Two-Pass Dynamic Numbering
The system SHALL render standardized WebinarAI branding, document classification metadata, and dynamic two-pass page numbering ("Page X of Y") across all pages of the document.

#### Scenario: Running header and title presentation
- **WHEN** the PDF is generated
- **THEN** each page displays the WebinarAI platform identifier, the webinar title (or neutral fallback), the generation timestamp, and the AI-generated study notes subtitle.

#### Scenario: Running footer with total page count
- **WHEN** a multi-page PDF document is produced
- **THEN** every page displays a standardized footer with dynamic "Page X of Y" page numbers and a prominent disclaimer stating that notes are AI-generated.

### Requirement: Server Storage and Idempotent Persistence
The system SHALL store generated PDFs in the configured server storage directory using unique filenames, update processing job records in MySQL, and support idempotent execution.

#### Scenario: Successful PDF persistence and job status update
- **WHEN** PDF generation completes for a processing job
- **THEN** the PDF is stored under `storage/pdfs/` with a server-generated filename, `ProcessingJob.pdf_path` is updated with the relative path, and `ProcessingJob.pdf_status` is set to 'completed'.

#### Scenario: Idempotent generation call
- **WHEN** PDF generation is requested for a job that already has an existing, readable PDF file corresponding to the current summary
- **THEN** the system reuses the existing PDF file without re-generating duplicates or re-writing disk artifacts.

#### Scenario: Generation failure handling
- **WHEN** PDF generation encounters a fatal layout or filesystem error
- **THEN** the system updates `ProcessingJob.pdf_status` to 'failed', records a sanitized error message on the job, and raises a controlled exception.

### Requirement: Authenticated and Authorized PDF Download
The system SHALL provide a protected HTTP endpoint to download generated summary PDFs, enforcing user authentication, tenant isolation, and path traversal prevention.

#### Scenario: Authorized job owner downloads PDF
- **WHEN** an authenticated user requests the PDF download for a job they own and the PDF exists
- **THEN** the server returns the PDF file with appropriate `application/pdf` headers and attachment disposition.

#### Scenario: Unauthorized cross-tenant download rejected
- **WHEN** an authenticated user attempts to download a PDF belonging to a processing job owned by another user
- **THEN** the server rejects the request with HTTP 403 Forbidden.

#### Scenario: Unauthenticated download rejected
- **WHEN** an unauthenticated client requests a PDF download endpoint
- **THEN** the server denies access and redirects to the login route or returns HTTP 401/403.

#### Scenario: Path traversal defense
- **WHEN** a client attempts path traversal via URL manipulation or forged path parameters
- **THEN** the server resolves the target path strictly within the configured PDF folder and returns HTTP 400 or 404 for any out-of-bounds path.

### Requirement: Dashboard Integration and Action Controls
The system SHALL expose downloadable links and stage status indicators on the user dashboard interface for all processing jobs.

#### Scenario: Download button displayed when PDF is ready
- **WHEN** an authenticated user views the dashboard and a processing job has `pdf_status == 'completed'` and a valid `pdf_path`
- **THEN** the job list displays an active "Download PDF" button linked to the secure download route.

#### Scenario: Status indicator displayed when PDF is not ready
- **WHEN** a job's PDF is pending, generating, or failed
- **THEN** the job list displays an appropriate status badge and prevents download until generation succeeds.
