"""
Database connection and utilities manager
"""
import sqlite3
import os
from flask import g
from config import DATABASE_PATH, SCHEMA_PATH


def get_db():
    """Get database connection for current request"""
    if 'db' not in g:
        g.db = sqlite3.connect(
            DATABASE_PATH,
            timeout=30.0,  # Increase timeout to 30 seconds
            isolation_level=None  # Autocommit mode to reduce locks
        )
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    """
    Close database connection
    Called at the end of each request
    """
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """
    Initialize database from schema.sql
    Only creates tables if database doesn't exist
    """
    db_exists = os.path.exists(DATABASE_PATH)
    
    if not db_exists:
        print("[*] Database not found. Creating new database...")
        db = sqlite3.connect(DATABASE_PATH)
        
        # Read schema.sql
        with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
            schema = f.read()
        
        # Execute schema
        db.executescript(schema)
        db.commit()
        
        # Create default admin user with bcrypt hash
        from services.auth_service import hash_password
        admin_password = hash_password('admin123')
        db.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ('admin', admin_password, 'admin')
        )
        db.commit()
        db.close()
        
        print("[+] Database created successfully!")
        print("    Default admin user: admin / admin123")
    else:
        print("[+] Database found. Using existing database.")


def execute_query(query, params=None, fetch_one=False, fetch_all=False, commit=False):
    """
    Execute a database query with retry logic for locked database
    
    Args:
        query: SQL query string
        params: Query parameters (optional)
        fetch_one: Return single row (optional)
        fetch_all: Return all rows (optional)
        commit: Commit transaction (optional)
    
    Returns:
        Query result or last row ID
    """
    import time
    max_retries = 3
    retry_delay = 0.1  # 100ms
    
    for attempt in range(max_retries):
        db = None # Initialize db to None for the finally block
        try:
            db = get_db()
            cursor = db.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if commit:
                db.commit()
                return cursor.lastrowid
            
            if fetch_one:
                return cursor.fetchone()
            
            if fetch_all:
                return cursor.fetchall()
            
            return None # No fetch, no commit, return None
                
        except sqlite3.OperationalError as e:
            if 'database is locked' in str(e) and attempt < max_retries - 1:
                print(f"[DB] Database locked, retrying... (attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
                continue
            else:
                # If it's a lock error on the last attempt, or another OperationalError, re-raise
                raise
        except Exception as e:
            # Catch any other exception, rollback if commit was intended
            if commit and db: # Ensure db is not None before rollback
                db.rollback()
            raise
    # This part should ideally not be reached if max_retries is exhausted and an error occurred
    # or if a successful return happened. It's a fallback in case the loop finishes without return.
    return None


def dict_from_row(row):
    """
    Convert sqlite3.Row to dictionary
    """
    if row is None:
        return None
    return dict(row)


def list_from_rows(rows):
    """
    Convert list of sqlite3.Row to list of dictionaries
    """
    return [dict(row) for row in rows]
