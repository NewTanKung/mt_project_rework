"""
Unit and integration tests for transcription engine, search, editing, and jobs.
"""
from unittest.mock import patch, MagicMock
from database import execute, query_one, query_all
from services.transcription.models import get_all_models, WHISPER_MODELS
from services.transcription.transcript import search_in_transcription, update_transcription
from services.transcription.jobs import create_transcription_job, _transcribe_worker


def test_available_models_list():
    """Verify default models dictionary contains standard whisper model sizes."""
    assert 'tiny' in WHISPER_MODELS
    assert 'base' in WHISPER_MODELS
    assert 'small' in WHISPER_MODELS
    assert 'medium' in WHISPER_MODELS
    all_models = get_all_models()
    assert len(all_models) == len(WHISPER_MODELS)


def test_search_transcription_xss_safety(app):
    """Verify transcription search highlights matches and escapes raw HTML/script tags."""
    with app.app_context():
        # Setup test meeting, participant, voice_file, and text_file with script tags
        execute("INSERT INTO meetings (meeting_id, meeting_name, meeting_date, status) VALUES (999, 'XSS Test', '2026-10-22', 'completed')")
        execute("INSERT INTO participants (participant_id, participant_name, role) VALUES (999, 'Attacker', 'Guest')")
        execute("INSERT INTO participant_meeting (participant_id, meeting_id) VALUES (999, 999)")
        execute(
            """INSERT INTO voice_file (voice_id, person_id, meeting_id, name, speaker_name, file_path, start_time, end_time, duration) 
               VALUES (999, 999, 999, 'Attacker_01.wav', 'Attacker', 'storage/audio/999/Attacker_01.wav', '00:00:01', '00:00:10', 9.0)"""
        )
        execute(
            """INSERT INTO text_file (id, meeting_id, voice_id, content, person_id)
               VALUES (999, 999, 999, '<script>alert(1)</script> Here is important secret discussion.', 999)"""
        )

        # 1. Search for keyword "secret"
        res = search_in_transcription(999, query="secret")
        assert res['success'] is True
        assert res['total'] == 1
        item = res['results'][0]

        # The <script> must be escaped to &lt;script&gt;
        assert "<script>" not in item['text']
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in item['text']
        # The query term must be wrapped in <mark>
        assert "<mark>secret</mark>" in item['text']


def test_update_transcription_text_and_speaker(user_client, app):
    """Verify editing transcription updates both text and voice_file speaker_name without touching files."""
    with app.app_context():
        execute("INSERT INTO meetings (meeting_id, meeting_name, meeting_date, status) VALUES (998, 'Edit Test', '2026-10-22', 'completed')")
        execute("INSERT INTO participants (participant_id, participant_name, role) VALUES (998, 'Old Speaker', 'Guest')")
        execute("INSERT INTO participant_meeting (participant_id, meeting_id) VALUES (998, 998)")
        execute(
            """INSERT INTO voice_file (voice_id, person_id, meeting_id, name, speaker_name, file_path, start_time, end_time, duration) 
               VALUES (998, 998, 998, 'Old_01.wav', 'Old Speaker', 'storage/audio/998/Old_01.wav', '00:01:00', '00:01:10', 10.0)"""
        )
        execute(
            """INSERT INTO text_file (id, meeting_id, voice_id, content, person_id)
               VALUES (998, 998, 998, 'Initial transcribed sentence.', 998)"""
        )

    # Call PUT endpoint
    update_res = user_client.put(
        '/api/user/transcriptions/998',
        json={
            'speaker_name': 'New Speaker',
            'text': 'Corrected transcribed sentence.',
            'start_time': '00:01:05',
            'end_time': '00:01:15'
        }
    )
    assert update_res.status_code == 200
    assert update_res.get_json()['success'] is True

    # Verify DB update
    with app.app_context():
        vf = query_one("SELECT speaker_name, start_time, end_time FROM voice_file WHERE voice_id = 998")
        assert vf['speaker_name'] == 'New Speaker'
        assert vf['start_time'] == '00:01:05'
        assert vf['end_time'] == '00:01:15'

        tf = query_one("SELECT content FROM text_file WHERE voice_id = 998")
        assert tf['content'] == 'Corrected transcribed sentence.'


def test_transcription_job_lifecycle(app):
    """Test creating and running a transcription job with duplicate prevention."""
    with app.app_context():
        execute("INSERT INTO meetings (meeting_id, meeting_name, meeting_date, status) VALUES (997, 'Job Test', '2026-10-22', 'completed')")
        execute("INSERT INTO participants (participant_id, participant_name, role) VALUES (997, 'Speaker A', 'Member')")
        execute("INSERT INTO participant_meeting (participant_id, meeting_id) VALUES (997, 997)")
        audio_file_rel = 'storage/audio/997/SpeakerA_01.wav'
        execute(
            """INSERT INTO voice_file (voice_id, person_id, meeting_id, name, speaker_name, file_path, start_time, end_time, duration) 
               VALUES (997, 997, 997, 'SpeakerA_01.wav', 'Speaker A', ?, '00:00:00', '00:00:05', 5.0)""",
            (audio_file_rel,)
        )

        # Create dummy file on disk so transcribe step doesn't skip
        from core.paths import resolve_path
        abs_audio = resolve_path(audio_file_rel)
        import os
        os.makedirs(os.path.dirname(abs_audio), exist_ok=True)
        with open(abs_audio, 'wb') as f:
            f.write(b'RIFF' + b'\x00' * 100)

        mock_seg = MagicMock()
        mock_seg.text = 'Mock transcription text'
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_seg], MagicMock())

        with patch('services.transcription.jobs.get_cached_model', return_value=mock_model):
            # Create and run job
            job_id = create_transcription_job(997, model_used='base', language='th')
            assert job_id is not None
            _transcribe_worker(job_id, 997, 'base', 'th')

            # Verify job completed
            job = query_one("SELECT status, progress FROM transcription_jobs WHERE job_id = ?", (job_id,))
            assert job['status'] == 'completed'
            assert job['progress'] == 100

            # Verify text_file was created
            texts = query_all("SELECT content FROM text_file WHERE meeting_id = 997")
            assert len(texts) == 1
            assert texts[0]['content'] == 'Mock transcription text'

            # Re-running transcription for same meeting should NOT create duplicates (Fix B10)
            job_id_2 = create_transcription_job(997, model_used='base', language='th')
            _transcribe_worker(job_id_2, 997, 'base', 'th')
            texts_after = query_all("SELECT content FROM text_file WHERE meeting_id = 997")
            assert len(texts_after) == 1
