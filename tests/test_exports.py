"""
Tests for meeting export features (TXT, SRT, DOCX, PDF, JSON).
"""
import os
import json
from database import execute
from services.exporters.common import safe_filename
from services.exporters.txt import export_meeting_to_txt
from services.exporters.srt import export_meeting_to_srt
from services.exporters.docx import export_meeting_to_docx
from services.exporters.pdf import export_meeting_to_pdf
from services.exporters.json_export import export_meeting_to_json


def test_safe_filename():
    """Verify filename sanitization handles dangerous characters."""
    assert safe_filename('Report: 2026/10/22 *draft*?') == 'Report_2026_10_22_draft'
    assert safe_filename('../../../evil') == 'evil'
    assert safe_filename('') == 'meeting'


def setup_sample_meeting(app):
    """Helper to setup a meeting with participant and transcript."""
    with app.app_context():
        execute("INSERT INTO meetings (meeting_id, meeting_name, meeting_date, description, status) VALUES (990, 'Export Test Meeting', '2026-10-22', 'Test export description', 'completed')")
        execute("INSERT INTO participants (participant_id, participant_name, role) VALUES (990, 'Somchai Dee', 'Chairman')")
        execute("INSERT INTO participant_meeting (participant_id, meeting_id) VALUES (990, 990)")
        execute(
            """INSERT INTO voice_file (voice_id, person_id, meeting_id, name, speaker_name, file_path, start_time, end_time, duration) 
               VALUES (990, 990, 990, 'Somchai_01.wav', 'Somchai Dee', 'storage/audio/990/Somchai_01.wav', '00:00:01', '00:00:05', 4.0)"""
        )
        execute(
            """INSERT INTO text_file (id, meeting_id, voice_id, content, person_id)
               VALUES (990, 990, 990, 'สวัสดีครับทุกคน ยินดีต้อนรับสู่การประชุม', 990)"""
        )


def test_export_txt(app):
    setup_sample_meeting(app)
    with app.app_context():
        res = export_meeting_to_txt(990)
        assert res['success'] is True
        assert os.path.exists(res['filepath'])
        with open(res['filepath'], 'r', encoding='utf-8') as f:
            content = f.read()
            assert 'การประชุม: Export Test Meeting' in content
            assert 'สวัสดีครับทุกคน' in content


def test_export_srt(app):
    setup_sample_meeting(app)
    with app.app_context():
        res = export_meeting_to_srt(990)
        assert res['success'] is True
        assert os.path.exists(res['filepath'])
        with open(res['filepath'], 'r', encoding='utf-8') as f:
            content = f.read()
            assert '00:00:01,000 --> 00:00:05,000' in content
            assert '[Somchai Dee]' in content


def test_export_docx(app):
    setup_sample_meeting(app)
    with app.app_context():
        res = export_meeting_to_docx(990)
        assert res['success'] is True
        assert os.path.exists(res['filepath'])
        assert res['filepath'].endswith('.docx')


def test_export_pdf(app):
    setup_sample_meeting(app)
    with app.app_context():
        res = export_meeting_to_pdf(990)
        assert res['success'] is True
        assert os.path.exists(res['filepath'])
        assert res['filepath'].endswith('.pdf')


def test_export_json_and_download_route(user_client, app):
    setup_sample_meeting(app)
    with app.app_context():
        res = export_meeting_to_json(990)
        assert res['success'] is True
        assert os.path.exists(res['filepath'])
        with open(res['filepath'], 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert data['meeting_info']['meeting_id'] == 990
            assert len(data['transcriptions']) == 1

    # Test the API download route that was previously missing (Fix B8)
    http_res = user_client.get('/api/user/meetings/990/download_json')
    assert http_res.status_code == 200
    assert 'application/json' in http_res.content_type
    json_body = json.loads(http_res.data)
    assert json_body['meeting_info']['meeting_id'] == 990
