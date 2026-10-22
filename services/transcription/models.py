"""
Faster Whisper model definitions, status checks, downloads, and deletion.
"""
import os
import shutil
import logging
import threading
from typing import Dict, Any
from services.storage_service import get_storage_settings
from core.paths import resolve_path

logger = logging.getLogger(__name__)

# Registry of supported Faster Whisper models
WHISPER_MODELS: Dict[str, Dict[str, Any]] = {
    'tiny': {
        'repo': 'Systran/faster-whisper-tiny',
        'size': '75 MB',
        'approx_bytes': 75 * 1024 * 1024,
        'speed': 'เร็วที่สุด',
        'accuracy': 'ต่ำ',
        'description': 'เหมาะสำหรับทดสอบ'
    },
    'base': {
        'repo': 'Systran/faster-whisper-base',
        'size': '142 MB',
        'approx_bytes': 142 * 1024 * 1024,
        'speed': 'เร็ว',
        'accuracy': 'ปานกลาง',
        'description': 'แนะนำสำหรับการใช้งานทั่วไป'
    },
    'small': {
        'repo': 'Systran/faster-whisper-small',
        'size': '466 MB',
        'approx_bytes': 466 * 1024 * 1024,
        'speed': 'ปานกลาง',
        'accuracy': 'ดี',
        'description': 'สมดุลระหว่างความเร็วและความแม่นยำ'
    },
    'medium': {
        'repo': 'Systran/faster-whisper-medium',
        'size': '1.5 GB',
        'approx_bytes': 1500 * 1024 * 1024,
        'speed': 'ช้า',
        'accuracy': 'ดีมาก',
        'description': 'ความแม่นยำสูง'
    },
    'large': {
        'repo': 'Systran/faster-whisper-large-v3',
        'size': '3 GB',
        'approx_bytes': 3100 * 1024 * 1024,
        'speed': 'ช้ามาก',
        'accuracy': 'ดีที่สุด',
        'description': 'ความแม่นยำสูงสุด (large-v3)'
    }
}

# In-memory download tracking state
_download_state: Dict[str, Dict[str, Any]] = {}
_state_lock = threading.Lock()


def get_models_directory() -> str:
    """Get the absolute path to the directory where models are stored."""
    storage = get_storage_settings()
    models_dir = resolve_path(storage.get('model_path', 'storage/models'))
    os.makedirs(models_dir, exist_ok=True)
    return models_dir


def get_model_repo_name(model_name: str) -> str:
    """Get the Hugging Face repository ID for a model name."""
    info = WHISPER_MODELS.get(model_name)
    if not info:
        raise ValueError(f"Unknown model: {model_name}")
    return info['repo']


def check_model_downloaded(model_name: str) -> bool:
    """Check if a Faster Whisper model is completely downloaded in storage/models."""
    try:
        models_dir = get_models_directory()
        repo = get_model_repo_name(model_name)
        # HuggingFace cache folder naming: models--Systran--faster-whisper-<name>
        folder_name = f"models--{repo.replace('/', '--')}"
        model_path = os.path.join(models_dir, folder_name)

        if not os.path.exists(model_path):
            return False

        snapshots_dir = os.path.join(model_path, 'snapshots')
        if not os.path.exists(snapshots_dir):
            return False

        snapshots = os.listdir(snapshots_dir)
        if not snapshots:
            return False

        snapshot_path = os.path.join(snapshots_dir, snapshots[0])
        has_config = os.path.exists(os.path.join(snapshot_path, 'config.json'))
        has_model = os.path.exists(os.path.join(snapshot_path, 'model.bin'))
        if not (has_config and has_model):
            return False

        # Check for any lingering .incomplete files
        for root, _, files in os.walk(model_path):
            for file in files:
                if file.endswith('.incomplete'):
                    return False

        return True
    except Exception as e:
        logger.error("Error checking model %s: %s", model_name, e)
        return False


def get_all_models() -> list[dict]:
    """Get list of all supported Whisper models with download status."""
    result = []
    for model_name, info in WHISPER_MODELS.items():
        is_dl = check_model_downloaded(model_name)
        result.append({
            'name': model_name,
            'size': info['size'],
            'speed': info['speed'],
            'accuracy': info['accuracy'],
            'description': info['description'],
            'is_downloaded': is_dl
        })
    return result


def download_model(model_name: str, progress_callback=None) -> dict:
    """
    Download Faster Whisper model into the application's models directory.
    Runs synchronously (intended to be called in a background thread).
    """
    if model_name not in WHISPER_MODELS:
        return {'success': False, 'message': f'Invalid model name: {model_name}'}

    repo = get_model_repo_name(model_name)
    models_dir = get_models_directory()

    with _state_lock:
        _download_state[model_name] = {
            'status': 'downloading',
            'progress': 10,
            'error': None
        }

    try:
        logger.info("Starting download for model %s (%s) into %s", model_name, repo, models_dir)
        from faster_whisper.utils import download_model as fw_download
        
        # Download files into cache directory
        fw_download(repo, output_dir=None, cache_dir=models_dir)

        with _state_lock:
            _download_state[model_name] = {
                'status': 'completed',
                'progress': 100,
                'error': None
            }
        logger.info("Successfully downloaded model %s", model_name)
        return {'success': True, 'message': f'ดาวน์โหลดโมเดล {model_name} สำเร็จ'}

    except Exception as e:
        err_msg = str(e)
        logger.exception("Error downloading model %s: %s", model_name, err_msg)
        with _state_lock:
            _download_state[model_name] = {
                'status': 'failed',
                'progress': 0,
                'error': err_msg
            }
        return {'success': False, 'message': f'Error downloading model: {err_msg}'}


def get_download_progress(model_name: str) -> dict:
    """
    Get download status and progress percentage for a model.
    Returns: {'status': str, 'progress': int, 'error': str | None}
    """
    if check_model_downloaded(model_name):
        return {'status': 'completed', 'progress': 100, 'error': None}

    with _state_lock:
        state = _download_state.get(model_name)
        if state:
            return dict(state)

    return {'status': 'not_started', 'progress': 0, 'error': None}


def delete_model(model_name: str) -> dict:
    """
    Delete a downloaded model from storage/models and evict from memory cache.
    """
    if model_name not in WHISPER_MODELS:
        return {'success': False, 'message': f'Invalid model: {model_name}'}

    try:
        from services.transcription.engine import evict_model
        evict_model(model_name)
    except Exception:
        pass

    try:
        models_dir = get_models_directory()
        repo = get_model_repo_name(model_name)
        folder_name = f"models--{repo.replace('/', '--')}"
        target_dir = os.path.join(models_dir, folder_name)

        if not os.path.exists(target_dir):
            return {'success': False, 'message': 'Model not found'}

        shutil.rmtree(target_dir, ignore_errors=False)
        with _state_lock:
            _download_state.pop(model_name, None)

        logger.info("Deleted model %s from %s", model_name, target_dir)
        return {'success': True, 'message': f'Model {model_name} deleted successfully'}

    except Exception as e:
        logger.exception("Error deleting model %s: %s", model_name, e)
        return {'success': False, 'message': f'Error deleting model: {str(e)}'}


def get_model_info(model_name: str) -> dict | None:
    """Get detailed model info and download state."""
    if model_name not in WHISPER_MODELS:
        return None
    info = dict(WHISPER_MODELS[model_name])
    info['name'] = model_name
    info['is_downloaded'] = check_model_downloaded(model_name)
    return info
