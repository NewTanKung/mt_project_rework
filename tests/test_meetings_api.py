"""
Unit tests for Meeting APIs, presets, and cascade deletion.
"""
def test_create_get_list_delete_meeting(user_client):
    # 1. Create meeting
    payload = {
        'meeting_name': 'Test Project Meeting',
        'description': 'Discussion about project refactoring',
        'meeting_location': 'Room 101',
        'meeting_date': '2026-10-22',
        'participants': [
            {'name': 'Alice', 'role': 'ประธาน'},
            {'name': 'Bob', 'role': 'สมาชิก'}
        ]
    }
    create_res = user_client.post('/api/user/meetings', json=payload)
    assert create_res.status_code == 200
    meeting_id = create_res.get_json()['meeting_id']

    # 2. Get details
    get_res = user_client.get(f'/api/user/meetings/{meeting_id}')
    assert get_res.status_code == 200
    m = get_res.get_json()['meeting']
    assert m['meeting_name'] == 'Test Project Meeting'
    assert len(m['participants']) == 2

    # 3. List meetings (verifies has_transcription is present)
    list_res = user_client.get('/api/user/meetings')
    assert list_res.status_code == 200
    meetings = list_res.get_json()['meetings']
    found = next((x for x in meetings if x['meeting_id'] == meeting_id), None)
    assert found is not None
    assert found['has_transcription'] is False

    # 4. Modify meeting
    patch_res = user_client.patch(f'/api/user/meetings/{meeting_id}', json={'meeting_name': 'Renamed Meeting'})
    assert patch_res.status_code == 200

    # 5. Delete meeting
    del_res = user_client.delete(f'/api/user/meetings/{meeting_id}')
    assert del_res.status_code == 200

    # Verify not found
    get_again = user_client.get(f'/api/user/meetings/{meeting_id}')
    assert get_again.status_code == 404


def test_presets_api(user_client):
    res = user_client.post('/api/user/presets', json={
        'preset_name': 'Board Meeting Preset',
        'members': [{'name': 'Chairperson', 'role': 'ประธาน'}]
    })
    assert res.status_code == 200
    preset_id = res.get_json()['preset_id']

    res = user_client.get('/api/user/presets')
    assert res.status_code == 200
    presets = res.get_json()['presets']
    assert any(p['channel_preset_id'] == preset_id for p in presets)
