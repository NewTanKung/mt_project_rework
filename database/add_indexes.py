"""
Database Migration: Add Indexes
Run this script to add missing indexes for better query performance
"""
import sqlite3
import os

# Get database path
db_path = os.path.join(os.path.dirname(__file__), '..', 'database.db')

# Connect to database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("[Migration] Adding database indexes...")

try:
    # Index for voice_file queries by meeting_id
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_voice_meeting ON voice_file(meeting_id)")
    print("✅ Created index: idx_voice_meeting")
    
    # Index for voice_file queries by person_id
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_voice_person ON voice_file(person_id)")
    print("✅ Created index: idx_voice_person")
    
    # Index for text_file queries by meeting_id
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_text_meeting ON text_file(meeting_id)")
    print("✅ Created index: idx_text_meeting")
    
    # Index for text_file queries by voice_id (for joining)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_text_voice ON text_file(voice_id)")
    print("✅ Created index: idx_text_voice")
    
    # Index for text_file queries by person_id
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_text_person ON text_file(person_id)")
    print("✅ Created index: idx_text_person")
    
    # Index for transcription_jobs queries by meeting_id
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_meeting ON transcription_jobs(meeting_id)")
    print("✅ Created index: idx_jobs_meeting")
    
    # Index for transcription_jobs queries by status (for active job checks)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON transcription_jobs(status)")
    print("✅ Created index: idx_jobs_status")
    
    # Composite index for preset_member queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_preset_member_preset ON preset_member(preset_id)")
    print("✅ Created index: idx_preset_member_preset")
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_preset_member_user ON preset_member(user_id)")
    print("✅ Created index: idx_preset_member_user")
    
    # Commit changes
    conn.commit()
    print("\n[Migration] ✅ All indexes created successfully!")
    
except Exception as e:
    print(f"\n[Migration] ❌ Error: {e}")
    conn.rollback()
    
finally:
    conn.close()
