"""
Unit tests for authentication, login/logout, and session guards.
"""
def test_login_success(client):
    res = client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin123'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['user']['username'] == 'admin'
    assert data['redirect'] == '/admin/devices'


def test_login_invalid(client):
    res = client.post('/api/auth/login', json={'username': 'admin', 'password': 'wrongpassword'})
    assert res.status_code == 401
    assert res.get_json()['success'] is False


def test_session_state(client):
    # Before login
    res = client.get('/api/auth/session')
    assert res.get_json()['logged_in'] is False

    # Login
    client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin123'})
    res = client.get('/api/auth/session')
    assert res.get_json()['logged_in'] is True
    assert res.get_json()['user']['role'] == 'admin'

    # Logout
    res = client.post('/api/auth/logout')
    assert res.status_code == 200
    assert res.get_json()['redirect'] == '/login'

    res = client.get('/api/auth/session')
    assert res.get_json()['logged_in'] is False


def test_unauthenticated_api_blocked(client):
    res = client.get('/api/user/meetings')
    assert res.status_code == 401

    res = client.get('/api/admin/devices')
    assert res.status_code == 401


def test_regular_user_cannot_access_admin_api(user_client):
    res = user_client.get('/api/admin/devices')
    assert res.status_code == 401
