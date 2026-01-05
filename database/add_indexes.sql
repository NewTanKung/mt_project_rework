-- Database schema migration: Add indexes for better query performance
-- Run this script to add missing indexes
-- Index for voice_file queries by meeting_id
CREATE INDEX IF NOT EXISTS idx_voice_meeting ON voice_file(meeting_id);
-- Index for voice_file queries by person_id
CREATE INDEX IF NOT EXISTS idx_voice_person ON voice_file(person_id);
-- Index for text_file queries by meeting_id
CREATE INDEX IF NOT EXISTS idx_text_meeting ON text_file(meeting_id);
-- Index for text_file queries by voice_id (for joining)
CREATE INDEX IF NOT EXISTS idx_text_voice ON text_file(voice_id);
-- Index for text_file queries by person_id
CREATE INDEX IF NOT EXISTS idx_text_person ON text_file(person_id);
-- Index for transcription_jobs queries by meeting_id
CREATE INDEX IF NOT EXISTS idx_jobs_meeting ON transcription_jobs(meeting_id);
-- Index for transcription_jobs queries by status (for active job checks)
CREATE INDEX IF NOT EXISTS idx_jobs_status ON transcription_jobs(status);
-- Composite index for preset_member queries
CREATE INDEX IF NOT EXISTS idx_preset_member_preset ON preset_member(preset_id);
CREATE INDEX IF NOT EXISTS idx_preset_member_user ON preset_member(user_id);