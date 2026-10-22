"""
Multi-channel audio recording session with real-time speech detection and zero-copy callback.
"""
import os
import logging
import threading
import numpy as np
import sounddevice as sd
from datetime import datetime
from typing import Dict, List, Any
from services.storage_service import get_storage_settings
from services.recording.writer import SegmentWriter, SegmentJob
from config import RMS_THRESHOLD, MIN_SPEECH_DURATION, MIN_SILENCE_DURATION

logger = logging.getLogger(__name__)


class RecordingSession:
    """
    Manages audio input streams across multiple physical devices/channels,
    performs voice activity detection, and offloads finished speech segments.
    """
    def __init__(self, meeting_id: int, participants: list[dict]):
        self.meeting_id = meeting_id
        self.participants = participants
        self.is_recording = False
        self.is_paused = False
        self.start_time: datetime | None = None

        # VAD thresholds
        self.rms_threshold = RMS_THRESHOLD
        self.min_speech_duration = MIN_SPEECH_DURATION
        self.min_silence_duration = MIN_SILENCE_DURATION

        # Per-participant state
        self.buffers: Dict[int, list[np.ndarray]] = {}
        self.buffer_lock = threading.Lock()
        self.is_speaking: Dict[int, bool] = {}
        self.silent_samples: Dict[int, int] = {}
        self.last_rms: Dict[int, float] = {}
        self.segment_counters: Dict[int, int] = {}

        # Audio streams & hardware rates
        self.device_sample_rates: Dict[int, int] = {}
        self.streams: List[sd.InputStream] = []
        self.writer = SegmentWriter()

        # Destination directory for this meeting
        storage = get_storage_settings()
        self.meeting_audio_path = os.path.join(storage['audio_path'], f"meeting_{meeting_id}")
        os.makedirs(self.meeting_audio_path, exist_ok=True)

    def start(self) -> dict:
        """Start the recording session across all configured devices."""
        if self.is_recording:
            return {'success': False, 'message': 'Already recording'}

        # Detect sample rates
        rate_res = self._detect_sample_rates()
        if not rate_res['success']:
            return rate_res

        # Verify device availability
        verify_res = self._verify_devices()
        if not verify_res['success']:
            return verify_res

        for p in self.participants:
            pid = p['participant_id']
            self.buffers[pid] = []
            self.is_speaking[pid] = False
            self.silent_samples[pid] = 0
            self.last_rms[pid] = 0.0
            self.segment_counters[pid] = 0

        self.writer.start()
        self.is_recording = True
        self.is_paused = False
        self.start_time = datetime.now()

        # Start an input stream for each unique device index
        device_indices = set(p['device_index'] for p in self.participants)
        for dev_idx in device_indices:
            dev_participants = [p for p in self.participants if p['device_index'] == dev_idx]
            max_channel = max(p['channel_index'] for p in dev_participants)
            num_channels = max_channel + 1
            device_rate = self.device_sample_rates.get(dev_idx, 16000)

            def make_callback(participants_for_device, rate):
                def audio_callback(indata, frames, time_info, status):
                    if status:
                        logger.warning("PortAudio status: %s", status)
                    if not self.is_recording or self.is_paused:
                        return

                    for p in participants_for_device:
                        pid = p['participant_id']
                        ch_idx = p['channel_index']
                        channel_data = indata[:, ch_idx].copy()

                        # Calculate RMS level
                        rms = float(np.sqrt(np.mean(channel_data ** 2)))
                        self.last_rms[pid] = rms
                        silence_threshold_samples = int(rate * self.min_silence_duration)

                        if rms >= self.rms_threshold:
                            # Active speech
                            if not self.is_speaking.get(pid, False):
                                self.is_speaking[pid] = True
                                logger.debug("Speech started for %s (RMS=%.4f)", p['participant_name'], rms)
                            self.silent_samples[pid] = 0
                            with self.buffer_lock:
                                self.buffers[pid].append(channel_data)

                        elif self.is_speaking.get(pid, False):
                            # Trailing silence after speech
                            self.silent_samples[pid] += len(channel_data)
                            with self.buffer_lock:
                                self.buffers[pid].append(channel_data)

                            if self.silent_samples[pid] >= silence_threshold_samples:
                                # Silence duration threshold exceeded: finalize segment
                                self._flush_participant_segment(pid, rate)
                return audio_callback

            try:
                stream = sd.InputStream(
                    device=dev_idx,
                    channels=num_channels,
                    samplerate=device_rate,
                    blocksize=1024,
                    callback=make_callback(dev_participants, device_rate)
                )
                stream.start()
                self.streams.append(stream)
            except Exception as e:
                logger.exception("Failed to open audio stream on device %d: %s", dev_idx, e)
                self.stop()
                return {'success': False, 'message': f'Failed to open audio device {dev_idx}: {str(e)}'}

        logger.info("Recording session started for meeting %d with %d devices",
                    self.meeting_id, len(device_indices))
        return {'success': True, 'message': 'Recording started'}

    def pause(self) -> dict:
        """Pause recording."""
        if not self.is_recording or self.is_paused:
            return {'success': False, 'message': 'Not recording or already paused'}
        self.is_paused = True
        return {'success': True, 'message': 'Recording paused'}

    def resume(self) -> dict:
        """Resume recording."""
        if not self.is_recording or not self.is_paused:
            return {'success': False, 'message': 'Not paused'}
        self.is_paused = False
        return {'success': True, 'message': 'Recording resumed'}

    def stop(self) -> dict:
        """
        Stop recording, flush remaining audio buffers, and wait for segment writer.
        Completely deadlock-free.
        """
        if not self.is_recording:
            return {'success': False, 'message': 'Not recording'}

        self.is_recording = False
        self.is_paused = False

        # Close all hardware streams
        for stream in self.streams:
            try:
                stream.stop()
                stream.close()
            except Exception as e:
                logger.error("Error closing stream: %s", e)
        self.streams.clear()

        # Flush any remaining audio in participant buffers
        for p in self.participants:
            pid = p['participant_id']
            rate = self.device_sample_rates.get(p['device_index'], 16000)
            self._flush_participant_segment(pid, rate)

        # Wait for writer worker to finish all WAV and DB operations
        self.writer.close()
        logger.info("Recording session stopped for meeting %d. Total segments: %d",
                    self.meeting_id, self.writer.total_saved)
        return {'success': True, 'total_segments': self.writer.total_saved}

    def _flush_participant_segment(self, participant_id: int, sample_rate: int):
        """Extract current buffered chunks and submit to writer."""
        with self.buffer_lock:
            chunks = self.buffers.get(participant_id, [])
            self.buffers[participant_id] = []
            self.is_speaking[participant_id] = False
            self.silent_samples[participant_id] = 0

        if not chunks:
            return

        participant = next((p for p in self.participants if p['participant_id'] == participant_id), None)
        if not participant:
            return

        self.segment_counters[participant_id] = self.segment_counters.get(participant_id, 0) + 1
        seg_idx = self.segment_counters[participant_id]

        total_samples = sum(len(c) for c in chunks)
        duration = total_samples / sample_rate

        if self.start_time:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            start_sec = max(0.0, elapsed - duration)
            end_sec = elapsed
            start_str = self._format_time(start_sec)
            end_str = self._format_time(end_sec)
        else:
            start_str = "00:00:00"
            end_str = "00:00:00"

        job = SegmentJob(
            meeting_id=self.meeting_id,
            participant_id=participant_id,
            speaker_name=participant.get('participant_name') or f"ID-{participant_id}",
            segment_index=seg_idx,
            chunks=chunks,
            device_sample_rate=sample_rate,
            folder_path=self.meeting_audio_path,
            start_time_str=start_str,
            end_time_str=end_str
        )
        self.writer.submit(job)

    def get_audio_levels(self) -> dict:
        """
        Get instantaneous audio RMS levels and speaking state for each participant.
        Zero-copy, lock-free query.
        """
        levels = {}
        for p in self.participants:
            pid = p['participant_id']
            levels[pid] = {
                'name': p.get('participant_name') or f"ID-{pid}",
                'is_speaking': self.is_speaking.get(pid, False),
                'rms': round(self.last_rms.get(pid, 0.0), 4)
            }
        return levels

    def _detect_sample_rates(self) -> dict:
        device_indices = set(p['device_index'] for p in self.participants)
        for dev_idx in device_indices:
            rate = self._get_supported_rate(dev_idx)
            if rate is None:
                return {
                    'success': False,
                    'message': f'Device index {dev_idx} does not support common audio sample rates'
                }
            self.device_sample_rates[dev_idx] = rate
        return {'success': True, 'message': 'Sample rates verified'}

    def _get_supported_rate(self, device_index: int) -> int | None:
        rates_to_try = [16000, 44100, 48000, 22050, 8000]
        for rate in rates_to_try:
            try:
                sd.check_input_settings(device=device_index, channels=1, samplerate=rate)
                return rate
            except Exception:
                continue
        return None

    def _verify_devices(self) -> dict:
        try:
            devices = sd.query_devices()
            issues = []
            for p in self.participants:
                dev_idx = p['device_index']
                ch_idx = p['channel_index']
                if dev_idx >= len(devices):
                    issues.append(f"Device index {dev_idx} not found for {p.get('participant_name')}")
                    continue
                dev = devices[dev_idx]
                if dev['max_input_channels'] == 0:
                    issues.append(f"Device '{dev['name']}' has no audio inputs")
                elif ch_idx >= dev['max_input_channels']:
                    issues.append(f"Channel {ch_idx} exceeds max input channels ({dev['max_input_channels']}) on '{dev['name']}'")
            if issues:
                return {'success': False, 'message': 'Device verification failed', 'issues': issues}
            return {'success': True, 'message': 'All devices verified'}
        except Exception as e:
            return {'success': False, 'message': str(e), 'issues': [str(e)]}

    @staticmethod
    def _format_time(seconds: float) -> str:
        s = int(seconds)
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        return f"{h:02d}:{m:02d}:{sec:02d}"
