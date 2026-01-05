-- Migration: Add Participant Attendance System
-- Date: 2025-12-25
-- Description: เพิ่ม role column ใน participants และสร้าง participant_meeting table
-- 1. เพิ่ม role column ใน participants table (ถ้ายังไม่มี)
ALTER TABLE participants
ADD COLUMN role TEXT DEFAULT 'สมาชิก';
-- 2. สร้าง participant_meeting table
CREATE TABLE IF NOT EXISTS participant_meeting (
    participant_meeting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id INTEGER NOT NULL,
    meeting_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_started',
    checked_at TEXT,
    FOREIGN KEY (participant_id) REFERENCES participants(participant_id),
    FOREIGN KEY (meeting_id) REFERENCES meetings(meeting_id)
);
-- 3. สร้าง indexes เพื่อเพิ่มประสิทธิภาพ
CREATE INDEX IF NOT EXISTS idx_participant_meeting_meeting ON participant_meeting(meeting_id);
CREATE INDEX IF NOT EXISTS idx_participant_meeting_participant ON participant_meeting(participant_id);
CREATE INDEX IF NOT EXISTS idx_participant_meeting_status ON participant_meeting(status);
-- 4. อัพเดท existing participants ให้มี role (ถ้า role เป็น NULL)
UPDATE participants
SET role = 'สมาชิก'
WHERE role IS NULL;