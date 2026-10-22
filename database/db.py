"""
Database connection manager and query helpers.
Uses SQLite WAL mode, thread-local connections for background threads,
and flask.g for request contexts.
"""
import sqlite3
import threading
from contextlib import contextmanager
from flask import has_app_context, g
from config import DATABASE_PATH

_thread_local = threading.local()


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Create and configure a new SQLite connection with WAL mode."""
    target_path = db_path or DATABASE_PATH
    conn = sqlite3.connect(
        target_path,
        timeout=30.0,
        isolation_level=None,  # Autocommit mode by default; transactions managed explicitly
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db(db_path: str | None = None) -> sqlite3.Connection:
    """
    Get database connection for current request context or current thread.
    """
    if has_app_context():
        if 'db' not in g or g.db is None:
            g.db = connect(db_path)
        return g.db
    else:
        # Background worker threads or standalone scripts
        conn = getattr(_thread_local, 'connection', None)
        if conn is None:
            conn = connect(db_path)
            _thread_local.connection = conn
        return conn


def close_db(e=None):
    """Close request-scoped database connection."""
    if has_app_context():
        db = g.pop('db', None)
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def close_thread_db():
    """Close thread-local database connection if any."""
    conn = getattr(_thread_local, 'connection', None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _thread_local.connection = None


@contextmanager
def transaction(db: sqlite3.Connection | None = None):
    """
    Context manager for atomic database transactions.
    Begins an IMMEDIATE transaction, commits on completion, or rolls back on error.
    """
    conn = db or get_db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def query_one(query: str, params: tuple | list = (), db: sqlite3.Connection | None = None) -> dict | None:
    """Execute a query and return a single row as a dictionary, or None."""
    conn = db or get_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    row = cursor.fetchone()
    return dict(row) if row is not None else None


def query_all(query: str, params: tuple | list = (), db: sqlite3.Connection | None = None) -> list[dict]:
    """Execute a query and return all matching rows as dictionaries."""
    conn = db or get_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    return [dict(r) for r in rows]


def execute(query: str, params: tuple | list = (), db: sqlite3.Connection | None = None) -> int:
    """Execute a DML/DDL query and return cursor.lastrowid."""
    conn = db or get_db()
    cursor = conn.cursor()
    cursor.execute(query, params)
    return cursor.lastrowid


def execute_many(query: str, seq_of_params: list | tuple, db: sqlite3.Connection | None = None):
    """Execute query across a sequence of parameters."""
    conn = db or get_db()
    cursor = conn.cursor()
    cursor.executemany(query, seq_of_params)


# Backward compatibility wrappers for existing code
def execute_query(query, params=None, fetch_one=False, fetch_all=False, commit=False):
    """Compatibility wrapper matching old db_manager.execute_query."""
    conn = get_db()
    cursor = conn.cursor()
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)

    if commit:
        # Autocommit isolation_level=None already commits DML
        return cursor.lastrowid

    if fetch_one:
        return cursor.fetchone()

    if fetch_all:
        return cursor.fetchall()

    return None


def dict_from_row(row):
    """Compatibility converter."""
    if row is None:
        return None
    return dict(row)


def list_from_rows(rows):
    """Compatibility converter."""
    return [dict(r) for r in rows]
