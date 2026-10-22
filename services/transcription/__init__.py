"""
Transcription package exports.
"""
from services.transcription.models import (
    WHISPER_MODELS,
    get_all_models,
    check_model_downloaded,
    download_model,
    get_download_progress,
    delete_model,
    get_model_info,
    get_models_directory
)
from services.transcription.engine import (
    get_cached_model,
    evict_model
)
from services.transcription.jobs import (
    transcribe_meeting,
    create_transcription_job,
    get_transcription_job_status,
    start_transcription_job,
    recover_stale_jobs
)
from services.transcription.transcript import (
    get_transcript,
    search_in_transcription,
    update_transcription,
    delete_meeting_transcription,
    build_summary,
    write_summary_json
)

def get_available_models():
    """Compatibility helper returning list of models with download info."""
    models = []
    for name, info in WHISPER_MODELS.items():
        if check_model_downloaded(name):
            models.append({
                'name': name,
                'size': info['size'],
                'display_name': f"{name} ({info['size']})"
            })
    if not models:
        for name, info in WHISPER_MODELS.items():
            models.append({
                'name': name,
                'size': info['size'],
                'display_name': f"{name} ({info['size']}) - จะดาวน์โหลดเมื่อใช้งาน"
            })
    return models

__all__ = [
    'WHISPER_MODELS',
    'get_all_models',
    'get_available_models',
    'check_model_downloaded',
    'download_model',
    'get_download_progress',
    'delete_model',
    'get_model_info',
    'get_models_directory',
    'get_cached_model',
    'evict_model',
    'transcribe_meeting',
    'create_transcription_job',
    'get_transcription_job_status',
    'start_transcription_job',
    'recover_stale_jobs',
    'get_transcript',
    'search_in_transcription',
    'update_transcription',
    'delete_meeting_transcription',
    'build_summary',
    'write_summary_json',
]
