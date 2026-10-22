"""
Error handling definitions and Flask error handlers.
"""
import logging
from flask import jsonify, request

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Custom exception for API errors that return JSON responses."""
    def __init__(self, message: str, status_code: int = 400, payload: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}


def register_error_handlers(app):
    """Register application-wide error handlers."""
    
    @app.errorhandler(ApiError)
    def handle_api_error(error):
        response_data = {
            'success': False,
            'message': error.message,
            **error.payload
        }
        return jsonify(response_data), error.status_code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        # Handle all uncaught errors on API routes as JSON
        if request.path.startswith('/api/'):
            logger.exception("Unexpected API error on %s %s: %s", request.method, request.path, error)
            return jsonify({
                'success': False,
                'message': f"Internal Server Error: {str(error)}"
            }), 500
            
        # Re-raise or let default handler handle web pages
        raise error
