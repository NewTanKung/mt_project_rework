"""
Tests for recording pipeline: SegmentWriter, RecordingSession, and deadlock prevention.
"""
import os
import time
import numpy as np
from unittest.mock import patch, MagicMock
from database import execute, query_one, query_all
from services.recording.writer import SegmentWriter, SegmentJob
from services.recording.session import RecordingSession
from services.recording.registry import (
    start_recording_session,
    stop_recording_session,
    get_session_status
)


def test_segment_writer_writes_wav_and_records_db(app, tmp_path):
    """Verify SegmentWriter background thread drains queue, writes WAV, and inserts DB row."""
    with app.app_context():
        execute("INSERT INTO meetings (meeting_id, meeting_name, meeting_date, status) VALUES (888, 'Rec Test', '2026-10-22', 'recording')")
        execute("INSERT INTO participants (participant_id, participant_name, role) VALUES (888, 'Rec Participant', 'User')")
        execute("INSERT INTO participant_meeting (participant_id, meeting_id) VALUES (888, 888)")

        audio_folder = str(tmp_path / "audio_888")
        os.makedirs(audio_folder, exist_ok=True)

        writer = SegmentWriter()

        # Generate 0.5s of 16kHz audio chunk
        sample_rate = 16000
        chunk = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, 8000)) * 32767).astype(np.int16)

        job = SegmentJob(
            meeting_id=888,
            participant_id=888,
            speaker_name='Rec Participant',
            segment_index=1,
            chunks=[chunk],
            device_sample_rate=sample_rate,
            folder_path=audio_folder,
            start_time_str='00:00:00',
            end_time_str='00:00:01'
        )

        writer.start()
        writer.submit(job)
        writer.close()

        assert writer.total_saved == 1

        # Check file was written to disk
        wavs = [f for f in os.listdir(audio_folder) if f.startswith('Rec_Participant_1') and f.endswith('.wav')]
        assert len(wavs) == 1

        # Check DB row was inserted
        row = query_one("SELECT * FROM voice_file WHERE meeting_id = 888")
        assert row is not None
        assert row['speaker_name'] == 'Rec Participant'


def test_recording_session_deadlock_free_stop(app, tmp_path):
    """
    Critical Test: Ensure RecordingSession.stop() flushes buffered audio chunks
    to SegmentWriter without hanging / deadlocking (Fix B1 & B2).
    """
    with app.app_context():
        execute("INSERT INTO meetings (meeting_id, meeting_name, meeting_date, status) VALUES (887, 'Deadlock Test', '2026-10-22', 'recording')")
        execute("INSERT INTO participants (participant_id, participant_name, role) VALUES (887, 'Speaker One', 'User')")
        execute("INSERT INTO participant_meeting (participant_id, meeting_id) VALUES (887, 887)")

        participants = [{
            'participant_id': 887,
            'participant_name': 'Speaker One',
            'channel_id': 1,
            'device_index': 0,
            'channel_index': 0
        }]

        session = RecordingSession(887, participants)

        # Mock sounddevice InputStream, query_devices, and check_input_settings
        mock_stream = MagicMock()
        mock_devices = [{'name': 'Mock Mic', 'default_samplerate': 16000.0, 'max_input_channels': 2}]
        with patch('sounddevice.InputStream', return_value=mock_stream), \
             patch('sounddevice.query_devices', return_value=mock_devices), \
             patch('sounddevice.check_input_settings', return_value=None):

            start_res = session.start()
            assert start_res['success'] is True
            assert session.is_recording is True

            # Populate participant buffer with chunks directly under lock
            dummy_chunk = np.zeros(1600, dtype=np.int16)
            with session.buffer_lock:
                session.buffers[887].append(dummy_chunk)
                session.buffers[887].append(dummy_chunk)
                session.is_speaking[887] = True

            # Stop must complete within 5 seconds without deadlock
            t0 = time.time()
            stop_res = session.stop()
            elapsed = time.time() - t0

            assert elapsed < 5.0, "Session.stop() took too long or deadlocked!"
            assert stop_res['success'] is True
            assert session.is_recording is False
            assert len(session.buffers[887]) == 0


def test_recording_registry_lifecycle(app):
    """Test starting and stopping sessions via the registry."""
    with app.app_context():
        execute("INSERT INTO meetings (meeting_id, meeting_name, meeting_date, status) VALUES (886, 'Registry Test', '2026-10-22', 'idle')")
        execute("INSERT INTO participants (participant_id, participant_name, role) VALUES (886, 'Speaker Reg', 'User')")
        execute("INSERT INTO participant_meeting (participant_id, meeting_id) VALUES (886, 886)")

        participants = [{
            'participant_id': 886,
            'participant_name': 'Speaker Reg',
            'channel_id': 1,
            'device_index': 0,
            'channel_index': 0
        }]

        mock_stream = MagicMock()
        mock_devices = [{'name': 'Mock Mic', 'default_samplerate': 16000.0, 'max_input_channels': 2}]
        with patch('sounddevice.InputStream', return_value=mock_stream), \
             patch('sounddevice.query_devices', return_value=mock_devices), \
             patch('sounddevice.check_input_settings', return_value=None):

            res = start_recording_session(886, participants)
            assert res['success'] is True
            status_before = get_session_status(886)
            assert status_before['is_recording'] is True

            stop_res = stop_recording_session(886)
            assert stop_res['success'] is True
            status_after = get_session_status(886)
            assert status_after['is_recording'] is False
