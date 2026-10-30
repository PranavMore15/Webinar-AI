"""
Administrative Console Routes for WebinarAI.
Provides user management, global job lifecycle monitoring, and error inspection.
All endpoints protected server-side by @admin_required.
"""

from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for
from app.models import db, User, ProcessingJob, JobRecipient
from app.utils.auth import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/')
@admin_required
def root():
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """
    Administrative management console.
    Displays user accounts, global processing job queue, and error audit logs.
    """
    # Fetch all registered users
    users = User.query.order_by(User.created_at.desc()).all()
    
    # Fetch all processing jobs across all users
    jobs = ProcessingJob.query.order_by(ProcessingJob.created_at.desc()).all()

    # Calculate system metrics
    total_users = len(users)
    active_users = sum(1 for u in users if u.is_active)
    admin_users = sum(1 for u in users if u.role == 'admin')
    
    total_jobs = len(jobs)
    ready_jobs = sum(1 for j in jobs if j.overall_status in ('ready', 'pending'))
    completed_jobs = sum(1 for j in jobs if j.overall_status == 'completed')
    failed_jobs = sum(1 for j in jobs if j.overall_status == 'failed' or j.error_message)

    return render_template(
        'admin/dashboard.html',
        users=users,
        jobs=jobs,
        stats={
            'total_users': total_users,
            'active_users': active_users,
            'admin_users': admin_users,
            'total_jobs': total_jobs,
            'ready_jobs': ready_jobs,
            'completed_jobs': completed_jobs,
            'failed_jobs': failed_jobs
        }
    )

@admin_bp.route('/api/users/<int:user_id>/toggle-status', methods=['POST'])
@admin_required
def toggle_user_status(user_id):
    """
    Safely toggles an account between active and deactivated status.
    Protects against self-deactivation and deactivating the last active administrator.
    """
    current_admin_id = session.get('user_id')
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User account not found.'}), 404

    # Safeguard 1: Prevent self-deactivation
    if user.id == current_admin_id and user.is_active:
        return jsonify({
            'success': False,
            'message': 'Action rejected: You cannot deactivate your own currently active administrator account.'
        }), 400

    # Safeguard 2: Prevent deactivating the last active administrator
    if user.role == 'admin' and user.is_active:
        active_admins = User.query.filter_by(role='admin', is_active=True).count()
        if active_admins <= 1:
            return jsonify({
                'success': False,
                'message': 'Action rejected: Cannot deactivate the last active administrator account.'
            }), 400

    try:
        user.is_active = not user.is_active
        db.session.commit()
        status_label = "activated" if user.is_active else "deactivated"
        return jsonify({
            'success': True,
            'message': f"Account '{user.username}' has been successfully {status_label}.",
            'user_id': user.id,
            'is_active': user.is_active
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Failed to update user status: {str(e)}'}), 500

@admin_bp.route('/api/jobs/<int:job_id>/details', methods=['GET'])
@admin_required
def get_job_details(job_id):
    """
    Returns full diagnostic details and error records for an individual processing job.
    """
    job = db.session.get(ProcessingJob, job_id)
    if not job:
        return jsonify({'success': False, 'message': 'Job not found.'}), 404

    recipients = job.recipients.limit(100).all()
    recipient_list = [
        {
            'email': r.email,
            'student_name': r.student_name,
            'status': r.delivery_status,
            'attempts': r.attempt_count,
            'last_error': r.last_error
        }
        for r in recipients
    ]

    return jsonify({
        'success': True,
        'job': {
            'id': job.id,
            'owner_username': job.owner.username if job.owner else 'Unknown',
            'title': job.title,
            'input_type': job.input_type,
            'input_file_name': job.input_file_name,
            'input_file_path': job.input_file_path,
            'overall_status': job.overall_status,
            'transcript_status': job.transcript_status,
            'summary_status': job.summary_status,
            'pdf_status': job.pdf_status,
            'pdf_path': job.pdf_path,
            'pdf_ready': job.pdf_status == 'completed' and bool(job.pdf_path),
            'email_status': job.email_status,
            'total_recipients': job.total_recipients,
            'successful_emails': job.successful_emails,
            'failed_emails': job.failed_emails,
            'error_message': job.error_message,
            'created_at': job.created_at.strftime('%Y-%m-%d %H:%M:%S') if job.created_at else '',
            'recipients': recipient_list
        }
    }), 200
