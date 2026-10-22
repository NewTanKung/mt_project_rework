"""
Pytest configuration, fixtures, and mocks.
"""
import os
import sys
import pytest
from app import create_app
from database import query_one, execute
from services.auth_service import hash_password

@pytest.fixture
def app(tmp_path):
    """Create Flask application configured for testing with an isolated database."""
    db_file = str(tmp_path / "test.db")
    storage_dir = str(tmp_path / "storage")
    audio_dir = str(tmp_path / "storage" / "audio")
    export_dir = str(tmp_path / "storage" / "exports")
    trans_dir = str(tmp_path / "storage" / "transcriptions")
    model_dir = str(tmp_path / "storage" / "models")
    
    for d in [storage_dir, audio_dir, export_dir, trans_dir, model_dir]:
        os.makedirs(d, exist_ok=True)

    test_config = {
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'DATABASE_PATH': db_file
    }

    app_instance = create_app(test_config)

    # Ensure regular user exists for testing
    with app_instance.app_context():
        u = query_one("SELECT id FROM users WHERE username = 'testuser'")
        if not u:
            execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                ('testuser', hash_password('user123'), 'user')
            )

    yield app_instance


@pytest.fixture
def client(app):
    """Anonymous HTTP test client."""
    return app.test_client()


@pytest.fixture
def admin_client(app):
    """Test client authenticated as admin."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'admin'
        sess['role'] = 'admin'
    return client


@pytest.fixture
def user_client(app):
    """Test client authenticated as regular user."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['user_id'] = 2
        sess['username'] = 'testuser'
        sess['role'] = 'user'
    return client
