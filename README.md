# Meeting Recorder Desktop Application

แอปพลิเคชันเดสก์ท็อปสำหรับบันทึกเสียงและถอดเสียงการประชุมแบบ Multi-channel Offline 100% พัฒนาด้วย Python Flask, PyWebView, SQLite WAL Mode, sounddevice และ Faster-Whisper

---

## สถาปัตยกรรมระบบ (System Architecture)

- **UI & Presentation**: HTML5, Bootstrap 5 (Bundled Offline), Vanilla JS
- **Desktop Runtime**: PyWebView 5.x (In-process Werkzeug WSGI server daemon thread)
- **Application Server**: Python Flask Application Factory (`create_app`)
- **Database & Persistence**: SQLite with WAL (`journal_mode=WAL`), foreign keys enabled, thread-local connections for background workers, and automated versioned migration runner (`PRAGMA user_version`) with automated pre-migration backups.
- **Audio Pipeline**: Non-blocking `sounddevice` input streams with real-time speech activity detection (RMS) decoupled from disk I/O via asynchronous worker thread (`SegmentWriter`).
- **Speech-to-Text Engine**: Faster-Whisper 1.1.1 exclusively (CTranslate2 backend) with thread-safe singleton model cache and parallel segment transcription.
- **Exporters**: Multi-format transcription exporter (TXT, SRT, DOCX, PDF via ReportLab, JSON Summary).

---

## โครงสร้างโปรเจกต์ (Project Structure)

```text
mt_project_rework/
├── main.py                     # Entry point (PyWebView GUI & in-process Flask server)
├── app.py                      # Flask Application Factory & blueprint registration
├── config.py                   # Centralized application configuration & environment variables
├── .env.example                # Example environment variable file
├── requirements.txt            # Production runtime dependencies
├── requirements-dev.txt        # Development & testing dependencies
├── database.db                 # SQLite production database (ignored in git)
├── core/                       # Core infrastructure utilities
│   ├── auth.py                 # Session guards & role decorators (@login_required, @admin_required)
│   ├── errors.py               # Centralized API error handlers & JSON responses
│   ├── logging_setup.py        # Rotating log file configuration
│   └── paths.py                # Portable storage paths resolution & conversion
├── database/                   # Database engine & migrations
│   ├── db.py                   # Connection pooling, WAL setup, transaction context manager
│   ├── migrate.py              # Automated migration engine with pre-migration backups
│   └── migrations/             # Versioned SQL & Python migration scripts (001 - 004)
├── services/                   # Business logic layer
│   ├── auth_service.py         # Bcrypt authentication & user management
│   ├── storage_service.py      # Storage settings configuration
│   ├── channel_service.py      # Audio channel assignments & presets
│   ├── attendance_service.py   # Participant attendance tracking
│   ├── device_service.py       # Audio device detection & status
│   ├── meeting_service.py      # Meeting lifecycle & cascade cleanup
│   ├── recording/              # Multi-channel recording engine
│   │   ├── writer.py           # Background queue worker writing WAV files
│   │   ├── session.py          # Real-time recording session & VAD logic
│   │   └── registry.py         # Thread-safe recording session registry
│   ├── transcription/          # Speech-to-text pipeline
│   │   ├── engine.py           # Faster-Whisper singleton model cache
│   │   ├── models.py           # Whisper model definitions & download manager
│   │   ├── jobs.py             # Background transcription queue & worker
│   │   └── transcript.py       # Transcripts query, editing, search (XSS-safe), summary
│   └── exporters/              # Transcription export handlers
│       ├── common.py           # Export data loader & safe filename sanitizer
│       ├── txt.py              # Plain text export
│       ├── srt.py              # SubRip subtitle export
│       ├── docx.py             # Microsoft Word export
│       ├── pdf.py              # PDF export with Thai font support
│       └── json_export.py      # Full JSON meeting summary export
├── api/                        # REST API blueprints
│   ├── auth_routes.py          # Login, logout, session status
│   ├── admin_routes.py         # Devices, channels, presets, users, models, storage APIs
│   ├── user_routes.py          # Meetings CRUD, recording, transcription, search, downloads
│   └── attendance_routes.py    # Attendance initialization, status updates, summaries
├── templates/                  # Jinja2 HTML templates
│   ├── admin/                  # Admin dashboard pages
│   └── user/                   # User meeting management pages
├── static/                     # Static assets (CSS, JS, fonts)
├── storage/                    # Default local storage directory
│   ├── audio/                  # Meeting audio recordings (.wav)
│   ├── transcriptions/         # Generated transcription text files
│   ├── exports/                # Exported reports (PDF, DOCX, TXT, SRT, JSON)
│   └── models/                 # Downloaded Faster-Whisper models
└── tests/                      # Automated test suite (Pytest)
    ├── conftest.py             # Isolated fixtures (app, client, admin_client, user_client)
    ├── test_auth.py            # Authentication & role guard tests
    ├── test_admin_api.py       # Admin device/channel/user/model API tests
    ├── test_meetings_api.py    # Meeting CRUD & presets tests
    ├── test_migrations.py      # Database migration & zero-data-loss tests
    ├── test_attendance_api.py  # Attendance lifecycle tests
    ├── test_recording.py       # Deadlock-free recording & segment writer tests
    ├── test_transcription.py   # Model registry, XSS-safe search, and transcription jobs
    └── test_exports.py         # Multi-format exports (TXT, SRT, DOCX, PDF, JSON)
```

