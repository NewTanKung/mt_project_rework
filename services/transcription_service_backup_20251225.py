"""
Transcription Service
Handles transcription jobs using Faster Whisper
"""
import os
import json
import threading
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
                'display_name': f"{name} ({info['size']}) - ‡∏à‡∏∞‡∏î‡∏≤‡∏ß‡∏ô‡πå‡πÇ‡∏´‡∏•‡∏î‡πÄ‡∏°‡∏∑‡πà‡∏≠‡πÉ‡∏ä‡πâ‡∏á‡∏≤‡∏ô"
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
        try:
            # Update status to processing
            execute_query(
                "UPDATE transcription_jobs SET status = 'processing' WHERE job_id = ?",
                (job_id,),
                commit=True
            )
            
            # ‚úÖ Load model from cache (‡∏•‡∏î load time!)
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
            
            # ‚úÖ Parallel processing (‡πÄ‡∏£‡πá‡∏ß‡∏Ç‡∏∂‡πâ‡∏ô 50-70%!)
            max_workers = min(4, total_files)  # ‡πÉ‡∏ä‡πâ‡∏™‡∏π‡∏á‡∏™‡∏∏‡∏î 4 threads
            processed = 0
            
            def transcribe_file(voice_file):
                """Transcribe single file"""
                # ‚úÖ Run inside app context for database access
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
                        
                        # Save text file
                        storage_settings = get_storage_settings()
                        text_root = storage_settings.get('text_path', 'storage/text')
                        os.makedirs(text_root, exist_ok=True)
                        
                        base_name = os.path.splitext(os.path.basename(file_path))[0]
                        text_filename = f"{base_name}_transcription.txt"
                        text_filepath = os.path.join(text_root, text_filename)
                        
                        with open(text_filepath, 'w', encoding='utf-8') as f:
                            f.write(f"‡πÑ‡∏ü‡∏•‡πå‡πÄ‡∏™‡∏µ‡∏¢‡∏á: {os.path.basename(file_path)}\n")
                            f.write(f"‡πÇ‡∏°‡πÄ‡∏î‡∏•: {model_used}\n")
                            f.write(f"‡∏†‡∏≤‡∏©‡∏≤: {language}\n")
                            f.write(f"‡∏ß‡∏±‡∏ô‡∏ó‡∏µ‡πà: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
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
                    
                    if result['success']:
                        print(f"[Transcription] ‚úÖ {processed}/{total_files}: {result['file']}")
                    else:
                        print(f"[Transcription] ‚ùå {processed}/{total_files}: {result.get('error')}")
            
            # Create consolidated JSON
            _create_meeting_json(meeting_id, model_used, language)
            
            # Update job status to completed
            execute_query(
                "UPDATE transcription_jobs SET status = 'completed', completed_at = ? WHERE job_id = ?",
                (datetime.now(), job_id),
                commit=True
            )
            
            print(f"[Transcription] ‚úÖ Job {job_id} completed successfully!")
            
        except Exception as e:
            print(f"[Transcription] ‚ùå Job {job_id} failed: {e}")
            execute_query(
                "UPDATE transcription_jobs SET status = 'failed', error_message = ? WHERE job_id = ?",
                (str(e), job_id),
                commit=True
            )
            
            # Create consolidated JSON file for the meeting
            _create_meeting_json(meeting_id, model_used, language)
            
            # Mark job as completed
            execute_query(
                "UPDATE transcription_jobs SET status = 'completed', progress = 100 WHERE job_id = ?",
                (job_id,),
                commit=True
            )
            
            # Update meeting status to 'transcribed'
            execute_query(
                "UPDATE meetings SET status = 'transcribed' WHERE meeting_id = ?",
                (meeting_id,),
                commit=True
            )
            
            print(f"[Transcription] Job {job_id} completed. Processed {processed}/{total_files} files.")
            
        except Exception as e:
            print(f"[Transcription] Job {job_id} failed: {e}")
            
            # Mark job as failed
            execute_query(
                "UPDATE transcription_jobs SET status = 'failed', error_message = ? WHERE job_id = ?",
                (str(e), job_id),
                commit=True
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
            'message': '‡πÑ‡∏°‡πà‡∏û‡∏ö‡πÑ‡∏ü‡∏•‡πå‡πÄ‡∏™‡∏µ‡∏¢‡∏á‡∏™‡∏≥‡∏´‡∏£‡∏±‡∏ö‡∏Å‡∏≤‡∏£‡∏õ‡∏£‡∏∞‡∏ä‡∏∏‡∏°‡∏ô‡∏µ‡πâ'
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
            'message': '‡∏°‡∏µ‡∏á‡∏≤‡∏ô transcription ‡∏ó‡∏µ‡πà‡∏Å‡∏≥‡∏•‡∏±‡∏á‡∏î‡∏≥‡πÄ‡∏ô‡∏¥‡∏ô‡∏Å‡∏≤‡∏£‡∏≠‡∏¢‡∏π‡πà‡πÅ‡∏•‡πâ‡∏ß',
            'job_id': active_job['job_id']
        }
    
    # Validate model name
    if model_used not in ['tiny', 'base', 'small', 'medium', 'large']:
        return {
            'success': False,
            'message': f'‡πÇ‡∏°‡πÄ‡∏î‡∏•‡πÑ‡∏°‡πà‡∏ñ‡∏π‡∏Å‡∏ï‡πâ‡∏≠‡∏á: {model_used}'
        }
    
    # Check if model is downloaded
    from services.model_service import check_model_downloaded
    if not check_model_downloaded(model_used):
        return {
            'success': False,
            'message': f'‡πÇ‡∏°‡πÄ‡∏î‡∏• {model_used} ‡∏¢‡∏±‡∏á‡πÑ‡∏°‡πà‡πÑ‡∏î‡πâ‡∏î‡∏≤‡∏ß‡∏ô‡πå‡πÇ‡∏´‡∏•‡∏î ‡∏Å‡∏£‡∏∏‡∏ì‡∏≤‡∏î‡∏≤‡∏ß‡∏ô‡πå‡πÇ‡∏´‡∏•‡∏î‡∏ú‡πà‡∏≤‡∏ô‡∏´‡∏ô‡πâ‡∏≤ Admin ‡∏Å‡πà‡∏≠‡∏ô'
        }
    
    # Create transcription job
    job_id = create_transcription_job(meeting_id, model_used, language)
    
    if not job_id:
        return {
            'success': False,
            'message': '‡πÑ‡∏°‡πà‡∏™‡∏≤‡∏°‡∏≤‡∏£‡∏ñ‡∏™‡∏£‡πâ‡∏≤‡∏á‡∏á‡∏≤‡∏ô‡∏ñ‡∏≠‡∏î‡πÄ‡∏™‡∏µ‡∏¢‡∏á‡πÑ‡∏î‡πâ'
        }
    
    # Start transcription in background
    if start_transcription_job(job_id):
        return {
            'success': True,
            'job_id': job_id,
            'message': '‡πÄ‡∏£‡∏¥‡πà‡∏°‡∏ñ‡∏≠‡∏î‡πÄ‡∏™‡∏µ‡∏¢‡∏á‡πÅ‡∏•‡πâ‡∏ß'
        }
    else:
        return {
            'success': False,
            'message': '‡πÑ‡∏°‡πà‡∏™‡∏≤‡∏°‡∏≤‡∏£‡∏ñ‡πÄ‡∏£‡∏¥‡πà‡∏°‡∏á‡∏≤‡∏ô‡∏ñ‡∏≠‡∏î‡πÄ‡∏™‡∏µ‡∏¢‡∏á‡πÑ‡∏î‡πâ'
        }


def _create_meeting_json(meeting_id, model_used, language):
    """
    Create consolidated JSON file for meeting transcriptions
    
    Args:
        meeting_id: Meeting ID
        model_used: Model used for transcription
        language: Language code
    """
    try:
        # Get all transcriptions with speaker info and timestamps
        transcriptions = execute_query(
            """SELECT 
                t.content,
                t.voice_id,
                COALESCE(t.name, 'Unknown') as speaker_name,
                v.start_time,
                v.end_time,
                v.file_path
               FROM text_file t
               LEFT JOIN voice_file v ON t.voice_id = v.voice_id
               WHERE t.meeting_id = ?
               ORDER BY v.start_time""",
            (meeting_id,),
            fetch_all=True
        )
        
        if not transcriptions:
            return
        
        # Get meeting info
        meeting = execute_query(
            "SELECT meeting_name, meeting_date FROM meetings WHERE meeting_id = ?",
            (meeting_id,),
            fetch_one=True
        )
        
        # Build JSON structure
        json_data = {
            "meeting_id": meeting_id,
            "meeting_name": meeting['meeting_name'] if meeting else f"Meeting {meeting_id}",
            "meeting_date": meeting['meeting_date'] if meeting else "",
            "model_used": model_used,
            "language": language,
            "transcription_date": datetime.now().isoformat(),
            "transcriptions": []
        }
        
        for trans in transcriptions:
            json_data["transcriptions"].append({
                "voice_id": trans['voice_id'],
                "speaker_name": trans['speaker_name'] or "Unknown",
                "start_time": trans['start_time'] or "",
                "end_time": trans['end_time'] or "",
                "text": trans['content'] or ""
            })
        
        # Save JSON file
        storage_settings = get_storage_settings()
        text_root = storage_settings.get('text_path', 'storage/text')
        os.makedirs(text_root, exist_ok=True)
        
        json_filename = f"meeting_{meeting_id}_transcription.json"
        json_filepath = os.path.join(text_root, json_filename)
        
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        print(f"[Transcription] Saved JSON file: {json_filepath}")
        
    except Exception as e:
        print(f"[Transcription] Error creating JSON: {e}")


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
        text_root = storage_settings.get('text_path', 'storage/text')
        
        # Delete JSON file
        json_filename = f"meeting_{meeting_id}_transcription.json"
        json_filepath = os.path.join(text_root, json_filename)
        if os.path.exists(json_filepath):
            os.remove(json_filepath)
            print(f"[Transcription] Deleted JSON file: {json_filepath}")
        
        # Get all text files for this meeting
        text_files = execute_query(
            "SELECT name FROM text_file WHERE meeting_id = ?",
            (meeting_id,),
            fetch_all=True
        )
        
        # Delete individual text files
        for text_file in text_files:
            txt_filepath = os.path.join(text_root, text_file['name'])
            if os.path.exists(txt_filepath):
                os.remove(txt_filepath)
                print(f"[Transcription] Deleted text file: {txt_filepath}")
        
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
 
  
 #   S e a r c h   i n   t r a n s c r i p t i o n  
 d e f   s e a r c h _ i n _ t r a n s c r i p t i o n ( m e e t i n g _ i d ,   q u e r y = N o n e ,   s p e a k e r = N o n e ,   t i m e _ f r o m = N o n e ,   t i m e _ t o = N o n e ) :  
         " " " S e a r c h   a n d   f i l t e r   t r a n s c r i p t i o n s " " "  
         t r y :  
                 i m p o r t   r e  
                  
                 #   B a s e   q u e r y  
                 s q l   =   " " "  
                         S E L E C T   t f . t e x t _ i d ,   t f . c o n t e n t ,   v f . v o i c e _ i d ,   v f . n a m e ,   v f . s t a r t _ t i m e ,   v f . e n d _ t i m e  
                         F R O M   t e x t _ f i l e   t f  
                         J O I N   v o i c e _ f i l e   v f   O N   t f . v o i c e _ i d   =   v f . v o i c e _ i d  
                         W H E R E   t f . m e e t i n g _ i d   =   ?  
                 " " "  
                 p a r a m s   =   [ m e e t i n g _ i d ]  
                  
                 #   A d d   f i l t e r s  
                 i f   s p e a k e r :  
                         s q l   + =   "   A N D   v f . n a m e   L I K E   ? "  
                         p a r a m s . a p p e n d ( f " % { s p e a k e r } % " )  
                  
                 i f   t i m e _ f r o m :  
                         s q l   + =   "   A N D   v f . s t a r t _ t i m e   > =   ? "  
                         p a r a m s . a p p e n d ( t i m e _ f r o m )  
                  
                 i f   t i m e _ t o :  
                         s q l   + =   "   A N D   v f . e n d _ t i m e   < =   ? "  
                         p a r a m s . a p p e n d ( t i m e _ t o )  
                  
                 s q l   + =   "   O R D E R   B Y   v f . s t a r t _ t i m e   A S C "  
                  
                 r e s u l t s   =   e x e c u t e _ q u e r y ( s q l ,   t u p l e ( p a r a m s ) ,   f e t c h _ a l l = T r u e )  
                  
                 #   F i l t e r   a n d   h i g h l i g h t   b y   q u e r y  
                 f i l t e r e d _ r e s u l t s   =   [ ]  
                 f o r   r e s u l t   i n   r e s u l t s :  
                         c o n t e n t   =   r e s u l t [ ' c o n t e n t ' ]   o r   ' '  
                          
                         i f   q u e r y :  
                                 i f   q u e r y . l o w e r ( )   i n   c o n t e n t . l o w e r ( ) :  
                                         #   H i g h l i g h t   m a t c h e s  
                                         h i g h l i g h t e d   =   r e . s u b (  
                                                 f ' ( { r e . e s c a p e ( q u e r y ) } ) ' ,  
                                                 r ' < m a r k > \ 1 < / m a r k > ' ,  
                                                 c o n t e n t ,  
                                                 f l a g s = r e . I G N O R E C A S E  
                                         )  
                                         r e s u l t _ d i c t   =   d i c t ( r e s u l t )  
                                         r e s u l t _ d i c t [ ' c o n t e n t ' ]   =   h i g h l i g h t e d  
                                         r e s u l t _ d i c t [ ' s p e a k e r _ n a m e ' ]   =   r e s u l t [ ' n a m e ' ] . s p l i t ( ' _ ' ) [ 0 ]   i f   ' _ '   i n   r e s u l t [ ' n a m e ' ]   e l s e   r e s u l t [ ' n a m e ' ]  
                                         f i l t e r e d _ r e s u l t s . a p p e n d ( r e s u l t _ d i c t )  
                         e l s e :  
                                 r e s u l t _ d i c t   =   d i c t ( r e s u l t )  
                                 r e s u l t _ d i c t [ ' s p e a k e r _ n a m e ' ]   =   r e s u l t [ ' n a m e ' ] . s p l i t ( ' _ ' ) [ 0 ]   i f   ' _ '   i n   r e s u l t [ ' n a m e ' ]   e l s e   r e s u l t [ ' n a m e ' ]  
                                 f i l t e r e d _ r e s u l t s . a p p e n d ( r e s u l t _ d i c t )  
                  
                 r e t u r n   {  
                         ' s u c c e s s ' :   T r u e ,  
                         ' r e s u l t s ' :   f i l t e r e d _ r e s u l t s ,  
                         ' c o u n t ' :   l e n ( f i l t e r e d _ r e s u l t s )  
                 }  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 p r i n t ( f " [ S e a r c h ]   ‚ ù R  E r r o r :   { e } " )  
                 i m p o r t   t r a c e b a c k  
                 t r a c e b a c k . p r i n t _ e x c ( )  
                 r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   s t r ( e ) }  
  
  
 #   U p d a t e   t r a n s c r i p t i o n  
 d e f   u p d a t e _ t r a n s c r i p t i o n ( v o i c e _ i d ,   s p e a k e r _ n a m e = N o n e ,   t e x t = N o n e ,   s t a r t _ t i m e = N o n e ,   e n d _ t i m e = N o n e ) :  
         " " " U p d a t e   t r a n s c r i p t i o n   t e x t   a n d   m e t a d a t a " " "  
         t r y :  
                 #   G e t   m e e t i n g _ i d  
                 v o i c e _ d a t a   =   e x e c u t e _ q u e r y (  
                         " S E L E C T   m e e t i n g _ i d ,   n a m e   F R O M   v o i c e _ f i l e   W H E R E   v o i c e _ i d   =   ? " ,  
                         ( v o i c e _ i d , ) ,  
                         f e t c h _ o n e = T r u e  
                 )  
                  
                 i f   n o t   v o i c e _ d a t a :  
                         r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   ' V o i c e   f i l e   n o t   f o u n d ' }  
                  
                 m e e t i n g _ i d   =   v o i c e _ d a t a [ ' m e e t i n g _ i d ' ]  
                 c u r r e n t _ n a m e   =   v o i c e _ d a t a [ ' n a m e ' ]  
                  
                 #   U p d a t e   t e x t _ f i l e  
                 i f   t e x t   i s   n o t   N o n e :  
                         e x e c u t e _ q u e r y (  
                                 " U P D A T E   t e x t _ f i l e   S E T   c o n t e n t   =   ?   W H E R E   v o i c e _ i d   =   ? " ,  
                                 ( t e x t ,   v o i c e _ i d ) ,  
                                 c o m m i t = T r u e  
                         )  
                  
                 #   U p d a t e   v o i c e _ f i l e   m e t a d a t a  
                 u p d a t e s   =   [ ]  
                 p a r a m s   =   [ ]  
                  
                 i f   s t a r t _ t i m e   i s   n o t   N o n e :  
                         u p d a t e s . a p p e n d ( " s t a r t _ t i m e   =   ? " )  
                         p a r a m s . a p p e n d ( s t a r t _ t i m e )  
                  
                 i f   e n d _ t i m e   i s   n o t   N o n e :  
                         u p d a t e s . a p p e n d ( " e n d _ t i m e   =   ? " )  
                         p a r a m s . a p p e n d ( e n d _ t i m e )  
                  
                 i f   s p e a k e r _ n a m e   i s   n o t   N o n e :  
                         #   U p d a t e   f i l e n a m e  
                         p a r t s   =   c u r r e n t _ n a m e . s p l i t ( ' _ ' )  
                         i f   l e n ( p a r t s )   >   1 :  
                                 n e w _ n a m e   =   f " { s p e a k e r _ n a m e } _ { ' _ ' . j o i n ( p a r t s [ 1 : ] ) } "  
                         e l s e :  
                                 n e w _ n a m e   =   f " { s p e a k e r _ n a m e } _ { c u r r e n t _ n a m e } "  
                          
                         u p d a t e s . a p p e n d ( " n a m e   =   ? " )  
                         p a r a m s . a p p e n d ( n e w _ n a m e )  
                  
                 i f   u p d a t e s :  
                         s q l   =   f " U P D A T E   v o i c e _ f i l e   S E T   { ' ,   ' . j o i n ( u p d a t e s ) }   W H E R E   v o i c e _ i d   =   ? "  
                         p a r a m s . a p p e n d ( v o i c e _ i d )  
                         e x e c u t e _ q u e r y ( s q l ,   t u p l e ( p a r a m s ) ,   c o m m i t = T r u e )  
                  
                 #   R e c r e a t e   J S O N  
                 j o b _ d a t a   =   e x e c u t e _ q u e r y (  
                         " S E L E C T   m o d e l _ u s e d ,   l a n g u a g e   F R O M   t r a n s c r i p t i o n _ j o b s   W H E R E   m e e t i n g _ i d   =   ?   L I M I T   1 " ,  
                         ( m e e t i n g _ i d , ) ,  
                         f e t c h _ o n e = T r u e  
                 )  
                  
                 i f   j o b _ d a t a :  
                         _ c r e a t e _ m e e t i n g _ j s o n ( m e e t i n g _ i d ,   j o b _ d a t a . g e t ( ' m o d e l _ u s e d ' ,   ' u n k n o w n ' ) ,   j o b _ d a t a . g e t ( ' l a n g u a g e ' ,   ' t h ' ) )  
                  
                 p r i n t ( f " [ T r a n s c r i p t i o n ]   ‚ S&   U p d a t e d   t r a n s c r i p t i o n   { v o i c e _ i d } " )  
                 r e t u r n   { ' s u c c e s s ' :   T r u e ,   ' m e s s a g e ' :   ' U p d a t e d   s u c c e s s f u l l y ' }  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 p r i n t ( f " [ T r a n s c r i p t i o n ]   ‚ ù R  E r r o r   u p d a t i n g :   { e } " )  
                 i m p o r t   t r a c e b a c k  
                 t r a c e b a c k . p r i n t _ e x c ( )  
                 r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   s t r ( e ) }  
  
  
 #   E x p o r t   f u n c t i o n s  
 d e f   e x p o r t _ m e e t i n g _ t o _ t x t ( m e e t i n g _ i d ) :  
         " " " E x p o r t   t o   p l a i n   t e x t " " "  
         t r y :  
                 f r o m   d a t e t i m e   i m p o r t   d a t e t i m e  
                  
                 m e e t i n g   =   e x e c u t e _ q u e r y (  
                         " S E L E C T   m e e t i n g _ n a m e ,   m e e t i n g _ d a t e   F R O M   m e e t i n g s   W H E R E   m e e t i n g _ i d   =   ? " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ o n e = T r u e  
                 )  
                  
                 i f   n o t   m e e t i n g :  
                         r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   ' M e e t i n g   n o t   f o u n d ' }  
                  
                 t r a n s c r i p t i o n s   =   e x e c u t e _ q u e r y (  
                         " " " S E L E C T   t f . c o n t e n t ,   v f . n a m e ,   v f . s t a r t _ t i m e ,   v f . e n d _ t i m e  
                               F R O M   t e x t _ f i l e   t f   J O I N   v o i c e _ f i l e   v f   O N   t f . v o i c e _ i d   =   v f . v o i c e _ i d  
                               W H E R E   t f . m e e t i n g _ i d   =   ?   O R D E R   B Y   v f . s t a r t _ t i m e   A S C " " " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ a l l = T r u e  
                 )  
                  
                 i f   n o t   t r a n s c r i p t i o n s :  
                         r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   ' N o   t r a n s c r i p t i o n s ' }  
                  
                 p a r t i c i p a n t s   =   e x e c u t e _ q u e r y (  
                         " S E L E C T   D I S T I N C T   p a r t i c i p a n t _ n a m e   F R O M   m e e t i n g _ p a r t i c i p a n t s   W H E R E   m e e t i n g _ i d   =   ? " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ a l l = T r u e  
                 )  
                 p a r t _ n a m e s   =   ' ,   ' . j o i n ( [ p [ ' p a r t i c i p a n t _ n a m e ' ]   f o r   p   i n   p a r t i c i p a n t s ] )   i f   p a r t i c i p a n t s   e l s e   ' - '  
                  
                 l i n e s   =   [  
                         f " ‡ ∏ Å ‡ ∏ ≤ ‡ ∏ £ ‡ ∏ : ‡ ∏ £ ‡ ∏ ∞ ‡ ∏ `‡ ∏ ∏ ‡ ∏ ° :   { m e e t i n g [ ' m e e t i n g _ n a m e ' ] } " ,  
                         f " ‡ ∏ ß ‡ ∏ ± ‡ ∏ "!‡ ∏  ‡ ∏ µ ‡ π ∆:   { m e e t i n g [ ' m e e t i n g _ d a t e ' ] } " ,  
                         f " ‡ ∏ S‡ ∏ π ‡ π 0 ‡ π ¨ ‡ ∏  ‡ π 0 ‡ ∏ ≤ ‡ ∏ £ ‡ π ∆‡ ∏ ß ‡ ∏ ° :   { p a r t _ n a m e s } " ,  
                         " " ,   " ‚  Å "   *   5 0 ,   " "  
                 ]  
                  
                 f o r   t   i n   t r a n s c r i p t i o n s :  
                         s p e a k e r   =   t [ ' n a m e ' ] . s p l i t ( ' _ ' ) [ 0 ]   i f   ' _ '   i n   t [ ' n a m e ' ]   e l s e   ' ‡ π  ‡ ∏ ° ‡ π ∆‡ ∏ £ ‡ ∏ ∞ ‡ ∏ a‡ ∏ ∏ '  
                         t i m e _ r a n g e   =   f " { t [ ' s t a r t _ t i m e ' ] }   -   { t [ ' e n d _ t i m e ' ] } "   i f   t [ ' s t a r t _ t i m e ' ]   e l s e   ' '  
                         l i n e s . e x t e n d ( [ f " [ { s p e a k e r } ]   { t i m e _ r a n g e } " ,   t [ ' c o n t e n t ' ]   o r   ' ' ,   " " ] )  
                  
                 s t o r a g e _ s e t t i n g s   =   g e t _ s t o r a g e _ s e t t i n g s ( )  
                 e x p o r t _ p a t h   =   s t o r a g e _ s e t t i n g s . g e t ( ' e x p o r t _ p a t h ' ,   ' s t o r a g e / e x p o r t s ' )  
                 o s . m a k e d i r s ( e x p o r t _ p a t h ,   e x i s t _ o k = T r u e )  
                  
                 f i l e n a m e   =   f " m e e t i n g _ { m e e t i n g _ i d } _ { d a t e t i m e . n o w ( ) . s t r f t i m e ( ' % Y % m % d _ % H % M % S ' ) } . t x t "  
                 f i l e p a t h   =   o s . p a t h . j o i n ( e x p o r t _ p a t h ,   f i l e n a m e )  
                  
                 w i t h   o p e n ( f i l e p a t h ,   ' w ' ,   e n c o d i n g = ' u t f - 8 ' )   a s   f :  
                         f . w r i t e ( ' \ n ' . j o i n ( l i n e s ) )  
                  
                 r e t u r n   { ' s u c c e s s ' :   T r u e ,   ' f i l e p a t h ' :   f i l e p a t h ,   ' f i l e n a m e ' :   f i l e n a m e }  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 p r i n t ( f " [ E x p o r t ]   ‚ ù R  T X T   e r r o r :   { e } " )  
                 r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   s t r ( e ) }  
  
  
 d e f   e x p o r t _ m e e t i n g _ t o _ s r t ( m e e t i n g _ i d ) :  
         " " " E x p o r t   t o   S R T   s u b t i t l e " " "  
         t r y :  
                 f r o m   d a t e t i m e   i m p o r t   d a t e t i m e  
                  
                 t r a n s c r i p t i o n s   =   e x e c u t e _ q u e r y (  
                         " " " S E L E C T   t f . c o n t e n t ,   v f . n a m e ,   v f . s t a r t _ t i m e ,   v f . e n d _ t i m e  
                               F R O M   t e x t _ f i l e   t f   J O I N   v o i c e _ f i l e   v f   O N   t f . v o i c e _ i d   =   v f . v o i c e _ i d  
                               W H E R E   t f . m e e t i n g _ i d   =   ?   O R D E R   B Y   v f . s t a r t _ t i m e   A S C " " " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ a l l = T r u e  
                 )  
                  
                 i f   n o t   t r a n s c r i p t i o n s :  
                         r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   ' N o   t r a n s c r i p t i o n s ' }  
                  
                 l i n e s   =   [ ]  
                 f o r   i d x ,   t   i n   e n u m e r a t e ( t r a n s c r i p t i o n s ,   1 ) :  
                         s p e a k e r   =   t [ ' n a m e ' ] . s p l i t ( ' _ ' ) [ 0 ]   i f   ' _ '   i n   t [ ' n a m e ' ]   e l s e   ' ‡ π  ‡ ∏ ° ‡ π ∆‡ ∏ £ ‡ ∏ ∞ ‡ ∏ a‡ ∏ ∏ '  
                         s t a r t   =   ( t [ ' s t a r t _ t i m e ' ]   +   ' , 0 0 0 ' )   i f   t [ ' s t a r t _ t i m e ' ]   e l s e   ' 0 0 : 0 0 : 0 0 , 0 0 0 '  
                         e n d   =   ( t [ ' e n d _ t i m e ' ]   +   ' , 0 0 0 ' )   i f   t [ ' e n d _ t i m e ' ]   e l s e   ' 0 0 : 0 0 : 0 0 , 0 0 0 '  
                         l i n e s . e x t e n d ( [ s t r ( i d x ) ,   f " { s t a r t }   - - >   { e n d } " ,   f " [ { s p e a k e r } ]   { t [ ' c o n t e n t ' ]   o r   ' ' } " ,   " " ] )  
                  
                 s t o r a g e _ s e t t i n g s   =   g e t _ s t o r a g e _ s e t t i n g s ( )  
                 e x p o r t _ p a t h   =   s t o r a g e _ s e t t i n g s . g e t ( ' e x p o r t _ p a t h ' ,   ' s t o r a g e / e x p o r t s ' )  
                 o s . m a k e d i r s ( e x p o r t _ p a t h ,   e x i s t _ o k = T r u e )  
                  
                 f i l e n a m e   =   f " m e e t i n g _ { m e e t i n g _ i d } _ { d a t e t i m e . n o w ( ) . s t r f t i m e ( ' % Y % m % d _ % H % M % S ' ) } . s r t "  
                 f i l e p a t h   =   o s . p a t h . j o i n ( e x p o r t _ p a t h ,   f i l e n a m e )  
                  
                 w i t h   o p e n ( f i l e p a t h ,   ' w ' ,   e n c o d i n g = ' u t f - 8 ' )   a s   f :  
                         f . w r i t e ( ' \ n ' . j o i n ( l i n e s ) )  
                  
                 r e t u r n   { ' s u c c e s s ' :   T r u e ,   ' f i l e p a t h ' :   f i l e p a t h ,   ' f i l e n a m e ' :   f i l e n a m e }  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 p r i n t ( f " [ E x p o r t ]   ‚ ù R  S R T   e r r o r :   { e } " )  
                 r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   s t r ( e ) }  
  
  
 d e f   e x p o r t _ m e e t i n g _ t o _ d o c x ( m e e t i n g _ i d ) :  
         " " " E x p o r t   t o   W o r d   d o c u m e n t " " "  
         t r y :  
                 f r o m   d a t e t i m e   i m p o r t   d a t e t i m e  
                 f r o m   d o c x   i m p o r t   D o c u m e n t  
                 f r o m   d o c x . s h a r e d   i m p o r t   P t ,   R G B C o l o r  
                 f r o m   d o c x . e n u m . t e x t   i m p o r t   W D _ A L I G N _ P A R A G R A P H  
                  
                 m e e t i n g   =   e x e c u t e _ q u e r y (  
                         " S E L E C T   m e e t i n g _ n a m e ,   m e e t i n g _ d a t e   F R O M   m e e t i n g s   W H E R E   m e e t i n g _ i d   =   ? " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ o n e = T r u e  
                 )  
                  
                 i f   n o t   m e e t i n g :  
                         r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   ' M e e t i n g   n o t   f o u n d ' }  
                  
                 t r a n s c r i p t i o n s   =   e x e c u t e _ q u e r y (  
                         " " " S E L E C T   t f . c o n t e n t ,   v f . n a m e ,   v f . s t a r t _ t i m e ,   v f . e n d _ t i m e  
                               F R O M   t e x t _ f i l e   t f   J O I N   v o i c e _ f i l e   v f   O N   t f . v o i c e _ i d   =   v f . v o i c e _ i d  
                               W H E R E   t f . m e e t i n g _ i d   =   ?   O R D E R   B Y   v f . s t a r t _ t i m e   A S C " " " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ a l l = T r u e  
                 )  
                  
                 i f   n o t   t r a n s c r i p t i o n s :  
                         r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   ' N o   t r a n s c r i p t i o n s ' }  
                  
                 p a r t i c i p a n t s   =   e x e c u t e _ q u e r y (  
                         " S E L E C T   D I S T I N C T   p a r t i c i p a n t _ n a m e   F R O M   m e e t i n g _ p a r t i c i p a n t s   W H E R E   m e e t i n g _ i d   =   ? " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ a l l = T r u e  
                 )  
                 p a r t _ n a m e s   =   ' ,   ' . j o i n ( [ p [ ' p a r t i c i p a n t _ n a m e ' ]   f o r   p   i n   p a r t i c i p a n t s ] )   i f   p a r t i c i p a n t s   e l s e   ' - '  
                  
                 d o c   =   D o c u m e n t ( )  
                  
                 #   T i t l e  
                 t i t l e   =   d o c . a d d _ p a r a g r a p h ( m e e t i n g [ ' m e e t i n g _ n a m e ' ] )  
                 t i t l e . a l i g n m e n t   =   W D _ A L I G N _ P A R A G R A P H . C E N T E R  
                 t i t l e . r u n s [ 0 ] . f o n t . s i z e   =   P t ( 1 8 )  
                 t i t l e . r u n s [ 0 ] . f o n t . b o l d   =   T r u e  
                  
                 #   D a t e  
                 d a t e _ p a r a   =   d o c . a d d _ p a r a g r a p h ( m e e t i n g [ ' m e e t i n g _ d a t e ' ] )  
                 d a t e _ p a r a . a l i g n m e n t   =   W D _ A L I G N _ P A R A G R A P H . C E N T E R  
                  
                 d o c . a d d _ p a r a g r a p h ( ' ‚  Å '   *   5 0 )  
                  
                 #   P a r t i c i p a n t s  
                 p a r t _ p a r a   =   d o c . a d d _ p a r a g r a p h ( )  
                 p a r t _ p a r a . a d d _ r u n ( ' ‡ ∏ S‡ ∏ π ‡ π 0 ‡ π ¨ ‡ ∏  ‡ π 0 ‡ ∏ ≤ ‡ ∏ £ ‡ π ∆‡ ∏ ß ‡ ∏ ° :   ' ) . b o l d   =   T r u e  
                 p a r t _ p a r a . a d d _ r u n ( p a r t _ n a m e s )  
                  
                 d o c . a d d _ p a r a g r a p h ( ' ‚  Å '   *   5 0 )  
                 d o c . a d d _ p a r a g r a p h ( )  
                  
                 #   T r a n s c r i p t i o n s  
                 f o r   t   i n   t r a n s c r i p t i o n s :  
                         s p e a k e r   =   t [ ' n a m e ' ] . s p l i t ( ' _ ' ) [ 0 ]   i f   ' _ '   i n   t [ ' n a m e ' ]   e l s e   ' ‡ π  ‡ ∏ ° ‡ π ∆‡ ∏ £ ‡ ∏ ∞ ‡ ∏ a‡ ∏ ∏ '  
                         t i m e _ r a n g e   =   f " { t [ ' s t a r t _ t i m e ' ] }   -   { t [ ' e n d _ t i m e ' ] } "   i f   t [ ' s t a r t _ t i m e ' ]   e l s e   ' '  
                          
                         s p e a k e r _ p a r a   =   d o c . a d d _ p a r a g r a p h ( )  
                         s p e a k e r _ r u n   =   s p e a k e r _ p a r a . a d d _ r u n ( f " [ { s p e a k e r } ]   " )  
                         s p e a k e r _ r u n . f o n t . b o l d   =   T r u e  
                         s p e a k e r _ r u n . f o n t . c o l o r . r g b   =   R G B C o l o r ( 0 ,   0 ,   2 5 5 )  
                         s p e a k e r _ p a r a . a d d _ r u n ( t i m e _ r a n g e )  
                          
                         d o c . a d d _ p a r a g r a p h ( t [ ' c o n t e n t ' ]   o r   ' ' )  
                         d o c . a d d _ p a r a g r a p h ( )  
                  
                 s t o r a g e _ s e t t i n g s   =   g e t _ s t o r a g e _ s e t t i n g s ( )  
                 e x p o r t _ p a t h   =   s t o r a g e _ s e t t i n g s . g e t ( ' e x p o r t _ p a t h ' ,   ' s t o r a g e / e x p o r t s ' )  
                 o s . m a k e d i r s ( e x p o r t _ p a t h ,   e x i s t _ o k = T r u e )  
                  
                 f i l e n a m e   =   f " m e e t i n g _ { m e e t i n g _ i d } _ { d a t e t i m e . n o w ( ) . s t r f t i m e ( ' % Y % m % d _ % H % M % S ' ) } . d o c x "  
                 f i l e p a t h   =   o s . p a t h . j o i n ( e x p o r t _ p a t h ,   f i l e n a m e )  
                  
                 d o c . s a v e ( f i l e p a t h )  
                  
                 r e t u r n   { ' s u c c e s s ' :   T r u e ,   ' f i l e p a t h ' :   f i l e p a t h ,   ' f i l e n a m e ' :   f i l e n a m e }  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 p r i n t ( f " [ E x p o r t ]   ‚ ù R  D O C X   e r r o r :   { e } " )  
                 i m p o r t   t r a c e b a c k  
                 t r a c e b a c k . p r i n t _ e x c ( )  
                 r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   s t r ( e ) }  
  
  
 #   S e a r c h   i n   t r a n s c r i p t i o n  
 d e f   s e a r c h _ i n _ t r a n s c r i p t i o n ( m e e t i n g _ i d ,   q u e r y = N o n e ,   s p e a k e r = N o n e ,   t i m e _ f r o m = N o n e ,   t i m e _ t o = N o n e ) :  
         " " " S e a r c h   a n d   f i l t e r   t r a n s c r i p t i o n s " " "  
         t r y :  
                 i m p o r t   r e  
                  
                 #   B a s e   q u e r y  
                 s q l   =   " " "  
                         S E L E C T   t f . t e x t _ i d ,   t f . c o n t e n t ,   v f . v o i c e _ i d ,   v f . n a m e ,   v f . s t a r t _ t i m e ,   v f . e n d _ t i m e  
                         F R O M   t e x t _ f i l e   t f  
                         J O I N   v o i c e _ f i l e   v f   O N   t f . v o i c e _ i d   =   v f . v o i c e _ i d  
                         W H E R E   t f . m e e t i n g _ i d   =   ?  
                 " " "  
                 p a r a m s   =   [ m e e t i n g _ i d ]  
                  
                 #   A d d   f i l t e r s  
                 i f   s p e a k e r :  
                         s q l   + =   "   A N D   v f . n a m e   L I K E   ? "  
                         p a r a m s . a p p e n d ( f " % { s p e a k e r } % " )  
                  
                 i f   t i m e _ f r o m :  
                         s q l   + =   "   A N D   v f . s t a r t _ t i m e   > =   ? "  
                         p a r a m s . a p p e n d ( t i m e _ f r o m )  
                  
                 i f   t i m e _ t o :  
                         s q l   + =   "   A N D   v f . e n d _ t i m e   < =   ? "  
                         p a r a m s . a p p e n d ( t i m e _ t o )  
                  
                 s q l   + =   "   O R D E R   B Y   v f . s t a r t _ t i m e   A S C "  
                  
                 r e s u l t s   =   e x e c u t e _ q u e r y ( s q l ,   t u p l e ( p a r a m s ) ,   f e t c h _ a l l = T r u e )  
                  
                 #   F i l t e r   a n d   h i g h l i g h t   b y   q u e r y  
                 f i l t e r e d _ r e s u l t s   =   [ ]  
                 f o r   r e s u l t   i n   r e s u l t s :  
                         c o n t e n t   =   r e s u l t [ ' c o n t e n t ' ]   o r   ' '  
                          
                         i f   q u e r y :  
                                 i f   q u e r y . l o w e r ( )   i n   c o n t e n t . l o w e r ( ) :  
                                         #   H i g h l i g h t   m a t c h e s  
                                         h i g h l i g h t e d   =   r e . s u b (  
                                                 f ' ( { r e . e s c a p e ( q u e r y ) } ) ' ,  
                                                 r ' < m a r k > \ 1 < / m a r k > ' ,  
                                                 c o n t e n t ,  
                                                 f l a g s = r e . I G N O R E C A S E  
                                         )  
                                         r e s u l t _ d i c t   =   d i c t ( r e s u l t )  
                                         r e s u l t _ d i c t [ ' c o n t e n t ' ]   =   h i g h l i g h t e d  
                                         r e s u l t _ d i c t [ ' s p e a k e r _ n a m e ' ]   =   r e s u l t [ ' n a m e ' ] . s p l i t ( ' _ ' ) [ 0 ]   i f   ' _ '   i n   r e s u l t [ ' n a m e ' ]   e l s e   r e s u l t [ ' n a m e ' ]  
                                         f i l t e r e d _ r e s u l t s . a p p e n d ( r e s u l t _ d i c t )  
                         e l s e :  
                                 r e s u l t _ d i c t   =   d i c t ( r e s u l t )  
                                 r e s u l t _ d i c t [ ' s p e a k e r _ n a m e ' ]   =   r e s u l t [ ' n a m e ' ] . s p l i t ( ' _ ' ) [ 0 ]   i f   ' _ '   i n   r e s u l t [ ' n a m e ' ]   e l s e   r e s u l t [ ' n a m e ' ]  
                                 f i l t e r e d _ r e s u l t s . a p p e n d ( r e s u l t _ d i c t )  
                  
                 r e t u r n   {  
                         ' s u c c e s s ' :   T r u e ,  
                         ' r e s u l t s ' :   f i l t e r e d _ r e s u l t s ,  
                         ' c o u n t ' :   l e n ( f i l t e r e d _ r e s u l t s )  
                 }  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 p r i n t ( f " [ S e a r c h ]   ‚ ù R  E r r o r :   { e } " )  
                 i m p o r t   t r a c e b a c k  
                 t r a c e b a c k . p r i n t _ e x c ( )  
                 r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   s t r ( e ) }  
  
  
 #   U p d a t e   t r a n s c r i p t i o n  
 d e f   u p d a t e _ t r a n s c r i p t i o n ( v o i c e _ i d ,   s p e a k e r _ n a m e = N o n e ,   t e x t = N o n e ,   s t a r t _ t i m e = N o n e ,   e n d _ t i m e = N o n e ) :  
         " " " U p d a t e   t r a n s c r i p t i o n   t e x t   a n d   m e t a d a t a " " "  
         t r y :  
                 #   G e t   m e e t i n g _ i d  
                 v o i c e _ d a t a   =   e x e c u t e _ q u e r y (  
                         " S E L E C T   m e e t i n g _ i d ,   n a m e   F R O M   v o i c e _ f i l e   W H E R E   v o i c e _ i d   =   ? " ,  
                         ( v o i c e _ i d , ) ,  
                         f e t c h _ o n e = T r u e  
                 )  
                  
                 i f   n o t   v o i c e _ d a t a :  
                         r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   ' V o i c e   f i l e   n o t   f o u n d ' }  
                  
                 m e e t i n g _ i d   =   v o i c e _ d a t a [ ' m e e t i n g _ i d ' ]  
                 c u r r e n t _ n a m e   =   v o i c e _ d a t a [ ' n a m e ' ]  
                  
                 #   U p d a t e   t e x t _ f i l e  
                 i f   t e x t   i s   n o t   N o n e :  
                         e x e c u t e _ q u e r y (  
                                 " U P D A T E   t e x t _ f i l e   S E T   c o n t e n t   =   ?   W H E R E   v o i c e _ i d   =   ? " ,  
                                 ( t e x t ,   v o i c e _ i d ) ,  
                                 c o m m i t = T r u e  
                         )  
                  
                 #   U p d a t e   v o i c e _ f i l e   m e t a d a t a  
                 u p d a t e s   =   [ ]  
                 p a r a m s   =   [ ]  
                  
                 i f   s t a r t _ t i m e   i s   n o t   N o n e :  
                         u p d a t e s . a p p e n d ( " s t a r t _ t i m e   =   ? " )  
                         p a r a m s . a p p e n d ( s t a r t _ t i m e )  
                  
                 i f   e n d _ t i m e   i s   n o t   N o n e :  
                         u p d a t e s . a p p e n d ( " e n d _ t i m e   =   ? " )  
                         p a r a m s . a p p e n d ( e n d _ t i m e )  
                  
                 i f   s p e a k e r _ n a m e   i s   n o t   N o n e :  
                         #   U p d a t e   f i l e n a m e  
                         p a r t s   =   c u r r e n t _ n a m e . s p l i t ( ' _ ' )  
                         i f   l e n ( p a r t s )   >   1 :  
                                 n e w _ n a m e   =   f " { s p e a k e r _ n a m e } _ { ' _ ' . j o i n ( p a r t s [ 1 : ] ) } "  
                         e l s e :  
                                 n e w _ n a m e   =   f " { s p e a k e r _ n a m e } _ { c u r r e n t _ n a m e } "  
                          
                         u p d a t e s . a p p e n d ( " n a m e   =   ? " )  
                         p a r a m s . a p p e n d ( n e w _ n a m e )  
                  
                 i f   u p d a t e s :  
                         s q l   =   f " U P D A T E   v o i c e _ f i l e   S E T   { ' ,   ' . j o i n ( u p d a t e s ) }   W H E R E   v o i c e _ i d   =   ? "  
                         p a r a m s . a p p e n d ( v o i c e _ i d )  
                         e x e c u t e _ q u e r y ( s q l ,   t u p l e ( p a r a m s ) ,   c o m m i t = T r u e )  
                  
                 #   R e c r e a t e   J S O N  
                 j o b _ d a t a   =   e x e c u t e _ q u e r y (  
                         " S E L E C T   m o d e l _ u s e d ,   l a n g u a g e   F R O M   t r a n s c r i p t i o n _ j o b s   W H E R E   m e e t i n g _ i d   =   ?   L I M I T   1 " ,  
                         ( m e e t i n g _ i d , ) ,  
                         f e t c h _ o n e = T r u e  
                 )  
                  
                 i f   j o b _ d a t a :  
                         _ c r e a t e _ m e e t i n g _ j s o n ( m e e t i n g _ i d ,   j o b _ d a t a . g e t ( ' m o d e l _ u s e d ' ,   ' u n k n o w n ' ) ,   j o b _ d a t a . g e t ( ' l a n g u a g e ' ,   ' t h ' ) )  
                  
                 p r i n t ( f " [ T r a n s c r i p t i o n ]   ‚ S&   U p d a t e d   t r a n s c r i p t i o n   { v o i c e _ i d } " )  
                 r e t u r n   { ' s u c c e s s ' :   T r u e ,   ' m e s s a g e ' :   ' U p d a t e d   s u c c e s s f u l l y ' }  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 p r i n t ( f " [ T r a n s c r i p t i o n ]   ‚ ù R  E r r o r   u p d a t i n g :   { e } " )  
                 i m p o r t   t r a c e b a c k  
                 t r a c e b a c k . p r i n t _ e x c ( )  
                 r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   s t r ( e ) }  
  
  
 #   E x p o r t   f u n c t i o n s  
 d e f   e x p o r t _ m e e t i n g _ t o _ t x t ( m e e t i n g _ i d ) :  
         " " " E x p o r t   t o   p l a i n   t e x t " " "  
         t r y :  
                 f r o m   d a t e t i m e   i m p o r t   d a t e t i m e  
                  
                 m e e t i n g   =   e x e c u t e _ q u e r y (  
                         " S E L E C T   m e e t i n g _ n a m e ,   m e e t i n g _ d a t e   F R O M   m e e t i n g s   W H E R E   m e e t i n g _ i d   =   ? " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ o n e = T r u e  
                 )  
                  
                 i f   n o t   m e e t i n g :  
                         r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   ' M e e t i n g   n o t   f o u n d ' }  
                  
                 t r a n s c r i p t i o n s   =   e x e c u t e _ q u e r y (  
                         " " " S E L E C T   t f . c o n t e n t ,   v f . n a m e ,   v f . s t a r t _ t i m e ,   v f . e n d _ t i m e  
                               F R O M   t e x t _ f i l e   t f   J O I N   v o i c e _ f i l e   v f   O N   t f . v o i c e _ i d   =   v f . v o i c e _ i d  
                               W H E R E   t f . m e e t i n g _ i d   =   ?   O R D E R   B Y   v f . s t a r t _ t i m e   A S C " " " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ a l l = T r u e  
                 )  
                  
                 i f   n o t   t r a n s c r i p t i o n s :  
                         r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   ' N o   t r a n s c r i p t i o n s ' }  
                  
                 p a r t i c i p a n t s   =   e x e c u t e _ q u e r y (  
                         " S E L E C T   D I S T I N C T   p a r t i c i p a n t _ n a m e   F R O M   m e e t i n g _ p a r t i c i p a n t s   W H E R E   m e e t i n g _ i d   =   ? " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ a l l = T r u e  
                 )  
                 p a r t _ n a m e s   =   ' ,   ' . j o i n ( [ p [ ' p a r t i c i p a n t _ n a m e ' ]   f o r   p   i n   p a r t i c i p a n t s ] )   i f   p a r t i c i p a n t s   e l s e   ' - '  
                  
                 l i n e s   =   [  
                         f " ‡ ∏ Å ‡ ∏ ≤ ‡ ∏ £ ‡ ∏ : ‡ ∏ £ ‡ ∏ ∞ ‡ ∏ `‡ ∏ ∏ ‡ ∏ ° :   { m e e t i n g [ ' m e e t i n g _ n a m e ' ] } " ,  
                         f " ‡ ∏ ß ‡ ∏ ± ‡ ∏ "!‡ ∏  ‡ ∏ µ ‡ π ∆:   { m e e t i n g [ ' m e e t i n g _ d a t e ' ] } " ,  
                         f " ‡ ∏ S‡ ∏ π ‡ π 0 ‡ π ¨ ‡ ∏  ‡ π 0 ‡ ∏ ≤ ‡ ∏ £ ‡ π ∆‡ ∏ ß ‡ ∏ ° :   { p a r t _ n a m e s } " ,  
                         " " ,   " ‚  Å "   *   5 0 ,   " "  
                 ]  
                  
                 f o r   t   i n   t r a n s c r i p t i o n s :  
                         s p e a k e r   =   t [ ' n a m e ' ] . s p l i t ( ' _ ' ) [ 0 ]   i f   ' _ '   i n   t [ ' n a m e ' ]   e l s e   ' ‡ π  ‡ ∏ ° ‡ π ∆‡ ∏ £ ‡ ∏ ∞ ‡ ∏ a‡ ∏ ∏ '  
                         t i m e _ r a n g e   =   f " { t [ ' s t a r t _ t i m e ' ] }   -   { t [ ' e n d _ t i m e ' ] } "   i f   t [ ' s t a r t _ t i m e ' ]   e l s e   ' '  
                         l i n e s . e x t e n d ( [ f " [ { s p e a k e r } ]   { t i m e _ r a n g e } " ,   t [ ' c o n t e n t ' ]   o r   ' ' ,   " " ] )  
                  
                 s t o r a g e _ s e t t i n g s   =   g e t _ s t o r a g e _ s e t t i n g s ( )  
                 e x p o r t _ p a t h   =   s t o r a g e _ s e t t i n g s . g e t ( ' e x p o r t _ p a t h ' ,   ' s t o r a g e / e x p o r t s ' )  
                 o s . m a k e d i r s ( e x p o r t _ p a t h ,   e x i s t _ o k = T r u e )  
                  
                 f i l e n a m e   =   f " m e e t i n g _ { m e e t i n g _ i d } _ { d a t e t i m e . n o w ( ) . s t r f t i m e ( ' % Y % m % d _ % H % M % S ' ) } . t x t "  
                 f i l e p a t h   =   o s . p a t h . j o i n ( e x p o r t _ p a t h ,   f i l e n a m e )  
                  
                 w i t h   o p e n ( f i l e p a t h ,   ' w ' ,   e n c o d i n g = ' u t f - 8 ' )   a s   f :  
                         f . w r i t e ( ' \ n ' . j o i n ( l i n e s ) )  
                  
                 r e t u r n   { ' s u c c e s s ' :   T r u e ,   ' f i l e p a t h ' :   f i l e p a t h ,   ' f i l e n a m e ' :   f i l e n a m e }  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 p r i n t ( f " [ E x p o r t ]   ‚ ù R  T X T   e r r o r :   { e } " )  
                 r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   s t r ( e ) }  
  
  
 d e f   e x p o r t _ m e e t i n g _ t o _ s r t ( m e e t i n g _ i d ) :  
         " " " E x p o r t   t o   S R T   s u b t i t l e " " "  
         t r y :  
                 f r o m   d a t e t i m e   i m p o r t   d a t e t i m e  
                  
                 t r a n s c r i p t i o n s   =   e x e c u t e _ q u e r y (  
                         " " " S E L E C T   t f . c o n t e n t ,   v f . n a m e ,   v f . s t a r t _ t i m e ,   v f . e n d _ t i m e  
                               F R O M   t e x t _ f i l e   t f   J O I N   v o i c e _ f i l e   v f   O N   t f . v o i c e _ i d   =   v f . v o i c e _ i d  
                               W H E R E   t f . m e e t i n g _ i d   =   ?   O R D E R   B Y   v f . s t a r t _ t i m e   A S C " " " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ a l l = T r u e  
                 )  
                  
                 i f   n o t   t r a n s c r i p t i o n s :  
                         r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   ' N o   t r a n s c r i p t i o n s ' }  
                  
                 l i n e s   =   [ ]  
                 f o r   i d x ,   t   i n   e n u m e r a t e ( t r a n s c r i p t i o n s ,   1 ) :  
                         s p e a k e r   =   t [ ' n a m e ' ] . s p l i t ( ' _ ' ) [ 0 ]   i f   ' _ '   i n   t [ ' n a m e ' ]   e l s e   ' ‡ π  ‡ ∏ ° ‡ π ∆‡ ∏ £ ‡ ∏ ∞ ‡ ∏ a‡ ∏ ∏ '  
                         s t a r t   =   ( t [ ' s t a r t _ t i m e ' ]   +   ' , 0 0 0 ' )   i f   t [ ' s t a r t _ t i m e ' ]   e l s e   ' 0 0 : 0 0 : 0 0 , 0 0 0 '  
                         e n d   =   ( t [ ' e n d _ t i m e ' ]   +   ' , 0 0 0 ' )   i f   t [ ' e n d _ t i m e ' ]   e l s e   ' 0 0 : 0 0 : 0 0 , 0 0 0 '  
                         l i n e s . e x t e n d ( [ s t r ( i d x ) ,   f " { s t a r t }   - - >   { e n d } " ,   f " [ { s p e a k e r } ]   { t [ ' c o n t e n t ' ]   o r   ' ' } " ,   " " ] )  
                  
                 s t o r a g e _ s e t t i n g s   =   g e t _ s t o r a g e _ s e t t i n g s ( )  
                 e x p o r t _ p a t h   =   s t o r a g e _ s e t t i n g s . g e t ( ' e x p o r t _ p a t h ' ,   ' s t o r a g e / e x p o r t s ' )  
                 o s . m a k e d i r s ( e x p o r t _ p a t h ,   e x i s t _ o k = T r u e )  
                  
                 f i l e n a m e   =   f " m e e t i n g _ { m e e t i n g _ i d } _ { d a t e t i m e . n o w ( ) . s t r f t i m e ( ' % Y % m % d _ % H % M % S ' ) } . s r t "  
                 f i l e p a t h   =   o s . p a t h . j o i n ( e x p o r t _ p a t h ,   f i l e n a m e )  
                  
                 w i t h   o p e n ( f i l e p a t h ,   ' w ' ,   e n c o d i n g = ' u t f - 8 ' )   a s   f :  
                         f . w r i t e ( ' \ n ' . j o i n ( l i n e s ) )  
                  
                 r e t u r n   { ' s u c c e s s ' :   T r u e ,   ' f i l e p a t h ' :   f i l e p a t h ,   ' f i l e n a m e ' :   f i l e n a m e }  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 p r i n t ( f " [ E x p o r t ]   ‚ ù R  S R T   e r r o r :   { e } " )  
                 r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   s t r ( e ) }  
  
  
 d e f   e x p o r t _ m e e t i n g _ t o _ d o c x ( m e e t i n g _ i d ) :  
         " " " E x p o r t   t o   W o r d   d o c u m e n t " " "  
         t r y :  
                 f r o m   d a t e t i m e   i m p o r t   d a t e t i m e  
                 f r o m   d o c x   i m p o r t   D o c u m e n t  
                 f r o m   d o c x . s h a r e d   i m p o r t   P t ,   R G B C o l o r  
                 f r o m   d o c x . e n u m . t e x t   i m p o r t   W D _ A L I G N _ P A R A G R A P H  
                  
                 m e e t i n g   =   e x e c u t e _ q u e r y (  
                         " S E L E C T   m e e t i n g _ n a m e ,   m e e t i n g _ d a t e   F R O M   m e e t i n g s   W H E R E   m e e t i n g _ i d   =   ? " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ o n e = T r u e  
                 )  
                  
                 i f   n o t   m e e t i n g :  
                         r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   ' M e e t i n g   n o t   f o u n d ' }  
                  
                 t r a n s c r i p t i o n s   =   e x e c u t e _ q u e r y (  
                         " " " S E L E C T   t f . c o n t e n t ,   v f . n a m e ,   v f . s t a r t _ t i m e ,   v f . e n d _ t i m e  
                               F R O M   t e x t _ f i l e   t f   J O I N   v o i c e _ f i l e   v f   O N   t f . v o i c e _ i d   =   v f . v o i c e _ i d  
                               W H E R E   t f . m e e t i n g _ i d   =   ?   O R D E R   B Y   v f . s t a r t _ t i m e   A S C " " " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ a l l = T r u e  
                 )  
                  
                 i f   n o t   t r a n s c r i p t i o n s :  
                         r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   ' N o   t r a n s c r i p t i o n s ' }  
                  
                 p a r t i c i p a n t s   =   e x e c u t e _ q u e r y (  
                         " S E L E C T   D I S T I N C T   p a r t i c i p a n t _ n a m e   F R O M   m e e t i n g _ p a r t i c i p a n t s   W H E R E   m e e t i n g _ i d   =   ? " ,  
                         ( m e e t i n g _ i d , ) ,   f e t c h _ a l l = T r u e  
                 )  
                 p a r t _ n a m e s   =   ' ,   ' . j o i n ( [ p [ ' p a r t i c i p a n t _ n a m e ' ]   f o r   p   i n   p a r t i c i p a n t s ] )   i f   p a r t i c i p a n t s   e l s e   ' - '  
                  
                 d o c   =   D o c u m e n t ( )  
                  
                 #   T i t l e  
                 t i t l e   =   d o c . a d d _ p a r a g r a p h ( m e e t i n g [ ' m e e t i n g _ n a m e ' ] )  
                 t i t l e . a l i g n m e n t   =   W D _ A L I G N _ P A R A G R A P H . C E N T E R  
                 t i t l e . r u n s [ 0 ] . f o n t . s i z e   =   P t ( 1 8 )  
                 t i t l e . r u n s [ 0 ] . f o n t . b o l d   =   T r u e  
                  
                 #   D a t e  
                 d a t e _ p a r a   =   d o c . a d d _ p a r a g r a p h ( m e e t i n g [ ' m e e t i n g _ d a t e ' ] )  
                 d a t e _ p a r a . a l i g n m e n t   =   W D _ A L I G N _ P A R A G R A P H . C E N T E R  
                  
                 d o c . a d d _ p a r a g r a p h ( ' ‚  Å '   *   5 0 )  
                  
                 #   P a r t i c i p a n t s  
                 p a r t _ p a r a   =   d o c . a d d _ p a r a g r a p h ( )  
                 p a r t _ p a r a . a d d _ r u n ( ' ‡ ∏ S‡ ∏ π ‡ π 0 ‡ π ¨ ‡ ∏  ‡ π 0 ‡ ∏ ≤ ‡ ∏ £ ‡ π ∆‡ ∏ ß ‡ ∏ ° :   ' ) . b o l d   =   T r u e  
                 p a r t _ p a r a . a d d _ r u n ( p a r t _ n a m e s )  
                  
                 d o c . a d d _ p a r a g r a p h ( ' ‚  Å '   *   5 0 )  
                 d o c . a d d _ p a r a g r a p h ( )  
                  
                 #   T r a n s c r i p t i o n s  
                 f o r   t   i n   t r a n s c r i p t i o n s :  
                         s p e a k e r   =   t [ ' n a m e ' ] . s p l i t ( ' _ ' ) [ 0 ]   i f   ' _ '   i n   t [ ' n a m e ' ]   e l s e   ' ‡ π  ‡ ∏ ° ‡ π ∆‡ ∏ £ ‡ ∏ ∞ ‡ ∏ a‡ ∏ ∏ '  
                         t i m e _ r a n g e   =   f " { t [ ' s t a r t _ t i m e ' ] }   -   { t [ ' e n d _ t i m e ' ] } "   i f   t [ ' s t a r t _ t i m e ' ]   e l s e   ' '  
                          
                         s p e a k e r _ p a r a   =   d o c . a d d _ p a r a g r a p h ( )  
                         s p e a k e r _ r u n   =   s p e a k e r _ p a r a . a d d _ r u n ( f " [ { s p e a k e r } ]   " )  
                         s p e a k e r _ r u n . f o n t . b o l d   =   T r u e  
                         s p e a k e r _ r u n . f o n t . c o l o r . r g b   =   R G B C o l o r ( 0 ,   0 ,   2 5 5 )  
                         s p e a k e r _ p a r a . a d d _ r u n ( t i m e _ r a n g e )  
                          
                         d o c . a d d _ p a r a g r a p h ( t [ ' c o n t e n t ' ]   o r   ' ' )  
                         d o c . a d d _ p a r a g r a p h ( )  
                  
                 s t o r a g e _ s e t t i n g s   =   g e t _ s t o r a g e _ s e t t i n g s ( )  
                 e x p o r t _ p a t h   =   s t o r a g e _ s e t t i n g s . g e t ( ' e x p o r t _ p a t h ' ,   ' s t o r a g e / e x p o r t s ' )  
                 o s . m a k e d i r s ( e x p o r t _ p a t h ,   e x i s t _ o k = T r u e )  
                  
                 f i l e n a m e   =   f " m e e t i n g _ { m e e t i n g _ i d } _ { d a t e t i m e . n o w ( ) . s t r f t i m e ( ' % Y % m % d _ % H % M % S ' ) } . d o c x "  
                 f i l e p a t h   =   o s . p a t h . j o i n ( e x p o r t _ p a t h ,   f i l e n a m e )  
                  
                 d o c . s a v e ( f i l e p a t h )  
                  
                 r e t u r n   { ' s u c c e s s ' :   T r u e ,   ' f i l e p a t h ' :   f i l e p a t h ,   ' f i l e n a m e ' :   f i l e n a m e }  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 p r i n t ( f " [ E x p o r t ]   ‚ ù R  D O C X   e r r o r :   { e } " )  
                 i m p o r t   t r a c e b a c k  
                 t r a c e b a c k . p r i n t _ e x c ( )  
                 r e t u r n   { ' s u c c e s s ' :   F a l s e ,   ' m e s s a g e ' :   s t r ( e ) }  
 