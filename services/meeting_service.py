"""
Meeting service - Meeting and preset management
"""
from database.db_manager import execute_query, list_from_rows, dict_from_row
from datetime import datetime


def get_all_meetings(search=None, status=None):
    """
    Get all meetings with optional filters
    
    Args:
        search: Search term for meeting name
        status: Filter by status
    
    Returns:
        list: List of meeting dictionaries
    """
    query = "SELECT * FROM meetings WHERE 1=1"
    params = []
    
    if search:
        query += " AND meeting_name LIKE ?"
        params.append(f"%{search}%")
    
    if status:
        query += " AND status = ?"
        params.append(status)
    
    query += " ORDER BY meeting_date DESC, start_time DESC"
    
    meetings = execute_query(query, tuple(params) if params else None, fetch_all=True)
    return list_from_rows(meetings)


def get_meeting_by_id(meeting_id):
    """
    Get meeting by ID with participants
    
    Returns:
        dict: Meeting with participants list
    """
    # Get meeting
    query = "SELECT * FROM meetings WHERE meeting_id = ?"
    meeting = execute_query(query, (meeting_id,), fetch_one=True)
    
    if not meeting:
        return None
    
    meeting_dict = dict_from_row(meeting)
    
    # Get participants
    participants = get_meeting_participants(meeting_id)
    meeting_dict['participants'] = participants
    
    return meeting_dict


def create_meeting(meeting_name, description, meeting_location, meeting_date, 
                   participants, channel_preset_id=None):
    """
    Create new meeting
    
    Args:
        meeting_name: Name of meeting
        description: Meeting description
        meeting_location: Location
        meeting_date: Date (YYYY-MM-DD)
        participants: List of {name, channel_id}
        channel_preset_id: Optional preset ID
    
    Returns:
        int: New meeting ID
    """
    # Insert meeting
    query = """
        INSERT INTO meetings (
            meeting_name, description, meeting_location, 
            channel_preset_id, meeting_date, status
        ) VALUES (?, ?, ?, ?, ?, 'registered')
    """
    meeting_id = execute_query(
        query, 
        (meeting_name, description, meeting_location, channel_preset_id, meeting_date),
        commit=True
    )
    
    # If no preset selected, create a temporary one for this meeting
    if not channel_preset_id:
        import time
        temp_preset_name = f"Meeting_{meeting_id}_participants_{int(time.time())}"
        channel_preset_id = execute_query(
            "INSERT INTO channel_preset (preset_name, show) VALUES (?, 0)",
            (temp_preset_name,),
            commit=True
        )
        
        # Update meeting with temp preset
        execute_query(
            "UPDATE meetings SET channel_preset_id = ? WHERE meeting_id = ?",
            (channel_preset_id, meeting_id),
            commit=True
        )
    
    # Add participants to preset
    for participant in participants:
        # Get or create participant with role
        participant_id = get_or_create_participant(
            participant['name'],
            participant.get('role', 'สมาชิก')
        )
        
        # Check if already exists in preset
        existing = execute_query(
            "SELECT id FROM preset_member WHERE preset_id = ? AND user_id = ?",
            (channel_preset_id, participant_id),
            fetch_one=True
        )
        
        if not existing:
            # Add participant to preset
            execute_query(
                "INSERT INTO preset_member (preset_id, user_id, channel_id) VALUES (?, ?, ?)",
                (channel_preset_id, participant_id, participant.get('channel_id')),
                commit=True
            )
    
    return meeting_id


def update_meeting(meeting_id, meeting_name=None, description=None):
    """
    Update meeting details
    
    Returns:
        bool: True if successful
    """
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
    query = f"UPDATE meetings SET {', '.join(updates)} WHERE meeting_id = ?"
    execute_query(query, tuple(params), commit=True)
    return True


