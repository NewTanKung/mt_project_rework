-- Migration 001: Baseline schema (matches existing SQLite database structure)

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    role TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audio_devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    device_index INTEGER NOT NULL,
    max_input_channels INTEGER NOT NULL,
    host_api TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_connected' CHECK(status IN ('ready', 'disabled', 'not_connected'))
);

CREATE TABLE IF NOT EXISTS audio_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    device_name TEXT,
    device_index INTEGER,
    channel_index INTEGER,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS channel_preset (
    channel_preset_id INTEGER PRIMARY KEY,
    preset_name TEXT NOT NULL,
    show INTEGER
);

CREATE TABLE IF NOT EXISTS meetings (
    meeting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_name TEXT NOT NULL,
    description TEXT,
    meeting_location TEXT,
    channel_preset_id INTEGER,
    meeting_date TEXT,
    start_time TEXT,
    end_time TEXT,
    totaltime TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS participants (
    participant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_name TEXT,
    role TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS participant_meeting (
    participant_meeting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    participant_id INTEGER NOT NULL,
    meeting_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'not_started'
);

CREATE TABLE IF NOT EXISTS preset_member (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preset_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    channel_id INTEGER
);

CREATE TABLE IF NOT EXISTS voice_file (
    voice_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    start_time TEXT,
    end_time TEXT,
    person_id INTEGER,
    meeting_id INTEGER,
    voice BLOB,
    file_path TEXT,
    file_size INTEGER,
    duration REAL
);

CREATE TABLE IF NOT EXISTS text_file (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    voice_id INTEGER,
    name TEXT,
    person_id INTEGER,
    meeting_id INTEGER,
    content TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    model_used TEXT,
    language TEXT DEFAULT 'th',
    confidence REAL
);

CREATE TABLE IF NOT EXISTS storage_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT NOT NULL UNIQUE,
    setting_value TEXT
);

CREATE TABLE IF NOT EXISTS transcription_jobs (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    model_used TEXT,
    language TEXT DEFAULT 'th',
    progress INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    files_created TEXT
);
