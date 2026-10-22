"""
Unit tests for database migration runner.
"""
import os
import shutil
import sqlite3
from database.migrate import migrate, get_user_version

def test_fresh_database_migration(tmp_path):
    """Test initializing a completely fresh database from version 0 to current."""
    db_file = str(tmp_path / "fresh.db")
    migrate(db_file)

    conn = sqlite3.connect(db_file)
    version = get_user_version(conn)
    assert version >= 4

    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    assert 'users' in tables
    assert 'meetings' in tables
    assert 'voice_file' in tables
    assert 'text_file' in tables
    assert 'participant_meeting' in tables

    # Check admin was seeded
    cursor.execute("SELECT username, role FROM users WHERE username = 'admin'")
    admin = cursor.fetchone()
    assert admin is not None
    assert admin[1] == 'admin'
    conn.close()


def test_legacy_database_migration(tmp_path):
    """Test migrating a copy of the actual database.db with data preservation."""
    original_db = "database.db"
    if not os.path.exists(original_db):
        return

    test_db = str(tmp_path / "legacy.db")
    shutil.copy2(original_db, test_db)

    # Force user_version = 0 to simulate pre-migration state
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    initial_meetings = cursor.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
    initial_voices = cursor.execute("SELECT COUNT(*) FROM voice_file").fetchone()[0]
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()

    # Run migration
    migrate(test_db)

    conn = sqlite3.connect(test_db)
    assert get_user_version(conn) >= 4

    cursor = conn.cursor()
    # Verify speaker_name exists
    cursor.execute("PRAGMA table_info(voice_file)")
    cols = [r[1] for r in cursor.fetchall()]
    assert 'speaker_name' in cols

    # Verify checked_at exists
    cursor.execute("PRAGMA table_info(participant_meeting)")
    cols = [r[1] for r in cursor.fetchall()]
    assert 'checked_at' in cols

    # Verify data counts preserved exactly
    cursor.execute("SELECT COUNT(*) FROM meetings")
    assert cursor.fetchone()[0] == initial_meetings

    cursor.execute("SELECT COUNT(*) FROM voice_file")
    assert cursor.fetchone()[0] == initial_voices

    # Verify backup was created
    backups = [f for f in os.listdir(tmp_path) if f.startswith("legacy.db.bak-")]
    assert len(backups) >= 1

    conn.close()
