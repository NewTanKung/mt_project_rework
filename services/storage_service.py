"""
Storage service - Storage path management and validation.
"""
import os
import logging
from database import query_all, query_one, execute
from core.paths import to_storage_path, resolve_path
from config import BASE_DIR, EXPORT_DIR, AUDIO_DIR, TRANSCRIPTION_DIR, MODEL_DIR

logger = logging.getLogger(__name__)


def get_storage_settings() -> dict:
    """
    Get all storage settings resolved to absolute paths.
    """
    rows = query_all("SELECT setting_key, setting_value FROM storage_settings")
    raw_settings = {r['setting_key']: r['setting_value'] for r in rows}
    
    return {
        'export_path': resolve_path(raw_settings.get('export_path')) or EXPORT_DIR,
        'audio_path': resolve_path(raw_settings.get('audio_path')) or AUDIO_DIR,
        'transcription_path': resolve_path(raw_settings.get('transcription_path')) or TRANSCRIPTION_DIR,
        'model_path': resolve_path(raw_settings.get('model_path')) or MODEL_DIR,
    }


def update_storage_settings(export_path: str | None = None,
                            audio_path: str | None = None,
                            transcription_path: str | None = None,
                            model_path: str | None = None) -> bool:
    """
    Update storage settings in the database, saving paths in normalized portable form.
    """
    settings = {
        'export_path': export_path,
        'audio_path': audio_path,
        'transcription_path': transcription_path,
        'model_path': model_path,
    }
    
    for key, value in settings.items():
        if value is not None:
            # Save portable path (relative if inside BASE_DIR)
            portable_val = to_storage_path(value)
            
            existing = query_one("SELECT id FROM storage_settings WHERE setting_key = ?", (key,))
            if existing:
                execute(
                    "UPDATE storage_settings SET setting_value = ? WHERE setting_key = ?",
                    (portable_val, key)
                )
            else:
                execute(
                    "INSERT INTO storage_settings (setting_key, setting_value) VALUES (?, ?)",
                    (key, portable_val)
                )
                
            # Create physical directory if not exists
            abs_path = resolve_path(value)
            try:
                os.makedirs(abs_path, exist_ok=True)
            except Exception as e:
                logger.error("Error creating directory %s: %s", abs_path, e)
                
    return True


def validate_path(path: str | None) -> dict:
    """
    Validate if a path exists or can be created, and is writable.
    """
    if not path or not path.strip():
        return {'valid': False, 'message': 'Path ว่างเปล่า'}
        
    abs_path = resolve_path(path.strip())
    
    if not os.path.exists(abs_path):
        try:
            os.makedirs(abs_path, exist_ok=True)
        except PermissionError:
            return {'valid': False, 'message': f'ไม่มีสิทธิ์สร้างโฟลเดอร์: {abs_path}'}
        except Exception as e:
            return {'valid': False, 'message': f'ไม่สามารถสร้างโฟลเดอร์: {str(e)}'}
            
    if not os.access(abs_path, os.W_OK):
        return {'valid': False, 'message': f'ไม่มีสิทธิ์เขียนไฟล์ใน: {abs_path}'}
        
    return {'valid': True, 'message': 'Path ถูกต้อง'}
