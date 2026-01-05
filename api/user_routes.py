"""
User API routes
"""
from flask import Blueprint, request, jsonify, session
from database.db_manager import execute_query
from services.meeting_service import (
    get_all_meetings, get_meeting_by_id, create_meeting, update_meeting,
    delete_meeting, get_all_presets, create_preset, update_meeting_status
)
from services.channel_service import get_all_channels

user_bp = Blueprint('user', __name__, url_prefix='/api/user')


# ================== Channel APIs ==================

@user_bp.route('/channels', methods=['GET'])
def get_channels():
    """Get all active channels for user"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    channels = get_all_channels()
    return jsonify({'channels': channels})


# ================== Preset APIs ==================

@user_bp.route('/presets', methods=['GET'])
def get_presets():
    """Get all visible presets"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    presets = get_all_presets()
    return jsonify({'presets': presets})


@user_bp.route('/presets', methods=['POST'])
def add_preset():
    """Create new preset"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    
    if 'preset_name' not in data or 'members' not in data:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
    
    preset_id = create_preset(data['preset_name'], data['members'])
    
    return jsonify({'success': True, 'preset_id': preset_id})


# ================== Meeting APIs ==================

@user_bp.route('/meetings', methods=['GET'])
def get_meetings():
    """Get all meetings with optional filters"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    search = request.args.get('search')
    status = request.args.get('status')
    
    meetings = get_all_meetings(search, status)
    
    # Add transcription status
    for meeting in meetings:
        # Check if has transcription
        from database.db_manager import execute_query
        has_transcription = execute_query(
            "SELECT COUNT(*) as count FROM text_file WHERE meeting_id = ?",
            (meeting['meeting_id'],),
            fetch_one=True
        )
        meeting['has_transcription'] = has_transcription['count'] > 0 if has_transcription else False
    
    return jsonify({'meetings': meetings})


@user_bp.route('/meetings/<int:meeting_id>', methods=['GET'])
def get_meeting(meeting_id):
    """Get meeting details"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        meeting = get_meeting_by_id(meeting_id)
        
        if not meeting:
            return jsonify({'success': False, 'message': 'Meeting not found'}), 404
        
        # Get transcriptions if exists
        from services.transcription_service import get_meeting_transcriptions
        from database.db_manager import execute_query
        
        transcriptions = get_meeting_transcriptions(meeting_id)
        
        # Format transcriptions with timestamps
        formatted_transcriptions = []
        if transcriptions:
            for trans in transcriptions:
                try:
                    # Convert Row to dict
                    trans_dict = dict(trans) if hasattr(trans, 'keys') else trans
                    
                    voice_info = execute_query(
                        "SELECT start_time, end_time, name FROM voice_file WHERE voice_id = ?",
                        (trans_dict['voice_id'],),
                        fetch_one=True
                    )
                    
                    # Extract speaker name from filename (format: ชื่อ_X_date.wav)
                    speaker_name = 'ไม่ระบุ'
                    if voice_info and voice_info['name']:
                        # Split by underscore and take first part
                        speaker_name = voice_info['name'].split('_')[0] if '_' in voice_info['name'] else voice_info['name']
                    
                    formatted_transcriptions.append({
                        'voice_id': trans_dict.get('voice_id'),
                        'content': trans_dict.get('content', ''),
                        'speaker_name': speaker_name,
                        'start_time': voice_info['start_time'] if voice_info else '',
                        'end_time': voice_info['end_time'] if voice_info else ''
                    })
                except Exception as e:
                    print(f"Error formatting transcription: {e}")
                    continue
        
        meeting['transcriptions'] = formatted_transcriptions
        
        return jsonify({'meeting': meeting})
        
    except Exception as e:
        print(f"Error in get_meeting: {e}")
        return jsonify({'success': False, 'message': 'เกิดข้อผิดพลาด'}), 500


@user_bp.route('/meetings', methods=['POST'])
def add_meeting():
    """Create new meeting"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    
    # Validate required fields
    required = ['meeting_name', 'meeting_date', 'participants']
    for field in required:
        if field not in data:
            return jsonify({'success': False, 'message': f'Missing field: {field}'}), 400
    
    # Check if save as preset
    preset_id = None
    if data.get('save_preset') and data.get('preset_name'):
        preset_id = create_preset(data['preset_name'], data['participants'])
    
    # Create meeting
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
    """Update meeting details"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    
    update_meeting(
        meeting_id,
        meeting_name=data.get('meeting_name'),
        description=data.get('description')
    )
    
    return jsonify({'success': True})


@user_bp.route('/meetings/<int:meeting_id>', methods=['DELETE'])
def remove_meeting(meeting_id):
    """Delete meeting"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    delete_meeting(meeting_id)
    return jsonify({'success': True})


