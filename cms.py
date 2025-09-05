#!/usr/bin/env python3
"""
Devall CMS - One-file Flask-based CMS
A simple CMS with admin interface, user management, templates, and static page generation.
"""

import os
import sqlite3
import hashlib
import secrets
from datetime import datetime
from flask import Flask, request, redirect, url_for, render_template_string, flash, session, g
from functools import wraps
import json

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Database configuration
DATABASE = 'cms.db'

# Create pub directory if it doesn't exist
if not os.path.exists('pub'):
    os.makedirs('pub')

# Database connection helper
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Password hashing
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(password, hashed):
    return hash_password(password) == hashed

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Initialize database
def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT,
                role TEXT DEFAULT 'admin',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active BOOLEAN DEFAULT 1
            )
        ''')

        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Templates table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL, -- 'system' or 'content'
                content TEXT,
                is_default BOOLEAN DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Pages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                published BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Page templates table (many-to-many with custom content)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS page_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id INTEGER NOT NULL,
                template_id INTEGER NOT NULL,
                custom_content TEXT,
                use_default BOOLEAN DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (page_id) REFERENCES pages (id) ON DELETE CASCADE,
                FOREIGN KEY (template_id) REFERENCES templates (id) ON DELETE CASCADE
            )
        ''')

        # Insert default admin user if not exists
        cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('admin',))
        if cursor.fetchone()[0] == 0:
            cursor.execute('INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)',
                         ('admin', hash_password('admin123'), 'admin@devall.com'))

        # Insert default settings
        default_settings = [
            ('site_name', 'Devall CMS', 'Site name displayed in admin'),
            ('site_description', 'A simple Flask CMS', 'Site description'),
            ('admin_theme', 'light', 'Admin theme (light/dark)'),
            ('hide_system_blocks', '1', 'Hide system template blocks by default in page editor'),
        ]
        for key, value, desc in default_settings:
            cursor.execute('INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)',
                         (key, value, desc))

        # Insert default template blocks
        default_templates = [
            ('Base Header', 'base_header', 'system', '''<!DOCTYPE html>
<html lang="en">
<head>''', 1, 1),
            ('Meta Tags', 'meta', 'system', '''    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="A simple Flask CMS">
    <title>Devall CMS</title>''', 1, 2),
            ('Header Close', 'header_close', 'system', '''</head>
<body>''', 1, 3),
            ('Hero Section', 'hero', 'content', '''    <section class="hero bg-primary text-white py-5">
        <div class="container">
            <div class="row">
                <div class="col-lg-8 mx-auto text-center">
                    <h1 class="display-4">Welcome to Our Site</h1>
                    <p class="lead">Discover amazing content and features</p>
                    <a href="#content" class="btn btn-light btn-lg mt-3">Get Started</a>
                </div>
            </div>
        </div>
    </section>''', 1, 4),
            ('Navigation Menu', 'menu', 'content', '''    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="#">Devall CMS</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item"><a class="nav-link" href="#">Home</a></li>
                    <li class="nav-item"><a class="nav-link" href="#">About</a></li>
                    <li class="nav-item"><a class="nav-link" href="#">Services</a></li>
                    <li class="nav-item"><a class="nav-link" href="#">Contact</a></li>
                </ul>
            </div>
        </div>
    </nav>''', 1, 5),
            ('Content Section', 'section', 'content', '''    <section id="content" class="py-5 bg-light">
        <div class="container">
            <div class="row">
                <div class="col-lg-10 mx-auto">
                    <h2 class="mb-4">Main Content</h2>
                    <div class="content-wrapper">
                        <p>This is the main content section. You can edit this content in the page editor.</p>
                        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</p>
                    </div>
                </div>
            </div>
        </div>
    </section>''', 1, 6),
            ('Paragraph', 'paragraph', 'content', '''    <div class="mb-4">
        <p>This is a sample paragraph. You can edit this content in the page editor to customize your website.</p>
    </div>''', 1, 7),
            ('Footer', 'footer', 'system', '''    <footer class="bg-dark text-white py-4">
        <div class="container text-center">
            <p>&copy; 2024 Devall CMS. All rights reserved.</p>
        </div>
    </footer>

    <!-- Bootstrap JavaScript -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>''', 1, 8),
        ]

        for title, slug, category, content, is_default, sort_order in default_templates:
            cursor.execute('INSERT OR IGNORE INTO templates (title, slug, category, content, is_default, sort_order) VALUES (?, ?, ?, ?, ?, ?)',
                         (title, slug, category, content, is_default, sort_order))

        db.commit()

# HTML Templates
ADMIN_LAYOUT = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% if title %}{{ title }} - {% endif %}Devall CMS Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar { min-height: calc(100vh - 56px); }
        .template-block { border: 1px solid #dee2e6; border-radius: 0.375rem; margin-bottom: 1rem; }
        .template-block-header { background-color: #f8f9fa; padding: 0.75rem 1rem; border-bottom: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center; }
        .sort-buttons { display: flex; gap: 0.25rem; }
        .use-default-checkbox { margin-right: 0.5rem; }
        .grayed-textarea { background-color: #f8f9fa !important; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">Devall CMS</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('pages') }}">Pages</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('templates') }}">Templates</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('users') }}">Users</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="bi bi-person-circle"></i> {{ session.get('username', 'Admin') }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-menu-item" href="{{ url_for('logout') }}">Logout</a></li>
                        </ul>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show mt-3">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Template block sorting
        function moveBlock(blockId, direction) {
            const block = document.getElementById('block-' + blockId);
            const container = block.parentElement;

            if (direction === 'up') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock) {
                    container.insertBefore(block, prevBlock);
                }
            } else {
                const nextBlock = block.nextElementSibling;
                if (nextBlock) {
                    container.insertBefore(nextBlock, block);
                }
            }

            // Update sort order inputs
            updateSortOrder(container);
        }

        function updateSortOrder(container) {
            const blocks = container.querySelectorAll('[id^="block-"]');
            blocks.forEach((block, index) => {
                const sortInput = block.querySelector('input[name^="sort_order_"]');
                if (sortInput) {
                    sortInput.value = index;
                }
            });
        }

        // Toggle default content
        function toggleDefaultContent(checkbox, textareaId) {
            const textarea = document.getElementById(textareaId);
            if (checkbox.checked) {
                textarea.classList.add('grayed-textarea');
                textarea.readOnly = true;
                // Load default content
                const defaultContentId = textareaId.replace('template_', 'default_content_');
                const defaultContent = document.getElementById(defaultContentId);
                if (defaultContent) {
                    textarea.value = defaultContent.textContent;
                }
            } else {
                textarea.classList.remove('grayed-textarea');
                textarea.readOnly = false;
            }
        }

        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        });
    </script>
</body>
</html>
'''

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - Devall CMS Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar { min-height: calc(100vh - 56px); }
        .template-block { border: 1px solid #dee2e6; border-radius: 0.375rem; margin-bottom: 1rem; }
        .template-block-header { background-color: #f8f9fa; padding: 0.75rem 1rem; border-bottom: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center; }
        .sort-buttons { display: flex; gap: 0.25rem; }
        .use-default-checkbox { margin-right: 0.5rem; }
        .grayed-textarea { background-color: #f8f9fa !important; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="#">Devall CMS</a>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show mt-3">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                <div class="row justify-content-center mt-5">
                    <div class="col-md-6 col-lg-4">
                        <div class="card shadow">
                            <div class="card-header bg-primary text-white">
                                <h4 class="mb-0">Devall CMS Login</h4>
                            </div>
                            <div class="card-body">
                                <form method="post">
                                    <div class="mb-3">
                                        <label for="username" class="form-label">Username</label>
                                        <input type="text" class="form-control" id="username" name="username" required>
                                    </div>
                                    <div class="mb-3">
                                        <label for="password" class="form-label">Password</label>
                                        <input type="password" class="form-control" id="password" name="password" required>
                                    </div>
                                    <button type="submit" class="btn btn-primary w-100">Login</button>
                                </form>
                                <div class="mt-3 text-muted">
                                    <small>Default login: admin / admin123</small>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Template block sorting
        function moveBlock(blockId, direction) {
            const block = document.getElementById('block-' + blockId);
            const container = block.parentElement;

            if (direction === 'up') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock) {
                    container.insertBefore(block, prevBlock);
                }
            } else {
                const nextBlock = block.nextElementSibling;
                if (nextBlock) {
                    container.insertBefore(nextBlock, block);
                }
            }

            // Update sort order inputs
            updateSortOrder(container);
        }

        function updateSortOrder(container) {
            const blocks = container.querySelectorAll('[id^="block-"]');
            blocks.forEach((block, index) => {
                const sortInput = block.querySelector('input[name^="sort_order_"]');
                if (sortInput) {
                    sortInput.value = index;
                }
            });
        }

        // Toggle default content
        function toggleDefaultContent(checkbox, textareaId) {
            const textarea = document.getElementById(textareaId);
            if (checkbox.checked) {
                textarea.classList.add('grayed-textarea');
                textarea.readOnly = true;
                // Load default content
                const defaultContentId = textareaId.replace('template_', 'default_content_');
                const defaultContent = document.getElementById(defaultContentId);
                if (defaultContent) {
                    textarea.value = defaultContent.textContent;
                }
            } else {
                textarea.classList.remove('grayed-textarea');
                textarea.readOnly = false;
            }
        }

        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        });
    </script>
</body>
</html>
'''

DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - Devall CMS Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar { min-height: calc(100vh - 56px); }
        .template-block { border: 1px solid #dee2e6; border-radius: 0.375rem; margin-bottom: 1rem; }
        .template-block-header { background-color: #f8f9fa; padding: 0.75rem 1rem; border-bottom: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center; }
        .sort-buttons { display: flex; gap: 0.25rem; }
        .use-default-checkbox { margin-right: 0.5rem; }
        .grayed-textarea { background-color: #f8f9fa !important; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">Devall CMS</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('pages') }}">Pages</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('templates') }}">Templates</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('users') }}">Users</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="bi bi-person-circle"></i> {{ session.get('username', 'Admin') }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-menu-item" href="{{ url_for('logout') }}">Logout</a></li>
                        </ul>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show mt-3">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                <div class="row">
                    <div class="col-md-12">
                        <h1 class="mb-4">Dashboard</h1>
                    </div>
                </div>
                <div class="row">
                    <div class="col-md-3">
                        <div class="card text-white bg-primary mb-3">
                            <div class="card-body">
                                <div class="card-title">
                                    <i class="bi bi-file-earmark-text"></i> Pages
                                </div>
                                <h3>{{ pages_count }}</h3>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card text-white bg-success mb-3">
                            <div class="card-body">
                                <div class="card-title">
                                    <i class="bi bi-braces"></i> Templates
                                </div>
                                <h3>{{ templates_count }}</h3>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card text-white bg-info mb-3">
                            <div class="card-body">
                                <div class="card-title">
                                    <i class="bi bi-people"></i> Users
                                </div>
                                <h3>{{ users_count }}</h3>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card text-white bg-warning mb-3">
                            <div class="card-body">
                                <div class="card-title">
                                    <i class="bi bi-gear"></i> Published
                                </div>
                                <h3>{{ published_count }}</h3>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="row">
                    <div class="col-md-12">
                        <div class="card">
                            <div class="card-header">
                                <h5>Recent Activity</h5>
                            </div>
                            <div class="card-body">
                                <p>Welcome to Devall CMS! Use the navigation menu above to manage your content.</p>
                                <ul>
                                    <li>Create and edit pages using the Pages section</li>
                                    <li>Customize templates in the Templates section</li>
                                    <li>Manage users and settings</li>
                                    <li>Publish pages to generate static HTML files</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Template block sorting
        function moveBlock(blockId, direction) {
            const block = document.getElementById('block-' + blockId);
            const container = block.parentElement;

            if (direction === 'up') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock) {
                    container.insertBefore(block, prevBlock);
                }
            } else {
                const nextBlock = block.nextElementSibling;
                if (nextBlock) {
                    container.insertBefore(nextBlock, block);
                }
            }

            // Update sort order inputs
            updateSortOrder(container);
        }

        function updateSortOrder(container) {
            const blocks = container.querySelectorAll('[id^="block-"]');
            blocks.forEach((block, index) => {
                const sortInput = block.querySelector('input[name^="sort_order_"]');
                if (sortInput) {
                    sortInput.value = index;
                }
            });
        }

        // Toggle default content
        function toggleDefaultContent(checkbox, textareaId) {
            const textarea = document.getElementById(textareaId);
            if (checkbox.checked) {
                textarea.classList.add('grayed-textarea');
                textarea.readOnly = true;
                // Load default content
                const defaultContentId = textareaId.replace('template_', 'default_content_');
                const defaultContent = document.getElementById(defaultContentId);
                if (defaultContent) {
                    textarea.value = defaultContent.textContent;
                }
            } else {
                textarea.classList.remove('grayed-textarea');
                textarea.readOnly = false;
            }
        }

        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        });
    </script>
</body>
</html>
'''

# Routes
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ? AND active = 1', (username,))
        user = cursor.fetchone()

        if user and check_password(password, user['password_hash']):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password', 'error')

    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def admin_dashboard():
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

    return render_template_string(DASHBOARD_TEMPLATE,
                                pages_count=pages_count,
                                templates_count=templates_count,
                                users_count=users_count,
                                published_count=published_count)

# Users Management
@app.route('/admin/users')
@login_required
def users():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id, username, email, role, created_at, active FROM users ORDER BY created_at DESC')
    users_list = cursor.fetchall()

    template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Users - Devall CMS Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar { min-height: calc(100vh - 56px); }
        .template-block { border: 1px solid #dee2e6; border-radius: 0.375rem; margin-bottom: 1rem; }
        .template-block-header { background-color: #f8f9fa; padding: 0.75rem 1rem; border-bottom: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center; }
        .sort-buttons { display: flex; gap: 0.25rem; }
        .use-default-checkbox { margin-right: 0.5rem; }
        .grayed-textarea { background-color: #f8f9fa !important; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">Devall CMS</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('pages') }}">Pages</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('templates') }}">Templates</a></li>
                    <li class="nav-item"><a class="nav-link active" href="{{ url_for('users') }}">Users</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="bi bi-person-circle"></i> {{ session.get('username', 'Admin') }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-menu-item" href="{{ url_for('logout') }}">Logout</a></li>
                        </ul>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show mt-3">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                <div class="row">
                    <div class="col-12">
                        <div class="d-flex justify-content-between align-items-center mb-4">
                            <h1>Users</h1>
                            <a href="{{ url_for('add_user') }}" class="btn btn-primary">
                                <i class="bi bi-plus-circle"></i> Add User
                            </a>
                        </div>
                    </div>
                </div>
                <div class="row">
                    <div class="col-12">
                        <div class="card">
                            <div class="card-body">
                                <div class="table-responsive">
                                    <table class="table table-striped">
                                        <thead>
                                            <tr>
                                                <th>Username</th>
                                                <th>Email</th>
                                                <th>Role</th>
                                                <th>Status</th>
                                                <th>Created</th>
                                                <th>Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {% for user in users %}
                                            <tr>
                                                <td>{{ user.username }}</td>
                                                <td>{{ user.email or '-' }}</td>
                                                <td>
                                                    <span class="badge bg-primary">{{ user.role }}</span>
                                                </td>
                                                <td>
                                                    {% if user.active %}
                                                        <span class="badge bg-success">Active</span>
                                                    {% else %}
                                                        <span class="badge bg-secondary">Inactive</span>
                                                    {% endif %}
                                                </td>
                                                <td>{{ user.created_at[:10] }}</td>
                                                <td>
                                                    <a href="{{ url_for('edit_user', user_id=user.id) }}" class="btn btn-sm btn-outline-primary">
                                                        <i class="bi bi-pencil"></i> Edit
                                                    </a>
                                                    {% if user.id != session.get('user_id') %}
                                                    <a href="{{ url_for('delete_user', user_id=user.id) }}" class="btn btn-sm btn-outline-danger"
                                                       onclick="return confirm('Are you sure you want to delete this user?')">
                                                        <i class="bi bi-trash"></i> Delete
                                                    </a>
                                                    {% endif %}
                                                </td>
                                            </tr>
                                            {% endfor %}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Template block sorting
        function moveBlock(blockId, direction) {
            const block = document.getElementById('block-' + blockId);
            const container = block.parentElement;

            if (direction === 'up') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock) {
                    container.insertBefore(block, prevBlock);
                }
            } else {
                const nextBlock = block.nextElementSibling;
                if (nextBlock) {
                    container.insertBefore(nextBlock, block);
                }
            }

            // Update sort order inputs
            updateSortOrder(container);
        }

        function updateSortOrder(container) {
            const blocks = container.querySelectorAll('[id^="block-"]');
            blocks.forEach((block, index) => {
                const sortInput = block.querySelector('input[name^="sort_order_"]');
                if (sortInput) {
                    sortInput.value = index;
                }
            });
        }

        // Toggle default content
        function toggleDefaultContent(checkbox, textareaId) {
            const textarea = document.getElementById(textareaId);
            if (checkbox.checked) {
                textarea.classList.add('grayed-textarea');
                textarea.readOnly = true;
                // Load default content
                const defaultContentId = textareaId.replace('template_', 'default_content_');
                const defaultContent = document.getElementById(defaultContentId);
                if (defaultContent) {
                    textarea.value = defaultContent.textContent;
                }
            } else {
                textarea.classList.remove('grayed-textarea');
                textarea.readOnly = false;
            }
        }

        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        });
    </script>
</body>
</html>
'''

    return render_template_string(template, users=users_list)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        role = request.form.get('role', 'admin')

        if not username or not password:
            flash('Username and password are required', 'error')
            return redirect(url_for('add_user'))

        db = get_db()
        cursor = db.cursor()

        # Check if username already exists
        cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', (username,))
        if cursor.fetchone()[0] > 0:
            flash('Username already exists', 'error')
            return redirect(url_for('add_user'))

        cursor.execute('INSERT INTO users (username, password_hash, email, role) VALUES (?, ?, ?, ?)',
                     (username, hash_password(password), email, role))
        db.commit()

        flash('User created successfully', 'success')
        return redirect(url_for('users'))

    template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Add User - Devall CMS Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar { min-height: calc(100vh - 56px); }
        .template-block { border: 1px solid #dee2e6; border-radius: 0.375rem; margin-bottom: 1rem; }
        .template-block-header { background-color: #f8f9fa; padding: 0.75rem 1rem; border-bottom: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center; }
        .sort-buttons { display: flex; gap: 0.25rem; }
        .use-default-checkbox { margin-right: 0.5rem; }
        .grayed-textarea { background-color: #f8f9fa !important; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">Devall CMS</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('pages') }}">Pages</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('templates') }}">Templates</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('users') }}">Users</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="bi bi-person-circle"></i> {{ session.get('username', 'Admin') }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-menu-item" href="{{ url_for('logout') }}">Logout</a></li>
                        </ul>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show mt-3">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}    
    
    
    <div class="row">
        <div class="col-md-8 mx-auto">
            <div class="card">
                <div class="card-header">
                    <h4>Add New User</h4>
                </div>
                <div class="card-body">
                    <form method="post">
                        <div class="mb-3">
                            <label for="username" class="form-label">Username *</label>
                            <input type="text" class="form-control" id="username" name="username" required>
                        </div>
                        <div class="mb-3">
                            <label for="password" class="form-label">Password *</label>
                            <input type="password" class="form-control" id="password" name="password" required>
                        </div>
                        <div class="mb-3">
                            <label for="email" class="form-label">Email</label>
                            <input type="email" class="form-control" id="email" name="email">
                        </div>
                        <div class="mb-3">
                            <label for="role" class="form-label">Role</label>
                            <select class="form-select" id="role" name="role">
                                <option value="admin">Admin</option>
                                <option value="editor">Editor</option>
                            </select>
                        </div>
                        <div class="d-flex gap-2">
                            <button type="submit" class="btn btn-primary">Create User</button>
                            <a href="{{ url_for('users') }}" class="btn btn-secondary">Cancel</a>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
    
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Template block sorting
        function moveBlock(blockId, direction) {
            const block = document.getElementById('block-' + blockId);
            const container = block.parentElement;

            if (direction === 'up') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock) {
                    container.insertBefore(block, prevBlock);
                }
            } else {
                const nextBlock = block.nextElementSibling;
                if (nextBlock) {
                    container.insertBefore(nextBlock, block);
                }
            }

            // Update sort order inputs
            updateSortOrder(container);
        }

        function updateSortOrder(container) {
            const blocks = container.querySelectorAll('[id^="block-"]');
            blocks.forEach((block, index) => {
                const sortInput = block.querySelector('input[name^="sort_order_"]');
                if (sortInput) {
                    sortInput.value = index;
                }
            });
        }

        // Toggle default content
        function toggleDefaultContent(checkbox, textareaId) {
            const textarea = document.getElementById(textareaId);
            if (checkbox.checked) {
                textarea.classList.add('grayed-textarea');
                textarea.readOnly = true;
                // Load default content
                const defaultContentId = textareaId.replace('template_', 'default_content_');
                const defaultContent = document.getElementById(defaultContentId);
                if (defaultContent) {
                    textarea.value = defaultContent.textContent;
                }
            } else {
                textarea.classList.remove('grayed-textarea');
                textarea.readOnly = false;
            }
        }

        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        });
    </script>
