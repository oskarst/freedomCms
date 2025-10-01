#!/usr/bin/env python3
"""
Database configuration and utilities for Devall CMS
"""

import os
import sqlite3
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash as _check_pwd
import secrets
from flask import g

# Application constants
APP_SECRET = secrets.token_hex(16)
DB_PATH = 'cms.db'
PUB_DIR = 'pub'

# Ensure pub directory exists
if not os.path.exists(PUB_DIR):
    os.makedirs(PUB_DIR)

# Ensure media directories exist
MEDIA_DIR = os.path.join(PUB_DIR, 'content', 'images')
if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR, exist_ok=True)

def get_db():
    """Database connection helper"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

def close_connection(exception):
    """Close database connection"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def hash_password(password):
    """Hash password using a secure algorithm (pbkdf2:sha256)"""
    return generate_password_hash(password)

def check_password(password, hashed):
    """Check password against secure hash"""
    return _check_pwd(hashed, password)

def init_db():
    """Initialize database with tables and default data"""
    db = get_db()
    cursor = db.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            name TEXT,
            role TEXT DEFAULT 'admin',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Add name column to existing users table if it doesn't exist
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN name TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

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

    # Master table: page templates
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS page_template_defs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            content TEXT,
            is_default BOOLEAN DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            default_parameters TEXT DEFAULT '{}'
        )
    ''')
    

    # Pages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            published BOOLEAN DEFAULT 0,
            mode TEXT DEFAULT 'simple',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add template_group_id to pages if missing
    try:
        cursor.execute('ALTER TABLE pages ADD COLUMN template_group_id INTEGER')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add type to pages if missing ('page' | 'blog')
    try:
        cursor.execute("ALTER TABLE pages ADD COLUMN type TEXT DEFAULT 'page'")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add is_blog_container to pages if missing
    try:
        cursor.execute('ALTER TABLE pages ADD COLUMN is_blog_container BOOLEAN DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add excerpt to pages if missing (used for blog type pages)
    try:
        cursor.execute('ALTER TABLE pages ADD COLUMN excerpt TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add featured image columns to pages if missing
    try:
        cursor.execute('ALTER TABLE pages ADD COLUMN featured_png TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cursor.execute('ALTER TABLE pages ADD COLUMN featured_webp TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add author and published_date columns to pages if missing (for blog type pages)
    try:
        cursor.execute('ALTER TABLE pages ADD COLUMN author TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cursor.execute('ALTER TABLE pages ADD COLUMN published_date TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add custom CSS column to pages if missing
    try:
        cursor.execute('ALTER TABLE pages ADD COLUMN custom_css TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add default template columns to template_groups if missing
    try:
        cursor.execute('ALTER TABLE template_groups ADD COLUMN is_default_page BOOLEAN DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cursor.execute('ALTER TABLE template_groups ADD COLUMN is_default_blog BOOLEAN DEFAULT 0')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Page templates junction table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS page_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER NOT NULL,
            template_id INTEGER NOT NULL,
            title TEXT,
            custom_content TEXT,
            use_default BOOLEAN DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (page_id) REFERENCES pages (id) ON DELETE CASCADE,
            FOREIGN KEY (template_id) REFERENCES page_template_defs (id) ON DELETE CASCADE
        )
    ''')
    
    # Page template parameters for nested blocks
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS page_template_parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_template_id INTEGER NOT NULL,
            parameter_name TEXT NOT NULL,
            parameter_value TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (page_template_id) REFERENCES page_templates (id) ON DELETE CASCADE
        )
    ''')

    # Template groups (collections of template blocks)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS template_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT '',
            is_default BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Template group membership/order
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS template_group_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            template_id INTEGER NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES template_groups (id) ON DELETE CASCADE,
            FOREIGN KEY (template_id) REFERENCES page_template_defs (id) ON DELETE CASCADE
        )
    ''')

    # Blog categories (used only for pages with type='blog')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blog_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Page to blog category mapping (many-to-many)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS page_blog_categories (
            page_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            PRIMARY KEY (page_id, category_id),
            FOREIGN KEY (page_id) REFERENCES pages (id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES blog_categories (id) ON DELETE CASCADE
        )
    ''')

    

    # Media library table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL, -- base filename without size suffix
            ext TEXT NOT NULL,
            title TEXT,
            alt TEXT,
            original_path TEXT NOT NULL,
            small_path TEXT,
            medium_path TEXT,
            large_path TEXT,
            original_webp_path TEXT,
            small_webp_path TEXT,
            medium_webp_path TEXT,
            large_webp_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add WebP columns to media table if they don't exist
    try:
        cursor.execute('ALTER TABLE media ADD COLUMN original_webp_path TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cursor.execute('ALTER TABLE media ADD COLUMN small_webp_path TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cursor.execute('ALTER TABLE media ADD COLUMN medium_webp_path TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        cursor.execute('ALTER TABLE media ADD COLUMN large_webp_path TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add page_id column to media table if it doesn't exist
    try:
        cursor.execute('ALTER TABLE media ADD COLUMN page_id INTEGER')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Insert default admin user if not exists
    cursor.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('admin',))
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO users (username, password_hash, email, name) VALUES (?, ?, ?, ?)',
                     ('admin', hash_password('admin123'), 'admin@devall.com', 'Administrator'))

    # Insert default settings
    default_settings = [
        ('site_name', 'Devall CMS', 'Site name displayed in admin'),
        ('site_description', 'A simple Flask CMS', 'Site description'),
        ('base_url', 'http://localhost:5000', 'Base URL for the site (used in {{config:base_url}} shortcode)'),
        ('admin_theme', 'light', 'Admin theme (light/dark)'),
        ('hide_system_blocks', '1', 'Hide system template blocks by default in page editor'),
        ('media_small_width', '320', 'Media small width (px)'),
        ('media_medium_width', '640', 'Media medium width (px)'),
        ('media_large_width', '1024', 'Media large width (px)'),
               ('blog_latest_template', '<li class="blog-latest-item">\n<a href="{href}">{title}</a>\n<div class="featured-image">{featured_image}</div>\n<div class="excerpt">{excerpt}</div>\n<a class="btn btn-filled btn-lg mb0" href="{href}">Read More</a>\n</li>', 'Template for {{blog:latest}} shortcode. Should contain only li elements - ul wrapper is added automatically.'),
        ('blog_articles_per_page', '20', 'Number of blog articles to display per page in {{blog:latest}} shortcode.'),
        ('ai_provider', 'openai', 'AI Provider identifier (e.g. openai)'),
        ('ai_api_url', 'https://api.openai.com/v1/chat/completions', 'AI API base URL'),
        ('ai_api_key', '', 'AI API key'),
        ('ai_monthly_budget', '20', 'Monthly AI usage budget in USD'),
        ('ai_model', 'gpt-4o-mini', 'AI model identifier (e.g. gpt-4o-mini)'),
        ('wysiwyg_stylesheets', '', 'Comma-separated list of stylesheet URLs to load in WYSIWYG preview'),
    ]
    for key, value, desc in default_settings:
        cursor.execute('INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)',
                     (key, value, desc))

    # Insert default template blocks (Page)
    default_templates = [
        ('Base Header', 'base_header', 'system', '''<!DOCTYPE html>