# ================== Recording APIs ==================

@user_bp.route('/meetings/<int:meeting_id>/start', methods=['POST'])
def start_recording(meeting_id):
    """Start recording session"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from datetime import datetime
    from services.recording_service import start_recording_session
    from services.meeting_service import get_meeting_by_id
    
    # Get meeting details with participants
    meeting = get_meeting_by_id(meeting_id)
    if not meeting:
        return jsonify({'success': False, 'message': 'Meeting not found'}), 404
    
    # Check if participants have channel assignments
    if not meeting.get('participants'):
        return jsonify({'success': False, 'message': 'No participants assigned'}), 400
    
    # Get full channel info for each participant
    participants_with_channels = []
    for p in meeting['participants']:
        if not p.get('channel_id'):
            continue
        
        # Get channel details
        from services.channel_service import get_channel_by_id
        channel = get_channel_by_id(p['channel_id'])
        
        if channel:
            participants_with_channels.append({
                'participant_id': p['participant_id'],
                'participant_name': p['participant_name'],
                'channel_id': p['channel_id'],
                'device_index': channel['device_index'],
                'channel_index': channel['channel_index']
            })
    
    if not participants_with_channels:
        return jsonify({
'success': False,
            'message': 'No participants with valid channel assignments'
        }), 400
    
    # Start recording
    result = start_recording_session(meeting_id, participants_with_channels)
    
    if result['success']:
        start_time = datetime.now().strftime('%H:%M:%S')
        update_meeting_status(meeting_id, 'recording', start_time=start_time)
    
    return jsonify(result)


@user_bp.route('/meetings/<int:meeting_id>/pause', methods=['POST'])
def pause_recording(meeting_id):
    """Pause recording session"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.recording_service import pause_recording_session
    
    result = pause_recording_session(meeting_id)
    
    if result['success']:
        update_meeting_status(meeting_id, 'paused')
    
    return jsonify(result)


@user_bp.route('/meetings/<int:meeting_id>/resume', methods=['POST'])
def resume_recording(meeting_id):
    """Resume recording session"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.recording_service import resume_recording_session
    
    result = resume_recording_session(meeting_id)
    
    if result['success']:
        update_meeting_status(meeting_id, 'recording')
    
    return jsonify(result)


@user_bp.route('/meetings/<int:meeting_id>/stop', methods=['POST'])
def stop_recording(meeting_id):
    """Stop recording session"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from datetime import datetime
    from services.recording_service import stop_recording_session
    
    result = stop_recording_session(meeting_id)
    
    if result['success']:
        end_time = datetime.now().strftime('%H:%M:%S')
        
        # Calculate total time from voice segments
        from database.db_manager import execute_query
        total_duration = execute_query(
            "SELECT SUM(duration) as total FROM voice_file WHERE meeting_id = ?",
            (meeting_id,),
            fetch_one=True
        )
        
        total_seconds = total_duration['total'] if total_duration['total'] else 0
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        total_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        update_meeting_status(meeting_id, 'completed', end_time=end_time, total_time=total_time)
        
        result['end_time'] = end_time
        result['total_time'] = total_time
    
    return jsonify(result)


