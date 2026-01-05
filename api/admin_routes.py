"""
Admin API routes
"""
from flask import Blueprint, request, jsonify, session
from services.device_service import (
    scan_audio_devices, save_devices_to_db, get_all_devices,
    update_device_status, delete_device
)
from services.channel_service import (
    get_all_channels, create_channel, update_channel, delete_channel
)
from services.storage_service import (
    get_storage_settings, update_storage_settings, validate_path
)
from services.user_service import (
    create_user, update_user, delete_user, get_all_users
)
from database.db_manager import execute_query

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


# ================== Device APIs ==================

@admin_bp.route('/devices', methods=['GET'])
def get_devices():
    """Get all devices"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    devices = get_all_devices()
    return jsonify({'devices': devices})


@admin_bp.route('/devices/scan', methods=['POST'])
def scan_devices():
    """Scan for audio devices"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        devices = scan_audio_devices()
        count = save_devices_to_db(devices)
        
        return jsonify({
            'success': True,
            'devices_found': count,
            'devices': devices
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error scanning devices: {str(e)}'
        }), 500


@admin_bp.route('/devices/<int:device_id>', methods=['PATCH'])
def update_device(device_id):
    """Update device status"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    status = data.get('status')
    
    if status not in ['ready', 'disabled', 'not_connected']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400
    
    update_device_status(device_id, status)
    return jsonify({'success': True})


@admin_bp.route('/devices/<int:device_id>', methods=['DELETE'])
def remove_device(device_id):
    """Delete device"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    delete_device(device_id)
    return jsonify({'success': True})


# ================== Channel APIs ==================

@admin_bp.route('/channels', methods=['GET'])
def get_channels():
    """Get all channels"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    channels = get_all_channels()
    return jsonify({'channels': channels})


@admin_bp.route('/channels', methods=['POST'])
def add_channel():
    """Create new channel"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    
    required_fields = ['name', 'device_name', 'device_index', 'channel_index']
    for field in required_fields:
        if field not in data:
            return jsonify({'success': False, 'message': f'Missing field: {field}'}), 400
    
    channel_id = create_channel(
        data['name'],
        data['device_name'],
        data['device_index'],
        data['channel_index']
    )
    
    return jsonify({'success': True, 'channel_id': channel_id})


@admin_bp.route('/channels/<int:channel_id>', methods=['PATCH'])
def modify_channel(channel_id):
    """Update channel"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    
    # Build dynamic UPDATE query
    fields = []
    params = []
    
    if 'name' in data:
        fields.append("name = ?")
        params.append(data['name'])
    
    if 'device_name' in data:
        fields.append("device_name = ?")
        params.append(data['device_name'])
    
    if 'device_index' in data:
        fields.append("device_index = ?")
        params.append(data['device_index'])
    
    if 'channel_index' in data:
        fields.append("channel_index = ?")
        params.append(data['channel_index'])
    
    if 'is_active' in data:
        fields.append("is_active = ?")
        params.append(1 if data['is_active'] else 0)
    
    if not fields:
        return jsonify({'success': False, 'message': 'No fields to update'}), 400
    
    params.append(channel_id)
    query = f"UPDATE audio_channels SET {', '.join(fields)} WHERE id = ?"
    
    execute_query(query, tuple(params), commit=True)
    
    return jsonify({'success': True})


@admin_bp.route('/channels/<int:channel_id>', methods=['DELETE'])
def remove_channel(channel_id):
    """Delete channel"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    delete_channel(channel_id)
    return jsonify({'success': True})


# ================== Storage APIs ==================

@admin_bp.route('/storage', methods=['GET'])
def get_storage():
    """Get storage settings"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    settings = get_storage_settings()
    return jsonify({'settings': settings})


@admin_bp.route('/storage', methods=['POST'])
def update_storage():
    """Update storage settings"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    
    # Validate paths
    for key in ['export_path', 'audio_path', 'transcription_path', 'model_path']:
        if key in data:
            validation = validate_path(data[key])
            if not validation['valid']:
                return jsonify({
                    'success': False,
                    'message': validation['message']
                }), 400
    
    update_storage_settings(
        export_path=data.get('export_path'),
        audio_path=data.get('audio_path'),
        transcription_path=data.get('transcription_path'),
        model_path=data.get('model_path')
    )
    
    return jsonify({'success': True})


# ================== User APIs ==================

