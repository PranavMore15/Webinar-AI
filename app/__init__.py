import os
from flask import Flask
from app.config import Config

def create_app(config_class=Config):
    """Application factory for WebinarAI."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure required storage directories exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['AUDIO_FOLDER'], exist_ok=True)
    os.makedirs(app.config['PDF_FOLDER'], exist_ok=True)
    if 'SUMMARY_FOLDER' in app.config:
        os.makedirs(app.config['SUMMARY_FOLDER'], exist_ok=True)

    # Initialize extensions
    from app.models import db
    db.init_app(app)

    # Register Blueprints
    from app.routes.auth_routes import auth_bp
    from app.routes.dashboard_routes import dashboard_bp
    from app.routes.admin_routes import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)

    from flask import request, jsonify

    @app.errorhandler(500)
    def handle_500(e):
        if request.path.startswith('/api/'):
            return jsonify({
                'success': False,
                'status': 'error',
                'accessibility_status': 'Server Error',
                'message': 'An internal server error occurred while processing the request.'
            }), 500
        return e

    return app