---

## การติดตั้งและการเริ่มใช้งาน (Installation & Setup)

### 1. ความต้องการของระบบ (Prerequisites)
- **ระบบปฏิบัติการ**: Windows 10 / 11, macOS หรือ Linux
- **Python**: เวอร์ชัน 3.10 ขึ้นไป (แนะนำ Python 3.11)

### 2. สร้าง Virtual Environment
```bash
# Clone repository และเข้าสู่โฟลเดอร์
cd mt_project_rework

# สร้าง virtual environment
python -m venv .venv

# เปิดใช้งาน virtual environment
# บน Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# บน Windows (Command Prompt):
.\.venv\Scripts\activate.bat
# บน Linux/macOS:
source .venv/bin/activate
```

### 3. ติดตั้ง Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt

# สำหรับนักพัฒนา (รันเทสท์):
pip install -r requirements-dev.txt
```

### 4. กำหนดค่าคอนฟิก (Configuration)
คัดลอกไฟล์ `.env.example` เป็น `.env` (หากต้องการปรับแต่ง):
```bash
copy .env.example .env
```
หากไม่มีการระบุ `SECRET_KEY` ระบบจะสร้างคีย์ที่ปลอดภัยให้อัตโนมัติในโฟลเดอร์ `instance/secret_key`

---

## การเรียกใช้งาน (Running the Application)

### 1. รันโหมด Desktop Application (แนะนำ)
เปิดโปรแกรมในหน้าต่าง Desktop GUI ผ่าน PyWebView:
```bash
python main.py
```

### 2. รันโหมด Web Server เท่านั้น (สำหรับทดสอบผ่านเบราว์เซอร์)
```bash
python main.py --no-gui
# หรือ
python app.py
```
จากนั้นเปิดเบราว์เซอร์และเข้าไปที่ `http://127.0.0.1:5000`

---

## ข้อมูลเข้าสู่ระบบเริ่มต้น (Default Credentials)

เมื่อเริ่มต้นใช้งานฐานข้อมูลครั้งแรก ระบบจะสร้างผู้ดูแลระบบเริ่มต้นให้อัตโนมัติ:
- **Username**: `admin`
- **Password**: `admin123`
- **Role**: `admin`

*(แนะนำให้เปลี่ยนรหัสผ่านทันทีหลังจากการติดตั้งผ่านเมนู Admin > จัดการผู้ใช้)*

