"""
Admin API routes for managing audio devices, channels, storage paths, users, and Whisper models.
"""
import threading
from flask import Blueprint, request, jsonify, session
from core.auth import admin_required_api
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
from services.auth_service import (
    create_user, update_user, delete_user, get_all_users
)
from services.transcription import (
    get_all_models, download_model as download_model_svc,
    get_download_progress, delete_model as delete_model_svc,
    get_model_info as get_model_info_svc
)

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')
admin_bp.before_request(admin_required_api)


# ================== Device APIs ==================

@admin_bp.route('/devices', methods=['GET'])
def get_devices():
    """Get all devices."""
    devices = get_all_devices()
    return jsonify({'devices': devices})


@admin_bp.route('/devices/scan', methods=['POST'])
def scan_devices():
    """Scan for audio devices and update database."""
    devices = scan_audio_devices()
    count = save_devices_to_db(devices)
    return jsonify({
        'success': True,
        'devices_found': count,
        'devices': devices
    })


@admin_bp.route('/devices/<int:device_id>', methods=['PATCH'])
def update_device(device_id):
    """Update device status ('ready', 'disabled', 'not_connected')."""
    data = request.get_json(silent=True) or {}
    status = data.get('status')
    if status not in ['ready', 'disabled', 'not_connected']:
        return jsonify({'success': False, 'message': 'Invalid status'}), 400

    update_device_status(device_id, status)
    return jsonify({'success': True})


@admin_bp.route('/devices/<int:device_id>', methods=['DELETE'])
def remove_device(device_id):
    """Delete device from database."""
    delete_device(device_id)
    return jsonify({'success': True})


# ================== Channel APIs ==================

@admin_bp.route('/channels', methods=['GET'])
def get_channels():
    """Get all active audio channels."""
    channels = get_all_channels()
    return jsonify({'channels': channels})


@admin_bp.route('/channels', methods=['POST'])
def add_channel():
    """Create new audio channel mapping."""
    data = request.get_json(silent=True) or {}
    required = ['name', 'device_name', 'device_index', 'channel_index']
    for field in required:
        if field not in data:
            return jsonify({'success': False, 'message': f'Missing field: {field}'}), 400

    channel_id = create_channel(
        data['name'],
        data['device_name'],
        int(data['device_index']),
        int(data['channel_index'])
    )
    return jsonify({'success': True, 'channel_id': channel_id})


@admin_bp.route('/channels/<int:channel_id>', methods=['PATCH'])
def modify_channel(channel_id):
    """Update channel mapping."""
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'success': False, 'message': 'No fields to update'}), 400

    success = update_channel(
        channel_id,
        name=data.get('name'),
        device_name=data.get('device_name'),
        device_index=data.get('device_index'),
        channel_index=data.get('channel_index'),
        is_active=data.get('is_active')
    )
    return jsonify({'success': success})


@admin_bp.route('/channels/<int:channel_id>', methods=['DELETE'])
def remove_channel(channel_id):
    """Delete channel mapping."""
    delete_channel(channel_id)
    return jsonify({'success': True})


# ================== Storage APIs ==================

@admin_bp.route('/storage', methods=['GET'])
def get_storage():
    """Get current storage directory settings."""
    settings = get_storage_settings()
    return jsonify({'settings': settings})


@admin_bp.route('/storage', methods=['POST'])
def update_storage():
    """Update storage directory settings."""
    data = request.get_json(silent=True) or {}
    for key in ['export_path', 'audio_path', 'transcription_path', 'model_path']:
        if key in data and data[key]:
            validation = validate_path(data[key])
            if not validation['valid']:
                return jsonify({'success': False, 'message': validation['message']}), 400

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
    """Get all users."""
    users = get_all_users()
    return jsonify({'users': users})


@admin_bp.route('/users', methods=['POST'])
def add_user():
    """Create a new user."""
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'user')

    if not username or not password:
        return jsonify({'success': False, 'message': 'Missing username or password'}), 400
    if role not in ['admin', 'user']:
        return jsonify({'success': False, 'message': 'Invalid role'}), 400

    user_id = create_user(username, password, role)
    if user_id is None:
        return jsonify({'success': False, 'message': 'Username already exists'}), 400

    return jsonify({'success': True, 'user_id': user_id})


@admin_bp.route('/users/<int:user_id>', methods=['PATCH'])
def modify_user(user_id):
    """Update user information."""
    data = request.get_json(silent=True) or {}
    role = data.get('role')
    if role and role not in ['admin', 'user']:
        return jsonify({'success': False, 'message': 'Invalid role'}), 400

    update_user(
        user_id,
        username=data.get('username'),
        password=data.get('password'),
        role=role
    )
    return jsonify({'success': True})


@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
def remove_user(user_id):
    """Delete a user."""
    if user_id == session.get('user_id'):
        return jsonify({'success': False, 'message': 'Cannot delete yourself'}), 400

    delete_user(user_id)
    return jsonify({'success': True})


# ================== Model APIs ==================

@admin_bp.route('/models', methods=['GET'])
def get_models():
    """Get all available Whisper models with download status."""
    models = get_all_models()
    return jsonify({'models': models})


@admin_bp.route('/models/<model_name>/download', methods=['POST'])
def download_model(model_name):
    """Download a Faster Whisper model in a background thread."""
    def run_download():
        download_model_svc(model_name)

    thread = threading.Thread(target=run_download, daemon=True)
    thread.start()
    return jsonify({
        'success': True,
        'message': f'กำลังดาวน์โหลดโมเดล {model_name}...'
    })


@admin_bp.route('/models/<model_name>/progress', methods=['GET'])
def get_model_progress_route(model_name):
    """Get model download progress."""
    prog = get_download_progress(model_name)
    return jsonify(prog)


@admin_bp.route('/models/<model_name>/delete', methods=['DELETE'])
def delete_model_route(model_name):
    """Delete a downloaded Faster Whisper model."""
    result = delete_model_svc(model_name)
    return jsonify(result)


@admin_bp.route('/models/<model_name>', methods=['GET'])
def get_model_info_route(model_name):
    """Get detailed model information."""
    info = get_model_info_svc(model_name)
    if info:
        return jsonify({'model': info})
    return jsonify({'success': False, 'message': 'Model not found'}), 404
