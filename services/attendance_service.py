"""
Attendance Service
จัดการระบบเช็คผู้เข้าร่วมประชุม
"""

from database.db_manager import execute_query
from datetime import datetime

def initialize_attendance(meeting_id, participant_ids):
    """
    สร้าง attendance records สำหรับการประชุม
    
    Args:
        meeting_id: ID ของการประชุม
        participant_ids: list ของ participant IDs
    
    Returns:
        dict: {'success': bool, 'message': str, 'count': int}
    """
    try:
        # ตรวจสอบว่ามี records อยู่แล้วหรือไม่
        existing = execute_query(
            "SELECT COUNT(*) as count FROM participant_meeting WHERE meeting_id = ?",
            (meeting_id,),
            fetch_one=True
        )
        
        if existing and existing['count'] > 0:
            return {
                'success': False,
                'message': 'Attendance records already exist for this meeting'
            }
        
        # สร้าง records ใหม่
        count = 0
        for participant_id in participant_ids:
            execute_query(
                """INSERT INTO participant_meeting 
                   (participant_id, meeting_id, status) 
                   VALUES (?, ?, 'not_started')""",
                (participant_id, meeting_id),
                commit=True
            )
            count += 1
        
        print(f"[Attendance] ✅ Initialized {count} attendance records for meeting {meeting_id}")
        return {
            'success': True,
            'message': f'Created {count} attendance records',
            'count': count
        }
        
    except Exception as e:
        print(f"[Attendance] ❌ Error initializing: {str(e)}")
        return {'success': False, 'message': str(e)}


def mark_attendance(meeting_id, participant_id, status):
    """
    บันทึก/อัพเดทสถานะการเข้าร่วม
    
    Args:
        meeting_id: ID ของการประชุม
        participant_id: ID ของผู้เข้าร่วม
        status: 'present', 'absent', 'late'
    
    Returns:
        dict: {'success': bool, 'message': str}
    """
    try:
        # ตรวจสอบว่ามี record อยู่แล้วหรือไม่
        existing = execute_query(
            """SELECT participant_meeting_id FROM participant_meeting 
               WHERE meeting_id = ? AND participant_id = ?""",
            (meeting_id, participant_id),
            fetch_one=True
        )
        
        if not existing:
            # สร้างใหม่
            execute_query(
                """INSERT INTO participant_meeting 
                   (participant_id, meeting_id, status) 
                   VALUES (?, ?, ?)""",
                (participant_id, meeting_id, status),
                commit=True
            )
        else:
            # อัพเดท
            execute_query(
                """UPDATE participant_meeting 
                   SET status = ? 
                   WHERE meeting_id = ? AND participant_id = ?""",
                (status, meeting_id, participant_id),
                commit=True
            )
        
        print(f"[Attendance] ✅ Marked participant {participant_id} as {status}")
        return {
            'success': True,
            'message': f'Attendance marked as {status}'
        }
        
    except Exception as e:
        print(f"[Attendance] ❌ Error marking attendance: {str(e)}")
        return {'success': False, 'message': str(e)}


def get_attendance_summary(meeting_id):
    """
    ดึงสรุปผู้เข้าร่วมประชุม
    
    Args:
        meeting_id: ID ของการประชุม
    
    Returns:
        dict: {
            'success': bool,
            'participants': list,
            'summary': {'total': int, 'present': int, 'absent': int, 'not_started': int}
        }
    """
    try:
        # ดึงรายชื่อทั้งหมดพร้อมสถานะ
        participants = execute_query(
            """SELECT 
                pm.participant_meeting_id,
                pm.participant_id,
                p.participant_name,
                p.role,
                pm.status
               FROM participant_meeting pm
               JOIN participants p ON pm.participant_id = p.participant_id
               WHERE pm.meeting_id = ?
               ORDER BY p.participant_name""",
            (meeting_id,),
            fetch_all=True
        )
        
        # Query returns sqlite3.Row objects, need to convert to dict
        participants = [dict(row) for row in participants]

        # คำนวณสถิติ
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
        print(f"[Attendance] ❌ Error getting summary: {str(e)}")
        return {'success': False, 'message': str(e)}


def get_attendance_status(meeting_id, participant_id):
    """
    ดูสถานะการเข้าร่วมของคนเดียว
    
    Args:
        meeting_id: ID ของการประชุม
        participant_id: ID ของผู้เข้าร่วม
    
    Returns:
        dict: {'success': bool, 'status': str}
    """
    try:
        result = execute_query(
            """SELECT status FROM participant_meeting 
               WHERE meeting_id = ? AND participant_id = ?""",
            (meeting_id, participant_id),
            fetch_one=True
        )
        
        if result:
            result_dict = dict(result)
            return {
                'success': True,
                'status': result_dict['status']
            }
        else:
            return {
                'success': False,
                'message': 'No attendance record found'
            }
            
    except Exception as e:
        print(f"[Attendance] ❌ Error getting status: {str(e)}")
        return {'success': False, 'message': str(e)}


def delete_attendance(meeting_id):
    """
    ลบ attendance records ของการประชุม
    
    Args:
        meeting_id: ID ของการประชุม
    
    Returns:
        dict: {'success': bool, 'message': str}
    """
    try:
        execute_query(
            "DELETE FROM participant_meeting WHERE meeting_id = ?",
            (meeting_id,),
            commit=True
        )
        
        print(f"[Attendance] ✅ Deleted attendance records for meeting {meeting_id}")
        return {
            'success': True,
            'message': 'Attendance records deleted'
        }
        
    except Exception as e:
        print(f"[Attendance] ❌ Error deleting: {str(e)}")
        return {'success': False, 'message': str(e)}
