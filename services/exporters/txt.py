"""
Plain text meeting transcription export.
"""
import os
import logging
from datetime import datetime
from services.exporters.common import load_export_data, safe_filename, get_export_dir

logger = logging.getLogger(__name__)


def export_meeting_to_txt(meeting_id: int) -> dict:
    """Export meeting transcription to plain text."""
    try:
        meeting, transcriptions, part_names = load_export_data(meeting_id)
        if not meeting:
            return {'success': False, 'message': 'Meeting not found'}
        if not transcriptions:
            return {'success': False, 'message': 'No transcriptions found'}

        lines = [
            f"การประชุม: {meeting['meeting_name']}",
            f"วันที่: {meeting.get('meeting_date', '-')}",
            f"ผู้เข้าร่วม: {part_names}",
            "",
            "━" * 50,
            ""
        ]

        for t in transcriptions:
            speaker = t.get('speaker_name') or 'ไม่ระบุ'
            time_range = f"{t.get('start_time', '')} - {t.get('end_time', '')}".strip(" -")
            header = f"[{speaker}] {time_range}".strip()
            lines.extend([header, t.get('content', '') or '', ""])

        export_path = get_export_dir()
        clean_name = safe_filename(meeting['meeting_name'])
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"meeting_{meeting_id}_{clean_name}_{timestamp}.txt"
        filepath = os.path.join(export_path, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        return {'success': True, 'filepath': filepath, 'filename': filename}

    except Exception as e:
        logger.exception("Error exporting TXT for meeting %d: %s", meeting_id, e)
        return {'success': False, 'message': str(e)}
