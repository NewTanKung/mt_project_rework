"""
Transcription job queue, background worker, and lifecycle management.
"""
import os
import threading
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from database import query_one, query_all, execute, transaction
from services.storage_service import get_storage_settings
from services.transcription.models import check_model_downloaded, WHISPER_MODELS
from services.transcription.engine import get_cached_model
from services.transcription.transcript import write_summary_json
from core.paths import resolve_path
from config import MAX_TRANSCRIPTION_WORKERS

logger = logging.getLogger(__name__)


def create_transcription_job(meeting_id: int, model_used: str, language: str = 'th') -> int:
    """Create a new pending transcription job record."""
    return execute(
        """INSERT INTO transcription_jobs (meeting_id, model_used, language, status, progress)
           VALUES (?, ?, ?, 'pending', 0)""",
        (meeting_id, model_used, language)
    )


def get_transcription_job_status(job_id: int) -> dict | None:
    """Get status information for a transcription job."""
    return query_one("SELECT * FROM transcription_jobs WHERE job_id = ?", (job_id,))


def recover_stale_jobs():
    """
    Recover jobs that were left running or pending when the server last stopped.
    Called once during application initialization.
    """
    try:
        updated = execute(
            """UPDATE transcription_jobs
               SET status = 'failed', error_message = 'Interrupted by application restart'
               WHERE status IN ('pending', 'processing')"""
        )
        logger.info("Checked for stale transcription jobs on startup")
    except Exception as e:
        logger.error("Error recovering stale jobs: %s", e)


def start_transcription_job(job_id: int) -> bool:
    """Start background worker thread for a job."""
    job = get_transcription_job_status(job_id)
    if not job:
        return False

    thread = threading.Thread(
        target=_transcribe_worker,
        args=(job_id, job['meeting_id'], job['model_used'], job['language']),
        daemon=True
    )
    thread.start()
    return True


