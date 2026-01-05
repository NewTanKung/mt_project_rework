# Meeting Recorder Desktop Application

โปรแกรมบันทึกและถอดเสียงการประชุมแบบ Offline 100%

## Tech Stack
- **UI**: HTML + Bootstrap (Offline)
- **Backend**: Python Flask
- **Database**: SQLite
- **Desktop**: PyWebView
- **Audio**: sounddevice
- **Transcription**: Whisper / Faster-Whisper (offline)
- **PDF Export**: reportlab

## การติดตั้ง

### 1. สร้าง Virtual Environment
```bash
python -m venv venv
venv\Scripts\activate  # Windows
```

### 2. ติดตั้ง Dependencies
```bash
pip install -r requirements.txt
```

### 3. ดาวน์โหลด Bootstrap (Offline)
```bash
# Bootstrap CSS
curl -o static/css/bootstrap.min.css https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css

# Bootstrap JS
curl -o static/js/bootstrap.bundle.min.js https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js
```

หรือดาวน์โหลดจาก https://getbootstrap.com/docs/5.3/getting-started/download/

## การรัน

### รันแบบ Desktop Application (แนะนำ)
```bash
python main.py
```

### รันแบบ Web Server (สำหรับทดสอบ)
```bash
python app.py
```
จากนั้นเปิดเบราว์เซอร์ที่ http://127.0.0.1:5000

## ผู้ใช้เริ่มต้น
- **Username**: admin
- **Password**: admin
- **Role**: admin

## โครงสร้างโปรเจกต์
```
meeting_recorder/
├── main.py                 # WebView runner
├── app.py                  # Flask application
├── config.py               # Configuration
├── schema.sql              # Database schema
├── requirements.txt        # Dependencies
├── database/               # Database utilities
├── services/               # Business logic
├── api/                    # API routes
├── templates/              # HTML templates
├── static/                 # CSS, JS, images
└── storage/                # Audio, transcriptions, exports, models
```

## Features

### Admin (5 หน้า)
1. **อุปกรณ์**: ค้นหาและจัดการอุปกรณ์เสียง
2. **เชื่อมต่อ**: กำหนด Channel Mapping
3. **จัดเก็บ**: กำหนด path สำหรับเก็บไฟล์
4. **ผู้ใช้**: จัดการผู้ใช้งาน
5. **โมเดล**: ดาวน์โหลดและจัดการโมเดล Whisper

### User (3 หน้า)
1. **ลงทะเบียนการประชุม**: สร้างการประชุมและกำหนดผู้เข้าร่วม
2. **การประชุม**: บันทึกเสียงแบบ real-time
3. **จัดการประชุม**: ถอดเสียงและ export PDF

## License
MIT
