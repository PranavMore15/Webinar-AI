"""
ReportLab PDF Generation Service for WebinarAI.
Compiles structured AI educational summaries into publication-quality A4 PDF briefs
with dynamic two-pass page numbering, responsive typography, and robust Unicode handling.
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable,
)
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

# Color Palette (Tailored Academic / Modern Design System)
COLOR_PRIMARY = colors.HexColor("#1e3a8a")     # Deep Indigo
COLOR_SECONDARY = colors.HexColor("#0284c7")   # Ocean Cyan
COLOR_TEXT_MAIN = colors.HexColor("#0f172a")   # Slate 900
COLOR_TEXT_MUTED = colors.HexColor("#475569")  # Slate 600
COLOR_BG_CARD = colors.HexColor("#f8fafc")     # Slate 50
COLOR_BORDER = colors.HexColor("#e2e8f0")      # Slate 200
COLOR_ACCENT = colors.HexColor("#059669")      # Emerald 600
COLOR_HIGHLIGHT = colors.HexColor("#dbeafe")   # Blue 100


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that records all page drawings and appends dynamic
    'Page X of Y' numbering and running headers/footers in a final pass.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(COLOR_TEXT_MUTED)

        # Running Header on pages after the first
        if self._pageNumber > 1:
            self.drawString(40, 812, "WebinarAI — AI-Generated Educational Study Notes")
            doc_title = getattr(self, '_doc_title', '')
            if doc_title:
                clean_header_title = doc_title[:45] + ("..." if len(doc_title) > 45 else "")
                self.drawRightString(555, 812, clean_header_title)
            self.setStrokeColor(COLOR_BORDER)
            self.setLineWidth(0.5)
            self.line(40, 804, 555, 804)

        # Running Footer on all pages
        self.setStrokeColor(COLOR_BORDER)
        self.setLineWidth(0.5)
        self.line(40, 42, 555, 42)

        self.drawString(40, 30, "WebinarAI | AI-Generated Study Notes — Derived from webinar transcript")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(555, 30, page_str)
        self.restoreState()


def sanitize_pdf_text(text: Any) -> str:
    """
    Normalizes text for safe inclusion in ReportLab Paragraph flowables:
    1. Handles None / non-string gracefully.
    2. Replaces Unicode typographic quotes, dashes, and bullets with safe characters.
    3. Escapes HTML/XML markup delimiters (&, <, >) to prevent ReportLab XML parser crashes.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    replacements = {
        '“': '"',
        '”': '"',
        '‘': "'",
        '’': "'",
        '—': ' - ',
        '–': ' - ',
        '…': '...',
        '•': '*',
        ' ': ' ',  # Non-breaking space
        '\r\n': '\n',
        '\r': '\n',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # Escape XML entities for ReportLab Paragraph markup
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return text.strip()


def get_pdf_styles() -> Dict[str, ParagraphStyle]:
    """Builds and returns the typography styles dictionary for the document."""
    base_styles = getSampleStyleSheet()

    styles = {
        'BrandingTag': ParagraphStyle(
            'BrandingTag',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=12,
            textColor=COLOR_PRIMARY,
            textTransform='uppercase',
            spaceAfter=4
        ),
        'DocTitle': ParagraphStyle(
            'DocTitle',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=20,
            leading=24,
            textColor=COLOR_PRIMARY,
            spaceAfter=4
        ),
        'DocSubtitle': ParagraphStyle(
            'DocSubtitle',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=COLOR_TEXT_MUTED,
            spaceAfter=12
        ),
        'SectionHeading': ParagraphStyle(
            'SectionHeading',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=16,
            textColor=COLOR_PRIMARY,
            spaceBefore=14,
            spaceAfter=6,
            keepWithNext=True
        ),
        'BodyText': ParagraphStyle(
            'BodyText',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=9.5,
            leading=14,
            textColor=COLOR_TEXT_MAIN,
            spaceAfter=6
        ),
        'BulletItem': ParagraphStyle(
            'BulletItem',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=9.5,
            leading=14,
            textColor=COLOR_TEXT_MAIN,
            leftIndent=14,
            firstLineIndent=-10,
            spaceAfter=4
        ),
        'MetaLabel': ParagraphStyle(
            'MetaLabel',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=11,
            textColor=COLOR_TEXT_MUTED,
            textTransform='uppercase'
        ),
        'MetaValue': ParagraphStyle(
            'MetaValue',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=12,
            textColor=COLOR_TEXT_MAIN
        ),
        'TermName': ParagraphStyle(
            'TermName',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=12,
            textColor=COLOR_PRIMARY
        ),
        'TermDef': ParagraphStyle(
            'TermDef',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=12,
            textColor=COLOR_TEXT_MAIN
        ),
        'TableHeader': ParagraphStyle(
            'TableHeader',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=11,
            textColor=colors.white
        ),
        'CalloutText': ParagraphStyle(
            'CalloutText',
            parent=base_styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=9.5,
            leading=14,
            textColor=COLOR_TEXT_MAIN
        )
    }
    return styles


def build_pdf_document(
    summary_data: Dict[str, Any],
    output_path: str,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Compiles a structured summary dictionary into an A4 PDF at output_path.
    Gracefully omits empty or missing sections.
    """
    if metadata is None:
        metadata = {}

    styles = get_pdf_styles()
    printable_width = 515.27  # A4 width (595.27) - 2 * 40pt margins

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=45,
        bottomMargin=50
    )

    story = []

    # Title extraction
    title = summary_data.get('title') or metadata.get('title') or 'Webinar Educational Summary'
    sanitized_title = sanitize_pdf_text(title)

    # 1. Header / Cover Section
    story.append(Paragraph("WebinarAI &bull; Educational Briefing", styles['BrandingTag']))
    story.append(Paragraph(sanitized_title, styles['DocTitle']))
    story.append(Paragraph("AI-Generated Webinar Study Notes &amp; Revision Material", styles['DocSubtitle']))

    # Metadata Strip (Table)
    gen_time = metadata.get('created_at')
    if isinstance(gen_time, datetime):
        formatted_date = gen_time.strftime("%B %d, %Y, %H:%M UTC")
    else:
        formatted_date = datetime.now(timezone.utc).strftime("%B %d, %Y, %H:%M UTC")

    input_source = metadata.get('input_type', '').capitalize()
    if input_source:
        source_display = f"{input_source} ({metadata.get('input_file_name', 'File')})"
    else:
        source_display = metadata.get('input_file_name', 'Uploaded Webinar Content')

    job_id = metadata.get('job_id', '')
    doc_id_display = f"JOB-#{job_id}" if job_id else "AI-SUMMARY"

    meta_table_data = [
        [
            Paragraph("Document Reference", styles['MetaLabel']),
            Paragraph("Generation Timestamp", styles['MetaLabel']),
            Paragraph("Content Source", styles['MetaLabel'])
        ],
        [
            Paragraph(sanitize_pdf_text(doc_id_display), styles['MetaValue']),
            Paragraph(sanitize_pdf_text(formatted_date), styles['MetaValue']),
            Paragraph(sanitize_pdf_text(source_display), styles['MetaValue'])
        ]
    ]

    meta_table = Table(
        meta_table_data,
        colWidths=[120, 180, 215.27],
        style=[
            ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_CARD),
            ('BOX', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]
    )
    story.append(meta_table)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceAfter=8))

    # 2. Executive Overview Section
    overview = summary_data.get('overview', '').strip()
    if overview:
        story.append(Paragraph("1. Executive Summary &amp; Overview", styles['SectionHeading']))
        story.append(Paragraph(sanitize_pdf_text(overview), styles['BodyText']))
        story.append(Spacer(1, 4))

    # 3. Important Topics / Key Points Section
    key_points = summary_data.get('key_points', [])
    valid_key_points = [p for p in key_points if str(p).strip()]
    if valid_key_points:
        story.append(Paragraph("2. Key Discussion Topics &amp; Themes", styles['SectionHeading']))
        for point in valid_key_points:
            story.append(Paragraph(f"&bull; {sanitize_pdf_text(point)}", styles['BulletItem']))
        story.append(Spacer(1, 4))

    # 4. Technical Takeaways Section
    takeaways = summary_data.get('takeaways', [])
    valid_takeaways = [t for t in takeaways if str(t).strip()]
    if valid_takeaways:
        story.append(Paragraph("3. Technical Takeaways &amp; Insights", styles['SectionHeading']))
        for item in valid_takeaways:
            story.append(Paragraph(f"&bull; {sanitize_pdf_text(item)}", styles['BulletItem']))
        story.append(Spacer(1, 4))

    # 5. Action Items Section (optional)
    action_items = summary_data.get('action_items', [])
    valid_action_items = [a for a in action_items if str(a).strip()]
    if valid_action_items:
        story.append(Paragraph("4. Action Items &amp; Practical Steps", styles['SectionHeading']))
        for act in valid_action_items:
            story.append(Paragraph(f"&bull; {sanitize_pdf_text(act)}", styles['BulletItem']))
        story.append(Spacer(1, 4))

    # 6. Technical Terminology Section (optional)
    terminology = summary_data.get('terminology', [])
    valid_terms = []
    if isinstance(terminology, list):
        for term_item in terminology:
            if isinstance(term_item, dict) and term_item.get('term'):
                valid_terms.append((term_item.get('term', ''), term_item.get('definition', '')))
            elif isinstance(term_item, str) and ':' in term_item:
                p = term_item.split(':', 1)
                valid_terms.append((p[0], p[1]))

    if valid_terms:
        term_flowables = [
            Paragraph("5. Technical Terminology &amp; Key Concepts", styles['SectionHeading'])
        ]
        term_table_data = [
            [
                Paragraph("Technical Term", styles['TableHeader']),
                Paragraph("Contextual Definition", styles['TableHeader'])
            ]
        ]
        for term_name, term_def in valid_terms:
            term_table_data.append([
                Paragraph(sanitize_pdf_text(term_name), styles['TermName']),
                Paragraph(sanitize_pdf_text(term_def), styles['TermDef'])
            ])

        term_table = Table(
            term_table_data,
            colWidths=[145.27, 370.0],
            style=[
                ('BACKGROUND', (0, 0), (-1, 0), COLOR_PRIMARY),
                ('BOX', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COLOR_BG_CARD]),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]
        )
        term_flowables.append(term_table)
        term_flowables.append(Spacer(1, 6))
        story.append(KeepTogether(term_flowables))

    # 7. Conclusion Section (optional)
    conclusion = summary_data.get('conclusion', '').strip()
    if conclusion:
        concl_flowables = [
            Paragraph("6. Summary Conclusion", styles['SectionHeading'])
        ]
        callout_table = Table(
            [[Paragraph(sanitize_pdf_text(conclusion), styles['CalloutText'])]],
            colWidths=[printable_width],
            style=[
                ('BACKGROUND', (0, 0), (-1, -1), COLOR_BG_CARD),
                ('BOX', (0, 0), (-1, -1), 0.75, COLOR_SECONDARY),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ]
        )
        concl_flowables.append(callout_table)
        story.append(KeepTogether(concl_flowables))

    # Ensure parent output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Attach document title to canvasmaker for running header
    def canvasmaker_factory(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c._doc_title = sanitized_title
        return c

    doc.build(story, canvasmaker=canvasmaker_factory)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"ReportLab failed to generate non-empty PDF at {output_path}")

    return output_path


def get_pdf_folder() -> str:
    """Returns absolute path to the configured PDF storage folder."""
    try:
        folder = current_app.config.get('PDF_FOLDER')
        if folder:
            os.makedirs(folder, exist_ok=True)
            return os.path.abspath(folder)
    except RuntimeError:
        pass

    default_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'storage', 'pdfs')
    os.makedirs(default_folder, exist_ok=True)
    return os.path.abspath(default_folder)


def resolve_pdf_full_path(pdf_path: str) -> Optional[str]:
    """
    Safely resolves a stored relative or absolute PDF path against PDF_FOLDER.
    Guarantees path traversal prevention (must stay inside PDF_FOLDER).
    """
    if not pdf_path:
        return None

    base_folder = get_pdf_folder()

    # If already an absolute path, verify it is inside base_folder
    if os.path.isabs(pdf_path):
        candidate = os.path.abspath(pdf_path)
    else:
        # Strip potential leading prefixes
        clean_rel = pdf_path.replace('\\', '/')
        if clean_rel.startswith('storage/pdfs/'):
            clean_rel = clean_rel[len('storage/pdfs/'):]
        elif clean_rel.startswith('pdfs/'):
            clean_rel = clean_rel[len('pdfs/'):]

        candidate = os.path.abspath(os.path.join(base_folder, clean_rel))

    # Verify candidate is strictly contained within base_folder
    try:
        common = os.path.commonpath([base_folder, candidate])
        if os.path.abspath(common) == os.path.abspath(base_folder):
            return candidate
    except ValueError:
        return None

    return None


def generate_job_pdf(job_or_id: Union[Any, int], force: bool = False) -> Dict[str, Any]:
    """
    Orchestrates idempotent PDF generation for a ProcessingJob:
    1. Validates that the job exists and its Gemini summary is completed.
    2. Checks idempotency: if valid PDF already exists, reuses it without re-writing.
    3. Generates server-unique PDF in storage/pdfs/.
    4. Updates job.pdf_path and job.pdf_status = 'completed'.
    5. Commits changes to the database.
    """
    from app.models import db, ProcessingJob
    from app.services.gemini_service import load_job_summary, sanitize_text

    if isinstance(job_or_id, int):
        job = db.session.get(ProcessingJob, job_or_id)
        if not job:
            raise ValueError(f"ProcessingJob #{job_or_id} not found.")
    else:
        job = job_or_id

    # 1. Idempotency Check
    if not force and job.pdf_status == 'completed' and job.pdf_path:
        resolved_existing = resolve_pdf_full_path(job.pdf_path)
        if resolved_existing and os.path.exists(resolved_existing) and os.path.getsize(resolved_existing) > 0:
            logger.info(f"Job #{job.id} PDF already exists at {resolved_existing}. Reusing existing file.")
            return {
                'success': True,
                'job_id': job.id,
                'pdf_path': job.pdf_path,
                'full_path': resolved_existing,
                'idempotent': True
            }

    try:
        job.pdf_status = 'generating'
        db.session.commit()

        # 2. Retrieve Summary Data
        summary_data = load_job_summary(job.id)
        if not summary_data:
            raise ValueError(f"Cannot generate PDF for Job #{job.id}: No AI summary file exists on server.")

        # 3. Prepare target filename and paths
        pdf_folder = get_pdf_folder()
        unique_suffix = uuid.uuid4().hex[:8]
        filename = f"webinar_summary_job_{job.id}_{unique_suffix}.pdf"
        output_full_path = os.path.join(pdf_folder, filename)
        relative_storage_path = f"pdfs/{filename}"

        metadata = {
            'job_id': job.id,
            'title': job.title or summary_data.get('title'),
            'input_type': job.input_type,
            'input_file_name': job.input_file_name,
            'created_at': job.created_at
        }

        # 4. Build Document
        build_pdf_document(
            summary_data=summary_data,
            output_path=output_full_path,
            metadata=metadata
        )

        # 5. Persist to Database
        job.pdf_path = relative_storage_path
        job.pdf_status = 'completed'
        job.error_message = None
        db.session.commit()

        logger.info(f"Successfully generated PDF for Job #{job.id} at {output_full_path}")
        return {
            'success': True,
            'job_id': job.id,
            'pdf_path': relative_storage_path,
            'full_path': output_full_path,
            'idempotent': False
        }

    except Exception as e:
        db.session.rollback()
        err_msg = sanitize_text(str(e))
        job.pdf_status = 'failed'
        job.error_message = f"PDF Generation Failed: {err_msg}"
        db.session.commit()
        logger.error(f"Failed to generate PDF for Job #{job.id}: {err_msg}")
        raise
