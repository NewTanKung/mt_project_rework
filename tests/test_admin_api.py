"""
Unit tests for Admin APIs (devices, channels, storage, users, models).
"""
from unittest.mock import patch

def test_devices_crud(admin_client):
    # Mock scanning devices
    mock_devices = [
        {'device_index': 0, 'name': 'Mic 1', 'max_input_channels': 2, 'host_api': 'MME'}
    ]
    with patch('services.device_service.sd.query_devices', return_value=[{'name': 'Mic 1', 'max_input_channels': 2, 'hostapi': 0}]):
        with patch('services.device_service.sd.query_hostapis', return_value={'name': 'MME'}):
            scan_res = admin_client.post('/api/admin/devices/scan')
            assert scan_res.status_code == 200
            assert scan_res.get_json()['success'] is True

    # List devices
    list_res = admin_client.get('/api/admin/devices')
    assert list_res.status_code == 200
    devices = list_res.get_json()['devices']
    assert len(devices) >= 1
    dev_id = devices[0]['id']

    # Update status
    patch_res = admin_client.patch(f'/api/admin/devices/{dev_id}', json={'status': 'disabled'})
    assert patch_res.status_code == 200

    # Delete device
    del_res = admin_client.delete(f'/api/admin/devices/{dev_id}')
    assert del_res.status_code == 200


def test_channels_crud(admin_client):
    # Create channel
    res = admin_client.post('/api/admin/channels', json={
        'name': 'Channel 1',
        'device_name': 'Device A',
        'device_index': 0,
        'channel_index': 0
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    channel_id = data['channel_id']

    # List channels
    res = admin_client.get('/api/admin/channels')
    assert res.status_code == 200
    assert any(c['id'] == channel_id for c in res.get_json()['channels'])

    # Modify channel
    res = admin_client.patch(f'/api/admin/channels/{channel_id}', json={'name': 'Renamed Channel'})
    assert res.status_code == 200

    # Soft delete channel
    res = admin_client.delete(f'/api/admin/channels/{channel_id}')
    assert res.status_code == 200


def test_users_crud_and_self_delete_protection(admin_client):
    # Add new user
    res = admin_client.post('/api/admin/users', json={
        'username': 'newuser',
        'password': 'password123',
        'role': 'user'
    })
    assert res.status_code == 200
    uid = res.get_json()['user_id']

    # Update user
    res = admin_client.patch(f'/api/admin/users/{uid}', json={'role': 'admin'})
    assert res.status_code == 200

    # Prevent deleting self
    res = admin_client.delete('/api/admin/users/1')  # Admin has ID 1
    assert res.status_code == 400
    assert 'Cannot delete yourself' in res.get_json()['message']

    # Delete new user
    res = admin_client.delete(f'/api/admin/users/{uid}')
    assert res.status_code == 200


def test_models_api(admin_client):
    res = admin_client.get('/api/admin/models')
    assert res.status_code == 200
    models = res.get_json()['models']
    assert len(models) == 5
    assert any(m['name'] == 'base' for m in models)

    res = admin_client.get('/api/admin/models/base/progress')
    assert res.status_code == 200
    data = res.get_json()
    assert 'status' in data
    assert 'progress' in data
