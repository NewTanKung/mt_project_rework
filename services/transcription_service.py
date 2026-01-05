"""
Transcription Service
Handles transcription jobs using Faster Whisper
"""
import os
import json
import threading
import re
from datetime import datetime
from faster_whisper import WhisperModel
from database.db_manager import execute_query
from services.storage_service import get_storage_settings


def get_available_models():
    """
    Get list of available (downloaded) Faster Whisper models for transcription
    
    Returns:
        list: List of dictionaries with model info (name, size, display_name)
    """
    from services.model_service import WHISPER_MODELS, check_model_downloaded
    
    available = []
    
    for name, info in WHISPER_MODELS.items():
        # Check if model is downloaded using the updated function
        if check_model_downloaded(name):
            available.append({
                'name': name,
                'size': info['size'],
                'display_name': f"{name} ({info['size']})"
            })
    
    # If no models downloaded, show all with note
    if not available:
        for name, info in WHISPER_MODELS.items():
            available.append({
                'name': name,
                'size': info['size'],
                'display_name': f"{name} ({info['size']}) - จะดาวน์โหลดเมื่อใช้งาน"
            })
    
    return available


def create_transcription_job(meeting_id, model_used, language='th'):
    """
    Create a new transcription job record
    
    Args:
        meeting_id: Meeting ID
        model_used: Whisper model to use
        language: Language code (default: 'th')
    
    Returns:
        int: Job ID
    """
    job_id = execute_query(
        """INSERT INTO transcription_jobs (meeting_id, model_used, language, status, progress)
           VALUES (?, ?, ?, 'pending', 0)""",
        (meeting_id, model_used, language),
        commit=True
    )
    
    return job_id


def get_transcription_job_status(job_id):
    """
    Get transcription job status
    
    Returns:
        dict: Job status information
    """
    job = execute_query(
        "SELECT * FROM transcription_jobs WHERE job_id = ?",
        (job_id,),
        fetch_one=True
    )
    
    return job


def start_transcription_job(job_id):
    """
    Start transcription job in background thread
    
    Args:
        job_id: Job ID to start
    
    Returns:
        bool: True if started successfully
    """
    # Get job details
    job = get_transcription_job_status(job_id)
    
    if not job:
        return False
    
    # Get Flask app instance
    from flask import current_app
    app = current_app._get_current_object()
    
    # Start transcription in background thread with app context
    thread = threading.Thread(
        target=_transcribe_job_worker,
        args=(app, job_id, job['meeting_id'], job['model_used'], job['language'])
    )
    thread.daemon = True
    thread.start()
    
    return True


def _finalize_transcription_job(app, job_id, meeting_id, model_used, language, processed, total_files, success=True, error_message=None, transcription_start=None, transcription_end=None, parallel_workers=1):
    """
    Finalize transcription job - common logic for both success and failure paths
    
    Args:
        app: Flask application instance
        job_id: Job ID
        meeting_id: Meeting ID
        model_used: Model name
        language: Language code
        processed: Number of files processed
        total_files: Total number of files
        success: Whether job succeeded
        error_message: Error message if failed
        transcription_start: Start time of transcription
        transcription_end: End time of transcription
        parallel_workers: Number of parallel workers used
    """
    with app.app_context():
        try:
            # Create consolidated JSON with stats
            _create_meeting_json(
                meeting_id, model_used, language,
                transcription_start=transcription_start,
                transcription_end=transcription_end,
                total_files=total_files,
                parallel_workers=parallel_workers
            )
            
            if success:
                # Update job status to completed
                execute_query(
                    "UPDATE transcription_jobs SET status = 'completed', completed_at = ? WHERE job_id = ?",
                    (datetime.now(), job_id),
                    commit=True
                )
                print(f"[Transcription] ✅ Job {job_id} completed successfully!")
            else:
                # Update job status to failed
                execute_query(
                    "UPDATE transcription_jobs SET status = 'failed', error_message = ? WHERE job_id = ?",
                    (error_message, job_id),
                    commit=True
                )
                print(f"[Transcription] ❌ Job {job_id} failed: {error_message}")
            
            # Update meeting status to 'transcribed' even if some files failed
            execute_query(
                "UPDATE meetings SET status = 'transcribed' WHERE meeting_id = ?",
                (meeting_id,),
                commit=True
            )
            
            print(f"[Transcription] Job {job_id} finalized. Processed {processed}/{total_files} files.")
            
        except Exception as e:
            print(f"[Transcription] Error finalizing job {job_id}: {e}")


