"""
WebinarAI Database Initialization & Migration Tool
Handles pre-flight inspection, safe schema creation, table initialization,
and secure administrator provisioning.
"""

import os
import sys
import argparse
import getpass
import secrets
import pymysql
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

EXPECTED_TABLES = {'users', 'processing_jobs', 'job_recipients'}

def get_mysql_connection(use_database=False):
    """Establishes raw connection to MySQL server using .env credentials."""
    host = os.getenv('DB_HOST', 'localhost')
    port = int(os.getenv('DB_PORT', 3306))
    user = os.getenv('DB_USER', 'root')
    password = os.getenv('DB_PASSWORD', '')
    database = os.getenv('DB_NAME', 'webinar_ai_db') if use_database else None

    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def inspect_database_preflight():
    """
    Safely inspects the MySQL server before making any changes:
    1. Checks if schema exists.
    2. If existing, inspects existing tables.
    3. Halts on unexpected foreign tables.
    """
    db_name = os.getenv('DB_NAME', 'webinar_ai_db')
    print(f"\n[Pre-Flight] Connecting to MySQL server to inspect schema '{db_name}'...")
    
    conn = get_mysql_connection(use_database=False)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s",
                (db_name,)
            )
            schema_row = cursor.fetchone()

            if not schema_row:
                print(f"[Pre-Flight] Status: Target schema '{db_name}' does NOT exist yet. (Clean initial state)")
                return {'schema_exists': False, 'existing_tables': set()}

            print(f"[Pre-Flight] Status: Target schema '{db_name}' ALREADY EXISTS.")
            
            # Inspect tables in existing schema
            cursor.execute(
                "SELECT TABLE_NAME, TABLE_ROWS FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s",
                (db_name,)
            )
            tables = cursor.fetchall()
            existing_tables = {t['TABLE_NAME']: t['TABLE_ROWS'] for t in tables}

            if existing_tables:
                print(f"[Pre-Flight] Found {len(existing_tables)} existing table(s):")
                for tbl, rows in existing_tables.items():
                    print(f"  - {tbl} (~{rows or 0} rows)")

                # Check for unexpected foreign tables
                foreign_tables = set(existing_tables.keys()) - EXPECTED_TABLES
                if foreign_tables:
                    raise RuntimeError(
                        f"SAFETY ALERT: Schema '{db_name}' contains unexpected table(s): {foreign_tables}. "
                        f"Aborting migration to prevent modifying unrelated data."
                    )
            else:
                print(f"[Pre-Flight] Schema '{db_name}' exists but contains no tables.")

            return {'schema_exists': True, 'existing_tables': existing_tables}
    finally:
        conn.close()

def migrate_schema_and_tables():
    """Executes safe, idempotent schema and table creation."""
    db_name = os.getenv('DB_NAME', 'webinar_ai_db')
    inspection = inspect_database_preflight()

    conn = get_mysql_connection(use_database=False)
    try:
        with conn.cursor() as cursor:
            if not inspection['schema_exists']:
                print(f"[Migration] Creating schema '{db_name}' with utf8mb4 character set...")
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
                print(f"[Migration] Schema '{db_name}' created successfully.")
            else:
                print(f"[Migration] Reusing existing schema '{db_name}'.")
    finally:
        conn.close()

    # Create tables using SQLAlchemy models (idempotent CREATE TABLE IF NOT EXISTS)
    print("[Migration] Verifying and creating required tables (users, processing_jobs, job_recipients)...")
    from app import create_app
    from app.models import db, User
    app = create_app()
    with app.app_context():
        db.create_all()

    # Additive column migration for users table
    conn = get_mysql_connection(use_database=True)
    try:
        with conn.cursor() as cursor:
            # Check existing columns in users
            cursor.execute("""
                SELECT COLUMN_NAME 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users'
            """, (db_name,))
            cols = {r['COLUMN_NAME'] for r in cursor.fetchall()}

            if 'role' not in cols:
                print("[Migration] Adding column 'role' to table 'users'...")
                cursor.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user' AFTER password_hash")
                print("[Migration] Column 'role' added successfully.")
            else:
                print("[Migration] Column 'role' already exists in 'users'.")

            if 'is_active' not in cols:
                print("[Migration] Adding column 'is_active' to table 'users'...")
                cursor.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE AFTER role")
                print("[Migration] Column 'is_active' added successfully.")
            else:
                print("[Migration] Column 'is_active' already exists in 'users'.")

            # Assign configured admin the 'admin' role
            admin_user = os.getenv('ADMIN_USERNAME', 'admin')
            cursor.execute("UPDATE users SET role = 'admin', is_active = TRUE WHERE username = %s", (admin_user,))
            conn.commit()
            print(f"[Migration] Verified administrator '{admin_user}' has role='admin' and is_active=TRUE.")
    finally:
        conn.close()

    print("[Migration] All database tables and columns verified successfully.")

def provision_admin_user(username=None, password=None, email=None):
    """
    Safely provisions an authorized user with salted scrypt password hashing and admin role.
    Supports command arguments, environment variables, or interactive prompt.
    """
    from app import create_app
    from app.models import db, User
    app = create_app()

    username = username or os.getenv('ADMIN_USERNAME')
    password = password or os.getenv('ADMIN_PASSWORD')

    # If in interactive terminal and credentials not passed
    if not username and sys.stdin.isatty():
        username = input("Enter admin username: ").strip()
    elif not username:
        username = "admin"

    if not password and sys.stdin.isatty():
        password = getpass.getpass("Enter secure admin password: ")
        confirm = getpass.getpass("Confirm secure admin password: ")
        if password != confirm:
            print("Error: Passwords do not match.")
            return False
    elif not password:
        # Generate cryptographically secure random password
        password = secrets.token_urlsafe(16)
        # Store in .env without printing plaintext password
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        with open(env_path, 'a') as f:
            f.write(f"\n# Auto-generated initial admin credentials\nADMIN_USERNAME={username}\nADMIN_PASSWORD={password}\n")
        print(f"[Auth] Generated secure credentials and saved to local .env (ADMIN_USERNAME={username}).")

    with app.app_context():
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            existing_user.set_password(password)
            existing_user.role = 'admin'
            existing_user.is_active = True
            if email:
                existing_user.email = email
            db.session.commit()
            print(f"[Auth] Updated password and set role='admin' for existing authorized user '{username}'.")
            return True
        else:
            new_user = User(username=username, email=email, role='admin', is_active=True)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            print(f"[Auth] Authorized administrator '{username}' created with salted scrypt hash and role='admin'.")
            return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="WebinarAI Database Tool")
    parser.add_argument('--inspect', action='store_true', help="Perform read-only pre-flight schema inspection")
    parser.add_argument('--migrate', action='store_true', help="Execute safe schema and table creation")
    parser.add_argument('--create-admin', action='store_true', help="Provision an authorized administrator user")
    parser.add_argument('--username', help="Admin username")
    parser.add_argument('--password', help="Admin password")
    parser.add_argument('--email', help="Admin email (optional)")
    args = parser.parse_args()

    if args.inspect:
        inspect_database_preflight()
    elif args.migrate:
        migrate_schema_and_tables()
    elif args.create_admin:
        provision_admin_user(username=args.username, password=args.password, email=args.email)
    else:
        parser.print_help()
