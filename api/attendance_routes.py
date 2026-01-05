"""
Attendance API Routes
เส้นทาง API สำหรับระบบเช็คผู้เข้าร่วมประชุม
"""

from flask import Blueprint, request, jsonify, session
from services import attendance_service

attendance_bp = Blueprint('attendance', __name__, url_prefix='/api/user/meetings')


@attendance_bp.route('/<int:meeting_id>/attendance/init', methods=['POST'])
def init_attendance(meeting_id):
    """สร้าง attendance records สำหรับการประชุม"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        data = request.json
        participant_ids = data.get('participant_ids', [])
        
        if not participant_ids:
            return jsonify({'success': False, 'message': 'No participants provided'}), 400
        
        result = attendance_service.initialize_attendance(meeting_id, participant_ids)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"[API] Error initializing attendance: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@attendance_bp.route('/<int:meeting_id>/attendance/<int:participant_id>', methods=['PUT'])
def mark_attendance(meeting_id, participant_id):
    """บันทึกสถานะการเข้าร่วมของผู้เข้าร่วม"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        data = request.json
        status = data.get('status')
        
        if status not in ['present', 'absent', 'late', 'not_started']:
            return jsonify({'success': False, 'message': 'Invalid status'}), 400
        
        result = attendance_service.mark_attendance(meeting_id, participant_id, status)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"[API] Error marking attendance: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@attendance_bp.route('/<int:meeting_id>/attendance', methods=['GET'])
def get_attendance_summary(meeting_id):
    """ดึงสรุปผู้เข้าร่วมประชุม"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        result = attendance_service.get_attendance_summary(meeting_id)
        
        if result['success']:
            return jsonify(result), 200
        else:
            print(f"[API] Error getting attendance summary from service: {result.get('message')}")
            return jsonify(result), 400
            
    except Exception as e:
        print(f"[API] Error getting attendance summary exception: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@attendance_bp.route('/<int:meeting_id>/attendance/<int:participant_id>', methods=['GET'])
def get_participant_attendance(meeting_id, participant_id):
    """ดูสถานะการเข้าร่วมของผู้เข้าร่วมคนเดียว"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        result = attendance_service.get_attendance_status(meeting_id, participant_id)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 404
            
    except Exception as e:
        print(f"[API] Error getting participant attendance: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@attendance_bp.route('/<int:meeting_id>/attendance', methods=['DELETE'])
def delete_attendance(meeting_id):
    """ลบ attendance records ทั้งหมดของการประชุม"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        result = attendance_service.delete_attendance(meeting_id)
        
        if result['success']:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        print(f"[API] Error deleting attendance: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