def _transcribe_job_worker(app, job_id, meeting_id, model_used, language='th'):
    """
    Background worker for transcription job
    Runs inside Flask app context to access database
    
    Args:
        app: Flask application instance
        job_id: Job ID
        meeting_id: Meeting ID
        model_used: Whisper model name
        language: Language code
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from services.model_cache import get_cached_model
    
    with app.app_context():
        processed = 0
        total_files = 0
        transcription_start = None
        transcription_end = None
        max_workers = 1
        
        try:
            # ✅ บันทึกเวลาเริ่มถอดเสียง
            transcription_start = datetime.now()
            
            # Update status to processing
            execute_query(
                "UPDATE transcription_jobs SET status = 'processing' WHERE job_id = ?",
                (job_id,),
                commit=True
            )
            
            # ✅ Load model from cache (ลด load time!)
            print(f"[Transcription] Loading model from cache: {model_used}")
            model = get_cached_model(model_used, device="cpu", compute_type="int8")
            
            # Get all voice files for this meeting
            voice_files = execute_query(
                """SELECT voice_id, file_path, person_id, start_time, end_time 
                   FROM voice_file 
                   WHERE meeting_id = ?
                   ORDER BY voice_id""",
                (meeting_id,),
                fetch_all=True
            )
            
            if not voice_files:
                raise Exception("No voice files found for this meeting")
            
            total_files = len(voice_files)
            print(f"[Transcription] Processing {total_files} files...")
            
            # ✅ Parallel processing (เร็วขึ้น 50-70%!)
            from config import MAX_TRANSCRIPTION_WORKERS
            max_workers = min(MAX_TRANSCRIPTION_WORKERS, total_files)  # ใช้ค่าจาก config
            
            def transcribe_file(voice_file):
                """Transcribe single file"""
                # ✅ Run inside app context for database access
                with app.app_context():
                    voice_id = voice_file['voice_id']
                    file_path = voice_file['file_path']
                    person_id = voice_file['person_id']
                    
                    if not os.path.exists(file_path):
                        return {'success': False, 'error': f'File not found: {file_path}'}
                    
                    try:
                        # Transcribe
                        segments, info = model.transcribe(
                            file_path,
                            language=language,
                            vad_filter=True,
                            word_timestamps=False
                        )
                        
                        # Combine segments
                        full_text = " ".join(segment.text for segment in segments).strip()
                        
                        if not full_text:
                            return {'success': False, 'error': 'No text generated'}
                        
                        # Save text file in meeting-specific folder
                        storage_settings = get_storage_settings()
                        transcription_root = storage_settings.get('transcription_path', 'storage/transcriptions')
                        
                        # Create meeting-specific folder
                        meeting_text_folder = os.path.join(transcription_root, f'meeting_{meeting_id}')
                        os.makedirs(meeting_text_folder, exist_ok=True)
                        
                        base_name = os.path.splitext(os.path.basename(file_path))[0]
                        text_filename = f"{base_name}_transcription.txt"
                        text_filepath = os.path.join(meeting_text_folder, text_filename)
                        
                        with open(text_filepath, 'w', encoding='utf-8') as f:
                            f.write(f"ไฟล์เสียง: {os.path.basename(file_path)}\n")
                            f.write(f"โมเดล: {model_used}\n")
                            f.write(f"ภาษา: {language}\n")
                            f.write(f"วันที่: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                            f.write("-" * 50 + "\n\n")
                            f.write(full_text)
                        
                        # Save to database
                        execute_query(
                            """INSERT INTO text_file 
                               (voice_id, name, person_id, meeting_id, content, model_used, language)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (voice_id, text_filename, person_id, meeting_id, 
                             full_text, model_used, language),
                            commit=True
                        )
                        
                        return {
                            'success': True,
                            'file': os.path.basename(file_path),
                            'text_file': text_filepath,
                            'text_length': len(full_text)
                        }
                        
                    except Exception as e:
                        return {'success': False, 'error': str(e), 'file': file_path}
            
            # Process files in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(transcribe_file, vf): vf for vf in voice_files}
                
                for future in as_completed(futures):
                    processed += 1
                    result = future.result()
                    
                    # ✅ อัพเดต progress
                    progress_percent = int((processed / total_files) * 100)
                    execute_query(
                        "UPDATE transcription_jobs SET progress = ? WHERE job_id = ?",
                        (progress_percent, job_id),
                        commit=True
                    )
                    
                    if result['success']:
                        print(f"[Transcription] ✅ {processed}/{total_files}: {result['file']}")
                    else:
                        print(f"[Transcription] ❌ {processed}/{total_files}: {result.get('error')}")
            
            # ✅ บันทึกเวลาจบถอดเสียง
            transcription_end = datetime.now()
            
            # Finalize job as success
            _finalize_transcription_job(
                app, job_id, meeting_id, model_used, language,
                processed, total_files, success=True,
                transcription_start=transcription_start,
                transcription_end=transcription_end,
                parallel_workers=max_workers
            )
            
        except Exception as e:
            # บันทึกเวลาจบแม้ error
            if transcription_end is None:
                transcription_end = datetime.now()
            
            # Finalize job as failed
            _finalize_transcription_job(
                app, job_id, meeting_id, model_used, language,
                processed, total_files, success=False, error_message=str(e),
                transcription_start=transcription_start,
                transcription_end=transcription_end,
                parallel_workers=max_workers
            )


