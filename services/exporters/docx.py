"""
Microsoft Word (.docx) document export with participant headers and styled dialog blocks.
"""
import os
import logging
from datetime import datetime
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from services.exporters.common import load_export_data, safe_filename, get_export_dir

logger = logging.getLogger(__name__)


def export_meeting_to_docx(meeting_id: int) -> dict:
    """Export meeting transcription to Word document (.docx)."""
    try:
        meeting, transcriptions, part_names = load_export_data(meeting_id)
        if not meeting:
            return {'success': False, 'message': 'Meeting not found'}
        if not transcriptions:
            return {'success': False, 'message': 'No transcriptions found'}

        doc = Document()

        # Title
        title = doc.add_paragraph(meeting['meeting_name'])
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if title.runs:
            title.runs[0].font.size = Pt(18)
            title.runs[0].font.bold = True

        # Date & Description
        date_para = doc.add_paragraph(meeting.get('meeting_date', '-'))
        date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_paragraph('━' * 50)

        # Participants
        part_para = doc.add_paragraph()
        part_para.add_run('ผู้เข้าร่วม: ').bold = True
        part_para.add_run(part_names)

        doc.add_paragraph('━' * 50)
        doc.add_paragraph()

        # Dialog transcriptions
        for t in transcriptions:
            speaker = t.get('speaker_name') or 'ไม่ระบุ'
            time_range = f" ({t.get('start_time', '')} - {t.get('end_time', '')})" if t.get('start_time') else ''

            speaker_para = doc.add_paragraph()
            speaker_run = speaker_para.add_run(f"[{speaker}]")
            speaker_run.font.bold = True
            speaker_run.font.color.rgb = RGBColor(0, 102, 204)

            if time_range:
                time_run = speaker_para.add_run(time_range)
                time_run.font.size = Pt(9)
                time_run.font.color.rgb = RGBColor(128, 128, 128)

            content_para = doc.add_paragraph(t.get('content', '') or '')
            content_para.paragraph_format.left_indent = Pt(14)
            doc.add_paragraph()

        export_path = get_export_dir()
        clean_name = safe_filename(meeting['meeting_name'])
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"meeting_{meeting_id}_{clean_name}_{timestamp}.docx"
        filepath = os.path.join(export_path, filename)

        doc.save(filepath)
        return {'success': True, 'filepath': filepath, 'filename': filename}

    except Exception as e:
        logger.exception("Error exporting DOCX for meeting %d: %s", meeting_id, e)
        return {'success': False, 'message': str(e)}
