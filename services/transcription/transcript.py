"""
Transcript queries, full-text searching, inline editing, and JSON summary export.
"""
import os
import re
import json
import html
import logging
from datetime import datetime
from collections import defaultdict
from database import query_all, query_one, execute, transaction
from services.storage_service import get_storage_settings
from core.paths import resolve_path

logger = logging.getLogger(__name__)


def get_transcript(meeting_id: int) -> list[dict]:
    """
    Get all transcription items for a meeting with unified speaker names.
    Single query joining text_file and voice_file.
    """
    rows = query_all(
        """SELECT 
            tf.id as text_id,
            tf.voice_id,
            tf.content,
            COALESCE(vf.speaker_name, 'ไม่ระบุ') as speaker_name,
            COALESCE(vf.start_time, '00:00:00') as start_time,
            COALESCE(vf.end_time, '00:00:00') as end_time,
            COALESCE(vf.duration, 0.0) as duration,
            vf.file_path,
            tf.created_at
        FROM text_file tf
        JOIN voice_file vf ON tf.voice_id = vf.voice_id
        WHERE tf.meeting_id = ?
        ORDER BY vf.start_time ASC, tf.voice_id ASC""",
        (meeting_id,)
    )
    return rows


def search_in_transcription(meeting_id: int,
                            query: str | None = None,
                            speaker: str | None = None,
                            time_from: str | None = None,
                            time_to: str | None = None) -> dict:
    """
    Search meeting transcriptions with keyword, speaker, and time range filters.
    Keyword matches are highlighted safely with HTML escaping.
    """
    try:
        sql = """
            SELECT 
                tf.voice_id,
                tf.content as text,
                COALESCE(vf.speaker_name, 'ไม่ระบุ') as speaker_name,
                COALESCE(vf.start_time, '00:00:00') as start_time,
                COALESCE(vf.end_time, '00:00:00') as end_time,
                COALESCE(vf.duration, 0.0) as duration
            FROM text_file tf
            JOIN voice_file vf ON tf.voice_id = vf.voice_id
            WHERE tf.meeting_id = ?
        """
        params = [meeting_id]

        if speaker:
            sql += " AND (vf.speaker_name LIKE ? OR vf.name LIKE ?)"
            params.extend([f"%{speaker}%", f"%{speaker}%"])

        if time_from:
            sql += " AND vf.start_time >= ?"
            params.append(time_from)

        if time_to:
            sql += " AND vf.end_time <= ?"
            params.append(time_to)

        sql += " ORDER BY vf.start_time ASC"
        rows = query_all(sql, tuple(params))

        results = []
        for row in rows:
            raw_text = row['text'] or ''

            # Keyword filter
            if query and query.lower() not in raw_text.lower():
                continue

            # Escape HTML before inserting <mark> tag to prevent XSS
            safe_text = html.escape(raw_text)
            if query:
                escaped_query = html.escape(query)
                pattern = re.compile(re.escape(escaped_query), re.IGNORECASE)
                highlighted_text = pattern.sub(lambda m: f"<mark>{m.group()}</mark>", safe_text)
            else:
                highlighted_text = safe_text

            results.append({
                'voice_id': row['voice_id'],
                'speaker_name': row['speaker_name'],
                'text': highlighted_text,
                'original_text': raw_text,
                'start_time': row['start_time'],
                'end_time': row['end_time'],
                'duration': row['duration']
            })

        return {
            'success': True,
            'results': results,
            'total': len(results),
            'query': query,
            'filters': {
                'speaker': speaker,
                'time_from': time_from,
                'time_to': time_to
            }
        }
    except Exception as e:
        logger.exception("Error searching transcription: %s", e)
        return {
            'success': False,
            'results': [],
            'total': 0,
            'message': str(e)
        }


def update_transcription(voice_id: int,
                         speaker_name: str | None = None,
                         text: str | None = None,
                         start_time: str | None = None,
                         end_time: str | None = None) -> dict:
    """
    Update transcription content and speaker metadata.
    Updates database records directly without breaking filenames on disk.
    """
    try:
        voice_row = query_one("SELECT meeting_id FROM voice_file WHERE voice_id = ?", (voice_id,))
        if not voice_row:
            return {'success': False, 'message': 'Voice record not found'}

        meeting_id = voice_row['meeting_id']

        with transaction():
            if text is not None:
                execute(
                    "UPDATE text_file SET content = ? WHERE voice_id = ?",
                    (text, voice_id)
                )

            vf_updates = []
            vf_params = []
            if speaker_name is not None:
                vf_updates.append("speaker_name = ?")
                vf_params.append(speaker_name)
            if start_time is not None:
                vf_updates.append("start_time = ?")
                vf_params.append(start_time)
            if end_time is not None:
                vf_updates.append("end_time = ?")
                vf_params.append(end_time)

            if vf_updates:
                vf_params.append(voice_id)
                execute(
                    f"UPDATE voice_file SET {', '.join(vf_updates)} WHERE voice_id = ?",
                    tuple(vf_params)
                )

        # Regenerate meeting JSON summary file
        job = query_one(
            "SELECT model_used, language FROM transcription_jobs WHERE meeting_id = ? ORDER BY job_id DESC LIMIT 1",
            (meeting_id,)
        )
        model = job['model_used'] if job and job['model_used'] else 'unknown'
        lang = job['language'] if job and job['language'] else 'th'
        write_summary_json(meeting_id, model, lang)

        logger.info("Updated transcription voice_id=%d", voice_id)
        return {'success': True, 'message': 'Transcription updated successfully'}

    except Exception as e:
        logger.exception("Error updating transcription voice_id=%d: %s", voice_id, e)
        return {'success': False, 'message': f'Error updating: {str(e)}'}