---

## การทดสอบระบบ (Automated Testing)

โปรเจกต์มีชุด Automated Tests ครอบคลุมทุกฟังก์ชันหลัก 100% (27/27 tests passed):

```bash
# รันเทสท์ทั้งหมด
pytest -v

# รันพร้อมวัด Code Coverage
pytest --cov=. tests/
```

### รายการทดสอบหลัก:
1. **Migrations & Data Preservation**: ทดสอบ Migration Engine ตั้งแต่เวอร์ชันเริ่มต้น ตรวจสอบ PRAGMA user_version และยืนยัน Zero Data Loss กับข้อมูลฐานข้อมูลเดิม
2. **Authentication & Session Guards**: ทดสอบการล็อกอิน, การเข้ารหัสผ่าน bcrypt, session state, และการป้องกันสิทธิ์ Endpoint ระดับ Admin
3. **Admin APIs**: ทดสอบ CRUD ของ Audio Devices, Channels, Presets, Users, และ Whisper Models
4. **Meetings & Presets APIs**: ทดสอบการสร้าง แก้ไข ลบการประชุม และการทำ Cascade Delete ของไฟล์ที่เกี่ยวข้อง
5. **Attendance APIs**: ทดสอบการเช็คชื่อผู้เข้าร่วมการประชุม สรุปสถิติ (present, late, absent, not_started)
6. **Recording Pipeline**: ทดสอบการทำงานของ `SegmentWriter` แยก thread, การบันทึกไฟล์ WAV, และยืนยันว่า `RecordingSession.stop()` **ไม่เกิด Deadlock** เมื่อมีข้อมูลเสียงค้างใน buffer
7. **Transcription System**: ทดสอบ Faster-Whisper Model Cache, ป้องกันงานซ้ำซ้อน (Duplicate Prevention), และป้องกันการโจมตีผ่าน Search (XSS HTML escaping)
8. **Export System**: ทดสอบการส่งออกรายงานครบ 5 รูปแบบ (TXT, SRT, DOCX, PDF, JSON) และตรวจสอบ endpoint `/download_json`

---

## ฟีเจอร์ที่ได้รับการแก้ไขปรับปรุง (Key Refactoring Highlights)

1. **Deadlock-Free Recording**: แยกการเขียนไฟล์และฐานข้อมูลออกจาก Thread Audio Callback ของ PortAudio โดยใช้ `queue.Queue` และ background `SegmentWriter`
2. **Zero-Copy RMS**: คำนวณความดังเสียงแบบเรียลไทม์โดยไม่มี Memory Overhead
3. **Unified Faster-Whisper Pipeline**: เปลี่ยนมาใช้ Faster-Whisper (CTranslate2) 1.1.1 ล้วน และตัด dependencies ที่ขัดแย้งกันออก
4. **Automated SQLite Migrations**: ระบบรัน Migration อัตโนมัติพร้อมสำรองฐานข้อมูลก่อนรันทุกครั้ง (`.bak-<timestamp>`)
5. **Portable Path Management**: บันทึกเส้นทางไฟล์ในฐานข้อมูลเป็น Relative Path (`storage/...`) ป้องกันปัญหาไฟล์หลุดเมื่อย้าย Drive หรือย้ายโฟลเดอร์
6. **JSON Summary Download Route**: เพิ่ม Endpoint `/api/user/meetings/<id>/download_json` เพื่อรองรับปุ่มดาวน์โหลด JSON บนหน้าเว็บจัดการประชุม
7. **XSS Protection in Search**: ค้นหาข้อความถอดเสียงพร้อมไฮไลท์ `<mark>` อย่างปลอดภัยด้วยการ escape HTML
8. **Secure Embedded Server**: รัน Flask ผ่าน in-process `werkzeug.serving.make_server` ใน background thread แทนการ spawn subprocess

---

## สิทธิ์การใช้งาน (License)

MIT License
