"""
Main WebView Desktop Application Runner.
Hosts Flask in an in-process server thread and launches PyWebView.
"""
import sys
import time
import logging
import threading
import requests
import webview
from werkzeug.serving import make_server
from app import create_app
from config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG
from services.device_service import clear_all_devices
from services.recording import stop_all_active_recordings

logger = logging.getLogger(__name__)


class ServerThread(threading.Thread):
    """Runs Werkzeug WSGI server inside a background thread."""
    def __init__(self, app, host: str, port: int):
        super().__init__(name="FlaskServerThread", daemon=True)
        self.host = host
        self.port = port
        self.server = make_server(host, port, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        logger.info("Starting WSGI server on %s:%d", self.host, self.port)
        self.server.serve_forever()

    def shutdown(self):
        logger.info("Shutting down WSGI server...")
        self.server.shutdown()


def wait_for_server(host: str, port: int, timeout: int = 15) -> bool:
    """Wait until the HTTP server is responsive."""
    url = f"http://{host}:{port}/"
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(url, timeout=1.0)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    """Main application entry point."""
    print("=" * 50)
    print("  Meeting Recorder Desktop Application")
    print("=" * 50)

    app = create_app()
    server = ServerThread(app, FLASK_HOST, FLASK_PORT)
    server.start()

    print(f"[*] Starting server on http://{FLASK_HOST}:{FLASK_PORT}...")
    if not wait_for_server(FLASK_HOST, FLASK_PORT):
        print("ERROR: Server failed to start within timeout.")
        server.shutdown()
        sys.exit(1)

    print("[+] Server ready! Launching application window...")

    window = webview.create_window(
        title='บันทึกการประชุม',
        url=f'http://{FLASK_HOST}:{FLASK_PORT}',
        width=1280,
        height=800,
        resizable=True,
        fullscreen=False
    )

    try:
        webview.start(debug=FLASK_DEBUG)
    except KeyboardInterrupt:
        print("\n[!] Application interrupted by user")
    finally:
        print("[*] Cleaning up application resources...")
        try:
            stop_all_active_recordings()
        except Exception as e:
            logger.error("Error stopping recordings: %s", e)

        try:
            clear_all_devices()
        except Exception as e:
            logger.error("Error clearing devices: %s", e)

        server.shutdown()
        print("[+] Application closed cleanly.")


if __name__ == '__main__':
    main()
