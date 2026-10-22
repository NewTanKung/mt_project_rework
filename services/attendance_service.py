"""
Attendance Service
Manages meeting participant attendance records and statuses.
"""
import logging
from datetime import datetime
from database import query_one, query_all, execute, transaction

logger = logging.getLogger(__name__)


def initialize_attendance(meeting_id: int, participant_ids: list[int]) -> dict:
    """
    Initialize attendance records for a meeting.
    """
    try:
        existing = query_one(
            "SELECT COUNT(*) as count FROM participant_meeting WHERE meeting_id = ?",
            (meeting_id,)
        )
        
        if existing and existing['count'] > 0:
            return {
                'success': False,
                'message': 'Attendance records already exist for this meeting'
            }
            
        count = 0
        with transaction():
            for p_id in participant_ids:
                execute(
                    """INSERT INTO participant_meeting (participant_id, meeting_id, status)
                       VALUES (?, ?, 'not_started')""",
                    (p_id, meeting_id)
                )
                count += 1
                
        logger.info("Initialized %d attendance records for meeting %d", count, meeting_id)
        return {
            'success': True,
            'message': f'Created {count} attendance records',
            'count': count
        }
    except Exception as e:
        logger.exception("Error initializing attendance: %s", e)
        return {'success': False, 'message': str(e)}


def mark_attendance(meeting_id: int, participant_id: int, status: str) -> dict:
    """
    Record or update attendance status for a participant.
    """
    try:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        existing = query_one(
            """SELECT participant_meeting_id FROM participant_meeting
               WHERE meeting_id = ? AND participant_id = ?""",
            (meeting_id, participant_id)
        )
        
        if not existing:
            execute(
                """INSERT INTO participant_meeting (participant_id, meeting_id, status, checked_at)
                   VALUES (?, ?, ?, ?)""",
                (participant_id, meeting_id, status, now_str)
            )
        else:
            execute(
                """UPDATE participant_meeting
                   SET status = ?, checked_at = ?
                   WHERE meeting_id = ? AND participant_id = ?""",
                (status, now_str, meeting_id, participant_id)
            )
            
        logger.info("Marked participant %d in meeting %d as %s", participant_id, meeting_id, status)
        return {
            'success': True,
            'message': f'Attendance marked as {status}'
        }
    except Exception as e:
        logger.exception("Error marking attendance: %s", e)
        return {'success': False, 'message': str(e)}


def get_attendance_summary(meeting_id: int) -> dict:
    """
    Get full attendance list and statistical summary for a meeting.
    """
    try:
        participants = query_all(
            """SELECT 
                pm.participant_meeting_id,
                pm.participant_id,
                p.participant_name,
                p.role,
                pm.status,
                pm.checked_at
               FROM participant_meeting pm
               JOIN participants p ON pm.participant_id = p.participant_id
               WHERE pm.meeting_id = ?
               ORDER BY p.participant_name""",
            (meeting_id,)
        )

        total = len(participants)
        present = sum(1 for p in participants if p['status'] == 'present')
        absent = sum(1 for p in participants if p['status'] == 'absent')
        late = sum(1 for p in participants if p['status'] == 'late')
        not_started = sum(1 for p in participants if p['status'] == 'not_started')

        return {
            'success': True,
            'participants': participants,
            'summary': {
                'total': total,
                'present': present,
                'absent': absent,
                'late': late,
                'not_started': not_started
            }
        }
    except Exception as e:
        logger.exception("Error getting attendance summary: %s", e)
        return {'success': False, 'message': str(e)}


def get_attendance_status(meeting_id: int, participant_id: int) -> dict:
    """
    Get attendance status for a single participant.
    """
    try:
        result = query_one(
            """SELECT status FROM participant_meeting
               WHERE meeting_id = ? AND participant_id = ?""",
            (meeting_id, participant_id)
        )
        if result:
            return {'success': True, 'status': result['status']}
        return {'success': False, 'message': 'No attendance record found'}
    except Exception as e:
        logger.exception("Error getting participant status: %s", e)
        return {'success': False, 'message': str(e)}


def delete_attendance(meeting_id: int) -> dict:
    """
    Delete all attendance records for a meeting.
    """
    try:
        execute("DELETE FROM participant_meeting WHERE meeting_id = ?", (meeting_id,))
        logger.info("Deleted attendance records for meeting %d", meeting_id)
        return {'success': True, 'message': 'Attendance records deleted'}
    except Exception as e:
        logger.exception("Error deleting attendance: %s", e)
        return {'success': False, 'message': str(e)}
