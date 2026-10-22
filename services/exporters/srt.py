"""
SubRip (.srt) subtitle format export.
"""
import os
import logging
from datetime import datetime
from services.exporters.common import load_export_data, safe_filename, get_export_dir

logger = logging.getLogger(__name__)


def _format_srt_timestamp(time_str: str) -> str:
    """Format HH:MM:SS into HH:MM:SS,000."""
    if not time_str:
        return "00:00:00,000"
    parts = time_str.split(':')
    if len(parts) == 3:
        return f"{time_str},000"
    elif len(parts) == 2:
        return f"00:{time_str},000"
    return "00:00:00,000"


def export_meeting_to_srt(meeting_id: int) -> dict:
    """Export meeting transcription to SRT subtitle format."""
    try:
        meeting, transcriptions, _ = load_export_data(meeting_id)
        if not meeting:
            return {'success': False, 'message': 'Meeting not found'}
        if not transcriptions:
            return {'success': False, 'message': 'No transcriptions found'}

        lines = []
        for idx, t in enumerate(transcriptions, 1):
            speaker = t.get('speaker_name') or 'ไม่ระบุ'
            start = _format_srt_timestamp(t.get('start_time'))
            end = _format_srt_timestamp(t.get('end_time'))
            content = t.get('content', '') or ''

            lines.extend([
                str(idx),
                f"{start} --> {end}",
                f"[{speaker}] {content}",
                ""
            ])

        export_path = get_export_dir()
        clean_name = safe_filename(meeting['meeting_name'])
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"meeting_{meeting_id}_{clean_name}_{timestamp}.srt"
        filepath = os.path.join(export_path, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        return {'success': True, 'filepath': filepath, 'filename': filename}

    except Exception as e:
        logger.exception("Error exporting SRT for meeting %d: %s", meeting_id, e)
        return {'success': False, 'message': str(e)}
