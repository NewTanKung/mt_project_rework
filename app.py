"""
Flask Application Entry Point.
"""
from flask import Flask, render_template, session, redirect
import config
from core import setup_logging, register_error_handlers, page_login_required
from database import close_db, migrate
from api.auth_routes import auth_bp
from api.admin_routes import admin_bp
from api.user_routes import user_bp
from api.attendance_routes import attendance_bp
from services.transcription import recover_stale_jobs


def create_app(config_overrides: dict | None = None) -> Flask:
    """
    Create and configure Flask application instance.
    """
    app = Flask(__name__, instance_path=config.INSTANCE_DIR)
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['DATABASE_PATH'] = config.DATABASE_PATH
    
    if config_overrides:
        app.config.update(config_overrides)

    # Initialize logging and storage directories
    setup_logging()
    config.ensure_storage_dirs()

    # Run database migrations and recover stale jobs
    with app.app_context():
        migrate(app.config['DATABASE_PATH'])
        recover_stale_jobs()

    # Teardown database request connection
    app.teardown_appcontext(close_db)

    # Register API blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(attendance_bp)

    # Register centralized error handlers
    register_error_handlers(app)

    # Root route
    @app.route('/')
    def index():
        if 'user_id' in session:
            if session.get('role') == 'admin':
                return redirect('/admin/devices')
            return redirect('/user/register')
        return redirect('/login')

    # Login page
    @app.route('/login')
    def login_page():
        if 'user_id' in session:
            return redirect('/')
        return render_template('login.html')

    # Admin pages
    @app.route('/admin/<page>')
    @page_login_required(role='admin')
    def admin_page(page):
        valid_pages = ['devices', 'channels', 'storage', 'users', 'models']
        if page not in valid_pages:
            return redirect('/admin/devices')
        return render_template(f'admin/{page}.html')

    # User pages
    @app.route('/user/<page>')
    @page_login_required()
    def user_page(page):
        valid_pages = ['register', 'recording', 'manage']
        if page not in valid_pages:
            return redirect('/user/register')
        return render_template(f'user/{page}.html')

    return app


if __name__ == '__main__':
    application = create_app()
    application.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG
    )