def build_summary(meeting_id: int,
                  model_used: str = 'base',
                  language: str = 'th',
                  transcription_start: datetime | None = None,
                  transcription_end: datetime | None = None,
                  parallel_workers: int = 1) -> dict:
    """
    Build structured JSON summary dictionary containing meeting details,
    transcription items, speaker statistics, and technical performance metrics.
    """
    meeting = query_one(
        "SELECT meeting_name, meeting_date FROM meetings WHERE meeting_id = ?",
        (meeting_id,)
    )
    items = get_transcript(meeting_id)

    total_audio_duration = 0.0
    total_text_length = 0
    total_word_count = 0
    speakers_data = defaultdict(lambda: {
        'speaker_name': '',
        'audio_count': 0,
        'audio_duration': 0.0,
        'text_length': 0,
        'word_count': 0
    })

    transcription_list = []
    for item in items:
        content = item['content'] or ''
        duration = float(item['duration'] or 0.0)
        speaker_name = item['speaker_name'] or 'ไม่ระบุ'

        words = len(content.split())
        chars = len(content)

        total_text_length += chars
        total_word_count += words
        total_audio_duration += duration

        spk = speakers_data[speaker_name]
        spk['speaker_name'] = speaker_name
        spk['audio_count'] += 1
        spk['audio_duration'] += duration
        spk['text_length'] += chars
        spk['word_count'] += words

        transcription_list.append({
            'voice_id': item['voice_id'],
            'speaker_name': speaker_name,
            'start_time': item['start_time'],
            'end_time': item['end_time'],
            'duration': round(duration, 2),
            'text': content,
            'word_count': words,
            'char_count': chars
        })

    transcription_duration = None
    average_speed = None
    if transcription_start and transcription_end:
        transcription_duration = (transcription_end - transcription_start).total_seconds()
        if transcription_duration > 0:
            average_speed = round(total_audio_duration / transcription_duration, 2)

    speakers_stats = list(speakers_data.values())
    for s in speakers_stats:
        s['audio_duration'] = round(s['audio_duration'], 2)
    speakers_stats.sort(key=lambda x: x['audio_count'], reverse=True)

    return {
        'meeting_info': {
            'meeting_id': meeting_id,
            'meeting_name': meeting['meeting_name'] if meeting else 'Unknown',
            'meeting_date': meeting['meeting_date'] if meeting else None
        },
        'transcription_info': {
            'model_used': model_used,
            'language': language,
            'transcription_date': datetime.now().isoformat(),
            'transcription_start_time': transcription_start.isoformat() if transcription_start else None,
            'transcription_end_time': transcription_end.isoformat() if transcription_end else None,
            'transcription_duration_seconds': round(transcription_duration, 2) if transcription_duration else None
        },
        'statistics': {
            'total_audio_files': len(items),
            'total_audio_duration_seconds': round(total_audio_duration, 2),
            'total_text_length': total_text_length,
            'total_word_count': total_word_count,
            'average_transcription_speed': average_speed,
            'speakers_count': len(speakers_data),
            'parallel_workers': parallel_workers
        },
        'speakers_stats': speakers_stats,
        'transcriptions': transcription_list
    }


def write_summary_json(meeting_id: int,
                       model_used: str = 'base',
                       language: str = 'th',
                       transcription_start: datetime | None = None,
                       transcription_end: datetime | None = None,
                       parallel_workers: int = 1) -> str | None:
    """Generate and write meeting transcription JSON file into storage/transcriptions."""
    try:
        data = build_summary(
            meeting_id, model_used, language,
            transcription_start, transcription_end, parallel_workers
        )
        storage = get_storage_settings()
        folder = os.path.join(storage['transcription_path'], f"meeting_{meeting_id}")
        os.makedirs(folder, exist_ok=True)

        json_path = os.path.join(folder, f"meeting_{meeting_id}_transcription.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("Saved transcription summary to %s", json_path)
        return json_path
    except Exception as e:
        logger.exception("Failed to write summary JSON for meeting %d: %s", meeting_id, e)
        return None


def delete_meeting_transcription(meeting_id: int) -> bool:
    """Delete all transcription records and text files for a meeting."""
    try:
        storage = get_storage_settings()
        folder = os.path.join(storage['transcription_path'], f"meeting_{meeting_id}")
        if os.path.exists(folder):
            import shutil
            shutil.rmtree(folder, ignore_errors=True)

        with transaction():
            execute("DELETE FROM text_file WHERE meeting_id = ?", (meeting_id,))
            execute("DELETE FROM transcription_jobs WHERE meeting_id = ?", (meeting_id,))
            execute("UPDATE meetings SET status = 'completed' WHERE meeting_id = ?", (meeting_id,))

        logger.info("Deleted all transcriptions for meeting %d", meeting_id)
        return True
    except Exception as e:
        logger.exception("Error deleting transcriptions for meeting %d: %s", meeting_id, e)
        return False
