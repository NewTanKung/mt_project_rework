"""
Configuration settings for Meeting Recorder Application
"""
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load environment variables from .env if present
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Instance directory (for machine-specific generated secrets, etc.)
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')

# Database
DATABASE_PATH = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'database.db'))

def load_or_create_secret_key() -> str:
    """
    Get secret key from environment or persistent instance file, or generate a new one.
    """
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    secret_file = os.path.join(INSTANCE_DIR, 'secret_key')
    if os.path.exists(secret_file):
        try:
            with open(secret_file, 'r', encoding='utf-8') as f:
                key = f.read().strip()
                if key:
                    return key
        except Exception:
            pass
            
    key = secrets.token_hex(32)
    try:
        with open(secret_file, 'w', encoding='utf-8') as f:
            f.write(key)
    except Exception:
        pass
    return key

# Flask
SECRET_KEY = load_or_create_secret_key()
FLASK_HOST = os.environ.get('FLASK_HOST', '127.0.0.1')
FLASK_PORT = int(os.environ.get('FLASK_PORT', '5000'))
FLASK_DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'

# Storage paths (defaults relative to BASE_DIR)
STORAGE_DIR = os.path.join(BASE_DIR, 'storage')
AUDIO_DIR = os.path.join(STORAGE_DIR, 'audio')
TRANSCRIPTION_DIR = os.path.join(STORAGE_DIR, 'transcriptions')
EXPORT_DIR = os.path.join(STORAGE_DIR, 'exports')
MODEL_DIR = os.path.join(STORAGE_DIR, 'models')

# Audio recording settings
SAMPLE_RATE = 16000  # Hz (Whisper optimal)
CHANNELS = 1         # Mono
DTYPE = 'int16'      # 16-bit PCM
CHUNK_SIZE = 1024

# Speech Detection Settings
RMS_THRESHOLD = float(os.environ.get('RMS_THRESHOLD', '0.01'))
MIN_SPEECH_DURATION = float(os.environ.get('MIN_SPEECH_DURATION', '0.5'))
MIN_SILENCE_DURATION = float(os.environ.get('MIN_SILENCE_DURATION', '3.0'))
ENABLE_REALTIME_RESAMPLING = False

# Transcription settings
DEFAULT_LANGUAGE = os.environ.get('DEFAULT_LANGUAGE', 'th')
DEVICE = os.environ.get('DEVICE', 'cpu')  # 'cuda' or 'cpu'
COMPUTE_TYPE = os.environ.get('COMPUTE_TYPE', 'int8')
MAX_TRANSCRIPTION_WORKERS = int(os.environ.get('MAX_TRANSCRIPTION_WORKERS', '4'))

# Logging
LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'app.log')

def ensure_storage_dirs():
    """Ensure all required runtime directories exist."""
    for directory in [STORAGE_DIR, AUDIO_DIR, TRANSCRIPTION_DIR, EXPORT_DIR, MODEL_DIR, LOG_DIR, INSTANCE_DIR]:
        os.makedirs(directory, exist_ok=True)