@user_bp.route('/meetings/<int:meeting_id>/audio-levels', methods=['GET'])
def get_audio_levels(meeting_id):
    """Get current audio levels for speaker detection"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.recording_service import get_current_audio_levels
    
    levels = get_current_audio_levels(meeting_id)
    
    return jsonify({
        'success': True,
        'levels': levels
    })


# ================== Transcription APIs ==================

@user_bp.route('/models/downloaded', methods=['GET'])
def get_downloaded_models():
    """Get list of downloaded models"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.transcription_service import get_available_models
    
    models = get_available_models()
    return jsonify({'models': models})


@user_bp.route('/meetings/<int:meeting_id>/transcribe', methods=['POST'])
def start_transcription(meeting_id):
    """Start transcription job"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    # Frontend sends 'model_used', not 'model_name'
    model_name = data.get('model_used') or data.get('model_name', 'base')
    language = data.get('language', 'th')
    
    from services.transcription_service import transcribe_meeting
    
    result = transcribe_meeting(meeting_id, model_name, language)
    
    return jsonify(result)


@user_bp.route('/transcription/jobs/clear', methods=['POST'])
def clear_all_transcription_jobs():
    """Clear all stuck transcription jobs"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from database.db_manager import execute_query
    
    try:
        # Get count before cancelling
        count_before = execute_query(
            "SELECT COUNT(*) as count FROM transcription_jobs WHERE status IN ('pending', 'processing')",
            fetch_one=True
        )
        
        # Cancel all pending/processing jobs
        execute_query(
            """UPDATE transcription_jobs 
               SET status = 'failed', error_message = 'Cancelled by user'
               WHERE status IN ('pending', 'processing')""",
            commit=True
        )
        
        cancelled_count = count_before['count'] if count_before else 0
        
        return jsonify({
            'success': True,
            'message': f'ยกเลิกงาน {cancelled_count} งานสำเร็จ'
        })
    except Exception as e:
        print(f"Error clearing jobs: {e}")
        return jsonify({
            'success': False,
            'message': f'เกิดข้อผิดพลาด: {str(e)}'
        }), 500


@user_bp.route('/transcription/jobs/active', methods=['GET'])
def get_active_transcription_jobs():
    """Get all active (pending/processing) transcription jobs + recently completed"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        jobs = execute_query(
            """SELECT tj.job_id, tj.meeting_id, tj.status, tj.progress, 
                      tj.started_at, tj.completed_at, m.meeting_name
               FROM transcription_jobs tj
               JOIN meetings m ON tj.meeting_id = m.meeting_id
               WHERE tj.status IN ('pending', 'processing')
                  OR (tj.status = 'completed' 
                      AND datetime(tj.completed_at) > datetime('now', '-15 seconds'))
               ORDER BY tj.started_at DESC""",
            fetch_all=True
        )
        
        # ✅ แปลง Row objects เป็น dict
        jobs_list = []
        if jobs:
            for job in jobs:
                jobs_list.append({
                    'job_id': job['job_id'],
                    'meeting_id': job['meeting_id'],
                    'status': job['status'],
                    'progress': job['progress'] or 0,
                    'started_at': job['started_at'],
                    'completed_at': job['completed_at'] if 'completed_at' in job.keys() else None,
                    'meeting_name': job['meeting_name']
                })
        
        return jsonify({
            'success': True,
            'jobs': jobs_list,
            'count': len(jobs_list)
        })
        
    except Exception as e:
        print(f"[User Routes] Error getting active jobs: {e}")
        return jsonify({'success': False, 'message': str(e)})


@user_bp.route('/transcription/status/<int:job_id>', methods=['GET'])
def get_transcription_status(job_id):
    """Get transcription job status"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.transcription_service import get_transcription_job_status
    
    job = get_transcription_job_status(job_id)
    
    if not job:
        return jsonify({'success': False, 'message': 'Job not found'}), 404
    
    return jsonify({
        'job_id': job['job_id'],
        'status': job['status'],
        'progress': job.get('progress', 0),
        'error_message': job.get('error_message')
    })


