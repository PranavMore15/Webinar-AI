from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

def utc_now():
    return datetime.now(timezone.utc)

class User(db.Model):
    """Authorized operator and system administrator accounts."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user', nullable=False)  # 'admin' or 'user'
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    # Relationships
    jobs = db.relationship('ProcessingJob', backref='owner', cascade='all, delete-orphan', lazy='dynamic')

    def __init__(self, username: str = '', email: str = '', role: str = 'user', is_active: bool = True, password_hash: str = '', **kwargs):
        super().__init__(**kwargs)
        if username:
            self.username = username
        if email:
            self.email = email
        self.role = role
        self.is_active = is_active
        if password_hash:
            self.password_hash = password_hash

    def set_password(self, password: str):
        """Generates salted cryptographic hash of password."""
        self.password_hash = generate_password_hash(password, method='scrypt')

    def check_password(self, password: str) -> bool:
        """Verifies plaintext candidate password against stored hash."""
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'job_count': self.jobs.count() if hasattr(self.jobs, 'count') else len(self.jobs)
        }

    def __repr__(self):
        return f"<User id={self.id} username='{self.username}' role='{self.role}'>"


class ProcessingJob(db.Model):
    """Processing job lifecycle, media metadata, and delivery audit."""
    __tablename__ = 'processing_jobs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Input metadata
    title = db.Column(db.String(255), nullable=True)
    input_type = db.Column(db.String(20), nullable=False)  # 'video', 'audio', or 'transcript'
    input_file_name = db.Column(db.String(255), nullable=False)
    input_file_path = db.Column(db.String(500), nullable=False)

    # Automated Retrieval metadata (Prompt A6)
    source_type = db.Column(db.String(50), default='manual', nullable=True)  # 'manual', 'direct', 'youtube', 'gdrive', 'local_file', 'local_folder'
    source_url = db.Column(db.String(1000), nullable=True)
    retrieval_status = db.Column(db.String(50), default='completed', nullable=True)  # 'pending', 'retrieving', 'completed', 'failed'
    retrieval_error = db.Column(db.Text, nullable=True)

    # Stage statuses (discrete milestones)
    transcript_status = db.Column(db.String(50), default='pending', nullable=False)
    summary_status = db.Column(db.String(50), default='pending', nullable=False)
    pdf_status = db.Column(db.String(50), default='pending', nullable=False)
    pdf_path = db.Column(db.String(500), nullable=True)
    email_status = db.Column(db.String(50), default='pending', nullable=False)
    overall_status = db.Column(db.String(50), default='ready', nullable=False, index=True)

    # Recipient totals
    total_recipients = db.Column(db.Integer, default=0, nullable=False)
    successful_emails = db.Column(db.Integer, default=0, nullable=False)
    failed_emails = db.Column(db.Integer, default=0, nullable=False)

    # Error details & timestamps
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    recipients = db.relationship('JobRecipient', backref='job', cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self):
        return f"<ProcessingJob id={self.id} status='{self.overall_status}' input='{self.input_file_name}'>"


class JobRecipient(db.Model):
    """Per-student recipient delivery record for a specific processing job."""
    __tablename__ = 'job_recipients'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    job_id = db.Column(db.Integer, db.ForeignKey('processing_jobs.id', ondelete='CASCADE'), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False)
    student_name = db.Column(db.String(255), nullable=True)
    delivery_status = db.Column(db.String(30), default='pending', nullable=False, index=True)  # 'pending', 'sent', 'failed'
    attempt_count = db.Column(db.Integer, default=0, nullable=False)
    last_error = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('job_id', 'email', name='uq_job_recipient_email'),
    )

    def __repr__(self):
        return f"<JobRecipient id={self.id} job_id={self.job_id} email='{self.email}' status='{self.delivery_status}'>"
