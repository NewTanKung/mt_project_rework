"""
Database migration runner using PRAGMA user_version.
Executes versioned migrations (.sql or .py) with automatic backups.
"""
import os
import shutil
import sqlite3
import importlib.util
import logging
from datetime import datetime
from config import DATABASE_PATH, BASE_DIR

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), 'migrations')


def get_user_version(conn: sqlite3.Connection) -> int:
    """Get the current PRAGMA user_version of the database."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version")
    return cursor.fetchone()[0]


def set_user_version(conn: sqlite3.Connection, version: int):
    """Update the PRAGMA user_version."""
    conn.execute(f"PRAGMA user_version = {version}")


def backup_database(db_path: str) -> str | None:
    """Create a timestamped backup of the database before applying migrations."""
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        return None
        
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{db_path}.bak-{timestamp}"
    try:
        shutil.copy2(db_path, backup_path)
        logger.info(f"Database backed up to: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create database backup: {e}")
        raise RuntimeError(f"Database backup failed: {e}") from e


def load_migration_files() -> list[tuple[int, str, str]]:
    """
    Find and return sorted list of (version, filename, full_path) migrations.
    """
    if not os.path.exists(MIGRATIONS_DIR):
        return []
        
    migrations = []
    for filename in os.listdir(MIGRATIONS_DIR):
        if filename.endswith('.sql') or filename.endswith('.py'):
            prefix = filename.split('_')[0]
            if prefix.isdigit():
                version = int(prefix)
                full_path = os.path.join(MIGRATIONS_DIR, filename)
                migrations.append((version, filename, full_path))
                
    migrations.sort(key=lambda x: x[0])
    return migrations


def apply_migration(conn: sqlite3.Connection, version: int, filename: str, path: str):
    """Apply a single migration (.sql or .py)."""
    logger.info(f"Applying migration {version:03d}: {filename}...")
    
    conn.execute("BEGIN IMMEDIATE")
    try:
        if filename.endswith('.sql'):
            with open(path, 'r', encoding='utf-8') as f:
                sql = f.read()
            conn.executescript(sql)
        elif filename.endswith('.py'):
            # Load Python migration module dynamically
            spec = importlib.util.spec_from_file_location(f"migration_{version}", path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, 'apply'):
                    module.apply(conn)
                else:
                    raise AttributeError(f"Migration {filename} has no apply() function")
                    
        set_user_version(conn, version)
        conn.execute("COMMIT")
        logger.info(f"Successfully applied migration {version:03d}")
    except Exception as e:
        conn.execute("ROLLBACK")
        logger.error(f"Error applying migration {filename}: {e}")
        raise


def seed_default_admin(conn: sqlite3.Connection):
    """Seed default admin user if users table is empty."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    if count == 0:
        import bcrypt
        hashed = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ('admin', hashed, 'admin')
        )
        conn.commit()
        logger.info("Default admin user created: admin / admin123")


def migrate(db_path: str | None = None):
    """
    Main migration runner. Connects, handles legacy DB baseline detection,
    and applies all pending migrations in order.
    """
    target_db = db_path or DATABASE_PATH
    db_exists = os.path.exists(target_db) and os.path.getsize(target_db) > 0

    conn = sqlite3.connect(target_db, timeout=30.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    try:
        current_version = get_user_version(conn)

        # Baseline detection: if user_version is 0, check if tables already exist
        if current_version == 0:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            has_users = cursor.fetchone() is not None

            if has_users:
                # Existing database created before migration system: mark as baseline (version 1)
                logger.info(f"Existing database detected at {target_db}. Marking baseline as version 1.")
                set_user_version(conn, 1)
                current_version = 1
            else:
                logger.info(f"New database at {target_db}.")

        migrations = load_migration_files()
        pending = [m for m in migrations if m[0] > current_version]

        if pending and db_exists:
            backup_database(target_db)

        for version, filename, path in pending:
            apply_migration(conn, version, filename, path)

        # Ensure admin user exists
        seed_default_admin(conn)

        final_version = get_user_version(conn)
        logger.info(f"Database schema is up to date at version {final_version}.")
    finally:
        conn.close()


def init_db(db_path: str | None = None):
    """Initialize or upgrade database schema."""
    migrate(db_path)
