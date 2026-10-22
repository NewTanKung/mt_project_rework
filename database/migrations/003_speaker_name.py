"""
Migration 003: Add speaker_name column to voice_file and backfill from file name
"""
import sqlite3

def apply(conn: sqlite3.Connection):
    cursor = conn.cursor()
    
    # 1. Add speaker_name column if not present
    cursor.execute("PRAGMA table_info(voice_file)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'speaker_name' not in columns:
        cursor.execute("ALTER TABLE voice_file ADD COLUMN speaker_name TEXT")
        
    # 2. Backfill speaker_name from name column
    cursor.execute("SELECT voice_id, name, person_id FROM voice_file WHERE speaker_name IS NULL")
    rows = cursor.fetchall()
    
    for row in rows:
        voice_id = row[0]
        name = row[1] or ''
        speaker = 'ไม่ระบุ'
        if '_' in name:
            speaker = name.split('_')[0]
        elif name:
            speaker = name
            
        cursor.execute(
            "UPDATE voice_file SET speaker_name = ? WHERE voice_id = ?",
            (speaker, voice_id)
        )
        
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_voice_speaker ON voice_file(speaker_name)")
