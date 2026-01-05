"""
Recording service - Multi-channel audio recording with speech detection
"""
import sounddevice as sd
import numpy as np
import wave
import os
import threading
from datetime import datetime
from database.db_manager import execute_query
from services.storage_service import get_storage_settings


class RecordingSession:
    """
    Manages a multi-channel recording session
    """
    
    def __init__(self, meeting_id, participants, app=None):
        """
        Initialize recording session
        
        Args:
            meeting_id: Meeting ID
            participants: List of participant dictionaries
            app: Flask app instance for database context
        """
        self.meeting_id = meeting_id
        self.participants = participants
        self.app = app
        self.is_recording = False
        self.is_paused = False
        self.streams = {}
        self.buffers = {}
        self.buffer_locks = {}  # Lock for each participant's buffer
        self.segment_counters = {}
        self.start_time = None
        self.has_speech = {}  # Track if participant has spoken
        self.is_speaking = {}  # ✅ Track if participant is currently speaking
        
        # Audio settings
        self.target_sample_rate = 16000  # Target for Whisper
        self.device_sample_rates = {}  # Actual rates per device
        self.channels_per_device = {}
        
        # Speech detection settings (from config)
        from config import RMS_THRESHOLD, MIN_SPEECH_DURATION, MIN_SILENCE_DURATION, ENABLE_REALTIME_RESAMPLING
        self.rms_threshold = RMS_THRESHOLD
        self.min_speech_duration = MIN_SPEECH_DURATION
        self.min_silence_duration = MIN_SILENCE_DURATION
        self.enable_realtime_resampling = ENABLE_REALTIME_RESAMPLING
        
        # Recording settings
        self.block_size = 1024
        self.running = False
        # Storage
        storage = get_storage_settings()
        self.audio_path = storage['audio_path']
        
        # Create meeting audio folder
        self.meeting_audio_path = os.path.join(
            self.audio_path,
            f"meeting_{meeting_id}"
        )
        os.makedirs(self.meeting_audio_path, exist_ok=True)
    
    
    def start(self):
        """
        Start recording session
        
        Returns:
            dict: {success: bool, message: str}
        """
        if self.is_recording:
            return {'success': False, 'message': 'Already recording'}
        
        # Detect and set sample rates for each device
        rate_detection = self._detect_sample_rates()
        if not rate_detection['success']:
            return rate_detection
        
        # Verify devices
        verification = self._verify_devices()
        if not verification['success']:
            return verification
        
        # Initialize buffers, counters, and locks
        for participant in self.participants:
            p_id = participant['participant_id']
            self.buffers[p_id] = []
            self.buffer_locks[p_id] = threading.Lock()
            self.segment_counters[p_id] = 0
        
        # Start recording
        self.is_recording = True
        self.is_paused = False
        self.start_time = datetime.now()
        
        # Start recording threads for each unique device
        device_indices = set(p['device_index'] for p in self.participants)
        
        for device_index in device_indices:
            # Get participants for this device
            device_participants = [
                p for p in self.participants 
                if p['device_index'] == device_index
            ]
            
            # Start recording thread
            thread = threading.Thread(
                target=self._record_device,
                args=(device_index, device_participants)
            )
            thread.daemon = True
            thread.start()
        
        return {'success': True, 'message': 'Recording started'}
    
    
    def pause(self):
        """
        Pause recording
        """
        if not self.is_recording or self.is_paused:
            return {'success': False, 'message': 'Not recording or already paused'}
        
        self.is_paused = True
        return {'success': True, 'message': 'Recording paused'}
    
    
    def resume(self):
        """
        Resume recording
        """
        if not self.is_recording or not self.is_paused:
            return {'success': False, 'message': 'Not paused'}
        
        self.is_paused = False
        return {'success': True, 'message': 'Recording resumed'}
    
    
    def stop(self):
        """
        Stop recording and save final segments
        
        Returns:
            dict: {success: bool, total_segments: int}
        """
        if not self.is_recording:
            return {'success': False, 'message': 'Not recording'}
        
        self.is_recording = False
        self.running = False
        
        # Save any remaining segments in buffers
        total_saved = 0
        for participant_id in self.buffers.keys():
            with self.buffer_locks[participant_id]:
                if len(self.buffers[participant_id]) > 0:
                    self._save_segment(participant_id)
                    total_saved += 1
        
        return {'success': True, 'total_segments': total_saved}
    
    
    def get_audio_levels(self):
        """
        Get current audio levels and speaking status for all participants
        
        Returns:
            dict: {participant_id: {'name': str, 'is_speaking': bool, 'rms': float}}
        """
        import numpy as np
        import threading
        
        levels = {}
        
        for participant in self.participants:
            p_id = participant['participant_id']
            p_name = participant.get('participant_name', f'ID-{p_id}')
            
            # Get current speaking status
            is_speaking = self.is_speaking.get(p_id, False)
            
            # Calculate current RMS from recent buffer
            rms = 0.0
            try:
                buffer_lock = self.buffer_locks.get(p_id)
                if buffer_lock:
                    with buffer_lock:
                        buffer = self.buffers.get(p_id, [])
                        if len(buffer) > 0:
                            # Use last 1024 samples
                            recent_samples = buffer[-min(1024, len(buffer)):]
                            if len(recent_samples) > 0:
                                rms = float(np.sqrt(np.mean(np.array(recent_samples)**2)))
            except Exception as e:
                print(f"[Recording] Error calculating RMS for {p_name}: {e}")
            
            levels[p_id] = {
                'name': p_name,
                'is_speaking': is_speaking,
                'rms': round(rms, 4)
            }
        
        return levels
    
    
    def _detect_sample_rates(self):
        """
        Detect supported sample rate for each device
        
        Returns:
            dict: {success: bool, message: str}
        """
        device_indices = set(p['device_index'] for p in self.participants)
        
        for device_index in device_indices:
            rate = self._get_supported_sample_rate(device_index)
            
            if rate is None:
                return {
                    'success': False,
                    'message': f'Device {device_index} does not support any common sample rates'
                }
            
            self.device_sample_rates[device_index] = rate
            print(f"[Recording] Device {device_index} will use {rate}Hz")
        
        return {'success': True, 'message': 'Sample rates detected'}
    
    
    def _get_supported_sample_rate(self, device_index):
        """
        Find a supported sample rate for the device
        
        Args:
            device_index: Device index
            
        Returns:
            int: Supported sample rate or None
        """
        # Try common sample rates (prefer 16kHz for Whisper)
        rates_to_try = [16000, 44100, 48000, 22050, 8000]
        
        for rate in rates_to_try:
            try:
                # Test if this rate works
                sd.check_input_settings(
                    device=device_index,
                    channels=1,
                    samplerate=rate
                )
                return rate
            except Exception:
                continue
        
        return None
    
    
    def _verify_devices(self):
        """
        Verify that all required devices and channels are available
        
        Returns:
            dict: {success: bool, message: str, issues: list}
        """
        issues = []
        
        try:
            devices = sd.query_devices()
            
            for participant in self.participants:
                device_index = participant['device_index']
                channel_index = participant['channel_index']
                
                # Check if device exists
                if device_index >= len(devices):
                    issues.append(f"Device {device_index} not found for {participant['participant_name']}")
                    continue
                
                device = devices[device_index]
                
                # Check if device has input channels
                if device['max_input_channels'] == 0:
                    issues.append(f"Device {device['name']} has no input channels")
                    continue
                
                # Check if channel index is valid
                if channel_index >= device['max_input_channels']:
                    issues.append(
                        f"Channel {channel_index} not available on device {device['name']} "
                        f"(max: {device['max_input_channels']})"
                    )
            
            if issues:
                return {
                    'success': False,
                    'message': 'Device verification failed',
                    'issues': issues
                }
            
            return {'success': True, 'message': 'All devices verified'}
        
        except Exception as e:
            return {
                'success': False,
                'message': f'Error verifying devices: {str(e)}',
                'issues': [str(e)]
            }
    
    
    def _record_device(self, device_index, participants):
        """
        Record from a specific device
        
        Args:
            device_index: Device index
            participants: List of participants using this device
        """
        # Get max channel index needed
        max_channel = max(p['channel_index'] for p in participants)
        num_channels = max_channel + 1
        
        # Callback for audio stream
        def audio_callback(indata, frames, time_info, status):
            if status:
                print(f"Stream status: {status}")
            
            if self.is_recording and not self.is_paused:
                # Process each participant's channel
                for participant in participants:
                    p_id = participant['participant_id']
                    ch_idx = participant['channel_index']
                    
                    # Extract channel data
                    channel_data = indata[:, ch_idx].copy()
                    
                    # ✅ เช็คเสียงก่อนว่ามีเสียงพูดหรือไม่
                    rms = np.sqrt(np.mean(channel_data**2))
                    
                    # เริ่มบันทึกเมื่อตรวจพบเสียงพูด
                    if rms >= self.rms_threshold:
                        if not self.is_speaking.get(p_id, False):
                            # เพิ่งเริ่มพูด
                            self.is_speaking[p_id] = True
                            participant_name = participant.get('participant_name', f'ID-{p_id}')
                            print(f"[Recording] 🎤 {participant_name} เริ่มพูด (RMS={rms:.4f})")
                        
                        # บันทึก buffer เฉพาะเมื่อกำลังพูด
                        with self.buffer_locks[p_id]:
                            self.buffers[p_id].extend(channel_data)
                    
                    # หยุดบันทึกเมื่อเงียบ
                    elif self.is_speaking.get(p_id, False):
                        # ยังเก็บ silence หลังพูดนิดหน่อย
                        with self.buffer_locks[p_id]:
                            self.buffers[p_id].extend(channel_data)
                    
                    # เช็คว่าควรบันทึกไฟล์หรือยัง
                    self._process_buffer(p_id)
        
        # Get sample rate for this device
        device_rate = self.device_sample_rates.get(device_index, 16000)
        
        # Start stream
        try:
            with sd.InputStream(
                device=device_index,
                channels=num_channels,
                samplerate=device_rate,
                callback=audio_callback,
                blocksize=1024
            ):
                # Keep stream alive while recording
                while self.is_recording:
                    sd.sleep(100)
        
        except Exception as e:
            print(f"Error recording from device {device_index}: {e}")
    
    
    def _process_buffer(self, participant_id):
        """
        Process buffer for speech detection and segmentation
        
        Args:
            participant_id: Participant ID
        """
        # Get buffer with lock
        with self.buffer_locks[participant_id]:
            buffer = list(self.buffers[participant_id])  # Make a copy
        
        # Get participant info to determine sample rate
        participant = next(
            (p for p in self.participants if p['participant_id'] == participant_id),
            None
        )
        if not participant:
            return
        
        device_rate = self.device_sample_rates.get(participant['device_index'], 16000)
        
        # Need at least min_silence_duration of audio to check
        silence_samples = int(device_rate * self.min_silence_duration)
        if len(buffer) < silence_samples:
            return
        
        # Calculate RMS of recent audio
        recent_audio = np.array(buffer[-silence_samples:])
        rms = np.sqrt(np.mean(recent_audio**2))
        
        # ✅ ถ้ากำลังพูดอยู่ และเงียบนานพอ → บันทึกไฟล์
        if self.is_speaking.get(participant_id, False) and rms < self.rms_threshold:
            participant_name = participant.get('participant_name', f'ID-{participant_id}')
            print(f"[Recording] ✅ {participant_name} หยุดพูด - กำลังบันทึก (buffer={len(buffer)} samples)")
            
            # Save segment
            self._save_segment(participant_id)
            
            # Clear buffer and reset flags with lock
            with self.buffer_locks[participant_id]:
                self.buffers[participant_id] = []
            self.is_speaking[participant_id] = False
            self.has_speech[participant_id] = False
    
    
    def _save_segment(self, participant_id):
        """
        Save audio segment to WAV file and database
        
        Args:
            participant_id: Participant ID
        """
        # Get buffer copy with lock
        with self.buffer_locks[participant_id]:
            buffer = list(self.buffers[participant_id])
        
        if len(buffer) == 0:
            return
        
        # Get participant info
        participant = next(
            (p for p in self.participants if p['participant_id'] == participant_id),
            None
        )
        
        if not participant:
            return
        
        # Increment segment counter
        self.segment_counters[participant_id] += 1
        segment_num = self.segment_counters[participant_id]
        
        # Create filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{participant['participant_name']}_{segment_num}_{timestamp}.wav"
        filepath = os.path.join(self.meeting_audio_path, filename)
        
        # Get device's actual sample rate
        device_rate = self.device_sample_rates.get(participant['device_index'], 16000)
        
        # Convert buffer to numpy array
        audio_data = np.array(buffer, dtype=np.float32)
        
        # Resample to target rate (16kHz for Whisper) if needed
        if device_rate != self.target_sample_rate:
            try:
                from scipy import signal
                num_samples = int(len(audio_data) * self.target_sample_rate / device_rate)
                audio_data = signal.resample(audio_data, num_samples)
                actual_sample_rate = self.target_sample_rate
                print(f"[Recording] Resampled from {device_rate}Hz to {self.target_sample_rate}Hz")
            except ImportError:
                print(f"[Recording] Warning: scipy not available, saving at {device_rate}Hz")
                actual_sample_rate = device_rate
        else:
            actual_sample_rate = device_rate
        
        # Normalize to int16
        audio_int16 = np.int16(audio_data * 32767)
        
        # Save as WAV
        with wave.open(filepath, 'wb') as wf:
            wf.setnchannels(1)  # Mono
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(actual_sample_rate)
            wf.writeframes(audio_int16.tobytes())
        
        # Get file size and duration (using original buffer length and device rate)
        file_size = os.path.getsize(filepath)
        duration = len(buffer) / device_rate
        
        # Calculate segment times relative to meeting start
        if self.start_time:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            start_time = max(0, elapsed - duration)
            end_time = elapsed
            
            # Format as HH:MM:SS
            start_time_str = self._format_time(start_time)
            end_time_str = self._format_time(end_time)
        else:
            start_time_str = "00:00:00"
            end_time_str = "00:00:00"
        
        
        # Save to database
        try:
            if not self.app:
                error_msg = f"No Flask app context available for saving segment: {filename}"
                print(f"[Recording] ❌ ERROR: {error_msg}")
                raise RuntimeError(error_msg)
            
            with self.app.app_context():
                execute_query(
                    """INSERT INTO voice_file 
                       (meeting_id, person_id, file_path, file_size, duration, 
                        name, start_time, end_time) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (self.meeting_id, participant_id, filepath, file_size, duration,
                     filename, start_time_str, end_time_str),
                    commit=True
                )
                print(f"[Recording] ✅ Saved segment: {filename} ({duration:.1f}s, {start_time_str} - {end_time_str})")
                
        except Exception as e:
            error_msg = f"Failed to save segment to database: {filename} - {str(e)}"
            print(f"[Recording] ❌ ERROR: {error_msg}")
            # Re-raise to propagate error up
            raise RuntimeError(error_msg) from e
    
    
    def _format_time(self, seconds):
        """
        Format seconds to HH:MM:SS
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# Global recording sessions with thread safety
_active_sessions = {}
_sessions_lock = threading.RLock()  # Reentrant lock for thread-safe access


def start_recording_session(meeting_id, participants):
    """
    Start a new recording session
    
    Args:
        meeting_id: Meeting ID
        participants: List of participant dictionaries with device and channel info
        
    Returns:
        dict: {success: bool, message: str}
    """
    from flask import current_app
    from services import attendance_service
    
    app = current_app._get_current_object()
    
    # Filter out absent participants
    try:
        attendance_summary = attendance_service.get_attendance_summary(meeting_id)
        if attendance_summary['success']:
            # Create map of status by participant_id
            status_map = {
                p['participant_id']: p['status'] 
                for p in attendance_summary['participants']
            }
            
            # Filter participants list
            # Keep only if status is NOT 'absent' (so keep present, late, not_started)
            active_participants = []
            for p in participants:
                p_id = p.get('participant_id')
                status = status_map.get(p_id, 'not_started') # Default to present if not found? Or not_started.
                
                # If status is valid (present, late, not_started), keep them.
                # If absent, skip.
                if status != 'absent':
                    active_participants.append(p)
                else:
                    print(f"[Recording] 🚫 Skipping absent participant: {p.get('participant_name')} (ID: {p_id})")
            
            participants = active_participants
            
    except Exception as e:
        print(f"[Recording] ⚠️ Failed to check attendance: {e}. Proceeding with all participants.")

    session = RecordingSession(meeting_id, participants, app)
    result = session.start()
    
    if result['success']:
        with _sessions_lock:
            _active_sessions[meeting_id] = session
    
    return result


def pause_recording_session(meeting_id):
    """
    Pause recording session
    """
    with _sessions_lock:
        if meeting_id not in _active_sessions:
            return {'success': False, 'message': 'No active recording for this meeting'}
        
        return _active_sessions[meeting_id].pause()


def resume_recording_session(meeting_id):
    """
    Resume recording session
    """
    with _sessions_lock:
        if meeting_id not in _active_sessions:
            return {'success': False, 'message': 'No active recording for this meeting'}
        
        return _active_sessions[meeting_id].resume()


def stop_recording_session(meeting_id):
    """
    Stop recording session
    """
    with _sessions_lock:
        if meeting_id not in _active_sessions:
            return {'success': False, 'message': 'No active recording for this meeting'}
        
        session = _active_sessions[meeting_id]
    
    # Stop session outside lock to avoid blocking
    result = session.stop()
    
    # Remove from active sessions
    with _sessions_lock:
        del _active_sessions[meeting_id]
    
    return result


def get_current_audio_levels(meeting_id):
    """
    Get current audio levels for a recording session
    
    Args:
        meeting_id: Meeting ID
        
    Returns:
        dict: Audio levels per participant or empty dict
    """
    with _sessions_lock:
        if meeting_id not in _active_sessions:
            return {}
        
        session = _active_sessions[meeting_id]
    
    # ✅ เรียกใช้ method ที่เพิ่มใหม่
    return session.get_audio_levels()


def get_session_status(meeting_id):
    """
    Get recording session status
    
    Returns:
        dict: {is_recording: bool, is_paused: bool}
    """
    with _sessions_lock:
        if meeting_id not in _active_sessions:
            return {'is_recording': False, 'is_paused': False}
        
        session = _active_sessions[meeting_id]
        return {
            'is_recording': session.is_recording,
            'is_paused': session.is_paused
        }
