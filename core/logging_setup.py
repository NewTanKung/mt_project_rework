"""
Logging configuration with console output and rotating file handler.
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from config import LOG_DIR, LOG_FILE

def setup_logging(level=logging.INFO):
    """Set up application logging."""
    os.makedirs(LOG_DIR, exist_ok=True)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Avoid duplicate handlers if called multiple times
    if root_logger.handlers:
        return
        
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)
    
    # Rotating file handler (2MB per file, keeping up to 5 backups)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root_logger.addHandler(file_handler)
    
    # Lower noise from external libraries
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