</body>
</html>
    '''

    return render_template_string(template)

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        role = request.form.get('role', 'admin')
        active = request.form.get('active') == 'on'

        if not username:
            flash('Username is required', 'error')
            return redirect(url_for('edit_user', user_id=user_id))

        # Check if username already exists (excluding current user)
        cursor.execute('SELECT COUNT(*) FROM users WHERE username = ? AND id != ?', (username, user_id))
        if cursor.fetchone()[0] > 0:
            flash('Username already exists', 'error')
            return redirect(url_for('edit_user', user_id=user_id))

        if password:
            cursor.execute('UPDATE users SET username = ?, password_hash = ?, email = ?, role = ?, active = ? WHERE id = ?',
                         (username, hash_password(password), email, role, active, user_id))
        else:
            cursor.execute('UPDATE users SET username = ?, email = ?, role = ?, active = ? WHERE id = ?',
                         (username, email, role, active, user_id))

        db.commit()
        flash('User updated successfully', 'success')
        return redirect(url_for('users'))

    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()

    if not user:
        flash('User not found', 'error')
        return redirect(url_for('users'))

    template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Edit User - Devall CMS Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar { min-height: calc(100vh - 56px); }
        .template-block { border: 1px solid #dee2e6; border-radius: 0.375rem; margin-bottom: 1rem; }
        .template-block-header { background-color: #f8f9fa; padding: 0.75rem 1rem; border-bottom: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center; }
        .sort-buttons { display: flex; gap: 0.25rem; }
        .use-default-checkbox { margin-right: 0.5rem; }
        .grayed-textarea { background-color: #f8f9fa !important; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">Devall CMS</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('pages') }}">Pages</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('templates') }}">Templates</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('users') }}">Users</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="bi bi-person-circle"></i> {{ session.get('username', 'Admin') }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-menu-item" href="{{ url_for('logout') }}">Logout</a></li>
                        </ul>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show mt-3">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}    
    
    
    <div class="row">
        <div class="col-md-8 mx-auto">
            <div class="card">
                <div class="card-header">
                    <h4>Edit User</h4>
                </div>
                <div class="card-body">
                    <form method="post">
                        <div class="mb-3">
                            <label for="username" class="form-label">Username *</label>
                            <input type="text" class="form-control" id="username" name="username" value="{{ user.username }}" required>
                        </div>
                        <div class="mb-3">
                            <label for="password" class="form-label">New Password (leave blank to keep current)</label>
                            <input type="password" class="form-control" id="password" name="password">
                        </div>
                        <div class="mb-3">
                            <label for="email" class="form-label">Email</label>
                            <input type="email" class="form-control" id="email" name="email" value="{{ user.email or '' }}">
                        </div>
                        <div class="mb-3">
                            <label for="role" class="form-label">Role</label>
                            <select class="form-select" id="role" name="role">
                                <option value="admin" {{ 'selected' if user.role == 'admin' else '' }}>Admin</option>
                                <option value="editor" {{ 'selected' if user.role == 'editor' else '' }}>Editor</option>
                            </select>
                        </div>
                        <div class="mb-3 form-check">
                            <input type="checkbox" class="form-check-input" id="active" name="active" {{ 'checked' if user.active else '' }}>
                            <label class="form-check-label" for="active">Active</label>
                        </div>
                        <div class="d-flex gap-2">
                            <button type="submit" class="btn btn-primary">Update User</button>
                            <a href="{{ url_for('users') }}" class="btn btn-secondary">Cancel</a>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
    
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Template block sorting
        function moveBlock(blockId, direction) {
            const block = document.getElementById('block-' + blockId);
            const container = block.parentElement;

            if (direction === 'up') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock) {
                    container.insertBefore(block, prevBlock);
                }
            } else {
                const nextBlock = block.nextElementSibling;
                if (nextBlock) {
                    container.insertBefore(nextBlock, block);
                }
            }

            // Update sort order inputs
            updateSortOrder(container);
        }

        function updateSortOrder(container) {
            const blocks = container.querySelectorAll('[id^="block-"]');
            blocks.forEach((block, index) => {
                const sortInput = block.querySelector('input[name^="sort_order_"]');
                if (sortInput) {
                    sortInput.value = index;
                }
            });
        }

        // Toggle default content
        function toggleDefaultContent(checkbox, textareaId) {
            const textarea = document.getElementById(textareaId);
            if (checkbox.checked) {
                textarea.classList.add('grayed-textarea');
                textarea.readOnly = true;
                // Load default content
                const defaultContentId = textareaId.replace('template_', 'default_content_');
                const defaultContent = document.getElementById(defaultContentId);
                if (defaultContent) {
                    textarea.value = defaultContent.textContent;
                }
            } else {
                textarea.classList.remove('grayed-textarea');
                textarea.readOnly = false;
            }
        }

        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        });
    </script>
</body>
</html>
    '''

    return render_template_string(template, user=user)

@app.route('/admin/users/<int:user_id>/delete')
@login_required
def delete_user(user_id):
    # Prevent self-deletion
    if user_id == session.get('user_id'):
        flash('Cannot delete your own account', 'error')
        return redirect(url_for('users'))

    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()

    flash('User deleted successfully', 'success')
    return redirect(url_for('users'))

# Settings
@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def settings():
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        # Handle checkbox settings (they need special handling)
        cursor.execute('SELECT key FROM settings WHERE key IN (?, ?)', ('hide_system_blocks', 'admin_theme'))
        existing_keys = [row['key'] for row in cursor.fetchall()]

        # First, reset checkbox settings to '0' if not submitted
        for key in existing_keys:
            if key == 'hide_system_blocks':
                cursor.execute('UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?',
                             ('0', key))

        # Then update all submitted settings
        for key, value in request.form.items():
            if key.startswith('setting_'):
                setting_key = key[8:]  # Remove 'setting_' prefix
                cursor.execute('UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?',
                             (value, setting_key))

        db.commit()
        flash('Settings updated successfully', 'success')
        return redirect(url_for('settings'))

    cursor.execute('SELECT * FROM settings ORDER BY key')
    settings_list = cursor.fetchall()

    template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Settings - Devall CMS Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar { min-height: calc(100vh - 56px); }
        .template-block { border: 1px solid #dee2e6; border-radius: 0.375rem; margin-bottom: 1rem; }
        .template-block-header { background-color: #f8f9fa; padding: 0.75rem 1rem; border-bottom: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center; }
        .sort-buttons { display: flex; gap: 0.25rem; }
        .use-default-checkbox { margin-right: 0.5rem; }
        .grayed-textarea { background-color: #f8f9fa !important; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">Devall CMS</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('pages') }}">Pages</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('templates') }}">Templates</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('users') }}">Users</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="bi bi-person-circle"></i> {{ session.get('username', 'Admin') }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-menu-item" href="{{ url_for('logout') }}">Logout</a></li>
                        </ul>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show mt-3">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}    
    
    
    <div class="row">
        <div class="col-12">
            <h1 class="mb-4">Settings</h1>
        </div>
    </div>
    <div class="row">
        <div class="col-md-8 mx-auto">
            <div class="card">
                <div class="card-header">
                    <h5>CMS Settings</h5>
                </div>
                <div class="card-body">
                    <form method="post">
                        {% for setting in settings %}
                        <div class="mb-3">
                            <label for="setting_{{ setting.key }}" class="form-label">{{ setting.description or setting.key }}</label>
                            {% if setting.key == 'admin_theme' %}
                            <select class="form-select" id="setting_{{ setting.key }}" name="setting_{{ setting.key }}">
                                <option value="light" {{ 'selected' if setting.value == 'light' else '' }}>Light</option>
                                <option value="dark" {{ 'selected' if setting.value == 'dark' else '' }}>Dark</option>
                            </select>
                            {% elif setting.key == 'hide_system_blocks' %}
                            <div class="form-check">
                                <input type="checkbox" class="form-check-input" id="setting_{{ setting.key }}" name="setting_{{ setting.key }}" value="1" {{ 'checked' if setting.value == '1' else '' }}>
                                <label class="form-check-label" for="setting_{{ setting.key }}">
                                    Hide system template blocks by default in page editor
                                </label>
                            </div>
                            {% else %}
                            <input type="text" class="form-control" id="setting_{{ setting.key }}" name="setting_{{ setting.key }}" value="{{ setting.value }}">
                            {% endif %}
                        </div>
                        {% endfor %}
                        <button type="submit" class="btn btn-primary">Save Settings</button>
                    </form>
                </div>
            </div>
        </div>
    </div>
    
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Template block sorting
        function moveBlock(blockId, direction) {
            const block = document.getElementById('block-' + blockId);
            const container = block.parentElement;

            if (direction === 'up') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock) {
                    container.insertBefore(block, prevBlock);
                }
            } else {
                const nextBlock = block.nextElementSibling;
                if (nextBlock) {
                    container.insertBefore(nextBlock, block);
                }
            }

            // Update sort order inputs
            updateSortOrder(container);
        }

        function updateSortOrder(container) {
            const blocks = container.querySelectorAll('[id^="block-"]');
            blocks.forEach((block, index) => {
                const sortInput = block.querySelector('input[name^="sort_order_"]');
                if (sortInput) {
                    sortInput.value = index;
                }
            });
        }

        // Toggle default content
        function toggleDefaultContent(checkbox, textareaId) {
            const textarea = document.getElementById(textareaId);
            if (checkbox.checked) {
                textarea.classList.add('grayed-textarea');
                textarea.readOnly = true;
                // Load default content
                const defaultContentId = textareaId.replace('template_', 'default_content_');
                const defaultContent = document.getElementById(defaultContentId);
                if (defaultContent) {
                    textarea.value = defaultContent.textContent;
                }
            } else {
                textarea.classList.remove('grayed-textarea');
                textarea.readOnly = false;
            }
        }

        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        });
    </script>
