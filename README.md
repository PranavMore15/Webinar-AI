# WebinarAI: AI-Powered Webinar Summarization & Knowledge Distribution Platform

WebinarAI is a post-webinar knowledge distribution platform built for educational and enterprise environments. It allows authenticated users to process webinar recordings or transcripts, extract AI-generated summaries and engineering takeaways using Google Gemini, compile professional PDF briefs using ReportLab, and distribute them to student recipient lists via SMTP.

---

## Current Status: Admin Workspace Separation & Manual Recipient Entry Phase Completed

- **Strict Role Separation & Workspace Access Control:**
  - Administrators are strictly forbidden from accessing the processing workspace (`/dashboard`) and all workspace processing APIs (403 Forbidden / redirect to `/admin/dashboard`).
  - Removed "Workspace" navigation and action buttons from the administrator console and base navbar.
  - Regular users access the processing workspace and are denied access to the admin console.
- **Manual Recipient Entry in Section B:**
  - Added tabbed interface in Section B supporting both CSV spreadsheet uploads and manual individual email entry.
  - Real-time format validation and case-insensitive deduplication across both manual entries and CSV uploads.
  - Active recipient list with individual row removal/deletion buttons and "Clear All" action.
  - Transactional persistence in MySQL inserting both manual and CSV recipients into `JobRecipient`.
- **Role-Based Access Control & User Management:**
  - Distinct `admin` and `user` roles with default `user` role assignment for newly registered accounts.
  - Public user registration with comprehensive server-side input validation (`/register`).
  - Dual login modes for Standard Users and System Administrators (`/login` and `/admin/login`).
  - Server-side authorization decorators (`@user_required`, `@admin_required`) preventing privilege escalation.
  - Dedicated Administrator Console (`/admin/dashboard`) displaying registered accounts, account activation/deactivation controls, global job queue, and error diagnostic logs.
  - Security safeguards preventing administrators from deactivating themselves or deactivating the last active administrator.
- **UI Cleanup & Professional Branding:**
  - Complete removal of prototype/stage labels, evaluator notices, and hardcoded demonstrator credentials.
  - Unified professional Bootstrap 5 branding across all views with responsive navigation and account role pills.
- **Database Architecture & Additive Migration:**
  - MySQL Community Server schema `webinar_ai_db` on `localhost:3306` with InnoDB tables (`users`, `processing_jobs`, `job_recipients`).
  - Additive, non-destructive migration CLI in `init_db.py` preserving existing admin credentials and job histories.
  - Salted `scrypt` cryptographic password hashing; zero plaintext password exposure.
  - Cascading deletion guarantees and unique recipient constraints (`uq_job_recipient_email`).
- **Media Upload Pipeline & CSV Validation Engine:**
  - Mutually exclusive MP4 video and TXT/VTT transcript selection with backend content verification (`ftyp` box check for MP4, decodeability and cue headers for transcripts).
  - Safe, collision-resistant storage under `storage/uploads/` with UUID prefixes and path-traversal prevention.
  - Server-side CSV validation engine with 5-column statistical breakdown and tabbed preview.
  - Independent upload order support (webinar first or CSV first).
  - Transactional job persistence in MySQL creating `ProcessingJob` and bulk-inserting `JobRecipient` records.
- **Media & Audio Processing Pipeline:**
  - Safe parsing and normalization of `.txt` and WebVTT (`.vtt`) transcripts, stripping headers, timestamps, and cue IDs while preserving speaker labels.
  - Transcript uploads **strictly bypass** FFmpeg audio extraction and Whisper transcription.
  - Audio extraction from MP4 video via FFmpeg into **16kHz 16-bit mono WAV** (Whisper-native format) in `storage/audio/`.
  - Audio chunking support for long recordings (> 10 minutes).
  - Local speech-to-text transcription powered by OpenAI Whisper (`base` model running on CPU, configurable).
  - Automatic cleanup of temporary audio files upon pipeline completion.

---

## Prerequisites

- **Python:** 3.10+ (Verified on Python 3.13.16 64-bit)
- **FFmpeg & FFprobe:** Installed and verified in system PATH (`C:\Apps\ffmpeg\bin\ffmpeg.exe`)
- **MySQL Server:** Community Server running at `127.0.0.1:3306` with schema `webinar_ai_db`
- **Whisper Checkpoint:** Cached locally at `~/.cache/whisper/base.pt` (~142 MB)

---

## Setup and Launch Instructions

### 1. Create and Activate Virtual Environment

Open a PowerShell terminal in `c:\WebinarAI`:

```powershell
# Create Python virtual environment (if not already created)
python -m venv .venv

# Activate virtual environment on Windows
.\.venv\Scripts\Activate.ps1
```