def transcribe_meeting(meeting_id, model_used, language='th'):
    """
    Transcribe all audio files for a meeting using Faster Whisper
    
    Args:
        meeting_id: Meeting ID
        model_used: Whisper model name
        language: Language code
    
    Returns:
        dict: {success: bool, message: str, job_id: int}
    """
    # Check if meeting exists and has voice files
    voice_count = execute_query(
        "SELECT COUNT(*) as count FROM voice_file WHERE meeting_id = ?",
        (meeting_id,),
        fetch_one=True
    )
    
    if not voice_count or voice_count['count'] == 0:
        return {
            'success': False,
            'message': 'ไม่พบไฟล์เสียงสำหรับการประชุมนี้'
        }
    
    # Check if there's already an active transcription job for this meeting
    active_job = execute_query(
        """SELECT job_id, status FROM transcription_jobs 
           WHERE meeting_id = ? AND status IN ('pending', 'processing')""",
        (meeting_id,),
        fetch_one=True
    )
    
    if active_job:
        return {
            'success': False,
            'message': 'มีงาน transcription ที่กำลังดำเนินการอยู่แล้ว',
            'job_id': active_job['job_id']
        }
    
    # Validate model name
    if model_used not in ['tiny', 'base', 'small', 'medium', 'large']:
        return {
            'success': False,
            'message': f'โมเดลไม่ถูกต้อง: {model_used}'
        }
    
    # Check if model is downloaded
    from services.model_service import check_model_downloaded
    if not check_model_downloaded(model_used):
        return {
            'success': False,
            'message': f'โมเดล {model_used} ยังไม่ได้ดาวน์โหลด กรุณาดาวน์โหลดผ่านหน้า Admin ก่อน'
        }
    
    # Create transcription job
    job_id = create_transcription_job(meeting_id, model_used, language)
    
    if not job_id:
        return {
            'success': False,
            'message': 'ไม่สามารถสร้างงานถอดเสียงได้'
        }
    
    # Start transcription in background
    if start_transcription_job(job_id):
        return {
            'success': True,
            'job_id': job_id,
            'message': 'เริ่มถอดเสียงแล้ว'
        }
    else:
        return {
            'success': False,
            'message': 'ไม่สามารถเริ่มงานถอดเสียงได้'
        }