</body>
</html>
    '''

    return render_template_string(template, settings=settings_list)

# Templates Management
@app.route('/admin/templates')
@login_required
def templates():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT t.*,
               COUNT(CASE WHEN pt.use_default = 0 THEN 1 END) as override_count
        FROM templates t
        LEFT JOIN page_templates pt ON t.id = pt.template_id
        GROUP BY t.id
        ORDER BY t.sort_order
    ''')
    templates_list = cursor.fetchall()

    template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Templates - Devall CMS Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar { min-height: calc(100vh - 56px); }
        .template-block { border: 1px solid #dee2e6; border-radius: 0.375rem; margin-bottom: 1rem; }
        .template-block-header { background-color: #f8f9fa; padding: 0.75rem 1rem; border-bottom: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center; }
        .sort-buttons { display: flex; gap: 0.25rem; }
        .use-default-checkbox { margin-right: 0.5rem; }
        .grayed-textarea { background-color: #f8f9fa !important; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">Devall CMS</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('pages') }}">Pages</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('templates') }}">Templates</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('users') }}">Users</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="bi bi-person-circle"></i> {{ session.get('username', 'Admin') }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-menu-item" href="{{ url_for('logout') }}">Logout</a></li>
                        </ul>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show mt-3">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}    
    
    
    <div class="row">
        <div class="col-12">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1>Templates</h1>
                <a href="{{ url_for('add_template') }}" class="btn btn-primary">
                    <i class="bi bi-plus-circle"></i> Add Template
                </a>
            </div>
        </div>
    </div>
    <div class="row">
        <div class="col-12">
            <div class="card">
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-striped">
                            <thead>
                                <tr>
                                    <th>Title</th>
                                    <th>Slug</th>
                                    <th>Category</th>
                                    <th>Default</th>
                                    <th>Overrides</th>
                                    <th>Order</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for template in templates %}
                                <tr>
                                    <td>{{ template.title }}</td>
                                    <td><code>{{ template.slug }}</code></td>
                                    <td>
                                        <span class="badge bg-{{ 'primary' if template.category == 'system' else 'success' }}">
                                            {{ template.category.title() }}
                                        </span>
                                    </td>
                                    <td>
                                        {% if template.is_default %}
                                            <i class="bi bi-check-circle text-success"></i>
                                        {% else %}
                                            <i class="bi bi-x-circle text-muted"></i>
                                        {% endif %}
                                    </td>
                                    <td>
                                        {% if template.override_count > 0 %}
                                            <span class="badge bg-warning">{{ template.override_count }} page{{ 's' if template.override_count > 1 else '' }}</span>
                                        {% else %}
                                            <span class="text-muted">-</span>
                                        {% endif %}
                                    </td>
                                    <td>{{ template.sort_order }}</td>
                                    <td>
                                        <a href="{{ url_for('edit_template', template_id=template.id) }}" class="btn btn-sm btn-outline-primary">
                                            <i class="bi bi-pencil"></i> Edit
                                        </a>
                                        <a href="{{ url_for('delete_template', template_id=template.id) }}" class="btn btn-sm btn-outline-danger"
                                           onclick="return confirm('Are you sure you want to delete this template?')">
                                            <i class="bi bi-trash"></i> Delete
                                        </a>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Template block sorting
        function moveBlock(blockId, direction) {
            const block = document.getElementById('block-' + blockId);
            const container = block.parentElement;

            if (direction === 'up') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock) {
                    container.insertBefore(block, prevBlock);
                }
            } else {
                const nextBlock = block.nextElementSibling;
                if (nextBlock) {
                    container.insertBefore(nextBlock, block);
                }
            }

            // Update sort order inputs
            updateSortOrder(container);
        }

        function updateSortOrder(container) {
            const blocks = container.querySelectorAll('[id^="block-"]');
            blocks.forEach((block, index) => {
                const sortInput = block.querySelector('input[name^="sort_order_"]');
                if (sortInput) {
                    sortInput.value = index;
                }
            });
        }

        // Toggle default content
        function toggleDefaultContent(checkbox, textareaId) {
            const textarea = document.getElementById(textareaId);
            if (checkbox.checked) {
                textarea.classList.add('grayed-textarea');
                textarea.readOnly = true;
                // Load default content
                const defaultContentId = textareaId.replace('template_', 'default_content_');
                const defaultContent = document.getElementById(defaultContentId);
                if (defaultContent) {
                    textarea.value = defaultContent.textContent;
                }
            } else {
                textarea.classList.remove('grayed-textarea');
                textarea.readOnly = false;
            }
        }

        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        });
    </script>
</body>
</html>
    '''

    return render_template_string(template, templates=templates_list)

@app.route('/admin/templates/add', methods=['GET', 'POST'])
@login_required
def add_template():
    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        category = request.form.get('category')
        content = request.form.get('content')
        is_default = request.form.get('is_default') == 'on'
        sort_order = request.form.get('sort_order', 0)

        if not title or not slug or not category:
            flash('Title, slug, and category are required', 'error')
            return redirect(url_for('add_template'))

        db = get_db()
        cursor = db.cursor()

        # Check if slug already exists
        cursor.execute('SELECT COUNT(*) FROM templates WHERE slug = ?', (slug,))
        if cursor.fetchone()[0] > 0:
            flash('Template slug already exists', 'error')
            return redirect(url_for('add_template'))

        cursor.execute('INSERT INTO templates (title, slug, category, content, is_default, sort_order) VALUES (?, ?, ?, ?, ?, ?)',
                     (title, slug, category, content, is_default, sort_order))
        db.commit()

        flash('Template created successfully', 'success')
        return redirect(url_for('templates'))

    template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Add Template - Devall CMS Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar { min-height: calc(100vh - 56px); }
        .template-block { border: 1px solid #dee2e6; border-radius: 0.375rem; margin-bottom: 1rem; }
        .template-block-header { background-color: #f8f9fa; padding: 0.75rem 1rem; border-bottom: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center; }
        .sort-buttons { display: flex; gap: 0.25rem; }
        .use-default-checkbox { margin-right: 0.5rem; }
        .grayed-textarea { background-color: #f8f9fa !important; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">Devall CMS</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('pages') }}">Pages</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('templates') }}">Templates</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('users') }}">Users</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="bi bi-person-circle"></i> {{ session.get('username', 'Admin') }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-menu-item" href="{{ url_for('logout') }}">Logout</a></li>
                        </ul>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show mt-3">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}    
    
    
    <div class="row">
        <div class="col-md-10 mx-auto">
            <div class="card">
                <div class="card-header">
                    <h4>Add New Template Block</h4>
                </div>
                <div class="card-body">
                    <form method="post">
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="title" class="form-label">Title *</label>
                                    <input type="text" class="form-control" id="title" name="title" required>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="slug" class="form-label">Slug *</label>
                                    <input type="text" class="form-control" id="slug" name="slug" required>
                                    <div class="form-text">Unique identifier, no spaces</div>
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="category" class="form-label">Category *</label>
                                    <select class="form-select" id="category" name="category" required>
                                        <option value="system">System Template</option>
                                        <option value="content">Content Template</option>
                                    </select>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="sort_order" class="form-label">Sort Order</label>
                                    <input type="number" class="form-control" id="sort_order" name="sort_order" value="0">
                                </div>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label for="content" class="form-label">Content</label>
                            <textarea class="form-control" id="content" name="content" rows="10"></textarea>
                        </div>
                        <div class="mb-3 form-check">
                            <input type="checkbox" class="form-check-input" id="is_default" name="is_default" checked>
                            <label class="form-check-label" for="is_default">Include in default page templates</label>
                        </div>
                        <div class="d-flex gap-2">
                            <button type="submit" class="btn btn-primary">Create Template</button>
                            <a href="{{ url_for('templates') }}" class="btn btn-secondary">Cancel</a>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
    
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Template block sorting
        function moveBlock(blockId, direction) {
            const block = document.getElementById('block-' + blockId);
            const container = block.parentElement;

            if (direction === 'up') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock) {
                    container.insertBefore(block, prevBlock);
                }
            } else {
                const nextBlock = block.nextElementSibling;
                if (nextBlock) {
                    container.insertBefore(nextBlock, block);
                }
            }

            // Update sort order inputs
            updateSortOrder(container);
        }

        function updateSortOrder(container) {
            const blocks = container.querySelectorAll('[id^="block-"]');
            blocks.forEach((block, index) => {
                const sortInput = block.querySelector('input[name^="sort_order_"]');
                if (sortInput) {
                    sortInput.value = index;
                }
            });
        }

        // Toggle default content
        function toggleDefaultContent(checkbox, textareaId) {
            const textarea = document.getElementById(textareaId);
            if (checkbox.checked) {
                textarea.classList.add('grayed-textarea');
                textarea.readOnly = true;
                // Load default content
                const defaultContentId = textareaId.replace('template_', 'default_content_');
                const defaultContent = document.getElementById(defaultContentId);
                if (defaultContent) {
                    textarea.value = defaultContent.textContent;
                }
            } else {
                textarea.classList.remove('grayed-textarea');
                textarea.readOnly = false;
            }
        }

        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        });
    </script>
</body>
</html>
    '''

    return render_template_string(template)

