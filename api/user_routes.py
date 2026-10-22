"""
User API routes for meetings, recording sessions, transcription, exports, and audio devices.
"""
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file
from core.auth import login_required_api
from services.channel_service import get_all_channels, get_channel_by_id
from services.meeting_service import (
    get_all_meetings, get_meeting_by_id, create_meeting, update_meeting,
    delete_meeting, get_all_presets, create_preset, update_meeting_status,
    finalize_recording
)
from services.recording import (
    start_recording_session, pause_recording_session, resume_recording_session,
    stop_recording_session, get_current_audio_levels
)
from services.device_service import sync_device_indices, check_devices_availability
from services.transcription import (
    get_available_models, transcribe_meeting, get_transcription_job_status,
    get_transcript, search_in_transcription, update_transcription,
    delete_meeting_transcription
)
from services.exporters import (
    export_meeting_to_pdf, export_meeting_to_txt, export_meeting_to_srt,
    export_meeting_to_docx, export_meeting_to_json
)
from database import query_all, query_one, execute

user_bp = Blueprint('user', __name__, url_prefix='/api/user')
user_bp.before_request(login_required_api)


# ================== Channel APIs ==================

@user_bp.route('/channels', methods=['GET'])
def get_channels():
    """Get all active audio channels."""
    channels = get_all_channels()
    return jsonify({'channels': channels})


# ================== Preset APIs ==================

@user_bp.route('/presets', methods=['GET'])
def get_presets():
    """Get all visible presets."""
    presets = get_all_presets()
    return jsonify({'presets': presets})


@user_bp.route('/presets', methods=['POST'])
def add_preset():
    """Create new channel preset."""
    data = request.get_json(silent=True) or {}
    if 'preset_name' not in data or 'members' not in data:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    preset_id = create_preset(data['preset_name'], data['members'])
    return jsonify({'success': True, 'preset_id': preset_id})


# ================== Meeting APIs ==================

@user_bp.route('/meetings', methods=['GET'])
def get_meetings():
    """Get all meetings with optional filters."""
    search = request.args.get('search')
    status = request.args.get('status')
    meetings = get_all_meetings(search, status)
    return jsonify({'meetings': meetings})


@user_bp.route('/meetings/<int:meeting_id>', methods=['GET'])
def get_meeting(meeting_id):
    """Get meeting details including participants and transcription items."""
    meeting = get_meeting_by_id(meeting_id)
    if not meeting:
        return jsonify({'success': False, 'message': 'Meeting not found'}), 404

    # Format transcriptions for UI
    transcripts = get_transcript(meeting_id)
    formatted = []
    for t in transcripts:
        formatted.append({
            'voice_id': t['voice_id'],
            'content': t.get('content', '') or '',
            'speaker_name': t.get('speaker_name') or 'ไม่ระบุ',
            'start_time': t.get('start_time') or '',
            'end_time': t.get('end_time') or ''
        })

    meeting['transcriptions'] = formatted
    return jsonify({'meeting': meeting})


@user_bp.route('/meetings', methods=['POST'])
def add_meeting():
    """Create new meeting."""
    data = request.get_json(silent=True) or {}
    required = ['meeting_name', 'meeting_date', 'participants']
    for field in required:
        if field not in data:
            return jsonify({'success': False, 'message': f'Missing field: {field}'}), 400

    preset_id = None
    if data.get('save_preset') and data.get('preset_name'):
        preset_id = create_preset(data['preset_name'], data['participants'])

    meeting_id = create_meeting(
        data['meeting_name'],
        data.get('description', ''),
        data.get('meeting_location', ''),
        data['meeting_date'],
        data['participants'],
        preset_id
    )
    return jsonify({'success': True, 'meeting_id': meeting_id})


@user_bp.route('/meetings/<int:meeting_id>', methods=['PATCH'])
def modify_meeting(meeting_id):
    """Update meeting details."""
    data = request.get_json(silent=True) or {}
    update_meeting(
        meeting_id,
        meeting_name=data.get('meeting_name'),
        description=data.get('description')
    )
    return jsonify({'success': True})


@user_bp.route('/meetings/<int:meeting_id>', methods=['DELETE'])
def remove_meeting(meeting_id):
    """Delete meeting and associated records/files."""
    delete_meeting(meeting_id)
    return jsonify({'success': True})


