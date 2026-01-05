"""
Model service - Faster Whisper model management
"""
import os
from services.storage_service import get_storage_settings


# Available Whisper models with details
WHISPER_MODELS = {
    'tiny': {
        'size': '75 MB',
        'speed': 'เร็วที่สุด',
        'accuracy': 'ต่ำ',
        'description': 'เหมาะสำหรับทดสอบ'
    },
    'base': {
        'size': '142 MB',
        'speed': 'เร็ว',
        'accuracy': 'ปานกลาง',
        'description': 'แนะนำสำหรับการใช้งานทั่วไป'
    },
    'small': {
        'size': '466 MB',
        'speed': 'ปานกลาง',
        'accuracy': 'ดี',
        'description': 'สมดุลระหว่างความเร็วและความแม่นยำ'
    },
    'medium': {
        'size': '1.5 GB',
        'speed': 'ช้า',
        'accuracy': 'ดีมาก',
        'description': 'ความแม่นยำสูง'
    },
    'large': {
        'size': '3 GB',
        'speed': 'ช้ามาก',
        'accuracy': 'ดีที่สุด',
        'description': 'ความแม่นยำสูงสุด แต่ใช้เวลานาน'
    }
}


def get_models_directory():
    """
    Get the directory where models are stored
    
    Returns:
        str: Path to models directory
    """
    # Get storage settings
    storage = get_storage_settings()
    models_dir = storage.get('model_path', 'storage/models')
    
    # Create directory if not exists
    os.makedirs(models_dir, exist_ok=True)
    
    return models_dir


def get_all_models():
    """
    Get list of all available Whisper models with download status
    
    Returns:
        list: List of model dictionaries
    """
    models = []
    
    for model_name, info in WHISPER_MODELS.items():
        # Check if model is downloaded
        is_downloaded = check_model_downloaded(model_name)
        
        models.append({
            'name': model_name,
            'size': info['size'],
            'speed': info['speed'],
            'accuracy': info['accuracy'],
            'description': info['description'],
            'is_downloaded': is_downloaded
        })
    
    return models


def check_model_downloaded(model_name):
    """
    Check if a Faster Whisper model is downloaded
    
    Args:
        model_name: Model name (e.g., 'tiny', 'base', 'small', 'medium', 'large')
    
    Returns:
        bool: True if model is fully downloaded
    """
    try:
        # Get models directory
        models_dir = get_models_directory()
        
        # ✅ Support both patterns: faster-whisper-{name} and faster-whisper-{name}-v3
        possible_names = [
            f'models--Systran--faster-whisper-{model_name}',
            f'models--Systran--faster-whisper-{model_name}-v3'
        ]
        
        model_dir = None
        for name in possible_names:
            temp_dir = os.path.join(models_dir, name)
            if os.path.exists(temp_dir):
                model_dir = temp_dir
                break
        
        if not model_dir:
            return False
        
        # Check snapshots directory
        snapshots_dir = os.path.join(model_dir, 'snapshots')
        if not os.path.exists(snapshots_dir):
            return False
        
        # Check for snapshot folders
        try:
            snapshots = os.listdir(snapshots_dir)
            if not snapshots:
                return False
            
            # Check if snapshot has model files
            snapshot_path = os.path.join(snapshots_dir, snapshots[0])
            if os.path.isdir(snapshot_path):
                # Check for config.json or model.bin
                has_config = os.path.exists(os.path.join(snapshot_path, 'config.json'))
                has_model = os.path.exists(os.path.join(snapshot_path, 'model.bin'))
                
                if not (has_config or has_model):
                    return False
        except Exception as e:
            print(f"[Model Service] Error checking snapshots: {e}")
            return False
        
        # Check for incomplete files
        import glob
        incomplete_files = glob.glob(os.path.join(model_dir, '**', '*.incomplete'), recursive=True)
        if incomplete_files:
            return False
        
        return True
        
    except Exception as e:
        print(f"[Model Service] Error checking model {model_name}: {e}")
        return False