@app.route('/admin/templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_template(template_id):
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')
        category = request.form.get('category')
        content = request.form.get('content')
        is_default = request.form.get('is_default') == 'on'
        sort_order = request.form.get('sort_order', 0)

        if not title or not slug or not category:
            flash('Title, slug, and category are required', 'error')
            return redirect(url_for('edit_template', template_id=template_id))

        # Check if slug already exists (excluding current template)
        cursor.execute('SELECT COUNT(*) FROM templates WHERE slug = ? AND id != ?', (slug, template_id))
        if cursor.fetchone()[0] > 0:
            flash('Template slug already exists', 'error')
            return redirect(url_for('edit_template', template_id=template_id))

        cursor.execute('UPDATE templates SET title = ?, slug = ?, category = ?, content = ?, is_default = ?, sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                     (title, slug, category, content, is_default, sort_order, template_id))
        db.commit()

        flash('Template updated successfully', 'success')
        return redirect(url_for('templates'))

    cursor.execute('SELECT * FROM templates WHERE id = ?', (template_id,))
    template_data = cursor.fetchone()

    if not template_data:
        flash('Template not found', 'error')
        return redirect(url_for('templates'))

    # Get pages that are overriding this template
    cursor.execute('''
        SELECT p.id, p.title, p.slug, pt.custom_content, pt.use_default
        FROM pages p
        JOIN page_templates pt ON p.id = pt.page_id
        WHERE pt.template_id = ? AND pt.use_default = 0
        ORDER BY p.title
    ''', (template_id,))
    overriding_pages = cursor.fetchall()

    template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Edit Template - Devall CMS Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar { min-height: calc(100vh - 56px); }
        .template-block { border: 1px solid #dee2e6; border-radius: 0.375rem; margin-bottom: 1rem; }
        .template-block-header { background-color: #f8f9fa; padding: 0.75rem 1rem; border-bottom: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center; }
        .sort-buttons { display: flex; gap: 0.25rem; }
        .use-default-checkbox { margin-right: 0.5rem; }
        .grayed-textarea { background-color: #f8f9fa !important; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">Devall CMS</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('pages') }}">Pages</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('templates') }}">Templates</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('users') }}">Users</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="bi bi-person-circle"></i> {{ session.get('username', 'Admin') }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-menu-item" href="{{ url_for('logout') }}">Logout</a></li>
                        </ul>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show mt-3">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}    
    
    
    <div class="row">
        <div class="col-md-10 mx-auto">
            <div class="card">
                <div class="card-header">
                    <h4>Edit Template Block</h4>
                </div>
                <div class="card-body">
                    {% if overriding_pages %}
                    <div class="alert alert-warning">
                        <h6><i class="bi bi-exclamation-triangle"></i> Pages Overriding This Template</h6>
                        <p>The following pages have custom content for this template block:</p>
                        <ul class="mb-0">
                            {% for page in overriding_pages %}
                            <li>
                                <strong>{{ page.title }}</strong>
                                <a href="{{ url_for('edit_page', page_id=page.id) }}" class="btn btn-sm btn-outline-primary ms-2">Edit Page</a>
                            </li>
                            {% endfor %}
                        </ul>
                        <small class="text-muted">Changes to this template will not affect these pages until they switch back to using the default content.</small>
                    </div>
                    {% endif %}
                    <form method="post">
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="title" class="form-label">Title *</label>
                                    <input type="text" class="form-control" id="title" name="title" value="{{ template.title }}" required>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="slug" class="form-label">Slug *</label>
                                    <input type="text" class="form-control" id="slug" name="slug" value="{{ template.slug }}" required>
                                    <div class="form-text">Unique identifier, no spaces</div>
                                </div>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="category" class="form-label">Category *</label>
                                    <select class="form-select" id="category" name="category" required>
                                        <option value="system" {{ 'selected' if template.category == 'system' else '' }}>System Template</option>
                                        <option value="content" {{ 'selected' if template.category == 'content' else '' }}>Content Template</option>
                                    </select>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="sort_order" class="form-label">Sort Order</label>
                                    <input type="number" class="form-control" id="sort_order" name="sort_order" value="{{ template.sort_order }}">
                                </div>
                            </div>
                        </div>
                        <div class="mb-3">
                            <label for="content" class="form-label">Content</label>
                            <textarea class="form-control" id="content" name="content" rows="10">{{ template.content }}</textarea>
                        </div>
                        <div class="mb-3 form-check">
                            <input type="checkbox" class="form-check-input" id="is_default" name="is_default" {{ 'checked' if template.is_default else '' }}>
                            <label class="form-check-label" for="is_default">Include in default page templates</label>
                        </div>
                        <div class="d-flex gap-2">
                            <button type="submit" class="btn btn-primary">Update Template</button>
                            <a href="{{ url_for('templates') }}" class="btn btn-secondary">Cancel</a>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
    
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Template block sorting
        function moveBlock(blockId, direction) {
            const block = document.getElementById('block-' + blockId);
            const container = block.parentElement;

            if (direction === 'up') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock) {
                    container.insertBefore(block, prevBlock);
                }
            } else {
                const nextBlock = block.nextElementSibling;
                if (nextBlock) {
                    container.insertBefore(nextBlock, block);
                }
            }

            // Update sort order inputs
            updateSortOrder(container);
        }

        function updateSortOrder(container) {
            const blocks = container.querySelectorAll('[id^="block-"]');
            blocks.forEach((block, index) => {
                const sortInput = block.querySelector('input[name^="sort_order_"]');
                if (sortInput) {
                    sortInput.value = index;
                }
            });
        }

        // Toggle default content
        function toggleDefaultContent(checkbox, textareaId) {
            const textarea = document.getElementById(textareaId);
            if (checkbox.checked) {
                textarea.classList.add('grayed-textarea');
                textarea.readOnly = true;
                // Load default content
                const defaultContentId = textareaId.replace('template_', 'default_content_');
                const defaultContent = document.getElementById(defaultContentId);
                if (defaultContent) {
                    textarea.value = defaultContent.textContent;
                }
            } else {
                textarea.classList.remove('grayed-textarea');
                textarea.readOnly = false;
            }
        }

        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        });
    </script>
</body>
</html>
    '''

    return render_template_string(template, template=template_data, overriding_pages=overriding_pages)

@app.route('/admin/templates/<int:template_id>/delete')
@login_required
def delete_template(template_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('DELETE FROM templates WHERE id = ?', (template_id,))
    db.commit()

    flash('Template deleted successfully', 'success')
    return redirect(url_for('templates'))

# Import/Export Functions
def import_pages(import_data, overwrite_existing, cursor):
    """Import pages from JSON data"""
    imported_count = 0

    if not isinstance(import_data, list):
        raise ValueError("Invalid JSON format - expected array of pages")

    for page_data in import_data:
        try:
            # Check if page already exists
            cursor.execute('SELECT id FROM pages WHERE slug = ?', (page_data['slug'],))
            existing_page = cursor.fetchone()

            if existing_page and not overwrite_existing:
                continue  # Skip if page exists and we don't want to overwrite

            # Delete existing page if overwriting
            if existing_page and overwrite_existing:
                cursor.execute('DELETE FROM page_templates WHERE page_id = ?', (existing_page['id'],))
                cursor.execute('DELETE FROM pages WHERE id = ?', (existing_page['id'],))

            # Insert new page
            cursor.execute('''
                INSERT INTO pages (title, slug, published, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                page_data['title'],
                page_data['slug'],
                page_data.get('published', 0),
                page_data.get('created_at', datetime.now().isoformat()),
                page_data.get('updated_at', datetime.now().isoformat())
            ))

            page_id = cursor.lastrowid

            # Insert page templates
            if 'templates' in page_data:
                for template_data in page_data['templates']:
                    # Check if template exists, if not, skip it
                    cursor.execute('SELECT id FROM templates WHERE id = ?', (template_data['template_id'],))
                    if cursor.fetchone():
                        cursor.execute('''
                            INSERT INTO page_templates (page_id, template_id, custom_content, use_default, sort_order)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (
                            page_id,
                            template_data['template_id'],
                            template_data.get('custom_content', ''),
                            template_data.get('use_default', 1),
                            template_data.get('sort_order', 0)
                        ))
                    else:
                        print(f"Warning: Template ID {template_data['template_id']} not found, skipping template for page {page_data['slug']}")

            imported_count += 1

        except Exception as e:
            print(f"Error importing page {page_data.get('slug', 'unknown')}: {str(e)}")
            continue

    return imported_count

@app.route('/admin/pages/export/selected', methods=['POST'])
@login_required
def export_selected_pages():
    """Export selected pages to JSON"""
    selected_page_ids = request.form.getlist('selected_pages')

    if not selected_page_ids:
        flash('No pages selected for export', 'warning')
        return redirect(url_for('pages'))

    db = get_db()
    cursor = db.cursor()

    # Convert to integers for SQL query
    page_ids = [int(pid) for pid in selected_page_ids]

    # Get selected pages with their templates
    placeholders = ','.join('?' * len(page_ids))
    cursor.execute(f'''
        SELECT
            p.id, p.title, p.slug, p.published, p.created_at, p.updated_at,
            pt.id as pt_id, pt.template_id, pt.custom_content, pt.use_default, pt.sort_order,
            t.title as template_title, t.slug as template_slug
        FROM pages p
        LEFT JOIN page_templates pt ON p.id = pt.page_id
        LEFT JOIN templates t ON pt.template_id = t.id
        WHERE p.id IN ({placeholders})
        ORDER BY p.id, pt.sort_order
    ''', page_ids)

    rows = cursor.fetchall()

    # Group by page
    pages_data = {}
    for row in rows:
        page_id = row['id']

        if page_id not in pages_data:
            pages_data[page_id] = {
                'id': row['id'],
                'title': row['title'],
                'slug': row['slug'],
                'published': row['published'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
                'templates': []
            }

        if row['pt_id']:  # Only add if there's a page template
            pages_data[page_id]['templates'].append({
                'id': row['pt_id'],
                'template_id': row['template_id'],
                'template_title': row['template_title'],
                'template_slug': row['template_slug'],
                'custom_content': row['custom_content'] or '',
                'use_default': row['use_default'],
                'sort_order': row['sort_order']
            })

    # Convert to list
    export_data = list(pages_data.values())

    # Return JSON response
    response = app.response_class(
        response=json.dumps(export_data, indent=2, default=str),
        status=200,
        mimetype='application/json'
    )
    response.headers['Content-Disposition'] = f'attachment; filename=selected_pages_export.json'
    return response

@app.route('/admin/pages/export')
@login_required
def export_pages():
    """Export all pages to JSON"""
    db = get_db()
    cursor = db.cursor()

    # Get all pages with their templates
    cursor.execute('''
        SELECT
            p.id, p.title, p.slug, p.published, p.created_at, p.updated_at,
            pt.id as pt_id, pt.template_id, pt.custom_content, pt.use_default, pt.sort_order,
            t.title as template_title, t.slug as template_slug
        FROM pages p
        LEFT JOIN page_templates pt ON p.id = pt.page_id
        LEFT JOIN templates t ON pt.template_id = t.id
        ORDER BY p.id, pt.sort_order
    ''')

    rows = cursor.fetchall()

    # Group by page
    pages_data = {}
    for row in rows:
        page_id = row['id']

        if page_id not in pages_data:
            pages_data[page_id] = {
                'id': row['id'],
                'title': row['title'],
                'slug': row['slug'],
                'published': row['published'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
                'templates': []
            }

        if row['pt_id']:  # Only add if there's a page template
            pages_data[page_id]['templates'].append({
                'id': row['pt_id'],
                'template_id': row['template_id'],
                'template_title': row['template_title'],
                'template_slug': row['template_slug'],
                'custom_content': row['custom_content'] or '',
                'use_default': row['use_default'],
                'sort_order': row['sort_order']
            })

    # Convert to list
    export_data = list(pages_data.values())

    # Return JSON response
    response = app.response_class(
        response=json.dumps(export_data, indent=2, default=str),
        status=200,
        mimetype='application/json'
    )
    response.headers['Content-Disposition'] = 'attachment; filename=pages_export.json'
    return response

# Pages Management
@app.route('/admin/pages', methods=['GET', 'POST'])
@login_required
def pages():
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'import':
            import_file = request.files.get('import_file')
            overwrite_existing = request.form.get('overwrite_existing') == 'on'

            if import_file and import_file.filename.endswith('.json'):
                try:
                    import_data = json.load(import_file)
                    imported_count = import_pages(import_data, overwrite_existing, cursor)
                    db.commit()  # Commit the database changes
                    flash(f'Successfully imported {imported_count} page(s)', 'success')
                except Exception as e:
                    db.rollback()  # Rollback on error
                    flash(f'Import failed: {str(e)}', 'error')
            else:
                flash('Please select a valid JSON file', 'error')

            return redirect(url_for('pages'))

    cursor.execute('SELECT * FROM pages ORDER BY created_at DESC')
    pages_list = cursor.fetchall()

    template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pages - Devall CMS Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar { min-height: calc(100vh - 56px); }
        .template-block { border: 1px solid #dee2e6; border-radius: 0.375rem; margin-bottom: 1rem; }
        .template-block-header { background-color: #f8f9fa; padding: 0.75rem 1rem; border-bottom: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center; }
        .sort-buttons { display: flex; gap: 0.25rem; }
        .use-default-checkbox { margin-right: 0.5rem; }
        .grayed-textarea { background-color: #f8f9fa !important; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">Devall CMS</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('pages') }}">Pages</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('templates') }}">Templates</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('users') }}">Users</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="bi bi-person-circle"></i> {{ session.get('username', 'Admin') }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-menu-item" href="{{ url_for('logout') }}">Logout</a></li>
                        </ul>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show mt-3">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}    
    
    
    <div class="row">
        <div class="col-12">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1>Pages</h1>
                <div class="d-flex gap-2">
                    <form method="post" action="{{ url_for('export_selected_pages') }}" id="exportSelectedForm" style="display: none;">
                        <input type="hidden" name="action" value="export_selected">
                    </form>
                    <button type="button" id="exportSelectedBtn" class="btn btn-success" style="display: none;">
                        <i class="bi bi-download"></i> Export Selected
                    </button>
                    <a href="{{ url_for('export_pages') }}" class="btn btn-outline-success">
                        <i class="bi bi-download"></i> Export All
                    </a>
                    <button type="button" class="btn btn-outline-info" data-bs-toggle="modal" data-bs-target="#importModal">
                        <i class="bi bi-upload"></i> Import
                    </button>
                    <a href="{{ url_for('add_page') }}" class="btn btn-primary">
                        <i class="bi bi-plus-circle"></i> Add Page
                    </a>
                </div>
            </div>
        </div>
    </div>
    <div class="row">
        <div class="col-12">
            <div class="card">
                <div class="card-body">
                    <div class="table-responsive">
                        <table class="table table-striped">
                            <thead>
                                <tr>
                                    <th width="50">
                                        <input type="checkbox" id="selectAll" class="form-check-input">
                                    </th>
                                    <th>Title</th>
                                    <th>Slug</th>
                                    <th>Status</th>
                                    <th>Created</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for page in pages %}
                                <tr>
                                    <td>
                                        <input type="checkbox" class="form-check-input page-checkbox" name="selected_pages" value="{{ page.id }}">
                                    </td>
                                    <td>{{ page.title }}</td>
                                    <td><code>{{ page.slug }}</code></td>
                                    <td>
                                        {% if page.published %}
                                            <span class="badge bg-success">Published</span>
                                        {% else %}
                                            <span class="badge bg-warning">Draft</span>
                                        {% endif %}
                                    </td>
                                    <td>{{ page.created_at[:10] }}</td>
                                    <td>
                                        <a href="{{ url_for('edit_page', page_id=page.id) }}" class="btn btn-sm btn-outline-primary">
                                            <i class="bi bi-pencil"></i> Edit
                                        </a>
                                        <a href="{{ url_for('preview_page', page_id=page.id) }}" class="btn btn-sm btn-outline-info" target="_blank">
                                            <i class="bi bi-eye"></i> Preview
                                        </a>
                                        {% if page.published %}
                                        <a href="{{ url_for('publish_page', page_id=page.id) }}" class="btn btn-sm btn-outline-success">
                                            <i class="bi bi-upload"></i> Re-publish
                                        </a>
                                        {% else %}
                                        <a href="{{ url_for('publish_page', page_id=page.id) }}" class="btn btn-sm btn-outline-success">
                                            <i class="bi bi-upload"></i> Publish
                                        </a>
                                        {% endif %}
                                        <a href="{{ url_for('delete_page', page_id=page.id) }}" class="btn btn-sm btn-outline-danger"
                                           onclick="return confirm('Are you sure you want to delete this page?')">
                                            <i class="bi bi-trash"></i> Delete
                                        </a>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Template block sorting
        function moveBlock(blockId, direction) {
            const block = document.getElementById('block-' + blockId);
            const container = block.parentElement;

            if (direction === 'up') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock) {
                    container.insertBefore(block, prevBlock);
                }
            } else {
                const nextBlock = block.nextElementSibling;
                if (nextBlock) {
                    container.insertBefore(nextBlock, block);
                }
            }

            // Update sort order inputs
            updateSortOrder(container);
        }

        function updateSortOrder(container) {
            const blocks = container.querySelectorAll('[id^="block-"]');
            blocks.forEach((block, index) => {
                const sortInput = block.querySelector('input[name^="sort_order_"]');
                if (sortInput) {
                    sortInput.value = index;
                }
            });
        }

        // Toggle default content
        function toggleDefaultContent(checkbox, textareaId) {
            const textarea = document.getElementById(textareaId);
            if (checkbox.checked) {
                textarea.classList.add('grayed-textarea');
                textarea.readOnly = true;
                // Load default content
                const defaultContentId = textareaId.replace('template_', 'default_content_');
                const defaultContent = document.getElementById(defaultContentId);
                if (defaultContent) {
                    textarea.value = defaultContent.textContent;
                }
            } else {
                textarea.classList.remove('grayed-textarea');
                textarea.readOnly = false;
            }
        }

        // Handle checkbox selection for export
        document.addEventListener('DOMContentLoaded', function() {
            const selectAllCheckbox = document.getElementById('selectAll');
            const pageCheckboxes = document.querySelectorAll('.page-checkbox');
            const exportSelectedBtn = document.getElementById('exportSelectedBtn');
            const exportSelectedForm = document.getElementById('exportSelectedForm');

            if (selectAllCheckbox && pageCheckboxes.length > 0) {
                // Handle select all checkbox
                selectAllCheckbox.addEventListener('change', function() {
                    pageCheckboxes.forEach(checkbox => {
                        checkbox.checked = this.checked;
                    });
                    updateExportButton();
                });

                // Handle individual checkboxes
                pageCheckboxes.forEach(checkbox => {
                    checkbox.addEventListener('change', function() {
                        const checkedBoxes = document.querySelectorAll('.page-checkbox:checked');
                        selectAllCheckbox.checked = checkedBoxes.length === pageCheckboxes.length;
                        selectAllCheckbox.indeterminate = checkedBoxes.length > 0 && checkedBoxes.length < pageCheckboxes.length;
                        updateExportButton();
                    });
                });

                // Handle export selected button
                if (exportSelectedBtn) {
                    exportSelectedBtn.addEventListener('click', function() {
                        const selectedCheckboxes = document.querySelectorAll('.page-checkbox:checked');
                        if (selectedCheckboxes.length === 0) {
                            alert('Please select at least one page to export.');
                            return;
                        }

                        // Add selected page IDs to form
                        selectedCheckboxes.forEach(checkbox => {
                            const input = document.createElement('input');
                            input.type = 'hidden';
                            input.name = 'selected_pages';
                            input.value = checkbox.value;
                            exportSelectedForm.appendChild(input);
                        });

                        // Submit the form
                        exportSelectedForm.submit();
                    });
                }
            }

            function updateExportButton() {
                const checkedBoxes = document.querySelectorAll('.page-checkbox:checked');
                if (checkedBoxes.length > 0 && exportSelectedBtn) {
                    exportSelectedBtn.style.display = 'inline-block';
                    exportSelectedBtn.textContent = `Export Selected (${checkedBoxes.length})`;
                } else if (exportSelectedBtn) {
                    exportSelectedBtn.style.display = 'none';
                }
            }
        });

        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        });
    </script>

    <!-- Import Modal -->
    <div class="modal fade" id="importModal" tabindex="-1" aria-labelledby="importModalLabel" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title" id="importModalLabel">Import Pages</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <form method="post" enctype="multipart/form-data" action="{{ url_for('pages') }}">
                    <input type="hidden" name="action" value="import">
                    <div class="modal-body">
                        <div class="mb-3">
                            <label for="importFile" class="form-label">Select JSON file to import</label>
                            <input type="file" class="form-control" id="importFile" name="import_file" accept=".json" required>
                            <div class="form-text">Upload a JSON file exported from this CMS.</div>
                        </div>
                        <div class="form-check">
                            <input class="form-check-input" type="checkbox" id="overwriteExisting" name="overwrite_existing">
                            <label class="form-check-label" for="overwriteExisting">
                                Overwrite existing pages with same slug
                            </label>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="submit" class="btn btn-primary">Import Pages</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</body>
</html>
    '''

    return render_template_string(template, pages=pages_list)

@app.route('/admin/pages/add', methods=['GET', 'POST'])
@login_required
def add_page():
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        title = request.form.get('title')
        slug = request.form.get('slug')

        if not title or not slug:
            flash('Title and slug are required', 'error')
            return redirect(url_for('add_page'))

        # Check if slug already exists
        cursor.execute('SELECT COUNT(*) FROM pages WHERE slug = ?', (slug,))
        if cursor.fetchone()[0] > 0:
            flash('Page slug already exists', 'error')
            return redirect(url_for('add_page'))

        # Create page
        cursor.execute('INSERT INTO pages (title, slug) VALUES (?, ?)', (title, slug))
        page_id = cursor.lastrowid

        # Add default templates to page
        cursor.execute('SELECT * FROM templates WHERE is_default = 1 ORDER BY sort_order')
        default_templates = cursor.fetchall()

        for template in default_templates:
            cursor.execute('INSERT INTO page_templates (page_id, template_id, sort_order) VALUES (?, ?, ?)',
                         (page_id, template['id'], template['sort_order']))

        db.commit()
        flash('Page created successfully', 'success')
        return redirect(url_for('edit_page', page_id=page_id))

    template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Add Page - Devall CMS Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar { min-height: calc(100vh - 56px); }
        .template-block { border: 1px solid #dee2e6; border-radius: 0.375rem; margin-bottom: 1rem; }
        .template-block-header { background-color: #f8f9fa; padding: 0.75rem 1rem; border-bottom: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center; }
        .sort-buttons { display: flex; gap: 0.25rem; }
        .use-default-checkbox { margin-right: 0.5rem; }
        .grayed-textarea { background-color: #f8f9fa !important; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">Devall CMS</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('pages') }}">Pages</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('templates') }}">Templates</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('users') }}">Users</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="bi bi-person-circle"></i> {{ session.get('username', 'Admin') }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-menu-item" href="{{ url_for('logout') }}">Logout</a></li>
                        </ul>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show mt-3">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}    
    
    
    <div class="row">
        <div class="col-md-8 mx-auto">
            <div class="card">
                <div class="card-header">
                    <h4>Add New Page</h4>
                </div>
                <div class="card-body">
                    <form method="post">
                        <div class="mb-3">
                            <label for="title" class="form-label">Page Title *</label>
                            <input type="text" class="form-control" id="title" name="title" required>
                        </div>
                        <div class="mb-3">
                            <label for="slug" class="form-label">Page Slug *</label>
                            <input type="text" class="form-control" id="slug" name="slug" required>
                            <div class="form-text">URL-friendly identifier, no spaces (e.g., about-us, contact)</div>
                        </div>
                        <div class="d-flex gap-2">
                            <button type="submit" class="btn btn-primary">Create Page</button>
                            <a href="{{ url_for('pages') }}" class="btn btn-secondary">Cancel</a>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
    
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Template block sorting
        function moveBlock(blockId, direction) {
            const block = document.getElementById('block-' + blockId);
            const container = block.parentElement;

            if (direction === 'up') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock) {
                    container.insertBefore(block, prevBlock);
                }
            } else {
                const nextBlock = block.nextElementSibling;
                if (nextBlock) {
                    container.insertBefore(nextBlock, block);
                }
            }

            // Update sort order inputs
            updateSortOrder(container);
        }

        function updateSortOrder(container) {
            const blocks = container.querySelectorAll('[id^="block-"]');
            blocks.forEach((block, index) => {
                const sortInput = block.querySelector('input[name^="sort_order_"]');
                if (sortInput) {
                    sortInput.value = index;
                }
            });
        }

        // Toggle default content
        function toggleDefaultContent(checkbox, textareaId) {
            const textarea = document.getElementById(textareaId);
            if (checkbox.checked) {
                textarea.classList.add('grayed-textarea');
                textarea.readOnly = true;
                // Load default content
                const defaultContentId = textareaId.replace('template_', 'default_content_');
                const defaultContent = document.getElementById(defaultContentId);
                if (defaultContent) {
                    textarea.value = defaultContent.textContent;
                }
            } else {
                textarea.classList.remove('grayed-textarea');
                textarea.readOnly = false;
            }
        }

        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        });
    </script>