# ================== Recording APIs ==================

@user_bp.route('/meetings/<int:meeting_id>/start', methods=['POST'])
def start_recording(meeting_id):
    """Start audio recording for a meeting."""
    meeting = get_meeting_by_id(meeting_id)
    if not meeting:
        return jsonify({'success': False, 'message': 'Meeting not found'}), 404

    participants = meeting.get('participants', [])
    if not participants:
        return jsonify({'success': False, 'message': 'No participants assigned'}), 400

    participants_with_channels = []
    for p in participants:
        ch_id = p.get('channel_id')
        if not ch_id:
            continue
        channel = get_channel_by_id(ch_id)
        if channel:
            participants_with_channels.append({
                'participant_id': p['participant_id'],
                'participant_name': p['participant_name'],
                'channel_id': ch_id,
                'device_index': channel['device_index'],
                'channel_index': channel['channel_index']
            })

    if not participants_with_channels:
        return jsonify({
            'success': False,
            'message': 'No participants with valid channel assignments'
        }), 400

    result = start_recording_session(meeting_id, participants_with_channels)
    if result.get('success'):
        start_time = datetime.now().strftime('%H:%M:%S')
        update_meeting_status(meeting_id, 'recording', start_time=start_time)

    return jsonify(result)


@user_bp.route('/meetings/<int:meeting_id>/pause', methods=['POST'])
def pause_recording(meeting_id):
    """Pause recording."""
    result = pause_recording_session(meeting_id)
    if result.get('success'):
        update_meeting_status(meeting_id, 'paused')
    return jsonify(result)


@user_bp.route('/meetings/<int:meeting_id>/resume', methods=['POST'])
def resume_recording(meeting_id):
    """Resume recording."""
    result = resume_recording_session(meeting_id)
    if result.get('success'):
        update_meeting_status(meeting_id, 'recording')
    return jsonify(result)


@user_bp.route('/meetings/<int:meeting_id>/stop', methods=['POST'])
def stop_recording(meeting_id):
    """Stop recording session and finalize meeting time."""
    result = stop_recording_session(meeting_id)
    if result.get('success'):
        timing = finalize_recording(meeting_id)
        result.update(timing)
    return jsonify(result)


@user_bp.route('/meetings/<int:meeting_id>/audio-levels', methods=['GET'])
def get_audio_levels(meeting_id):
    """Get live audio levels for active recording."""
    levels = get_current_audio_levels(meeting_id)
    return jsonify({'success': True, 'levels': levels})


# ================== Transcription APIs ==================

@user_bp.route('/models/downloaded', methods=['GET'])
def get_downloaded_models():
    """Get available models for transcription dropdown."""
    models = get_available_models()
    return jsonify({'models': models})


@user_bp.route('/meetings/<int:meeting_id>/transcribe', methods=['POST'])
def start_transcription(meeting_id):
    """Start transcription job for a meeting."""
    data = request.get_json(silent=True) or {}
    model_name = data.get('model_used') or data.get('model_name', 'base')
    language = data.get('language', 'th')

    result = transcribe_meeting(meeting_id, model_name, language)
    return jsonify(result)


@user_bp.route('/transcription/jobs/clear', methods=['POST'])
def clear_all_transcription_jobs():
    """Cancel all active transcription jobs."""
    count_before = query_one(
        "SELECT COUNT(*) as count FROM transcription_jobs WHERE status IN ('pending', 'processing')"
    )
    cancelled_count = count_before['count'] if count_before else 0

    execute(
        """UPDATE transcription_jobs 
           SET status = 'failed', error_message = 'Cancelled by user'
           WHERE status IN ('pending', 'processing')"""
    )
    return jsonify({
        'success': True,
        'message': f'ยกเลิกงาน {cancelled_count} งานสำเร็จ'
    })


