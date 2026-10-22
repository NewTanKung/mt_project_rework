"""
Migration 002: Add checked_at column and performance indexes
"""
import sqlite3

def apply(conn: sqlite3.Connection):
    cursor = conn.cursor()
    
    # 1. Add checked_at column to participant_meeting if not exists
    cursor.execute("PRAGMA table_info(participant_meeting)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'checked_at' not in columns:
        cursor.execute("ALTER TABLE participant_meeting ADD COLUMN checked_at TEXT")

    # 2. Performance indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_voice_meeting ON voice_file(meeting_id)",
        "CREATE INDEX IF NOT EXISTS idx_voice_person ON voice_file(person_id)",
        "CREATE INDEX IF NOT EXISTS idx_text_meeting ON text_file(meeting_id)",
        "CREATE INDEX IF NOT EXISTS idx_text_voice ON text_file(voice_id)",
        "CREATE INDEX IF NOT EXISTS idx_text_person ON text_file(person_id)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_meeting ON transcription_jobs(meeting_id)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON transcription_jobs(status)",
        "CREATE INDEX IF NOT EXISTS idx_preset_member_preset ON preset_member(preset_id)",
        "CREATE INDEX IF NOT EXISTS idx_preset_member_user ON preset_member(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_participant_meeting_meeting ON participant_meeting(meeting_id)",
        "CREATE INDEX IF NOT EXISTS idx_participant_meeting_participant ON participant_meeting(participant_id)",
        "CREATE INDEX IF NOT EXISTS idx_participant_meeting_status ON participant_meeting(status)",
    ]
    
    for idx_sql in indexes:
        cursor.execute(idx_sql)
