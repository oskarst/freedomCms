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

    # New master tables: page and blog templates (split)
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
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blog_template_defs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
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

    # Blog categories
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blog_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL
        )
    ''')

    # Blog posts
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blog_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            content TEXT,
            excerpt TEXT,
            featured_image_url TEXT,
            featured BOOLEAN DEFAULT 0,
            published BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migration: add featured_image_url if missing
    try:
        cursor.execute('SELECT featured_image_url FROM blog_posts LIMIT 1')
    except sqlite3.OperationalError:
        cursor.execute('ALTER TABLE blog_posts ADD COLUMN featured_image_url TEXT')

    # Blog post categories mapping
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blog_post_categories (
            post_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            PRIMARY KEY (post_id, category_id),
            FOREIGN KEY (post_id) REFERENCES blog_posts (id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES blog_categories (id) ON DELETE CASCADE
        )
    ''')

    # Blog post templates mapping (similar to page_templates)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blog_post_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            template_id INTEGER NOT NULL,
            custom_content TEXT,
            use_default BOOLEAN DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES blog_posts (id) ON DELETE CASCADE,
            FOREIGN KEY (template_id) REFERENCES blog_template_defs (id) ON DELETE CASCADE
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        ('blog_posts_per_page', '10', 'Blog posts per page for index pagination'),
        ('media_small_width', '320', 'Media small width (px)'),
        ('media_medium_width', '640', 'Media medium width (px)'),
        ('media_large_width', '1024', 'Media large width (px)'),
        ('blog_index_base_header_slug', 'base_header', 'Blog index: slug for base header template'),
        ('blog_index_meta_slug', 'meta', 'Blog index: slug for meta template'),
        ('blog_index_header_close_slug', 'header_close', 'Blog index: slug for header close template'),
        ('blog_index_menu_slug', 'menu', 'Blog index: slug for menu template'),
        ('blog_index_content_slug', 'index_content', 'Blog index: slug for main content template'),
        ('blog_index_footer_slug', 'footer', 'Blog index: slug for footer template'),
        ('blog_index_body_close_slug', 'body_close', 'Blog index: slug for body close template'),
    ]
    for key, value, desc in default_settings:
        cursor.execute('INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)',
                     (key, value, desc))

    # Migrate legacy blog index slug values with 'blog_' prefix to new slugs
    legacy_map = {
        'blog_base_header': 'base_header',
        'blog_meta': 'meta',
        'blog_header_close': 'header_close',
        'blog_menu': 'menu',
        'blog_index_content': 'index_content',
        'blog_footer': 'footer',
        'blog_body_close': 'body_close',
    }
    for setting_key in ['blog_index_base_header_slug','blog_index_meta_slug','blog_index_header_close_slug','blog_index_menu_slug','blog_index_content_slug','blog_index_footer_slug','blog_index_body_close_slug']:
        cursor.execute('SELECT value FROM settings WHERE key = ?', (setting_key,))
        row = cursor.fetchone()
        if row and row['value'] and row['value'] in legacy_map:
            cursor.execute('UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?', (legacy_map[row['value']], setting_key))

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
        cursor.execute('INSERT OR IGNORE INTO page_template_defs (title, slug, category, content, is_default, sort_order) VALUES (?, ?, ?, ?, ?, ?)',
                     (title, slug, category, content, is_default, sort_order))

    # Insert default blog templates
    blog_templates = [
        ('Blog Base Header', 'base_header', 'system', '<!DOCTYPE html>\n<html lang="en">\n<head>', 1, 1),
        ('Blog Meta Tags', 'meta', 'system', '    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>Blog</title>', 1, 2),
        ('Blog Header Close', 'header_close', 'system', '    <!-- Bootstrap CSS -->\n    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">\n    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.8.1/font/bootstrap-icons.css" rel="stylesheet">\n    <!-- Custom styles for blog pages -->\n    <style>\n        body { padding-top: 20px; }\n        .navbar-brand { font-weight: bold; }\n        .template-block { margin-bottom: 2rem; }\n        section { padding: 3rem 0; }\n    </style>\n</head>\n<body>', 1, 3),
        ('Blog Menu', 'menu', 'content', '    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">\n        <div class="container">\n            <a class="navbar-brand" href="/blog/index.html">Devall Blog</a>\n            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNavBlog">\n                <span class="navbar-toggler-icon"></span>\n            </button>\n            <div class="collapse navbar-collapse" id="navbarNavBlog">\n                <ul class="navbar-nav me-auto">\n                    <li class="nav-item"><a class="nav-link" href="/blog/index.html">Home</a></li>\n                </ul>\n            </div>\n        </div>\n    </nav>', 1, 4),
        ('Blog Index Content', 'index_content', 'content', '    <div class="container py-4">\n        <div class="row">\n            <div class="col-lg-8">\n                <h1>Latest Blog Posts</h1>\n                {{ posts|safe }}\n            </div>\n            <div class="col-lg-4">\n                <h4>Categories</h4>\n                <ul>\n                    {{ categories|safe }}\n                </ul>\n            </div>\n        </div>\n    </div>', 1, 5),
        ('Blog Paragraph', 'paragraph', 'content', '    <section class="py-4">\n        <div class="container">\n            <div class="row">\n                <div class="col-lg-10 mx-auto">\n                    <p>{{ title }}</p>\n                    <p>{{ content }}</p>\n                </div>\n            </div>\n        </div>\n    </section>', 1, 6),
        ('Blog Footer', 'footer', 'content', '    <footer class="bg-dark text-white py-4 mt-5">\n        <div class="container">\n            <div class="row">\n                <div class="col-md-6">\n                    <p>&copy; 2024 Devall Blog. All rights reserved.</p>\n                </div>\n                <div class="col-md-6 text-end">\n                    <p>Powered by <a href="#" class="text-white">Devall CMS</a></p>\n                </div>\n            </div>\n        </div>\n    </footer>', 1, 7),
        ('Blog Body Close', 'body_close', 'system', '</body>\n</html>', 1, 8),
    ]
    for title, slug, category, content, is_default, sort_order in blog_templates:
        cursor.execute('INSERT OR IGNORE INTO blog_template_defs (title, slug, category, content, is_default, sort_order) VALUES (?, ?, ?, ?, ?, ?)',
                     (title, slug, category, content, is_default, sort_order))


    # Migration: move existing templates rows into split tables and update junctions
    cursor.execute('SELECT id, title, slug, category, content, is_default, sort_order FROM templates')
    legacy = cursor.fetchall()
    old_to_new_page = {}
    old_to_new_blog = {}
    for row in legacy:
        tid = row['id']
        title = row['title']
        slug = row['slug']
        category = row['category']
        content = row['content']
        is_default = row['is_default']
        sort_order = row['sort_order']
        if slug.startswith('blog_'):
            new_slug = slug[5:] or slug
            cursor.execute('INSERT OR IGNORE INTO blog_template_defs (title, slug, category, content, is_default, sort_order) VALUES (?, ?, ?, ?, ?, ?)',
                           (title, new_slug, category, content, is_default, sort_order))
            cursor.execute('SELECT id FROM blog_template_defs WHERE slug = ?', (new_slug,))
            new_id = cursor.fetchone()['id']
            old_to_new_blog[tid] = new_id
        else:
            new_slug = slug
            cursor.execute('INSERT OR IGNORE INTO page_template_defs (title, slug, category, content, is_default, sort_order) VALUES (?, ?, ?, ?, ?, ?)',
                           (title, new_slug, category, content, is_default, sort_order))
            cursor.execute('SELECT id FROM page_template_defs WHERE slug = ?', (new_slug,))
            new_id = cursor.fetchone()['id']
            old_to_new_page[tid] = new_id

    # Update junction tables to point to new ids
    for old_id, new_id in old_to_new_page.items():
        cursor.execute('UPDATE page_templates SET template_id = ? WHERE template_id = ?', (new_id, old_id))
    for old_id, new_id in old_to_new_blog.items():
        cursor.execute('UPDATE blog_post_templates SET template_id = ? WHERE template_id = ?', (new_id, old_id))

    db.commit()
