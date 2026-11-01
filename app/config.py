import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

class Config:
    """Base configuration for WebinarAI."""
    SECRET_KEY = os.getenv('SECRET_KEY', 'webinar-ai-demo-secret-key-2026')
    DEBUG = os.getenv('FLASK_DEBUG', '1') == '1'
    PORT = int(os.getenv('PORT', 5000))
    
    # Upload storage limits and directories
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB maximum request size
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'storage', 'uploads')
    AUDIO_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'storage', 'audio')
    PDF_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'storage', 'pdfs')
    SUMMARY_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'storage', 'summaries')
    
    # Google Gemini AI Summarization Configuration
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash')

    # Google Drive OAuth 2.0 (Prompt A4)
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')

    # YouTube Data API v3 (Prompt A5)
    YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', '')
    
    # Allowed file extensions
    ALLOWED_VIDEO_EXTENSIONS = {'mp4'}
    ALLOWED_TRANSCRIPT_EXTENSIONS = {'txt', 'vtt'}
    ALLOWED_CSV_EXTENSIONS = {'csv'}
    MAX_CSV_SIZE = 10 * 1024 * 1024  # 10MB maximum CSV file size
    MAX_TRANSCRIPT_SIZE = 10 * 1024 * 1024  # 10MB maximum transcript file size
    MAX_VIDEO_SIZE = 250 * 1024 * 1024  # 250MB maximum MP4 video size

    # FFmpeg and Audio Processing Configuration
    FFMPEG_PATH = os.getenv('FFMPEG_PATH', r'C:\Apps\ffmpeg\bin\ffmpeg.exe' if os.path.exists(r'C:\Apps\ffmpeg\bin\ffmpeg.exe') else 'ffmpeg')
    FFPROBE_PATH = os.getenv('FFPROBE_PATH', r'C:\Apps\ffmpeg\bin\ffprobe.exe' if os.path.exists(r'C:\Apps\ffmpeg\bin\ffprobe.exe') else 'ffprobe')
    AUDIO_CHUNK_SECONDS = int(os.getenv('AUDIO_CHUNK_SECONDS', 600))  # 10-minute audio chunk limit

    # Whisper Speech-to-Text Configuration
    WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'base')  # Default lightweight base model
    WHISPER_DEVICE = os.getenv('WHISPER_DEVICE', 'cpu')  # Run on CPU for local development

    # Database Configuration (MySQL Community Server)
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '3306')
    DB_NAME = os.getenv('DB_NAME', 'webinar_ai_db')
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')

    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
        if DB_PASSWORD or os.getenv('DB_USER') else 'sqlite:///' + os.path.join(os.path.dirname(os.path.dirname(__file__)), 'storage', 'webinar_ai_local.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', 3600)),
        'pool_pre_ping': True
    }

    # SMTP Email Delivery Configuration (Prompt 7)
    SMTP_HOST = os.getenv('SMTP_HOST', '')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', os.getenv('SMTP_USER', ''))
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'True').lower() in ('true', '1', 'yes')
    SMTP_USE_SSL = os.getenv('SMTP_USE_SSL', 'False').lower() in ('true', '1', 'yes')
    SMTP_FROM_EMAIL = os.getenv('SMTP_FROM_EMAIL', os.getenv('SMTP_SENDER_EMAIL', ''))
    SMTP_FROM_NAME = os.getenv('SMTP_FROM_NAME', 'WebinarAI Platform')
    SMTP_TIMEOUT = int(os.getenv('SMTP_TIMEOUT', 15))

class TestConfig(Config):
    """Isolated test configuration using SQLite in-memory to prevent touching MySQL during unit tests."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {}
    
    # Test SMTP Configuration (mocked offline)
    SMTP_HOST = 'localhost'
    SMTP_PORT = 1025
    SMTP_USERNAME = 'test@example.com'
    SMTP_PASSWORD = 'test_password'
    SMTP_USE_TLS = False
    SMTP_USE_SSL = False
    SMTP_FROM_EMAIL = 'noreply@webinarai.edu'
    SMTP_FROM_NAME = 'WebinarAI Test'
    SMTP_TIMEOUT = 5