@admin_bp.route('/users', methods=['GET'])
def get_users():
    """Get all users"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    users = get_all_users()
    return jsonify({'users': users})


@admin_bp.route('/users', methods=['POST'])
def add_user():
    """Create new user"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    
    required_fields = ['username', 'password', 'role']
    for field in required_fields:
        if field not in data:
            return jsonify({'success': False, 'message': f'Missing field: {field}'}), 400
    
    if data['role'] not in ['admin', 'user']:
        return jsonify({'success': False, 'message': 'Invalid role'}), 400
    
    user_id = create_user(data['username'], data['password'], data['role'])
    
    if user_id is None:
        return jsonify({'success': False, 'message': 'Username already exists'}), 400
    
    return jsonify({'success': True, 'user_id': user_id})


@admin_bp.route('/users/<int:user_id>', methods=['PATCH'])
def modify_user(user_id):
    """Update user"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json()
    
    if 'role' in data and data['role'] not in ['admin', 'user']:
        return jsonify({'success': False, 'message': 'Invalid role'}), 400
    
    update_user(
        user_id,
        username=data.get('username'),
        password=data.get('password'),
        role=data.get('role')
    )
    
    return jsonify({'success': True})


@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
def remove_user(user_id):
    """Delete user"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    # Prevent deleting self
    if user_id == session['user_id']:
        return jsonify({'success': False, 'message': 'Cannot delete yourself'}), 400
    
    delete_user(user_id)
    return jsonify({'success': True})


# ================== Model APIs ==================

@admin_bp.route('/models', methods=['GET'])
def get_models():
    """Get all available models with download status"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.model_service import get_all_models
    
    models = get_all_models()
    return jsonify({'models': models})


@admin_bp.route('/models/<model_name>/download', methods=['POST'])
def download_model(model_name):
    """Download a Whisper model"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.model_service import download_model as download_model_service
    import threading
    import os
    
    # Create result file
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    models_dir = os.path.join(project_root, 'storage', 'models')
    os.makedirs(models_dir, exist_ok=True)
    result_file = os.path.join(models_dir, f".{model_name}_result.txt")
    
    # Remove old result file
    if os.path.exists(result_file):
        os.remove(result_file)
    
    # Download in background thread
    def download_thread():
        result = download_model_service(model_name)
        print(f"Download result: {result}")
        
        # Save result to file
        try:
            import json
            with open(result_file, 'w') as f:
                json.dump(result, f)
        except Exception as e:
            print(f"Failed to save result: {e}")
    
    thread = threading.Thread(target=download_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True,
        'message': f'กำลังดาวน์โหลดโมเดล {model_name}...'
    })


@admin_bp.route('/models/<model_name>/progress', methods=['GET'])
def get_model_progress(model_name):
    """Get model download progress"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.model_service import get_download_progress, check_model_downloaded
    from database.db_manager import execute_query
    import os
    import json
    
    # Check for result file (error or success)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    models_dir = os.path.join(project_root, 'storage', 'models')
    result_file = os.path.join(models_dir, f".{model_name}_result.txt")
    
    if os.path.exists(result_file):
        try:
            with open(result_file, 'r') as f:
                result = json.load(f)
            
            if result['success']:
                # Clean up result file
                os.remove(result_file)
                return jsonify({
                    'status': 'completed',
                    'progress': 100
                })
            else:
                # Download failed
                error_msg = result.get('message', 'Unknown error')
                # Clean up result file
                os.remove(result_file)
                return jsonify({
                    'status': 'failed',
                    'progress': 0,
                    'error': error_msg
                })
        except:
            pass
    
    # Check if model is downloaded
    if check_model_downloaded(model_name):
        return jsonify({
            'status': 'completed',
            'progress': 100
        })
    
    # Get current progress
    progress = get_download_progress(model_name)
    
    if progress is not None:
        return jsonify({
            'status': 'downloading',
            'progress': progress
        })
    else:
        return jsonify({
            'status': 'not_started',
            'progress': 0
        })


@admin_bp.route('/models/<model_name>/delete', methods=['DELETE'])
def delete_model_route(model_name):
    """Delete a downloaded model"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.model_service import delete_model
    
    result = delete_model(model_name)
    return jsonify(result)


@admin_bp.route('/models/<model_name>', methods=['GET'])
def get_model_info(model_name):
    """Get detailed model information"""
    if 'user_id' not in session or session['role'] != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    from services.model_service import get_model_info as get_model_info_service
    
    info = get_model_info_service(model_name)
    
    if info:
        return jsonify({'model': info})
    else:
        return jsonify({'success': False, 'message': 'Model not found'}), 404