</body>
</html>
    '''

    return render_template_string(template)

@app.route('/admin/pages/<int:page_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_page(page_id):
    db = get_db()
    cursor = db.cursor()

    # Get page info
    cursor.execute('SELECT * FROM pages WHERE id = ?', (page_id,))
    page = cursor.fetchone()

    if not page:
        flash('Page not found', 'error')
        return redirect(url_for('pages'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'save':
            # Update page templates
            cursor.execute('SELECT pt.id, pt.template_id, pt.use_default, pt.sort_order FROM page_templates pt WHERE pt.page_id = ? ORDER BY pt.sort_order', (page_id,))
            existing_templates = cursor.fetchall()

            for pt in existing_templates:
                template_key = f'template_{pt["template_id"]}'
                use_default = request.form.get(f'use_default_{pt["template_id"]}') == 'on'
                custom_content = request.form.get(template_key, '')
                sort_order = request.form.get(f'sort_order_{pt["template_id"]}', 0)

                cursor.execute('UPDATE page_templates SET custom_content = ?, use_default = ?, sort_order = ? WHERE id = ?',
                             (custom_content, use_default, sort_order, pt['id']))

            db.commit()
            flash('Page saved successfully', 'success')

        elif action == 'publish':
            # Generate static HTML
            generate_page_html(page_id)
            cursor.execute('UPDATE pages SET published = 1 WHERE id = ?', (page_id,))
            db.commit()
            flash('Page published successfully', 'success')

        return redirect(url_for('edit_page', page_id=page_id))

    # Get page templates
    cursor.execute('''
        SELECT pt.id, pt.template_id, pt.custom_content, pt.use_default, pt.sort_order,
               t.title, t.slug, t.content as default_content, t.category
        FROM page_templates pt
        JOIN templates t ON pt.template_id = t.id
        WHERE pt.page_id = ?
        ORDER BY pt.sort_order
    ''', (page_id,))
    page_templates = cursor.fetchall()

    # Get hide system blocks setting
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('hide_system_blocks',))
    setting = cursor.fetchone()
    hide_system_blocks = setting and setting['value'] == '1'

    template = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Edit Page - Devall CMS Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        .sidebar { min-height: calc(100vh - 56px); }
        .template-block { border: 1px solid #dee2e6; border-radius: 0.375rem; margin-bottom: 1rem; }
        .template-block-header { background-color: #f8f9fa; padding: 0.75rem 1rem; border-bottom: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center; }
        .sort-buttons { display: flex; gap: 0.25rem; }
        .use-default-checkbox { margin-right: 0.5rem; }
        .grayed-textarea { background-color: #f8f9fa !important; }
        .system-block-hidden { opacity: 0.6; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="{{ url_for('admin_dashboard') }}">Devall CMS</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('admin_dashboard') }}">Dashboard</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('pages') }}">Pages</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('templates') }}">Templates</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('users') }}">Users</a></li>
                    <li class="nav-item"><a class="nav-link" href="{{ url_for('settings') }}">Settings</a></li>
                </ul>
                <ul class="navbar-nav">
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="bi bi-person-circle"></i> {{ session.get('username', 'Admin') }}
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-menu-item" href="{{ url_for('logout') }}">Logout</a></li>
                        </ul>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show mt-3">
                                {{ message }}
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}    
    
    
    <div class="row">
        <div class="col-12">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h1>Edit Page: {{ page.title }}</h1>
                <div class="d-flex gap-2 align-items-center">
                    <a href="{{ url_for('pages') }}" class="btn btn-outline-secondary rounded-pill">
                        <i class="bi bi-arrow-left"></i> Back to Pages
                    </a>
                    <button type="submit" form="pageForm" class="btn btn-primary rounded-pill">
                        <i class="bi bi-save"></i> Save Page
                    </button>
                    <a href="{{ url_for('preview_page', page_id=page.id) }}" class="btn btn-outline-info rounded-pill" target="_blank">
                        <i class="bi bi-eye"></i> Preview
                    </a>
                    <form method="post" class="d-inline">
                        <input type="hidden" name="action" value="publish">
                        <button type="submit" class="btn btn-success rounded-pill">
                            <i class="bi bi-upload"></i> Publish
                        </button>
                    </form>
                    <a href="{{ url_for('delete_page', page_id=page.id) }}" class="btn btn-outline-danger rounded-pill"
                       onclick="return confirm('Are you sure you want to delete this page?')">
                        <i class="bi bi-trash"></i> Delete
                    </a>
                </div>
            </div>
        </div>
    </div>

    <form method="post" id="pageForm">
        <input type="hidden" name="action" value="save">

        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5>Page Templates</h5>
                        <button type="button" id="toggleSystemBlocks" class="btn btn-sm btn-outline-secondary">
                            <i class="bi bi-eye-slash"></i> Show System Blocks
                        </button>
                    </div>
                    <div class="card-body">
                        <div id="templateBlocks">
                            {% for pt in page_templates %}
                            <div class="template-block mb-3 system-block-{{ pt.category }}" id="block-{{ pt.template_id }}" {% if pt.category == 'system' and hide_system_blocks %}style="display: none;"{% endif %}>
                                <div class="template-block-header">
                                    <div class="d-flex justify-content-between align-items-center w-100">
                                        <div>
                                            <strong>{{ pt.title }}</strong>
                                            <span class="badge bg-{{ 'primary' if pt.category == 'system' else 'success' }} ms-2">{{ pt.category.title() }}</span>
                                        </div>
                                        <div class="sort-buttons">
                                            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="moveBlock({{ pt.template_id }}, 'up')">
                                                <i class="bi bi-chevron-up"></i>
                                            </button>
                                            <button type="button" class="btn btn-sm btn-outline-secondary" onclick="moveBlock({{ pt.template_id }}, 'down')">
                                                <i class="bi bi-chevron-down"></i>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                                <div class="p-3">
                                    <div class="mb-2">
                                        <div class="form-check">
                                            <input type="checkbox" class="form-check-input use-default-checkbox"
                                                   id="use_default_{{ pt.template_id }}" name="use_default_{{ pt.template_id }}"
                                                   {{ 'checked' if pt.use_default else '' }}
                                                   onchange="toggleDefaultContent(this, 'template_{{ pt.template_id }}')">
                                            <label class="form-check-label" for="use_default_{{ pt.template_id }}">
                                                Use default template content
                                            </label>
                                        </div>
                                    </div>
                                    <input type="hidden" name="sort_order_{{ pt.template_id }}" value="{{ pt.sort_order }}">
                                    <textarea class="form-control {{ 'grayed-textarea' if pt.use_default else '' }}"
                                              id="template_{{ pt.template_id }}" name="template_{{ pt.template_id }}"
                                              rows="8" {{ 'readonly' if pt.use_default else '' }}>{{ pt.custom_content if not pt.use_default else pt.default_content }}</textarea>
                                    <div id="default_content_{{ pt.template_id }}" style="display: none;">{{ pt.default_content }}</div>
                                </div>
                            </div>
                            {% endfor %}
                        </div>

                    </div>
                </div>
            </div>
        </div>
    </form>
    
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Template block sorting
        function moveBlock(blockId, direction) {
            const block = document.getElementById('block-' + blockId);
            const container = block.parentElement;

            if (direction === 'up') {
                const prevBlock = block.previousElementSibling;
                if (prevBlock) {
                    container.insertBefore(block, prevBlock);
                }
            } else {
                const nextBlock = block.nextElementSibling;
                if (nextBlock) {
                    container.insertBefore(nextBlock, block);
                }
            }

            // Update sort order inputs
            updateSortOrder(container);
        }

        function updateSortOrder(container) {
            const blocks = container.querySelectorAll('[id^="block-"]');
            blocks.forEach((block, index) => {
                const sortInput = block.querySelector('input[name^="sort_order_"]');
                if (sortInput) {
                    sortInput.value = index;
                }
            });
        }

        // Toggle default content
        function toggleDefaultContent(checkbox, textareaId) {
            const textarea = document.getElementById(textareaId);
            if (checkbox.checked) {
                textarea.classList.add('grayed-textarea');
                textarea.readOnly = true;
                // Load default content
                const defaultContentId = textareaId.replace('template_', 'default_content_');
                const defaultContent = document.getElementById(defaultContentId);
                if (defaultContent) {
                    textarea.value = defaultContent.textContent;
                }
            } else {
                textarea.classList.remove('grayed-textarea');
                textarea.readOnly = false;
            }
        }

        // Handle system blocks toggle
        document.addEventListener('DOMContentLoaded', function() {
            const toggleBtn = document.getElementById('toggleSystemBlocks');
            const systemBlocks = document.querySelectorAll('.system-block-system');
            let systemBlocksHidden = {{ 'true' if hide_system_blocks else 'false' }};

            function updateToggleButton() {
                if (systemBlocksHidden) {
                    toggleBtn.innerHTML = '<i class="bi bi-eye-slash"></i> Show System Blocks';
                    toggleBtn.classList.remove('btn-outline-success');
                    toggleBtn.classList.add('btn-outline-secondary');
                } else {
                    toggleBtn.innerHTML = '<i class="bi bi-eye"></i> Hide System Blocks';
                    toggleBtn.classList.remove('btn-outline-secondary');
                    toggleBtn.classList.add('btn-outline-success');
                }
            }

            if (toggleBtn) {
                // Set initial state
                updateToggleButton();

                toggleBtn.addEventListener('click', function() {
                    systemBlocksHidden = !systemBlocksHidden;

                    systemBlocks.forEach(block => {
                        if (systemBlocksHidden) {
                            block.style.display = 'none';
                        } else {
                            block.style.display = 'block';
                        }
                    });

                    updateToggleButton();
                });
            }
        });

        // Initialize tooltips
        document.addEventListener('DOMContentLoaded', function() {
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        });
    </script>
</body>
</html>
    '''

    return render_template_string(template, page=page, page_templates=page_templates, hide_system_blocks=hide_system_blocks)