def download_model(model_name, progress_callback=None):
    """
    Download a Whisper model to project directory with progress tracking
    
    Args:
        model_name: Model name to download
        progress_callback: Optional callback function for progress updates
    
    Returns:
        dict: {success: bool, message: str, model_path: str}
    """
    if model_name not in WHISPER_MODELS:
        return {
            'success': False,
            'message': f'Invalid model name: {model_name}'
        }
    
    model_path = None
    progress_file = None
    
    try:
        import urllib.request
        import sys
        
        print(f"[Model Service] Downloading Whisper model: {model_name}")
        
        # Use direct path instead of get_storage_settings (to avoid app context issue)
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        models_dir = os.path.join(project_root, 'storage', 'models')
        os.makedirs(models_dir, exist_ok=True)
        
        model_path = os.path.join(models_dir, f"{model_name}.pt")
        
        # Check if already exists
        if os.path.exists(model_path):
            print(f"[Model Service] Model already exists, verifying...")
        
        # Use Faster Whisper instead
        from faster_whisper import WhisperModel
        
        print(f"[Model Service] Downloading Faster Whisper model: {model_name}")
        
        if progress_callback:
            progress_callback(0, f'กำลังดาวน์โหลดโมเดล {model_name}...')
        
        # Clean up any incomplete files from previous failed downloads
        try:
            import glob
            model_dir = os.path.join(models_dir, f'models--Systran--faster-whisper-{model_name}')
            if os.path.exists(model_dir):
                incomplete_files = glob.glob(os.path.join(model_dir, '**', '*.incomplete'), recursive=True)
                for incomplete_file in incomplete_files:
                    try:
                        os.remove(incomplete_file)
                        print(f"[Model Service] Removed incomplete file: {incomplete_file}")
                    except Exception as e:
                        print(f"[Model Service] Could not remove incomplete file: {e}")
        except Exception as e:
            print(f"[Model Service] Cleanup warning: {e}")
        
        # Create progress marker file
        progress_file = os.path.join(models_dir, f".{model_name}_progress.txt")
        with open(progress_file, 'w') as f:
            f.write('10')  # Started
        
        try:
            # Download using Faster Whisper (downloads from HuggingFace)
            model = WhisperModel(
                model_name,
                device="cpu",
                download_root=models_dir,
                compute_type="int8"
            )
            
            # Mark as complete
            with open(progress_file, 'w') as f:
                f.write('100')
            
            # Clean up progress file after a delay
            import time
            time.sleep(2)
            if os.path.exists(progress_file):
                os.remove(progress_file)
            
            return {
                'success': True,
                'message': f'ดาวน์โหลดโมเดล {model_name} สำเร็จ',
                'model_path': models_dir
            }
        except Exception as e:
            # Clean up progress file on error
            if os.path.exists(progress_file):
                os.remove(progress_file)
            raise e
    
    except Exception as e:
        error_msg = str(e)
        print(f"[Model Service] Error downloading model {model_name}: {error_msg}")
        
        # Clean up incomplete files if download failed
        try:
            import glob
            model_dir = os.path.join(get_models_directory(), f'models--Systran--faster-whisper-{model_name}')
            if os.path.exists(model_dir):
                # Find and remove .incomplete files
                incomplete_files = glob.glob(os.path.join(model_dir, '**', '*.incomplete'), recursive=True)
                for incomplete_file in incomplete_files:
                    try:
                        if os.path.exists(incomplete_file):
                            os.remove(incomplete_file)
                            print(f"[Model Service] Cleaned up incomplete file: {incomplete_file}")
                    except Exception as cleanup_err:
                        print(f"[Model Service] Could not remove {incomplete_file}: {cleanup_err}")
        except Exception as cleanup_error:
            print(f"[Model Service] Cleanup error: {cleanup_error}")
        
        if progress_callback:
            progress_callback(-1, f'ดาวน์โหลดล้มเหลว: {error_msg}')
        
        return {
            'success': False,
            'message': f'Error downloading model: {error_msg}'
        }


