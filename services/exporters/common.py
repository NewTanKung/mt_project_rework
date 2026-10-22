"""
Shared exporter utilities and data loader.
"""
import os
import re
from typing import Dict, Any, Tuple
from database import query_one
from services.storage_service import get_storage_settings
from services.meeting_service import get_meeting_participants
from services.transcription.transcript import get_transcript
from core.paths import resolve_path


def safe_filename(name: str) -> str:
    """Sanitize filename to prevent directory traversal or invalid OS characters."""
    if not name:
        return "meeting"
    # Replace invalid Windows filename characters
    cleaned = re.sub(r'[\\/*?:"<>|]', '_', name.strip())
    # Collapse multiple spaces or underscores
    cleaned = re.sub(r'[\s_]+', '_', cleaned)
    return cleaned[:100] or "meeting"


def get_export_dir() -> str:
    """Get absolute path to exports directory."""
    storage = get_storage_settings()
    export_path = resolve_path(storage.get('export_path', 'storage/exports'))
    os.makedirs(export_path, exist_ok=True)
    return export_path


def load_export_data(meeting_id: int) -> Tuple[Dict[str, Any] | None, list[dict], str]:
    """
    Load all meeting information, participants, and transcript items for export.
    Returns: (meeting_dict, transcript_items, participant_names_string)
    """
    meeting = query_one(
        "SELECT meeting_id, meeting_name, meeting_date, description, status FROM meetings WHERE meeting_id = ?",
        (meeting_id,)
    )
    if not meeting:
        return None, [], ""

    participants = get_meeting_participants(meeting_id)
    if participants:
        names = [p['participant_name'] for p in participants if p.get('participant_name')]
        part_str = ", ".join(names) if names else "-"
    else:
        part_str = "-"

    transcripts = get_transcript(meeting_id)
    return dict(meeting), transcripts, part_str