@user_bp.route('/transcription/jobs/active', methods=['GET'])
def get_active_transcription_jobs():
    """Get active and recently completed transcription jobs."""
    jobs = query_all(
        """SELECT tj.job_id, tj.meeting_id, tj.status, tj.progress, 
                  tj.started_at, tj.completed_at, m.meeting_name
           FROM transcription_jobs tj
           JOIN meetings m ON tj.meeting_id = m.meeting_id
           WHERE tj.status IN ('pending', 'processing')
              OR (tj.status = 'completed' 
                  AND datetime(tj.completed_at) > datetime('now', '-15 seconds'))
           ORDER BY tj.started_at DESC"""
    )
    return jsonify({
        'success': True,
        'jobs': jobs,
        'count': len(jobs)
    })


@user_bp.route('/transcription/status/<int:job_id>', methods=['GET'])
def get_transcription_status(job_id):
    """Get status of a specific transcription job."""
    job = get_transcription_job_status(job_id)
    if not job:
        return jsonify({'success': False, 'message': 'Job not found'}), 404
    return jsonify({
        'job_id': job['job_id'],
        'status': job['status'],
        'progress': job.get('progress', 0),
        'error_message': job.get('error_message')
    })


@user_bp.route('/meetings/<int:meeting_id>/search', methods=['GET'])
def search_meeting_transcription(meeting_id):
    """Search within meeting transcriptions."""
    query = request.args.get('q')
    speaker = request.args.get('speaker')
    time_from = request.args.get('time_from')
    time_to = request.args.get('time_to')

    result = search_in_transcription(meeting_id, query, speaker, time_from, time_to)
    return jsonify(result)


@user_bp.route('/transcriptions/<int:voice_id>', methods=['PUT'])
def update_transcription_api(voice_id):
    """Update transcription text and speaker name."""
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400

    result = update_transcription(
        voice_id,
        speaker_name=data.get('speaker_name'),
        text=data.get('text'),
        start_time=data.get('start_time'),
        end_time=data.get('end_time')
    )
    return jsonify(result)


@user_bp.route('/meetings/<int:meeting_id>/transcription', methods=['DELETE'])
def delete_transcription(meeting_id):
    """Delete transcription records and files."""
    delete_meeting_transcription(meeting_id)
    return jsonify({'success': True})


# ================== Device Sync APIs ==================

@user_bp.route('/devices/sync', methods=['POST'])
def sync_devices():
    """Sync device indices automatically."""
    result = sync_device_indices()
    return jsonify(result)


@user_bp.route('/devices/status', methods=['GET'])
def check_devices_status():
    """Check availability of devices used in active channels."""
    status = check_devices_availability()
    return jsonify({
        'success': True,
        'all_available': status['all_available'],
        'available_count': status['available'],
        'missing_count': status['missing'],
        'missing_devices': status['missing_devices']
    })


# ================== Export APIs ==================

def _send_export_file(result: dict, mimetype: str):
    if result.get('success'):
        return send_file(
            result['filepath'],
            as_attachment=True,
            download_name=result['filename'],
            mimetype=mimetype
        )
    return jsonify(result), 400


@user_bp.route('/meetings/<int:meeting_id>/export_pdf', methods=['GET'])
def export_pdf_route(meeting_id):
    """Export meeting transcription as PDF."""
    result = export_meeting_to_pdf(meeting_id)
    return _send_export_file(result, 'application/pdf')


@user_bp.route('/meetings/<int:meeting_id>/export_txt', methods=['GET'])
def export_txt_route(meeting_id):
    """Export meeting transcription as TXT."""
    result = export_meeting_to_txt(meeting_id)
    return _send_export_file(result, 'text/plain; charset=utf-8')


@user_bp.route('/meetings/<int:meeting_id>/export_srt', methods=['GET'])
def export_srt_route(meeting_id):
    """Export meeting transcription as SRT."""
    result = export_meeting_to_srt(meeting_id)
    return _send_export_file(result, 'application/x-subrip; charset=utf-8')


@user_bp.route('/meetings/<int:meeting_id>/export_docx', methods=['GET'])
def export_docx_route(meeting_id):
    """Export meeting transcription as Word document."""
    result = export_meeting_to_docx(meeting_id)
    return _send_export_file(
        result,
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


@user_bp.route('/meetings/<int:meeting_id>/download_json', methods=['GET'])
def download_json_route(meeting_id):
    """Export meeting transcription as JSON (fixes B8 404 error)."""
    result = export_meeting_to_json(meeting_id)
    return _send_export_file(result, 'application/json; charset=utf-8')