def delete_meeting(meeting_id):
    """
    Delete meeting and related data
    
    Returns:
        bool: True if successful
    """
    # Delete voice files
    execute_query("DELETE FROM voice_file WHERE meeting_id = ?", (meeting_id,), commit=True)
    
    # Delete text files
    execute_query("DELETE FROM text_file WHERE meeting_id = ?", (meeting_id,), commit=True)
    
    # Delete transcription jobs
    execute_query("DELETE FROM transcription_jobs WHERE meeting_id = ?", (meeting_id,), commit=True)
    
    # Delete meeting
    execute_query("DELETE FROM meetings WHERE meeting_id = ?", (meeting_id,), commit=True)
    
    return True


def get_or_create_participant(name, role='สมาชิก'):
    """
    Get participant ID by name, or create if not exists
    
    Returns:
        int: Participant ID
    """
    # Check if exists
    query = "SELECT participant_id FROM participants WHERE participant_name = ?"
    participant = execute_query(query, (name,), fetch_one=True)
    
    if participant:
        return participant['participant_id']
    
    # Create new with role
    return execute_query(
        "INSERT INTO participants (participant_name, role) VALUES (?, ?)",
        (name, role),
        commit=True
    )


def get_meeting_participants(meeting_id):
    """
    Get participants for a meeting
    
    Returns:
        list: List of participant dictionaries with channel info
    """
    query = """
        SELECT 
            p.participant_id,
            p.participant_name,
            pm.channel_id,
            ac.name as channel_name
        FROM meetings m
        JOIN preset_member pm ON pm.preset_id = m.channel_preset_id
        JOIN participants p ON p.participant_id = pm.user_id
        LEFT JOIN audio_channels ac ON ac.id = pm.channel_id
        WHERE m.meeting_id = ?
    """
    participants = execute_query(query, (meeting_id,), fetch_all=True)
    return list_from_rows(participants)


def get_all_presets():
    """
    Get all presets that are visible (show = 1)
    
    Returns:
        list: List of preset dictionaries with members
    """
    query = "SELECT * FROM channel_preset WHERE show = 1 ORDER BY preset_name"
    presets = execute_query(query, fetch_all=True)
    
    result = []
    for preset in presets:
        preset_dict = dict(preset)
        
        # Get members
        members_query = """
            SELECT 
                pm.id,
                pm.user_id,
                p.participant_name as name,
                p.role,
                pm.channel_id,
                ac.name as channel_name
            FROM preset_member pm
            JOIN participants p ON p.participant_id = pm.user_id
            LEFT JOIN audio_channels ac ON ac.id = pm.channel_id
            WHERE pm.preset_id = ?
        """
        members = execute_query(members_query, (preset_dict['channel_preset_id'],), fetch_all=True)
        preset_dict['members'] = list_from_rows(members)
        
        result.append(preset_dict)
    
    return result


def create_preset(preset_name, members):
    """
    Create new preset
    
    Args:
        preset_name: Name of preset
        members: List of {name, channel_id}
    
    Returns:
        int: New preset ID
    """
    # Create preset
    preset_id = execute_query(
        "INSERT INTO channel_preset (preset_name, show) VALUES (?, 1)",
        (preset_name,),
        commit=True
    )
    
    # Add members
    for member in members:
        participant_id = get_or_create_participant(member['name'], member.get('role', 'สมาชิก'))
        execute_query(
            "INSERT INTO preset_member (preset_id, user_id, channel_id) VALUES (?, ?, ?)",
            (preset_id, participant_id, member.get('channel_id')),
            commit=True
        )
    
    return preset_id


def update_meeting_status(meeting_id, status, start_time=None, end_time=None, total_time=None):
    """
    Update meeting status and timing
    
    Args:
        meeting_id: Meeting ID
        status: New status (registered, recording, paused, completed, transcribing, transcribed)
        start_time: Start time (HH:MM:SS)
        end_time: End time (HH:MM:SS)
        total_time: Total duration
    
    Returns:
        bool: True if successful
    """
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
    query = f"UPDATE meetings SET {', '.join(updates)} WHERE meeting_id = ?"
    execute_query(query, tuple(params), commit=True)
    return True
