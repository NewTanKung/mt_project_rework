"""
Thread-safe active recording sessions registry and public controller functions.
"""
import logging
import threading
from services.recording.session import RecordingSession
from services import attendance_service

logger = logging.getLogger(__name__)

_active_sessions: dict[int, RecordingSession] = {}
_sessions_lock = threading.RLock()


def start_recording_session(meeting_id: int, participants: list[dict]) -> dict:
    """
    Start a recording session for a meeting, filtering out absent participants.
    """
    active_participants = list(participants)
    try:
        att = attendance_service.get_attendance_summary(meeting_id)
        if att.get('success'):
            status_map = {p['participant_id']: p.get('status') for p in att.get('participants', [])}
            active_participants = [
                p for p in participants
                if status_map.get(p.get('participant_id')) != 'absent'
            ]
    except Exception as e:
        logger.warning("Could not filter attendance status: %s", e)

    if not active_participants:
        return {'success': False, 'message': 'No active participants available for recording'}

    with _sessions_lock:
        if meeting_id in _active_sessions:
            return {'success': False, 'message': 'Recording session already active for this meeting'}

        session = RecordingSession(meeting_id, active_participants)
        result = session.start()
        if result.get('success'):
            _active_sessions[meeting_id] = session
        return result


def pause_recording_session(meeting_id: int) -> dict:
    """Pause an active recording session."""
    with _sessions_lock:
        session = _active_sessions.get(meeting_id)
        if not session:
            return {'success': False, 'message': 'No active recording for this meeting'}
        return session.pause()


def resume_recording_session(meeting_id: int) -> dict:
    """Resume a paused recording session."""
    with _sessions_lock:
        session = _active_sessions.get(meeting_id)
        if not session:
            return {'success': False, 'message': 'No active recording for this meeting'}
        return session.resume()


def stop_recording_session(meeting_id: int) -> dict:
    """Stop recording session and flush all segments to disk."""
    with _sessions_lock:
        session = _active_sessions.pop(meeting_id, None)

    if not session:
        return {'success': False, 'message': 'No active recording for this meeting'}

    return session.stop()


def get_current_audio_levels(meeting_id: int) -> dict:
    """Get real-time audio levels for participants in a recording session."""
    with _sessions_lock:
        session = _active_sessions.get(meeting_id)
    if not session:
        return {}
    return session.get_audio_levels()


def get_session_status(meeting_id: int) -> dict:
    """Check recording and paused status for a meeting."""
    with _sessions_lock:
        session = _active_sessions.get(meeting_id)
    if not session:
        return {'is_recording': False, 'is_paused': False}
    return {
        'is_recording': session.is_recording,
        'is_paused': session.is_paused
    }


def stop_all_active_recordings():
    """Stop all running sessions on application shutdown."""
    with _sessions_lock:
        meeting_ids = list(_active_sessions.keys())
    for mid in meeting_ids:
        try:
            stop_recording_session(mid)
        except Exception as e:
            logger.error("Error stopping session %s on shutdown: %s", mid, e)
