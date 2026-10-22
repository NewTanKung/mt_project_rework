"""
Tests for Attendance API endpoints and service functions.
"""
import pytest
from database import query_all


def test_attendance_lifecycle(user_client):
    # 1. Create a meeting with participants
    meeting_payload = {
        'meeting_name': 'Attendance Test Meeting',
        'description': 'Testing attendance feature',
        'meeting_location': 'Conference Room B',
        'meeting_date': '2026-10-22',
        'participants': [
            {'name': 'Alice Smith', 'role': 'ประธาน'},
            {'name': 'Bob Jones', 'role': 'กรรมการ'}
        ]
    }
    create_res = user_client.post('/api/user/meetings', json=meeting_payload)
    assert create_res.status_code == 200
    meeting_id = create_res.get_json()['meeting_id']

    # Get participant IDs for this meeting
    meeting_details = user_client.get(f'/api/user/meetings/{meeting_id}').get_json()
    participants = meeting_details['meeting']['participants']
    assert len(participants) == 2
    p1_id = participants[0]['participant_id']
    p2_id = participants[1]['participant_id']

    # 2. Initialize attendance
    init_res = user_client.post(
        f'/api/user/meetings/{meeting_id}/attendance/init',
        json={'participant_ids': [p1_id, p2_id]}
    )
    assert init_res.status_code == 200
    assert init_res.get_json()['success'] is True

    # 3. Get attendance summary (initial state should be not_started)
    summary_res = user_client.get(f'/api/user/meetings/{meeting_id}/attendance')
    assert summary_res.status_code == 200
    summary_data = summary_res.get_json()
    assert summary_data['success'] is True
    assert summary_data['summary']['total'] == 2
    assert summary_data['summary']['not_started'] == 2

    # 4. Mark p1 as present, p2 as late
    mark_p1 = user_client.put(
        f'/api/user/meetings/{meeting_id}/attendance/{p1_id}',
        json={'status': 'present'}
    )
    assert mark_p1.status_code == 200
    assert mark_p1.get_json()['success'] is True

    mark_p2 = user_client.put(
        f'/api/user/meetings/{meeting_id}/attendance/{p2_id}',
        json={'status': 'late'}
    )
    assert mark_p2.status_code == 200

    # 5. Verify individual participant attendance
    p1_status = user_client.get(f'/api/user/meetings/{meeting_id}/attendance/{p1_id}')
    assert p1_status.status_code == 200
    assert p1_status.get_json()['status'] == 'present'
    assert p1_status.get_json()['checked_at'] is not None

    # 6. Verify summary updated correctly
    summary_res2 = user_client.get(f'/api/user/meetings/{meeting_id}/attendance')
    summary_data2 = summary_res2.get_json()['summary']
    assert summary_data2['present'] == 1
    assert summary_data2['late'] == 1
    assert summary_data2['not_started'] == 0

    # 7. Invalid status rejected
    invalid_mark = user_client.put(
        f'/api/user/meetings/{meeting_id}/attendance/{p1_id}',
        json={'status': 'invalid_status'}
    )
    assert invalid_mark.status_code == 400

    # 8. Reset/delete attendance
    del_res = user_client.delete(f'/api/user/meetings/{meeting_id}/attendance')
    assert del_res.status_code == 200

    # Verify attendance records deleted
    summary_res3 = user_client.get(f'/api/user/meetings/{meeting_id}/attendance')
    assert summary_res3.get_json()['summary']['total'] == 0