@app.route('/admin/pages/<int:page_id>/preview')
@login_required
def preview_page(page_id):
    return generate_page_html(page_id, preview=True)

@app.route('/admin/pages/<int:page_id>/publish')
@login_required
def publish_page(page_id):
    db = get_db()
    cursor = db.cursor()

    # Generate static HTML
    generate_page_html(page_id)

    # Update published status
    cursor.execute('UPDATE pages SET published = 1 WHERE id = ?', (page_id,))
    db.commit()

    flash('Page published successfully', 'success')
    return redirect(url_for('pages'))

@app.route('/admin/pages/<int:page_id>/delete')
@login_required
def delete_page(page_id):
    db = get_db()
    cursor = db.cursor()

    # Delete associated HTML file if it exists
    cursor.execute('SELECT slug FROM pages WHERE id = ?', (page_id,))
    page = cursor.fetchone()
    if page:
        html_file = os.path.join('pub', f'{page["slug"]}.html')
        if os.path.exists(html_file):
            os.remove(html_file)

    # Delete from database
    cursor.execute('DELETE FROM pages WHERE id = ?', (page_id,))
    db.commit()

    flash('Page deleted successfully', 'success')
    return redirect(url_for('pages'))

def generate_page_html(page_id, preview=False):
    """Generate static HTML for a page"""
    db = get_db()
    cursor = db.cursor()

    # Get page info
    cursor.execute('SELECT * FROM pages WHERE id = ?', (page_id,))
    page = cursor.fetchone()

    if not page:
        return "Page not found", 404

    # Get page templates
    cursor.execute('''
        SELECT pt.custom_content, pt.use_default, t.content as default_content, t.slug
        FROM page_templates pt
        JOIN templates t ON pt.template_id = t.id
        WHERE pt.page_id = ?
        ORDER BY pt.sort_order
    ''', (page_id,))
    page_templates = cursor.fetchall()

    # Build HTML content
    html_content = ''
    for pt in page_templates:
        content = pt['default_content'] if pt['use_default'] else pt['custom_content']
        html_content += content

    if preview:
        # Return HTML directly for preview
        return html_content
    else:
        # Save to file
        os.makedirs('pub', exist_ok=True)
        filename = os.path.join('pub', f'{page["slug"]}.html')

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return redirect(url_for('pages'))

# Main entry point
if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=4400)

