"""
Main WebView Runner
Starts Flask server in subprocess and opens PyWebView window
"""
import webview
import subprocess
import sys
import time
import requests
import os
from config import FLASK_HOST, FLASK_PORT


def is_flask_running():
    """
    Check if Flask server is running
    """
    try:
        response = requests.get(f'http://{FLASK_HOST}:{FLASK_PORT}/', timeout=2)
        # Flask is running if we get any response (200, 302, 404, etc.)
        return True
    except requests.exceptions.RequestException:
        return False


def start_flask():
    """
    Start Flask server in subprocess
    """
    # Get Python executable
    python_exe = sys.executable
    
    # Start Flask app (don't redirect output so we can see logs)
    flask_process = subprocess.Popen(
        [python_exe, 'app.py'],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    
    # Wait for Flask to be ready
    print("[*] Starting Flask server...")
    max_wait = 30  # seconds
    waited = 0
    
    while waited < max_wait:
        if is_flask_running():
            print("[+] Flask server is ready!")
            return flask_process
        
        # Check if process died
        if flask_process.poll() is not None:
            print("[!] Flask process terminated unexpectedly")
            return None
        
        time.sleep(1)
        waited += 1
        if waited % 5 == 0:
            print(f"   Waiting... ({waited}s)")
    
    print("[!] Flask server failed to start (timeout)")
    flask_process.terminate()
    return None


def main():
    """
    Main entry point
    """
    print("=" * 50)
    print("  Meeting Recorder Desktop Application")
    print("=" * 50)
    
    # Start Flask server
    flask_process = start_flask()
    
    if flask_process is None:
        print("ERROR: Could not start Flask server")
        sys.exit(1)
    
    # Create PyWebView window
    print("[*] Opening application window...")
    
    window = webview.create_window(
        title='บันทึกการประชุม',
        url=f'http://{FLASK_HOST}:{FLASK_PORT}',
        width=1280,
        height=800,
        resizable=True,
        fullscreen=False,
    )
    
    # Start WebView (blocking)
    try:
        webview.start(debug=True)
    except KeyboardInterrupt:
        print("\n[!] Application interrupted by user")
    finally:
        # Cleanup: clear devices and terminate Flask process
        print("[*] Cleaning up...")
        
        # Clear all devices from database
        try:
            from services.device_service import clear_all_devices
            clear_all_devices()
        except Exception as e:
            print(f"[!] Error clearing devices: {e}")
        
        flask_process.terminate()
        flask_process.wait()
        print("[+] Application closed successfully")


if __name__ == '__main__':
    main()
