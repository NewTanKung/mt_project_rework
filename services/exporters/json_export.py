"""
JSON export service providing the meeting transcription summary file for downloads.
"""
import os
import json
import logging
from datetime import datetime
from services.transcription.transcript import build_summary
from services.exporters.common import safe_filename, get_export_dir
from database import query_one

logger = logging.getLogger(__name__)


def export_meeting_to_json(meeting_id: int) -> dict:
    """Export meeting transcription summary as JSON file."""
    try:
        meeting = query_one(
            "SELECT meeting_name FROM meetings WHERE meeting_id = ?",
            (meeting_id,)
        )
        if not meeting:
            return {'success': False, 'message': 'Meeting not found'}

        data = build_summary(meeting_id)
        export_dir = get_export_dir()
        clean_name = safe_filename(meeting['meeting_name'])
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"meeting_{meeting_id}_{clean_name}_{timestamp}.json"
        filepath = os.path.join(export_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {'success': True, 'filepath': filepath, 'filename': filename}

    except Exception as e:
        logger.exception("Error exporting JSON for meeting %d: %s", meeting_id, e)
        return {'success': False, 'message': str(e)}
