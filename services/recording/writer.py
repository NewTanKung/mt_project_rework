"""
Background segment writer thread for saving audio segments to WAV and database.
Prevents heavy I/O from running inside PortAudio audio callback threads.
"""
import os
import wave
import queue
import logging
import threading
import numpy as np
from datetime import datetime
from dataclasses import dataclass
from database import execute
from core.paths import to_storage_path
from services.exporters.common import safe_filename

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000


@dataclass
class SegmentJob:
    meeting_id: int
    participant_id: int
    speaker_name: str
    segment_index: int
    chunks: list[np.ndarray]
    device_sample_rate: int
    folder_path: str
    start_time_str: str
    end_time_str: str


class SegmentWriter(threading.Thread):
    """
    Dedicated worker thread consuming finished audio segments,
    performing resampling, writing WAV files, and inserting voice_file records.
    """
    def __init__(self):
        super().__init__(name="SegmentWriter", daemon=True)
        self.queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self.total_saved = 0

    def submit(self, job: SegmentJob):
        """Submit a finished speech segment for background processing."""
        self.queue.put(job)

    def run(self):
        while not self._stop_event.is_set() or not self.queue.empty():
            try:
                job = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue

            try:
                self._process_job(job)
                self.total_saved += 1
            except Exception as e:
                logger.exception("Error writing audio segment: %s", e)
            finally:
                self.queue.task_done()

    def _process_job(self, job: SegmentJob):
        if not job.chunks:
            return

        # Concatenate audio chunks
        audio_data = np.concatenate(job.chunks).astype(np.float32)
        if len(audio_data) == 0:
            return

        device_rate = job.device_sample_rate
        target_rate = TARGET_SAMPLE_RATE

        # Resample to 16kHz for Whisper if device sample rate differs
        if device_rate != target_rate:
            try:
                from scipy import signal
                # Use resample_poly for better quality and performance
                import math
                gcd = math.gcd(target_rate, device_rate)
                up = target_rate // gcd
                down = device_rate // gcd
                audio_data = signal.resample_poly(audio_data, up, down)
                actual_rate = target_rate
            except Exception as e:
                logger.warning("Scipy resampling failed, falling back: %s", e)
                actual_rate = device_rate
        else:
            actual_rate = device_rate

        # Normalize and clip to 16-bit PCM
        audio_int16 = np.int16(np.clip(audio_data, -1.0, 1.0) * 32767)

        # Build clean filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        clean_speaker = safe_filename(job.speaker_name)
        filename = f"{clean_speaker}_{job.segment_index}_{timestamp}.wav"
        filepath = os.path.join(job.folder_path, filename)

        # Write WAV file
        with wave.open(filepath, 'wb') as wf:
            wf.setnchannels(1)      # Mono
            wf.setsampwidth(2)      # 16-bit
            wf.setframerate(actual_rate)
            wf.writeframes(audio_int16.tobytes())

        file_size = os.path.getsize(filepath)
        duration = len(audio_data) / actual_rate
        portable_path = to_storage_path(filepath)

        # Insert record into database
        execute(
            """INSERT INTO voice_file 
               (meeting_id, person_id, file_path, file_size, duration, 
                name, speaker_name, start_time, end_time) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job.meeting_id, job.participant_id, portable_path, file_size, duration,
             filename, job.speaker_name, job.start_time_str, job.end_time_str)
        )
        logger.info("Saved segment: %s (%.1fs, %s - %s)",
                    filename, duration, job.start_time_str, job.end_time_str)

    def close(self):
        """Signal worker to finish remaining queue and wait for completion."""
        self._stop_event.set()
        self.queue.join()
        self.join(timeout=10.0)
