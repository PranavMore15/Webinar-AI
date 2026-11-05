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
- **Google OAuth & APIs:** `google-auth`, `google-auth-oauthlib`, and `google-api-python-client` (included in `requirements.txt`)

---

## Setup and Launch Instructions

### 1. Create and Activate Virtual Environment

Open a PowerShell terminal in `c:\WebinarAI` (or your project directory):

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

This installs all core framework packages, database connectors, AI engines, and Google OAuth libraries (`google-auth`, `google-auth-oauthlib`, and `google-api-python-client`).

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

Always ensure your virtual environment is active before starting the server:

```powershell
# If using the active virtual environment:
python run.py

# Or run directly via virtual environment python:
.\.venv\Scripts\python.exe run.py
```

The server will start on:
👉 **`http://127.0.0.1:5000`**

- **User Sign In / Registration:** Visit `http://127.0.0.1:5000/login` or `http://127.0.0.1:5000/register`
- **Admin Console Sign In:** Visit `http://127.0.0.1:5000/login?type=admin` or click "Admin Login" on the login screen
- **Administrator Dashboard:** Once logged in as admin, navigate to `http://127.0.0.1:5000/admin/dashboard`

---

### 5. Running Automated Tests

To run the complete automated test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

---

## Feature: Automated Webinar Video Retrieval & Processing

WebinarAI supports multi-source webinar media retrieval, eliminating manual downloads:
1. **Direct Video/Audio Links**:
   - Downloads MP4 video or MP3/WAV/M4A audio directly over HTTP/HTTPS.
   - Protected by server-side **SSRF defenses** (`app/utils/ssrf.py`): DNS resolution checks, private IP blocking (RFC 1918, RFC 3927), link-local & cloud metadata rejection (`169.254.169.254`), approved port restrictions (80, 443, 8080, 8443), redirect re-validation, and streaming chunk-level byte counting (`MAX_VIDEO_SIZE` 250 MB).
   - Validates binary container magic signatures (`ftyp` box for MP4/M4A, ID3/MPEG frame sync for MP3, RIFF/WAVE for WAV) and rejects HTML error pages disguised as `.mp4`.
2. **Local Computer File & Folder Selection**:
   - Browser-authorized file picker and folder selector (`webkitdirectory`).
   - Discovers supported media files inside selected folders, displaying an interactive file inspector.
   - User explicitly selects the target recording (never silently uploading entire directory trees).
3. **Google Drive Integration**:
   - Connects user Google accounts via official Google OAuth 2.0 (`drive.readonly` scope) with CSRF state verification.
   - Requires `google-auth-oauthlib`, `google-api-python-client`, and `google-auth` installed via `requirements.txt`.
   - Requires `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` configured in `.env`.
   - Queries metadata via official Google Drive API v3.
   - Enforces download permission verification (`canDownload`), rate limit handling, and streams media directly into the processing pipeline.
   - Provides safe account disconnection endpoint (`/api/sources/gdrive/disconnect`).
4. **YouTube Compliance & Official Caption Integration**:
   - Validates YouTube video URLs across `watch?v=`, `youtu.be/`, and `/shorts/` formats.
   - Inspects video metadata and official caption tracks via official YouTube Data API v3.
   - When permitted captions are available, ingests the WebVTT transcript directly into the summarization pipeline without downloading video streams.
   - **Strict Non-Bypass Guardrails**: Unauthorized video downloading, stream scraping, or bypass tools (`yt-dlp`, `youtube-dl`) are strictly rejected. If captions are unavailable, users are clearly guided to manual upload.
5. **Direct Audio Pipeline Routing**:
   - Audio recordings (MP3, WAV, M4A) bypass video extraction and feed directly to Whisper transcription.
6. **Preserved Manual Uploads**:
   - Manual MP4 video, TXT transcript, and WebVTT transcript uploads remain fully functional.

---

## Configuration Variables (.env)