def _create_meeting_json(meeting_id, model_used, language, transcription_start=None, transcription_end=None, total_files=0, parallel_workers=1):
    """
    Create consolidated JSON file for meeting transcriptions with comprehensive statistics
    
    Args:
        meeting_id: Meeting ID
        model_used: Model used for transcription
        language: Language code
        transcription_start: Start time of transcription process
        transcription_end: End time of transcription process
        total_files: Total number of files processed
        parallel_workers: Number of parallel workers used
    """
    try:
        from datetime import datetime
        from collections import defaultdict
        
        # Get meeting info
        meeting = execute_query(
            "SELECT meeting_name, meeting_date FROM meetings WHERE meeting_id = ?",
            (meeting_id,),
            fetch_one=True
        )
        
        # Get all transcriptions with file info
        transcriptions = execute_query(
            """SELECT tf.voice_id, tf.content, tf.person_id,
                      vf.name as file_name, vf.start_time, vf.end_time, vf.duration
               FROM text_file tf
               JOIN voice_file vf ON tf.voice_id = vf.voice_id
               WHERE tf.meeting_id = ?
               ORDER BY vf.start_time ASC""",
            (meeting_id,),
            fetch_all=True
        )
        
        # ✅ คำนวณสถิติเชิงเทคนิค
        total_audio_duration = 0.0
        total_text_length = 0
        total_word_count = 0
        transcription_list = []
        speakers_data = defaultdict(lambda: {
            'speaker_name': '',
            'audio_count': 0,
            'audio_duration': 0.0,
            'text_length': 0,
            'word_count': 0
        })
        
        for trans in transcriptions:
            content = trans['content'] or ''
            duration = trans['duration'] or 0
            # Extract speaker name from filename
            speaker_name = trans['file_name'].split('_')[0] if '_' in trans['file_name'] else 'ไม่ระบุ'
            
            # Count words and characters
            words = len(content.split())
            chars = len(content)
            
            total_text_length += chars
            total_word_count += words
            total_audio_duration += duration
            
            # Update speaker stats
            speaker_id = trans['person_id'] or speaker_name
            speakers_data[speaker_id]['speaker_name'] = speaker_name
            speakers_data[speaker_id]['audio_count'] += 1
            speakers_data[speaker_id]['audio_duration'] += duration
            speakers_data[speaker_id]['text_length'] += chars
            speakers_data[speaker_id]['word_count'] += words
            
            transcription_list.append({
                'voice_id': trans['voice_id'],
                'speaker_name': speaker_name,
                'start_time': trans['start_time'] or '00:00:00',
                'end_time': trans['end_time'] or '00:00:00',
                'duration': duration,
                'text': content,
                'word_count': words,
                'char_count': chars
            })
        
        # ✅ คำนวณเวลาถอดเสียงและความเร็ว
        transcription_duration = None
        average_speed = None
        
        if transcription_start and transcription_end:
            transcription_duration = (transcription_end - transcription_start).total_seconds()
            # Speed ratio: audio duration / processing time
            if transcription_duration > 0:
                average_speed = round(total_audio_duration / transcription_duration, 2)
        
        # ✅ สร้าง speakers stats list
        speakers_stats = []
        for speaker_data in speakers_data.values():
            speakers_stats.append({
                'speaker_name': speaker_data['speaker_name'],
                'audio_count': speaker_data['audio_count'],
                'audio_duration': round(speaker_data['audio_duration'], 2),
                'text_length': speaker_data['text_length'],
                'word_count': speaker_data['word_count']
            })
        
        # Sort by audio count descending
        speakers_stats.sort(key=lambda x: x['audio_count'], reverse=True)
        
        # ✅ Build JSON data with new structure
        json_data = {
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
                'total_audio_files': len(transcriptions),
                'total_audio_duration_seconds': round(total_audio_duration, 2),
                'total_text_length': total_text_length,
                'total_word_count': total_word_count,
                'average_transcription_speed': average_speed,  # audio_duration / process_time
                'speakers_count': len(speakers_data),
                'parallel_workers': parallel_workers
            },
            'speakers_stats': speakers_stats,
            'transcriptions': transcription_list
        }
        
        # Save JSON file in meeting-specific folder
        storage_settings = get_storage_settings()
        transcription_root = storage_settings.get('transcription_path', 'storage/transcriptions')
        
        # Create meeting-specific folder
        meeting_text_folder = os.path.join(transcription_root, f'meeting_{meeting_id}')
        os.makedirs(meeting_text_folder, exist_ok=True)
        
        json_filename = f"meeting_{meeting_id}_transcription.json"
        json_filepath = os.path.join(meeting_text_folder, json_filename)
        
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        print(f"[Transcription] ✅ Created JSON: {json_filename}")
        print(f"[Transcription] 📊 Stats: {len(transcriptions)} files, {total_word_count} words, {round(total_audio_duration, 2)}s audio")
        if average_speed:
            print(f"[Transcription] ⚡ Speed: {average_speed}x realtime ({parallel_workers} workers)")
        
    except Exception as e:
        print(f"[Transcription] ❌ Error creating JSON: {e}")
        import traceback
        traceback.print_exc()