def get_download_progress(model_name):
    """
    Get current download progress for a Faster Whisper model
    
    Returns:
        dict: {status: str, progress: float} or None
    """
    try:
        models_dir = get_models_directory()
        progress_file = os.path.join(models_dir, f".{model_name}_progress.txt")
        model_dir = os.path.join(models_dir, f'models--Systran--faster-whisper-{model_name}')
        
        # Check if progress file exists (download started)
        if not os.path.exists(progress_file):
            return {'status': 'not_started', 'progress': 0}
        
        # Read progress marker
        try:
            with open(progress_file, 'r') as f:
                marker = int(f.read().strip())
                
            if marker >= 100:
                return {'status': 'completed', 'progress': 100}
        except:
            pass
        
        # Check if model directory exists
        if not os.path.exists(model_dir):
            return {'status': 'downloading', 'progress': 10}
        
        # Check for incomplete files
        import glob
        incomplete_files = glob.glob(os.path.join(model_dir, '**', '*.incomplete'), recursive=True)
        
        if incomplete_files:
            # Still downloading - estimate progress by checking file sizes
            total_size = 0
            downloaded_size = 0
            
            for file_path in glob.glob(os.path.join(model_dir, '**', '*'), recursive=True):
                if os.path.isfile(file_path):
                    size = os.path.getsize(file_path)
                    if not file_path.endswith('.incomplete'):
                        downloaded_size += size
                    total_size += size
            
            if total_size > 0:
                progress = min(95, 10 + (downloaded_size / total_size) * 85)
                return {'status': 'downloading', 'progress': int(progress)}
            
            return {'status': 'downloading', 'progress': 30}
        
        # Check if snapshots exist (download complete)
        snapshots_dir = os.path.join(model_dir, 'snapshots')
        if os.path.exists(snapshots_dir):
            snapshots = os.listdir(snapshots_dir)
            if snapshots:
                return {'status': 'completed', 'progress': 100}
        
        # In progress
        return {'status': 'downloading', 'progress': 50}
        
    except Exception as e:
        print(f"[Model Service] Error checking progress: {e}")
        return {'status': 'error', 'progress': 0}


def delete_model(model_name):
    """
    Delete a downloaded Whisper model
    
    Args:
        model_name: Model name to delete
    
    Returns:
        dict: {success: bool, message: str}
    """
    if model_name not in WHISPER_MODELS:
        return {
            'success': False,
            'message': f'Invalid model name: {model_name}'
        }
    
    try:
        # Get models directory
        models_dir = get_models_directory()
        model_path = os.path.join(models_dir, f"{model_name}.pt")
        
        if not os.path.exists(model_path):
            return {
                'success': False,
                'message': 'Model not found'
            }
        
        # Delete model file
        os.remove(model_path)
        
        print(f"[Model Service] Model deleted: {model_path}")
        
        return {
            'success': True,
            'message': f'Model {model_name} deleted successfully'
        }
    
    except Exception as e:
        print(f"[Model Service] Error deleting model {model_name}: {e}")
        return {
            'success': False,
            'message': f'Error deleting model: {str(e)}'
        }


def get_model_info(model_name):
    """
    Get detailed information about a specific model
    
    Args:
        model_name: Model name
    
    Returns:
        dict: Model information
    """
    if model_name not in WHISPER_MODELS:
        return None
    
    info = WHISPER_MODELS[model_name].copy()
    info['name'] = model_name
    info['is_downloaded'] = check_model_downloaded(model_name)
    
    # If downloaded, get file size
    if info['is_downloaded']:
        try:
            models_dir = get_models_directory()
            model_path = os.path.join(models_dir, f"{model_name}.pt")
            
            if os.path.exists(model_path):
                file_size = os.path.getsize(model_path)
                info['actual_size'] = f"{file_size / (1024*1024):.1f} MB"
                info['model_path'] = model_path
        except:
            pass
    
    return info

