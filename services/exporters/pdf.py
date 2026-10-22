"""
PDF Export Service with Thai font support (THSarabunPSK).
Reads transcription data from unified export loader and formats professional PDF report.
"""
import os
import logging
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

from services.exporters.common import load_export_data, safe_filename, get_export_dir
from config import BASE_DIR

logger = logging.getLogger(__name__)

_fonts_registered = False
_thai_font_available = False


def _register_thai_fonts():
    """Register Thai fonts for PDF generation - THSarabunPSK."""
    global _fonts_registered, _thai_font_available

    if _fonts_registered:
        return

    try:
        font_dir = os.path.join(BASE_DIR, 'font', 'THSarabunPSK')
        font_paths = {
            'normal': os.path.join(font_dir, 'THSarabun.ttf'),
            'bold': os.path.join(font_dir, 'THSarabun Bold.ttf'),
            'italic': os.path.join(font_dir, 'THSarabun Italic.ttf'),
            'bolditalic': os.path.join(font_dir, 'THSarabun BoldItalic.ttf')
        }

        font_found = False
        bold_found = False

        if os.path.exists(font_paths['normal']):
            pdfmetrics.registerFont(TTFont('ThaiFont', font_paths['normal']))
            font_found = True

        if os.path.exists(font_paths['bold']):
            pdfmetrics.registerFont(TTFont('ThaiFontBold', font_paths['bold']))
            bold_found = True

        _thai_font_available = font_found and bold_found
        _fonts_registered = True
        logger.info("Thai fonts registered successfully: %s", _thai_font_available)
    except Exception as e:
        logger.exception("Error registering Thai fonts: %s", e)
        _fonts_registered = True
        _thai_font_available = False


def _create_styles():
    """Create paragraph styles with Thai font."""
    styles = getSampleStyleSheet()
    font_name = 'ThaiFont' if _thai_font_available else 'Helvetica'
    font_bold = 'ThaiFontBold' if _thai_font_available else 'Helvetica-Bold'

    styles.add(ParagraphStyle(
        name='CustomTitle',
        fontName=font_bold,
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1a1a1a')
    ))
    styles.add(ParagraphStyle(
        name='CustomHeading1',
        fontName=font_bold,
        fontSize=15,
        leading=19,
        textColor=colors.HexColor('#2c3e50'),
        spaceBefore=8,
        spaceAfter=4
    ))
    styles.add(ParagraphStyle(
        name='CustomBody',
        fontName=font_name,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#333333')
    ))
    styles.add(ParagraphStyle(
        name='SpeakerName',
        fontName=font_bold,
        fontSize=12,
        leading=15,
        textColor=colors.HexColor('#0066cc')
    ))
    styles.add(ParagraphStyle(
        name='TimeInfo',
        fontName=font_name,
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#7f8c8d'),
        alignment=TA_RIGHT
    ))
    styles.add(ParagraphStyle(
        name='TableHeader',
        fontName=font_bold,
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#ffffff'),
        alignment=TA_CENTER
    ))
    styles.add(ParagraphStyle(
        name='TableCell',
        fontName=font_name,
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#333333')
    ))
    return styles


def export_meeting_to_pdf(meeting_id: int) -> dict:
    """Export meeting transcription to PDF."""
    try:
        _register_thai_fonts()
        meeting, transcriptions, part_names = load_export_data(meeting_id)

        if not meeting:
            return {'success': False, 'message': 'Meeting not found'}
        if not transcriptions:
            return {'success': False, 'message': 'No transcriptions found'}

        export_dir = get_export_dir()
        clean_name = safe_filename(meeting['meeting_name'])
        pdf_filename = f"meeting_{meeting_id}_{clean_name}_transcription.pdf"
        pdf_filepath = os.path.join(export_dir, pdf_filename)

        doc = SimpleDocTemplate(
            pdf_filepath,
            pagesize=A4,
            rightMargin=20 * mm,
            leftMargin=20 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm
        )

        styles = _create_styles()
        story = []

        # Title
        story.append(Paragraph(f"การประชุม: {meeting['meeting_name']}", styles['CustomTitle']))
        story.append(Spacer(1, 6 * mm))

        # Meeting info table
        info_data = [
            [
                Paragraph('<b>วันที่ประชุม:</b>', styles['CustomBody']),
                Paragraph(meeting.get('meeting_date') or '-', styles['CustomBody'])
            ],
            [
                Paragraph('<b>ผู้เข้าร่วม:</b>', styles['CustomBody']),
                Paragraph(part_names, styles['CustomBody'])
            ]
        ]
        info_table = Table(info_data, colWidths=[40 * mm, 130 * mm])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9fa')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e9ecef')),
            ('PADDING', (0, 0), (-1, -1), 3 * mm),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 8 * mm))

        # Transcription section
        story.append(Paragraph("บันทึกการประชุม", styles['CustomHeading1']))
        story.append(Spacer(1, 4 * mm))

        dialog_data = [
            [
                Paragraph("<b>เวลา</b>", styles['TableHeader']),
                Paragraph("<b>ผู้พูด</b>", styles['TableHeader']),
                Paragraph("<b>ข้อความ</b>", styles['TableHeader'])
            ]
        ]

        for t in transcriptions:
            speaker = t.get('speaker_name') or 'ไม่ระบุ'
            time_range = f"{t.get('start_time', '')} - {t.get('end_time', '')}".strip(" -") or "-"
            content = t.get('content', '') or '-'

            dialog_data.append([
                Paragraph(time_range, styles['TableCell']),
                Paragraph(speaker, styles['TableCell']),
                Paragraph(content, styles['TableCell'])
            ])

        dialog_table = Table(dialog_data, colWidths=[35 * mm, 35 * mm, 100 * mm], repeatRows=1)
        dialog_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fdfefe')]),
            ('PADDING', (0, 0), (-1, -1), 2.5 * mm),
        ]))
        story.append(dialog_table)

        doc.build(story)
        logger.info("PDF exported successfully to %s", pdf_filepath)
        return {'success': True, 'filepath': pdf_filepath, 'filename': pdf_filename}

    except Exception as e:
        logger.exception("Error exporting PDF for meeting %d: %s", meeting_id, e)
        return {'success': False, 'message': str(e)}