```env
# Flask Core
FLASK_APP=run.py
FLASK_ENV=development
SECRET_KEY=your-secure-secret-key

# Database (MySQL)
DATABASE_URI=mysql+pymysql://root:password@localhost:3306/webinar_ai_db

# Gemini AI Summarization
GEMINI_API_KEY=your-gemini-api-key

# SMTP Distribution
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=True
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=your_email@gmail.com

# Google Drive OAuth 2.0 (Prompt A4)
GOOGLE_CLIENT_ID=your-google-oauth-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-oauth-client-secret

# YouTube Data API v3 (Prompt A5)
YOUTUBE_API_KEY=your-youtube-data-api-key
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
├── migrations/
│   └── add_retrieval_columns.py # Schema migration for automated retrieval columns
├── app/
│   ├── __init__.py           # Flask app factory
│   ├── config.py             # Configuration (storage folders, size limits, FFmpeg & Whisper settings)
│   ├── models/
│   │   ├── __init__.py
│   │   └── schema.py         # SQLAlchemy models (User, ProcessingJob with retrieval columns, JobRecipient)
│   ├── providers/            # Content retrieval providers (Prompt A2-A5)
│   │   ├── __init__.py
│   │   ├── base.py           # BaseRetrievalProvider abstract interface
│   │   ├── direct_provider.py # Direct media retrieval with container verification
│   │   ├── local_provider.py # Local computer file and folder discovery provider
│   │   ├── gdrive_provider.py# Google Drive API v3 official provider
│   │   └── youtube_provider.py# YouTube Data API v3 official caption provider
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth_routes.py    # Registration, user login, admin login, Google OAuth routes
│   │   ├── admin_routes.py   # Admin console, user status toggling, diagnostics
│   │   └── dashboard_routes.py # Processing workspace, content source endpoints, submit-job
│   ├── services/
│   │   ├── __init__.py
│   │   ├── csv_service.py    # CSV validation & email deduplication engine
│   │   ├── media_service.py  # MP4/TXT/VTT validation, safe storage, and cleanup
│   │   ├── transcript_service.py # Audio/video transcript routing & speaker normalization
│   │   ├── audio_service.py  # FFmpeg audio extraction & chunking
│   │   ├── transcription_service.py # Local CPU Whisper transcription
│   │   ├── gemini_service.py # AI summarization engine
│   │   ├── pdf_service.py    # ReportLab PDF compilation
│   │   ├── email_service.py  # SMTP email distribution
│   │   └── pipeline_service.py # Asynchronous job pipeline orchestration & idempotency guards
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── auth.py           # Role-based decorators and validators
│   │   └── ssrf.py           # SSRF defense engine (DNS, IP ranges, redirect safety)
│   ├── static/
│   │   ├── css/style.css     # Custom dashboard styling
│   │   └── js/dashboard.js   # Dynamic frontend logic & source selectors
│   └── templates/
│       ├── base.html         # Bootstrap 5 base layout with role navigation
│       ├── login.html        # Authentication view
│       ├── register.html     # User registration form
│       ├── dashboard.html    # Processing workspace with 6 Webinar Content Sources
│       └── admin/
│           └── dashboard.html # Administrator console
├── storage/                  # Controlled local storage directories
│   ├── uploads/              # Staged recordings and transcripts (UUID-prefixed)
│   ├── audio/                # Extracted 16kHz mono WAV audio tracks
│   └── pdfs/                 # Generated PDF knowledge briefs
└── tests/
    ├── test_prompt1_foundation.py     # Foundation & route tests (6 tests)
    ├── test_csv_validation.py         # CSV validation test suite (15 tests)
    ├── test_database_models_offline.py# Offline SQLAlchemy model unit tests (7 tests)
    ├── test_media_upload_pipeline.py  # Media upload & job persistence tests (25 tests)
    ├── test_media_audio_processing.py # Audio extraction & Whisper transcription (19 tests)
    ├── test_gemini_summarization.py   # Gemini AI summarization tests (17 tests)
    ├── test_pdf_generation.py         # ReportLab PDF generation tests (16 tests)
    ├── test_email_delivery.py         # SMTP email delivery tests (26 tests)
    ├── test_role_based_auth.py        # Registration, login, roles, admin safeguards (31 tests)
    ├── test_pipeline_and_status.py    # Pipeline execution & status polling tests (5 tests)
    ├── test_mysql_live.py             # Live MySQL integration tests on localhost:3306 (6 tests)
    ├── test_source_selection_ui.py    # Source selector UI & accessibility check tests (14 tests)
    ├── test_direct_media_retrieval.py # Direct media retrieval & SSRF protection tests (15 tests)
    ├── test_local_selection.py        # Local file & folder selection tests (15 tests)
    ├── test_gdrive_integration.py     # Google Drive OAuth & API retrieval tests (16 tests)
    ├── test_youtube_integration.py    # YouTube Data API & caption tests (11 tests)
    └── test_pipeline_integration_a6.py# Schema, failure isolation & idempotency tests (5 tests)
```
