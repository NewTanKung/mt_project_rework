"""
Meeting service - Meeting creation, preset management, and status updates.
"""
import os
import shutil
import time
import logging
from datetime import datetime
from database import query_all, query_one, execute, transaction
from services.storage_service import get_storage_settings

logger = logging.getLogger(__name__)


def get_all_meetings(search: str | None = None, status: str | None = None) -> list[dict]:
    """
    Get all meetings with optional search and status filters.
    Includes has_transcription boolean flag calculated in SQL to prevent N+1 queries.
    """
    query = """
        SELECT m.*,
               EXISTS(SELECT 1 FROM text_file tf WHERE tf.meeting_id = m.meeting_id) as has_transcription
        FROM meetings m
        WHERE 1=1
    """
    params = []
    
    if search:
        query += " AND m.meeting_name LIKE ?"
        params.append(f"%{search}%")
        
    if status:
        query += " AND m.status = ?"
        params.append(status)
        
    query += " ORDER BY m.meeting_date DESC, m.start_time DESC"
    
    rows = query_all(query, tuple(params) if params else ())
    for r in rows:
        r['has_transcription'] = bool(r.get('has_transcription'))
    return rows


def get_meeting_by_id(meeting_id: int) -> dict | None:
    """Get meeting by ID along with participant list."""
    meeting = query_one("SELECT * FROM meetings WHERE meeting_id = ?", (meeting_id,))
    if not meeting:
        return None
        
    meeting_dict = dict(meeting)
    meeting_dict['participants'] = get_meeting_participants(meeting_id)
    return meeting_dict


def get_or_create_participant(name: str, role: str = 'สมาชิก') -> int:
    """Get participant ID by name, or create if not exists."""
    existing = query_one(
        "SELECT participant_id FROM participants WHERE participant_name = ?",
        (name,)
    )
    if existing:
        return existing['participant_id']
        
    return execute(
        "INSERT INTO participants (participant_name, role) VALUES (?, ?)",
        (name, role)
    )


def create_meeting(meeting_name: str,
                   description: str,
                   meeting_location: str,
                   meeting_date: str,
                   participants: list[dict],
                   channel_preset_id: int | None = None) -> int:
    """
    Create a new meeting with participant mappings inside an atomic transaction.
    """
    with transaction():
        meeting_id = execute(
            """INSERT INTO meetings (
                meeting_name, description, meeting_location, 
                channel_preset_id, meeting_date, status
            ) VALUES (?, ?, ?, ?, ?, 'registered')""",
            (meeting_name, description, meeting_location, channel_preset_id, meeting_date)
        )
        
        # If no preset selected, create an internal one for this meeting
        if not channel_preset_id:
            temp_name = f"Meeting_{meeting_id}_preset_{int(time.time())}"
            channel_preset_id = execute(
                "INSERT INTO channel_preset (preset_name, show) VALUES (?, 0)",
                (temp_name,)
            )
            execute(
                "UPDATE meetings SET channel_preset_id = ? WHERE meeting_id = ?",
                (channel_preset_id, meeting_id)
            )
            
        for participant in participants:
            p_id = get_or_create_participant(
                participant['name'],
                participant.get('role', 'สมาชิก')
            )
            
            existing = query_one(
                "SELECT id FROM preset_member WHERE preset_id = ? AND user_id = ?",
                (channel_preset_id, p_id)
            )
            if not existing:
                execute(
                    "INSERT INTO preset_member (preset_id, user_id, channel_id) VALUES (?, ?, ?)",
                    (channel_preset_id, p_id, participant.get('channel_id'))
                )

    return meeting_id


def update_meeting(meeting_id: int, meeting_name: str | None = None, description: str | None = None) -> bool:
    """Update meeting details."""
    updates = []
    params = []
    
    if meeting_name:
        updates.append("meeting_name = ?")
        params.append(meeting_name)
        
    if description is not None:
        updates.append("description = ?")
        params.append(description)
        
    if not updates:
        return False
        
    params.append(meeting_id)
    execute(f"UPDATE meetings SET {', '.join(updates)} WHERE meeting_id = ?", tuple(params))
    return True