# ================== Device Sync APIs ==================

@user_bp.route('/devices/sync', methods=['POST'])
def sync_devices():
    """Sync device indices automatically"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.device_service import sync_device_indices
    
    result = sync_device_indices()
    return jsonify(result)


@user_bp.route('/devices/status', methods=['GET'])
def check_devices_status():
    """Check if all required devices are available"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.device_service import check_devices_availability
    
    status = check_devices_availability()
    return jsonify({
        'success': True,
        'all_available': status['all_available'],
        'available_count': status['available'],
        'missing_count': status['missing'],
        'missing_devices': status['missing_devices']
    })

@user_bp.route('/meetings/<int:meeting_id>/export_pdf', methods=['GET'])
def export_meeting_pdf(meeting_id):
    """Export meeting transcription as PDF"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.pdf_service import export_meeting_to_pdf
    from flask import send_file
    
    result = export_meeting_to_pdf(meeting_id)
    
    if result['success']:
        # Send PDF file as download
        return send_file(
            result['filepath'],
            as_attachment=True,
            download_name=result['filename'],
            mimetype='application/pdf'
        )
    else:
        return jsonify(result), 400


@user_bp.route('/meetings/<int:meeting_id>/export_txt', methods=['GET'])
def export_meeting_txt(meeting_id):
    """Export meeting to TXT"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.transcription_service import export_meeting_to_txt
    from flask import send_file
    
    result = export_meeting_to_txt(meeting_id)
    
    if result['success']:
        return send_file(
            result['filepath'],
            as_attachment=True,
            download_name=result['filename'],
            mimetype='text/plain'
        )
    else:
        return jsonify(result), 400


@user_bp.route('/meetings/<int:meeting_id>/export_srt', methods=['GET'])
def export_meeting_srt(meeting_id):
    """Export meeting to SRT"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.transcription_service import export_meeting_to_srt
    from flask import send_file
    
    result = export_meeting_to_srt(meeting_id)
    
    if result['success']:
        return send_file(
            result['filepath'],
            as_attachment=True,
            download_name=result['filename'],
            mimetype='application/x-subrip'
        )
    else:
        return jsonify(result), 400


@user_bp.route('/meetings/<int:meeting_id>/export_docx', methods=['GET'])
def export_meeting_docx(meeting_id):
    """Export meeting to Word"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.transcription_service import export_meeting_to_docx
    from flask import send_file
    
    result = export_meeting_to_docx(meeting_id)
    
    if result['success']:
        return send_file(
            result['filepath'],
            as_attachment=True,
            download_name=result['filename'],
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
    else:
        return jsonify(result), 400


@user_bp.route('/meetings/<int:meeting_id>/search', methods=['GET'])
def search_meeting_transcription(meeting_id):
    """Search in meeting transcriptions"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.transcription_service import search_in_transcription
    
    # Get query parameters
    query = request.args.get('q', None)
    speaker = request.args.get('speaker', None)
    time_from = request.args.get('time_from', None)
    time_to = request.args.get('time_to', None)
    
    result = search_in_transcription(meeting_id, query, speaker, time_from, time_to)
    
    return jsonify(result)


@user_bp.route('/transcriptions/<int:voice_id>', methods=['PUT'])
def update_transcription_api(voice_id):
    """Update transcription text and metadata"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.transcription_service import update_transcription
    
    data = request.get_json()
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
    """Delete transcription files"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.transcription_service import delete_meeting_transcription
    
    delete_meeting_transcription(meeting_id)
    
    return jsonify({'success': True})
