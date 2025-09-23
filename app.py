#!/usr/bin/env python3
"""
Main application factory for Devall CMS
"""

import os
from flask import Flask, session
import secrets
from cms.db import init_db, close_connection, APP_SECRET, PUB_DIR
from cms.auth import bp as auth_bp, login_required
from cms.views.pages import bp as pages_bp
from cms.views.templates_ import bp as templates_bp
from cms.views.users import bp as users_bp
from cms.views.settings import bp as settings_bp
from cms.views.help import bp as help_bp
from cms.views.filemanager import bp as files_bp
from cms.views.media import bp as media_bp

def create_app():
    """Application factory"""
    app = Flask(__name__, template_folder='cms/templates')

    # Configuration
    app.config['SECRET_KEY'] = APP_SECRET
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    # Initialize database
    with app.app_context():
        init_db()

    # Register teardown
    app.teardown_appcontext(close_connection)

    # CSRF token setup
    @app.before_request
    def ensure_csrf_token():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(16)

    @app.context_processor
    def inject_csrf_token():
        return {'csrf_token': session.get('csrf_token', '')}
    
    @app.context_processor
    def inject_base_url():
        """Inject base_url into all templates"""
        from cms.db import get_db
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', ('base_url',))
            base_url_row = cursor.fetchone()
            base_url = base_url_row['value'] if base_url_row else 'http://localhost:5000'
            return {'base_url': base_url}
        except:
            return {'base_url': 'http://localhost:5000'}

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp, url_prefix='/admin')
    app.register_blueprint(templates_bp, url_prefix='/admin')
    app.register_blueprint(users_bp, url_prefix='/admin')
    app.register_blueprint(settings_bp, url_prefix='/admin')
    app.register_blueprint(help_bp, url_prefix='/admin')
    app.register_blueprint(files_bp, url_prefix='/admin')
    app.register_blueprint(media_bp, url_prefix='/admin')

    # Root route - redirect to login or dashboard
    @app.route('/')
    def index():
        from flask import redirect, url_for, session
        if 'user_id' in session:
            return redirect(url_for('dashboard'))
        return redirect(url_for('auth.login'))

    # Dashboard route
    @app.route('/admin')
    @login_required
    def dashboard():
        from flask import render_template
        from cms.db import get_db

        db = get_db()
        cursor = db.cursor()

        # Get counts
        cursor.execute('SELECT COUNT(*) FROM pages')
        pages_count = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM templates')
        templates_count = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM users')
        users_count = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM pages WHERE published = 1')
        published_count = cursor.fetchone()[0]

        return render_template('dashboard.html',
                             pages_count=pages_count,
                             templates_count=templates_count,
                             users_count=users_count,
                             published_count=published_count)

    # Serve generated files in /pub for previews and media thumbnails
    from flask import send_from_directory

    @app.route('/pub/<path:filename>')
    def serve_pub(filename):
        return send_from_directory(PUB_DIR, filename)

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=4400)