def delete_meeting(meeting_id: int) -> bool:
    """
    Delete a meeting and all associated database records and disk files (cascade cleanup).
    """
    with transaction():
        execute("DELETE FROM participant_meeting WHERE meeting_id = ?", (meeting_id,))
        execute("DELETE FROM voice_file WHERE meeting_id = ?", (meeting_id,))
        execute("DELETE FROM text_file WHERE meeting_id = ?", (meeting_id,))
        execute("DELETE FROM transcription_jobs WHERE meeting_id = ?", (meeting_id,))
        execute("DELETE FROM meetings WHERE meeting_id = ?", (meeting_id,))
        
    # Clean up files on disk
    try:
        storage = get_storage_settings()
        audio_folder = os.path.join(storage['audio_path'], f"meeting_{meeting_id}")
        if os.path.exists(audio_folder):
            shutil.rmtree(audio_folder, ignore_errors=True)
            
        trans_folder = os.path.join(storage['transcription_path'], f"meeting_{meeting_id}")
        if os.path.exists(trans_folder):
            shutil.rmtree(trans_folder, ignore_errors=True)
    except Exception as e:
        logger.error("Error cleaning up folders for meeting %d: %s", meeting_id, e)
        
    return True


def get_meeting_participants(meeting_id: int) -> list[dict]:
    """Get participants for a meeting with channel info."""
    return query_all(
        """SELECT 
            p.participant_id,
            p.participant_name,
            p.role,
            pm.channel_id,
            ac.name as channel_name
        FROM meetings m
        JOIN preset_member pm ON pm.preset_id = m.channel_preset_id
        JOIN participants p ON p.participant_id = pm.user_id
        LEFT JOIN audio_channels ac ON ac.id = pm.channel_id
        WHERE m.meeting_id = ?
        ORDER BY p.participant_id""",
        (meeting_id,)
    )


def get_all_presets() -> list[dict]:
    """Get all visible presets with member details (single join query)."""
    presets = query_all("SELECT * FROM channel_preset WHERE show = 1 ORDER BY preset_name")
    if not presets:
        return []
        
    preset_ids = [p['channel_preset_id'] for p in presets]
    placeholders = ','.join(['?'] * len(preset_ids))
    
    members = query_all(
        f"""SELECT 
            pm.id,
            pm.preset_id,
            pm.user_id,
            p.participant_name as name,
            p.role,
            pm.channel_id,
            ac.name as channel_name
        FROM preset_member pm
        JOIN participants p ON p.participant_id = pm.user_id
        LEFT JOIN audio_channels ac ON ac.id = pm.channel_id
        WHERE pm.preset_id IN ({placeholders})
        ORDER BY pm.id""",
        tuple(preset_ids)
    )
    
    # Group members by preset_id
    members_by_preset = {}
    for m in members:
        members_by_preset.setdefault(m['preset_id'], []).append(m)
        
    for p in presets:
        p['members'] = members_by_preset.get(p['channel_preset_id'], [])
        
    return presets


def create_preset(preset_name: str, members: list[dict]) -> int:
    """Create a new visible preset and its members."""
    with transaction():
        preset_id = execute(
            "INSERT INTO channel_preset (preset_name, show) VALUES (?, 1)",
            (preset_name,)
        )
        for member in members:
            p_id = get_or_create_participant(member['name'], member.get('role', 'สมาชิก'))
            execute(
                "INSERT INTO preset_member (preset_id, user_id, channel_id) VALUES (?, ?, ?)",
                (preset_id, p_id, member.get('channel_id'))
            )
            
    return preset_id


def update_meeting_status(meeting_id: int, status: str,
                          start_time: str | None = None,
                          end_time: str | None = None,
                          total_time: str | None = None) -> bool:
    """Update meeting status and timing."""
    updates = ["status = ?"]
    params = [status]
    
    if start_time:
        updates.append("start_time = ?")
        params.append(start_time)
        
    if end_time:
        updates.append("end_time = ?")
        params.append(end_time)
        
    if total_time:
        updates.append("totaltime = ?")
        params.append(total_time)
        
    params.append(meeting_id)
    execute(f"UPDATE meetings SET {', '.join(updates)} WHERE meeting_id = ?", tuple(params))
    return True


def finalize_recording(meeting_id: int) -> dict:
    """
    Finalize a recording session: calculates total duration from saved audio segments,
    sets meeting status to 'completed', and returns timing info.
    """
    end_time = datetime.now().strftime('%H:%M:%S')
    total_row = query_one(
        "SELECT SUM(duration) as total FROM voice_file WHERE meeting_id = ?",
        (meeting_id,)
    )
    total_seconds = total_row['total'] if total_row and total_row['total'] else 0
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    total_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    update_meeting_status(meeting_id, 'completed', end_time=end_time, total_time=total_time)
    return {
        'end_time': end_time,
        'total_time': total_time
    }