<html lang="en">
<head>''', 1, 1),
        ('Meta Tags', 'meta', 'system', '''    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="A simple Flask CMS">
    <title>Devall CMS</title>''', 1, 2),
        ('Header Close', 'header_close', 'system', '''    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">
    <!-- Custom styles for generated pages -->
    <style>
        body { padding-top: 20px; }
        .hero { margin-bottom: 2rem; }
        .navbar-brand { font-weight: bold; }
        footer { margin-top: 3rem; padding: 2rem 0; background-color: #f8f9fa; }
        .template-block { margin-bottom: 2rem; }
        section { padding: 3rem 0; }
    </style>
</head>
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
                <ul class="navbar-nav me-auto">
                    <li class="nav-item"><a class="navbar-brand" href="#" class="nav-link">Home</a></li>
                    <li class="nav-item"><a class="navbar-brand" href="#" class="nav-link">About</a></li>
                    <li class="nav-item"><a class="navbar-brand" href="#" class="nav-link">Contact</a></li>
                </ul>
            </div>
        </div>
    </nav>''', 1, 5),
        ('Content Section', 'content', 'content', '''    <section id="content" class="py-5">
        <div class="container">
            <div class="row">
                <div class="col-lg-10 mx-auto">
                    <h2>Content Section</h2>
                    <p>This is a sample content section. Edit this template to customize your page content.</p>
                </div>
            </div>
        </div>
    </section>''', 1, 6),
        ('Paragraph', 'paragraph', 'content', '''    <section class="py-4">
        <div class="container">
            <div class="row">
                <div class="col-lg-10 mx-auto">
                    <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.</p>
                </div>
            </div>
        </div>
    </section>''', 1, 7),
        ('Footer', 'footer', 'content', '''    <footer class="bg-dark text-white py-4 mt-5">
        <div class="container">
            <div class="row">
                <div class="col-md-6">
                    <p>&copy; 2024 Devall CMS. All rights reserved.</p>
                </div>
                <div class="col-md-6 text-end">
                    <p>Powered by <a href="#" class="text-white">Devall CMS</a></p>
                </div>
            </div>
        </div>
    </footer>''', 1, 8),
        ('Body Close', 'body_close', 'system', '</body>\n</html>', 1, 9),
    ]
    for title, slug, category, content, is_default, sort_order in default_templates:
        cursor.execute('INSERT OR IGNORE INTO page_template_defs (title, slug, category, content, is_default, sort_order, default_parameters) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (title, slug, category, content, is_default, sort_order, '{}'))

    # Migration: move existing templates rows into page_template_defs and update junctions
    cursor.execute('SELECT id, title, slug, category, content, is_default, sort_order FROM templates')
    legacy = cursor.fetchall()
    old_to_new_page = {}
    for row in legacy:
        tid = row['id']
        title = row['title']
        slug = row['slug']
        category = row['category']
        content = row['content']
        is_default = row['is_default']
        sort_order = row['sort_order']
        new_slug = slug
        cursor.execute('INSERT OR IGNORE INTO page_template_defs (title, slug, category, content, is_default, sort_order, default_parameters) VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (title, new_slug, category, content, is_default, sort_order, '{}'))
        cursor.execute('SELECT id FROM page_template_defs WHERE slug = ?', (new_slug,))
        new_id = cursor.fetchone()['id']
        old_to_new_page[tid] = new_id

    # Update junction tables to point to new ids
    for old_id, new_id in old_to_new_page.items():
        cursor.execute('UPDATE page_templates SET template_id = ? WHERE template_id = ?', (new_id, old_id))

    # Initialize a default template group if none exists: include all current blocks
    cursor.execute('SELECT COUNT(*) FROM template_groups')
    if (cursor.fetchone()[0] or 0) == 0:
        cursor.execute('INSERT INTO template_groups (title, slug, description, is_default) VALUES (?, ?, ?, ?)',
                       ('Default Template', 'default-template', 'Template built from current default blocks', 1))
        group_id = cursor.lastrowid
        cursor.execute('SELECT id FROM page_template_defs ORDER BY sort_order')
        rows = cursor.fetchall()
        order_index = 1
        for row in rows:
            cursor.execute('INSERT INTO template_group_blocks (group_id, template_id, sort_order) VALUES (?, ?, ?)',
                           (group_id, row['id'], order_index))
            order_index += 1

    db.commit()