def _transcribe_worker(job_id: int, meeting_id: int, model_used: str, language: str = 'th'):
    """
    Background worker thread performing speech recognition across all audio segments of a meeting.
    Uses thread-local database connections so it does not require an active Flask request context.
    """
    logger.info("Starting transcription job %d for meeting %d (model=%s, lang=%s)",
                job_id, meeting_id, model_used, language)

    transcription_start = datetime.now()
    transcription_end = None
    processed = 0
    total_files = 0
    max_workers = 1

    try:
        execute(
            "UPDATE transcription_jobs SET status = 'processing', started_at = ? WHERE job_id = ?",
            (transcription_start.strftime('%Y-%m-%d %H:%M:%S'), job_id)
        )

        model = get_cached_model(model_used)

        voice_files = query_all(
            """SELECT voice_id, file_path, person_id, start_time, end_time, name
               FROM voice_file
               WHERE meeting_id = ?
               ORDER BY voice_id""",
            (meeting_id,)
        )

        if not voice_files:
            raise RuntimeError("No voice files found for this meeting")

        total_files = len(voice_files)
        max_workers = min(MAX_TRANSCRIPTION_WORKERS, total_files)

        storage = get_storage_settings()
        meeting_text_folder = os.path.join(storage['transcription_path'], f"meeting_{meeting_id}")
        os.makedirs(meeting_text_folder, exist_ok=True)

        def transcribe_single(vf: dict) -> dict:
            voice_id = vf['voice_id']
            rel_or_abs = vf['file_path']
            abs_path = resolve_path(rel_or_abs)

            if not os.path.exists(abs_path):
                return {'success': False, 'error': f"Audio file not found: {abs_path}", 'voice_id': voice_id}

            try:
                segments, info = model.transcribe(
                    abs_path,
                    language=language,
                    vad_filter=True,
                    word_timestamps=False
                )
                full_text = " ".join(seg.text for seg in segments).strip()
                if not full_text:
                    full_text = "-"

                base_name = os.path.splitext(os.path.basename(abs_path))[0]
                txt_filename = f"{base_name}_transcription.txt"
                txt_path = os.path.join(meeting_text_folder, txt_filename)

                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(f"ไฟล์เสียง: {os.path.basename(abs_path)}\n")
                    f.write(f"โมเดล: {model_used}\n")
                    f.write(f"ภาษา: {language}\n")
                    f.write(f"วันที่: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("-" * 50 + "\n\n")
                    f.write(full_text)

                # Upsert into text_file: delete any existing transcription for this voice segment
                with transaction():
                    execute("DELETE FROM text_file WHERE voice_id = ?", (voice_id,))
                    execute(
                        """INSERT INTO text_file 
                           (voice_id, name, person_id, meeting_id, content, model_used, language)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (voice_id, txt_filename, vf['person_id'], meeting_id, full_text, model_used, language)
                    )

                return {'success': True, 'file': os.path.basename(abs_path), 'voice_id': voice_id}
            except Exception as ex:
                return {'success': False, 'error': str(ex), 'voice_id': voice_id}

        # Process segments with thread pool
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(transcribe_single, vf): vf for vf in voice_files}
            for future in as_completed(futures):
                processed += 1
                result = future.result()
                progress_pct = int((processed / total_files) * 100)
                execute(
                    "UPDATE transcription_jobs SET progress = ? WHERE job_id = ?",
                    (progress_pct, job_id)
                )
                if result['success']:
                    logger.info("Transcribed [%d/%d]: %s", processed, total_files, result.get('file'))
                else:
                    logger.warning("Failed [%d/%d]: %s", processed, total_files, result.get('error'))

        transcription_end = datetime.now()

        # Generate summary JSON
        write_summary_json(
            meeting_id,
            model_used=model_used,
            language=language,
            transcription_start=transcription_start,
            transcription_end=transcription_end,
            parallel_workers=max_workers
        )

        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with transaction():
            execute(
                "UPDATE transcription_jobs SET status = 'completed', completed_at = ?, progress = 100 WHERE job_id = ?",
                (now_str, job_id)
            )
            execute(
                "UPDATE meetings SET status = 'transcribed' WHERE meeting_id = ?",
                (meeting_id,)
            )

        logger.info("Job %d completed successfully! Processed %d/%d files.", job_id, processed, total_files)

    except Exception as e:
        logger.exception("Job %d failed: %s", job_id, e)
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with transaction():
            execute(
                "UPDATE transcription_jobs SET status = 'failed', error_message = ?, completed_at = ? WHERE job_id = ?",
                (str(e), now_str, job_id)
            )
            # Ensure summary JSON is still generated for any completed segments
            try:
                write_summary_json(meeting_id, model_used, language)
            except Exception:
                pass


def transcribe_meeting(meeting_id: int, model_used: str, language: str = 'th') -> dict:
    """
    Validate and launch transcription for a meeting.
    """
    voice_count = query_one(
        "SELECT COUNT(*) as count FROM voice_file WHERE meeting_id = ?",
        (meeting_id,)
    )
    if not voice_count or voice_count['count'] == 0:
        return {'success': False, 'message': 'ไม่พบไฟล์เสียงสำหรับการประชุมนี้'}

    active_job = query_one(
        """SELECT job_id FROM transcription_jobs
           WHERE meeting_id = ? AND status IN ('pending', 'processing')""",
        (meeting_id,)
    )
    if active_job:
        return {
            'success': False,
            'message': 'มีงาน transcription ที่กำลังดำเนินการอยู่แล้ว',
            'job_id': active_job['job_id']
        }

    if model_used not in WHISPER_MODELS:
        return {'success': False, 'message': f'โมเดลไม่ถูกต้อง: {model_used}'}

    if not check_model_downloaded(model_used):
        return {
            'success': False,
            'message': f'โมเดล {model_used} ยังไม่ได้ดาวน์โหลด กรุณาดาวน์โหลดผ่านหน้า Admin ก่อน'
        }

    job_id = create_transcription_job(meeting_id, model_used, language)
    if not job_id:
        return {'success': False, 'message': 'ไม่สามารถสร้างงานถอดเสียงได้'}

    started = start_transcription_job(job_id)
    if started:
        return {'success': True, 'job_id': job_id, 'message': 'เริ่มถอดเสียงแล้ว'}
    return {'success': False, 'message': 'ไม่สามารถเริ่มงานถอดเสียงได้'}
