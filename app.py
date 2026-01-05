"""
Flask Application Entry Point
"""
from flask import Flask, render_template, session, redirect, url_for
from database import init_db, close_db
from api.auth_routes import auth_bp
from api.admin_routes import admin_bp
from api.user_routes import user_bp
from api.attendance_routes import attendance_bp
import config


def create_app():
    """
    Create and configure Flask application
    """
    app = Flask(__name__)
    app.config['SECRET_KEY'] = config.SECRET_KEY
    
    # Initialize database
    with app.app_context():
        init_db()
    
    # Register teardown
    app.teardown_appcontext(close_db)
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(attendance_bp)
    
    # Root route
    @app.route('/')
    def index():
        if 'user_id' in session:
            # Redirect based on role
            if session['role'] == 'admin':
                return redirect('/admin/devices')
            else:
                return redirect('/user/register')
        return redirect('/login')
    
    # Login page
    @app.route('/login')
    def login_page():
        if 'user_id' in session:
            return redirect('/')
        return render_template('login.html')
    
    # Admin routes
    @app.route('/admin/<page>')
    def admin_page(page):
        if 'user_id' not in session or session['role'] != 'admin':
            return redirect('/login')
        
        # Valid admin pages
        valid_pages = ['devices', 'channels', 'storage', 'users', 'models']
        if page not in valid_pages:
            return redirect('/admin/devices')
        
        return render_template(f'admin/{page}.html')
    
    # User routes
    @app.route('/user/<page>')
    def user_page(page):
        if 'user_id' not in session:
            return redirect('/login')
        
        # Valid user pages
        valid_pages = ['register', 'recording', 'manage']
        if page not in valid_pages:
            return redirect('/user/register')
        
        return render_template(f'user/{page}.html')
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=True
    )
