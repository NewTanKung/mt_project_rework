"""
Attendance API Routes.
"""
from flask import Blueprint, request, jsonify
from core.auth import login_required_api
from services import attendance_service

attendance_bp = Blueprint('attendance', __name__, url_prefix='/api/user/meetings')
attendance_bp.before_request(login_required_api)


@attendance_bp.route('/<int:meeting_id>/attendance/init', methods=['POST'])
def init_attendance(meeting_id):
    """Initialize attendance records for a meeting."""
    data = request.get_json(silent=True) or {}
    participant_ids = data.get('participant_ids', [])
    if not participant_ids:
        return jsonify({'success': False, 'message': 'No participants provided'}), 400

    result = attendance_service.initialize_attendance(meeting_id, participant_ids)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@attendance_bp.route('/<int:meeting_id>/attendance/<int:participant_id>', methods=['PUT'])
def mark_attendance(meeting_id, participant_id):
    """Mark attendance status for a participant."""
    data = request.get_json(silent=True) or {}
    status = data.get('status')
    if status not in ['present', 'absent', 'late', 'not_started']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400

    result = attendance_service.mark_attendance(meeting_id, participant_id, status)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@attendance_bp.route('/<int:meeting_id>/attendance', methods=['GET'])
def get_attendance_summary(meeting_id):
    """Get full attendance summary for a meeting."""
    result = attendance_service.get_attendance_summary(meeting_id)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@attendance_bp.route('/<int:meeting_id>/attendance/<int:participant_id>', methods=['GET'])
def get_participant_attendance(meeting_id, participant_id):
    """Get attendance status for a single participant."""
    result = attendance_service.get_attendance_status(meeting_id, participant_id)
    status_code = 200 if result.get('success') else 404
    return jsonify(result), status_code


@attendance_bp.route('/<int:meeting_id>/attendance', methods=['DELETE'])
def delete_attendance(meeting_id):
    """Delete all attendance records for a meeting."""
    result = attendance_service.delete_attendance(meeting_id)
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code