def get_meeting_transcriptions(meeting_id):
    """
    Get all transcriptions for a meeting
    
    Args:
        meeting_id: Meeting ID
    
    Returns:
        list: List of transcriptions
    """
    transcriptions = execute_query(
        """SELECT 
           t.*,
           COALESCE(t.name, 'Unknown') as speaker_name
           FROM text_file t
           LEFT JOIN voice_file v ON t.voice_id = v.voice_id
           WHERE t.meeting_id = ?
           ORDER BY v.start_time, t.voice_id""",
        (meeting_id,),
        fetch_all=True
    )
    
    return transcriptions if transcriptions else []


def delete_meeting_transcription(meeting_id):
    """
    Delete all transcriptions and files for a meeting
    
    Args:
        meeting_id: Meeting ID
    
    Returns:
        bool: True if successful
    """
    try:
        # Get storage path
        storage_settings = get_storage_settings()
        transcription_root = storage_settings.get('transcription_path', 'storage/transcriptions')
        
        # Delete entire meeting folder
        meeting_text_folder = os.path.join(transcription_root, f'meeting_{meeting_id}')
        if os.path.exists(meeting_text_folder):
            import shutil
            shutil.rmtree(meeting_text_folder)
            print(f"[Transcription] Deleted meeting folder: {meeting_text_folder}")
        
        # Delete from database
        execute_query(
            "DELETE FROM text_file WHERE meeting_id = ?",
            (meeting_id,),
            commit=True
        )
        
        # Delete transcription jobs
        execute_query(
            "DELETE FROM transcription_jobs WHERE meeting_id = ?",
            (meeting_id,),
            commit=True
        )
        
        # Update meeting status back to 'completed'
        execute_query(
            "UPDATE meetings SET status = 'completed' WHERE meeting_id = ?",
            (meeting_id,),
            commit=True
        )
        
        print(f"[Transcription] Deleted all transcriptions for meeting {meeting_id}")
        return True
        
    except Exception as e:
        print(f"[Transcription] Error deleting transcriptions: {e}")
        return False