> **Note on PowerShell Execution Policy:** If you receive a script execution error when running `Activate.ps1`, run:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> .\.venv\Scripts\Activate.ps1
> ```

---

### 2. Install Python Dependencies

```powershell
pip install -r requirements.txt
```

---

### 3. Database Initialization & Additive Migration (Idempotent)

```powershell
# Inspect database pre-flight
python init_db.py --inspect

# Run safe schema migration
python init_db.py --migrate
```

---

### 4. Launch the Application

```powershell
python run.py
```

The server will start on:
👉 **`http://127.0.0.1:5000`**

- **User Sign In / Registration:** Visit `http://127.0.0.1:5000/login` or `http://127.0.0.1:5000/register`
- **Admin Console Sign In:** Visit `http://127.0.0.1:5000/login?type=admin` or click "Admin Login" on the login screen
- **Administrator Dashboard:** Once logged in as admin, navigate to `http://127.0.0.1:5000/admin/dashboard`

---

### 5. Running Automated Tests

To run the complete automated test suite (99 tests across all 7 test modules):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

---

## Project Structure

```text
WebinarAI/
├── .env                      # Local environment configuration (database, admin credentials)
├── .env.example              # Environment configuration template
├── .gitignore                # Git exclusions
├── PROJECT_SPEC.md           # Master project specification
├── PROJECT_STATUS.md         # Living project status and test audit
├── README.md                 # Setup & running instructions
├── requirements.txt          # Python dependencies
├── run.py                    # Application launcher
├── init_db.py                # Database migration and admin provisioning CLI
├── app/
│   ├── __init__.py           # Flask app factory
│   ├── config.py             # Configuration (storage folders, size limits, FFmpeg & Whisper settings)
│   ├── models/
│   │   ├── __init__.py
│   │   └── schema.py         # SQLAlchemy models (User with role & is_active, ProcessingJob, JobRecipient)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth_routes.py    # Registration, user login, admin login, session routes
│   │   ├── admin_routes.py   # Admin console, user status toggling, diagnostics
│   │   └── dashboard_routes.py # Processing workspace, /api/upload-webinar, /api/upload-csv, /api/submit-job
│   ├── services/
│   │   ├── __init__.py
│   │   ├── csv_service.py    # CSV validation & email deduplication engine
│   │   ├── media_service.py  # MP4/TXT/VTT validation, safe storage, and cleanup
│   │   ├── transcript_service.py # TXT and WebVTT parsing & speaker normalization
│   │   ├── audio_service.py  # FFmpeg audio extraction, duration probe & chunking
│   │   └── transcription_service.py # Local CPU Whisper transcription and chunk stitching
│   ├── utils/
│   │   ├── __init__.py
│   │   └── auth.py           # Role-based decorators (@login_required, @admin_required) and validators
│   ├── static/
│   │   ├── css/style.css     # Custom dashboard styling
│   │   └── js/dashboard.js   # Dynamic frontend logic & AJAX upload handler
│   └── templates/
│       ├── base.html         # Bootstrap 5 base layout with role navigation
│       ├── login.html        # Authentication view with User/Admin toggle
│       ├── register.html     # User registration form
│       ├── dashboard.html    # Full processing workspace
│       └── admin/
│           └── dashboard.html # Administrator console (user management, global job audit)
├── sample_data/              # Test files for demonstration
│   ├── sample_students.csv   # Mixed CSV (valid, duplicates, malformed, blank)
│   ├── sample_missing_email_column.csv # Rejected CSV missing email header
│   ├── sample_webinar.txt    # Sample TXT transcript
│   └── sample_webinar.vtt    # Sample WebVTT transcript with speaker tags
├── storage/                  # Controlled local storage directories
│   ├── uploads/              # Validated MP4, TXT, VTT uploads (UUID-prefixed)
│   ├── audio/                # Extracted 16kHz mono WAV audio tracks
│   └── pdfs/                 # Generated PDF knowledge briefs
└── tests/
    ├── test_prompt1_foundation.py     # Foundation & route tests (6 tests)
    ├── test_csv_validation.py         # CSV validation test suite (15 tests)
    ├── test_database_models_offline.py# Offline SQLAlchemy model unit tests (7 tests)
    ├── test_media_upload_pipeline.py  # Media upload & job persistence tests (25 tests)
    ├── test_media_audio_processing.py # Audio extraction & Whisper transcription (19 tests)
    ├── test_role_based_auth.py        # Registration, login, roles, admin safeguards, manual recipients (31 tests)
    └── test_mysql_live.py             # Live MySQL integration tests on localhost:3306 (6 tests)
```
