"""
Migration 004: Convert hard-coded project paths to portable relative paths
"""
import sqlite3
import re

def apply(conn: sqlite3.Connection):
    cursor = conn.cursor()
    
    # 1. Normalize storage_settings
    cursor.execute("SELECT id, setting_key, setting_value FROM storage_settings")
    settings = cursor.fetchall()
    
    for row in settings:
        sid, key, val = row[0], row[1], row[2]
        if not val:
            continue
            
        norm_val = val.replace('\\', '/')
        # Look for storage/... segment
        match = re.search(r'(storage/(?:exports|audio|transcriptions|models))', norm_val, re.IGNORECASE)
        if match:
            rel_path = match.group(1).lower()
            cursor.execute(
                "UPDATE storage_settings SET setting_value = ? WHERE id = ?",
                (rel_path, sid)
            )
            
    # 2. Normalize voice_file file_path
    cursor.execute("SELECT voice_id, file_path FROM voice_file WHERE file_path IS NOT NULL")
    files = cursor.fetchall()
    
    for row in files:
        vid, path = row[0], row[1]
        norm_path = path.replace('\\', '/')
        # Look for storage/audio/... segment
        match = re.search(r'(storage/audio/.+)', norm_path, re.IGNORECASE)
        if match:
            rel_path = match.group(1)
            cursor.execute(
                "UPDATE voice_file SET file_path = ? WHERE voice_id = ?",
                (rel_path, vid)
            )
