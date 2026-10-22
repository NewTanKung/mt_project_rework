"""
Path utilities for normalizing and resolving storage paths.
Ensures paths stored in the database are portable across machines.
"""
import os
from pathlib import Path
from config import BASE_DIR

def to_storage_path(path: str | None) -> str | None:
    """
    Convert an absolute path within BASE_DIR to a relative path with forward slashes.
    Paths outside BASE_DIR are preserved as absolute paths.
    """
    if not path:
        return path
        
    try:
        norm_path = os.path.abspath(path)
        norm_base = os.path.abspath(BASE_DIR)
        
        # Check if path is within BASE_DIR
        if norm_path.startswith(norm_base):
            rel = os.path.relpath(norm_path, norm_base)
            return rel.replace('\\', '/')
    except Exception:
        pass
        
    return path.replace('\\', '/')


def resolve_path(path: str | None) -> str | None:
    """
    Convert a relative path to an absolute path based on BASE_DIR.
    Absolute paths are returned unchanged (normalized).
    """
    if not path:
        return path
        
    # Check if already absolute
    if os.path.isabs(path):
        return os.path.normpath(path)
        
    # Relative path joined with BASE_DIR
    return os.path.normpath(os.path.join(BASE_DIR, path))
