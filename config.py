"""
Configuration settings for Meeting Recorder Application
"""
import os

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database
DATABASE_PATH = os.path.join(BASE_DIR, 'database.db')
SCHEMA_PATH = os.path.join(BASE_DIR, 'schema.sql')

# Flask
SECRET_KEY = 'your-secret-key-change-this-in-production'
FLASK_HOST = '127.0.0.1'
FLASK_PORT = 5000

# Storage paths (default)
STORAGE_DIR = os.path.join(BASE_DIR, 'storage')
AUDIO_DIR = os.path.join(STORAGE_DIR, 'audio')
TRANSCRIPTION_DIR = os.path.join(STORAGE_DIR, 'transcriptions')
EXPORT_DIR = os.path.join(STORAGE_DIR, 'exports')
MODEL_DIR = os.path.join(STORAGE_DIR, 'models')

# Audio recording settings
SAMPLE_RATE = 16000  # Hz (Whisper optimal)
CHANNELS = 1  # Mono
DTYPE = 'int16'  # 16-bit PCM
CHUNK_SIZE = 1024
# Speech Detection Settings
RMS_THRESHOLD = 0.01  # Minimum RMS level to consider as speech
MIN_SPEECH_DURATION = 0.5  # Minimum duration (seconds) to start recording
MIN_SILENCE_DURATION = 3.0  # ✅ เพิ่มเป็น 5 วิ - ต้องเงียบนาน 5 วิก่อนบันทึกไฟล์
ENABLE_REALTIME_RESAMPLING = False  # Set to True if devices support different sample rates

# Transcription settings
WHISPER_MODELS = ['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3']
DEFAULT_LANGUAGE = 'th'
DEVICE = 'cpu'  # 'cuda' or 'cpu'
MAX_TRANSCRIPTION_WORKERS = 4  # Max parallel workers for transcription

# Logging
LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'app.log')

# Ensure directories exist
for directory in [STORAGE_DIR, AUDIO_DIR, TRANSCRIPTION_DIR, EXPORT_DIR, MODEL_DIR, LOG_DIR]:
    os.makedirs(directory, exist_ok=True)
