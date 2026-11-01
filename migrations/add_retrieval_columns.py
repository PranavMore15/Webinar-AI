"""
Database Migration Script: Add Retrieval Columns to ProcessingJob (Prompt A6).

Adds columns:
- source_type VARCHAR(50) DEFAULT 'manual'
- source_url VARCHAR(1000) NULL
- retrieval_status VARCHAR(50) DEFAULT 'completed'
- retrieval_error TEXT NULL
"""

import sys
import os
import logging

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models import db
from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def run_migration():
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        if not inspector.has_table('processing_jobs'):
            logger.info("Table 'processing_jobs' does not exist yet. Running db.create_all().")
            db.create_all()
            logger.info("Tables created successfully.")
            return

        columns = [col['name'] for col in inspector.get_columns('processing_jobs')]
        logger.info("Existing columns in 'processing_jobs': %s", columns)

        alter_statements = []
        if 'source_type' not in columns:
            alter_statements.append("ALTER TABLE processing_jobs ADD COLUMN source_type VARCHAR(50) DEFAULT 'manual'")
        if 'source_url' not in columns:
            alter_statements.append("ALTER TABLE processing_jobs ADD COLUMN source_url VARCHAR(1000) NULL")
        if 'retrieval_status' not in columns:
            alter_statements.append("ALTER TABLE processing_jobs ADD COLUMN retrieval_status VARCHAR(50) DEFAULT 'completed'")
        if 'retrieval_error' not in columns:
            alter_statements.append("ALTER TABLE processing_jobs ADD COLUMN retrieval_error TEXT NULL")

        if not alter_statements:
            logger.info("All retrieval columns already exist in 'processing_jobs'. No migration needed.")
            return

        for stmt in alter_statements:
            logger.info("Executing: %s", stmt)
            db.session.execute(text(stmt))
        db.session.commit()
        logger.info("Migration completed successfully.")


if __name__ == '__main__':
    run_migration()