def search_in_transcription(meeting_id, query=None, speaker=None, time_from=None, time_to=None):
    """
    Search in meeting transcriptions with filters
    
    Args:
        meeting_id: Meeting ID
        query: Search keyword (optional)
        speaker: Filter by speaker name (optional)
        time_from: Filter start time (optional, format: HH:MM:SS)
        time_to: Filter end time (optional, format: HH:MM:SS)
    
    Returns:
        dict: {'success': bool, 'results': list, 'total': int}
    """
    try:
        # Build base query
        sql = """
            SELECT 
                tf.voice_id,
                tf.content as text,
                vf.name as file_name,
                vf.start_time,
                vf.end_time,
                vf.duration
            FROM text_file tf
            JOIN voice_file vf ON tf.voice_id = vf.voice_id
            WHERE tf.meeting_id = ?
        """
        params = [meeting_id]
        
        # Add filters
        if speaker:
            sql += " AND vf.name LIKE ?"
            params.append(f"%{speaker}%")
        
        if time_from:
            sql += " AND vf.start_time >= ?"
            params.append(time_from)
        
        if time_to:
            sql += " AND vf.end_time <= ?"
            params.append(time_to)
        
        sql += " ORDER BY vf.start_time ASC"
        
        # Execute query
        rows = execute_query(sql, tuple(params), fetch_all=True)
        
        results = []
        for row in rows:
            text = row['text'] or ''
            speaker_name = row['file_name'].split('_')[0] if '_' in row['file_name'] else 'ไม่ระบุ'
            
            # Filter by keyword if provided
            if query and query.lower() not in text.lower():
                continue
            
            # Highlight keyword in text
            highlighted_text = text
            if query:
                # Simple highlight with <mark> tag
                pattern = re.compile(re.escape(query), re.IGNORECASE)
                highlighted_text = pattern.sub(lambda m: f'<mark>{m.group()}</mark>', text)
            
            results.append({
                'voice_id': row['voice_id'],
                'speaker_name': speaker_name,
                'text': highlighted_text,
                'original_text': text,
                'start_time': row['start_time'] or '00:00:00',
                'end_time': row['end_time'] or '00:00:00',
                'duration': row['duration'] or 0
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
        print(f"[Transcription] ❌ Error searching: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'results': [],
            'total': 0,
            'message': str(e)
        }


def update_transcription(voice_id, speaker_name=None, text=None, start_time=None, end_time=None):
    """
    Update transcription text and metadata
    
    Args:
        voice_id: Voice file ID
        speaker_name: New speaker name (optional)
        text: New transcription text (optional)
        start_time: New start time (optional)
        end_time: New end time (optional)
    
    Returns:
        dict: {'success': bool, 'message': str}
    """
    try:
        # Get current data
        voice_file = execute_query(
            "SELECT meeting_id, name FROM voice_file WHERE voice_id = ?",
            (voice_id,),
            fetch_one=True
        )
        
        if not voice_file:
            return {'success': False, 'message': 'Voice file not found'}
        
        meeting_id = voice_file['meeting_id']
        
        # Update text_file if text provided
        if text is not None:
            execute_query(
                "UPDATE text_file SET content = ? WHERE voice_id = ?",
                (text, voice_id),
                commit=True
            )
        
        # Update voice_file metadata
        updates = []
        params = []
        
        if start_time is not None:
            updates.append("start_time = ?")
            params.append(start_time)
        
        if end_time is not None:
            updates.append("end_time = ?")
            params.append(end_time)
        
        if speaker_name is not None:
            # Update filename to reflect new speaker
            old_basename = voice_file['name']
            parts = old_basename.split('_', 1)
            new_name = f"{speaker_name}_{parts[1]}" if len(parts) > 1 else f"{speaker_name}_{old_basename}"
            updates.append("name = ?")
            params.append(new_name)
        
        if updates:
            sql = f"UPDATE voice_file SET {', '.join(updates)} WHERE voice_id = ?"
            params.append(voice_id)
            execute_query(sql, tuple(params), commit=True)
        
        # Recreate JSON file with updated data
        meeting = execute_query(
            "SELECT model_used, language FROM transcription_jobs WHERE meeting_id = ? ORDER BY job_id DESC LIMIT 1",
            (meeting_id,),
            fetch_one=True
        )
        
        if meeting:
            _create_meeting_json(meeting_id, meeting['model_used'] if meeting['model_used'] else 'unknown', meeting['language'] if meeting['language'] else 'th')
        
        print(f"[Transcription] ✅ Updated transcription {voice_id}")
        
        return {
            'success': True,
            'message': 'Transcription updated successfully'
        }
        
    except Exception as e:
        print(f"[Transcription] ❌ Error updating transcription: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'message': f'Error updating: {str(e)}'
        }


def export_meeting_to_txt(meeting_id):
    """Export meeting transcription to plain text"""
    try:
        from datetime import datetime
        
        meeting = execute_query(
            "SELECT meeting_name, meeting_date FROM meetings WHERE meeting_id = ?",
            (meeting_id,), fetch_one=True
        )
        
        if not meeting:
            return {'success': False, 'message': 'Meeting not found'}
        
        transcriptions = execute_query(
            """SELECT tf.content, vf.name, vf.start_time, vf.end_time
               FROM text_file tf JOIN voice_file vf ON tf.voice_id = vf.voice_id
               WHERE tf.meeting_id = ? ORDER BY vf.start_time ASC""",
            (meeting_id,), fetch_all=True
        )
        
        if not transcriptions:
            return {'success': False, 'message': 'No transcriptions'}
        
        # Get participants - simplified
        part_names = '-'
        
        lines = [
            f"การประชุม: {meeting['meeting_name']}",
            f"วันที่: {meeting['meeting_date']}",
            f"ผู้เข้าร่วม: {part_names}",
            "", "━" * 50, ""
        ]
        
        for t in transcriptions:
            speaker = t['name'].split('_')[0] if '_' in t['name'] else 'ไม่ระบุ'
            time_range = f"{t['start_time']} - {t['end_time']}" if t['start_time'] else ''
            lines.extend([f"[{speaker}] {time_range}", t['content'] or '', ""])
        
        storage_settings = get_storage_settings()
        export_path = storage_settings.get('export_path', 'storage/exports')
        os.makedirs(export_path, exist_ok=True)
        
        filename = f"meeting_{meeting_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(export_path, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return {'success': True, 'filepath': filepath, 'filename': filename}
        
    except Exception as e:
        print(f"[Export] ❌ TXT error: {e}")
        return {'success': False, 'message': str(e)}


def export_meeting_to_srt(meeting_id):
    """Export to SRT subtitle"""
    try:
        from datetime import datetime
        
        transcriptions = execute_query(
            """SELECT tf.content, vf.name, vf.start_time, vf.end_time
               FROM text_file tf JOIN voice_file vf ON tf.voice_id = vf.voice_id
               WHERE tf.meeting_id = ? ORDER BY vf.start_time ASC""",
            (meeting_id,), fetch_all=True
        )
        
        if not transcriptions:
            return {'success': False, 'message': 'No transcriptions'}
        
        lines = []
        for idx, t in enumerate(transcriptions, 1):
            speaker = t['name'].split('_')[0] if '_' in t['name'] else 'ไม่ระบุ'
            start = (t['start_time'] + ',000') if t['start_time'] else '00:00:00,000'
            end = (t['end_time'] + ',000') if t['end_time'] else '00:00:00,000'
            lines.extend([str(idx), f"{start} --> {end}", f"[{speaker}] {t['content'] or ''}", ""])
        
        storage_settings = get_storage_settings()
        export_path = storage_settings.get('export_path', 'storage/exports')
        os.makedirs(export_path, exist_ok=True)
        
        filename = f"meeting_{meeting_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.srt"
        filepath = os.path.join(export_path, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return {'success': True, 'filepath': filepath, 'filename': filename}
        
    except Exception as e:
        print(f"[Export] ❌ SRT error: {e}")
        return {'success': False, 'message': str(e)}


def export_meeting_to_docx(meeting_id):
    """Export to Word document"""
    try:
        from datetime import datetime
        from docx import Document
        from docx.shared import Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        
        meeting = execute_query(
            "SELECT meeting_name, meeting_date FROM meetings WHERE meeting_id = ?",
            (meeting_id,), fetch_one=True
        )
        
        if not meeting:
            return {'success': False, 'message': 'Meeting not found'}
        
        transcriptions = execute_query(
            """SELECT tf.content, vf.name, vf.start_time, vf.end_time
               FROM text_file tf JOIN voice_file vf ON tf.voice_id = vf.voice_id
               WHERE tf.meeting_id = ? ORDER BY vf.start_time ASC""",
            (meeting_id,), fetch_all=True
        )
        
        if not transcriptions:
            return {'success': False, 'message': 'No transcriptions'}
        
        # Get participants - simplified 
        part_names = '-'
        
        doc = Document()
        
        # Title
        title = doc.add_paragraph(meeting['meeting_name'])
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title.runs[0].font.size = Pt(18)
        title.runs[0].font.bold = True
        
        # Date
        date_para = doc.add_paragraph(meeting['meeting_date'])
        date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        doc.add_paragraph('━' * 50)
        
        # Participants
        part_para = doc.add_paragraph()
        part_para.add_run('ผู้เข้าร่วม: ').bold = True
        part_para.add_run(part_names)
        
        doc.add_paragraph('━' * 50)
        doc.add_paragraph()
        
        # Transcriptions
        for t in transcriptions:
            speaker = t['name'].split('_')[0] if '_' in t['name'] else 'ไม่ระบุ'
            time_range = f"{t['start_time']} - {t['end_time']}" if t['start_time'] else ''
            
            speaker_para = doc.add_paragraph()
            speaker_run = speaker_para.add_run(f"[{speaker}] ")
            speaker_run.font.bold = True
            speaker_run.font.color.rgb = RGBColor(0, 0, 255)
            speaker_para.add_run(time_range)
            
            doc.add_paragraph(t['content'] or '')
            doc.add_paragraph()
        
        storage_settings = get_storage_settings()
        export_path = storage_settings.get('export_path', 'storage/exports')
        os.makedirs(export_path, exist_ok=True)
        
        filename = f"meeting_{meeting_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        filepath = os.path.join(export_path, filename)
        
        doc.save(filepath)
        
        return {'success': True, 'filepath': filepath, 'filename': filename}
        
    except Exception as e:
        print(f"[Export] ❌ DOCX error: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'message': str(e)}
