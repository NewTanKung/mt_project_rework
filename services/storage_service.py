"""
Storage service - Storage path management
"""
from database.db_manager import execute_query, dict_from_row
import os


def get_storage_settings():
    """
    Get all storage settings
    
    Returns:
        dict: Dictionary of settings {key: value}
    """
    query = "SELECT setting_key, setting_value FROM storage_settings"
    rows = execute_query(query, fetch_all=True)
    
    settings = {}
    for row in rows:
        row_dict = dict(row)
        settings[row_dict['setting_key']] = row_dict['setting_value']
    
    # Return default values if not set
    return {
        'export_path': settings.get('export_path', os.path.join(os.getcwd(), 'storage', 'exports')),
        'audio_path': settings.get('audio_path', os.path.join(os.getcwd(), 'storage', 'audio')),
        'transcription_path': settings.get('transcription_path', os.path.join(os.getcwd(), 'storage', 'transcriptions')),
        'model_path': settings.get('model_path', os.path.join(os.getcwd(), 'storage', 'models'))
    }


def update_storage_settings(export_path=None, audio_path=None, transcription_path=None, model_path=None):
    """
    Update storage settings
    
    Returns:
        bool: True if successful
    """
    settings = {
        'export_path': export_path,
        'audio_path': audio_path,
        'transcription_path': transcription_path,
        'model_path': model_path
    }
    
    for key, value in settings.items():
        if value is not None:
            # Check if setting exists
            existing = execute_query(
                "SELECT id FROM storage_settings WHERE setting_key = ?",
                (key,),
                fetch_one=True
            )
            
            if existing:
                # Update
                execute_query(
                    "UPDATE storage_settings SET setting_value = ? WHERE setting_key = ?",
                    (value, key),
                    commit=True
                )
            else:
                # Insert
                execute_query(
                    "INSERT INTO storage_settings (setting_key, setting_value) VALUES (?, ?)",
                    (key, value),
                    commit=True
                )
            
            # Create directory if not exists
            try:
                os.makedirs(value, exist_ok=True)
            except Exception as e:
                print(f"Error creating directory {value}: {e}")
    
    return True


def validate_path(path):
    """
    Validate if path is writable
    
    Returns:
        dict: {valid: bool, message: str}
    """
    if not path:
        return {'valid': False, 'message': 'Path ว่างเปล่า'}
    
    # Check if path exists
    if not os.path.exists(path):
        try:
            os.makedirs(path, exist_ok=True)
        except PermissionError:
            return {'valid': False, 'message': f'ไม่มีสิทธิ์สร้างโฟลเดอร์: {path}'}
        except Exception as e:
            return {'valid': False, 'message': f'ไม่สามารถสร้างโฟลเดอร์: {str(e)}'}
    
    # Check if writable
    if not os.access(path, os.W_OK):
        return {'valid': False, 'message': f'ไม่มีสิทธิ์เขียนไฟล์ใน: {path}'}
    
    return {'valid': True, 'message': 'Path ถูกต้อง'}
