#!/usr/bin/env python3
"""
Pages blueprint for Devall CMS
"""

import json
import re
import sqlite3
from flask import Blueprint, request, redirect, url_for, render_template, flash, session
from ..auth import login_required
from ..db import get_db
from ..utils import slugify
from ..services.publisher import generate_page_html

bp = Blueprint('pages', __name__)

def cleanup_old_previews(page_id, current_filename=None):
    """Clean up old preview files for a page"""
    import os
    import glob
    from ..db import PUB_DIR
    
    # Remove old preview files for this page, but not the current one
    preview_dir = os.path.join(PUB_DIR, 'preview')
    pattern = os.path.join(preview_dir, f'preview_{page_id}_*.html')
    old_files = glob.glob(pattern)
    for file_path in old_files:
        # Don't delete the current file
        if current_filename and os.path.basename(file_path) == current_filename:
            continue
        try:
            os.remove(file_path)
        except OSError:
            pass  # File might already be deleted

def extract_parameters_from_content(content):
    """Extract parameter names and types from template content like {{ Content1 }}, {{ Title:wysiwyg }}, etc."""
    if not content:
        return []
    
    # Find all {{ parameter_name:type }} or {{ parameter_name }} patterns
    # First, skip system shortcodes that have complex patterns
    system_patterns = [
        r'\{\{\s*(?:page|blog|config):[^}]+\}\}',  # {{page:title}}, {{blog:latest}}, {{config:base_url}}
        r'\{\{\s*if\s+[^}]+\}\}',  # {{if page:featured}}
    ]
    
    for pattern in system_patterns:
        content = re.sub(pattern, '', content)
    
    # Now find remaining parameters
    pattern = r'\{\{\s*([^}:]+)(?::([^}]+))?\s*\}\}'
    matches = re.findall(pattern, content)
    
    # Remove duplicates while preserving order, extract parameter info
    seen = set()
    unique_matches = []
    for match in matches:
        param_name = match[0].strip()
        param_type = match[1].strip() if match[1] else 'text'  # Default to 'text' if no type specified
        
        
        # Create parameter info dict
        param_info = {
            'name': param_name,
            'type': param_type,
            'full_name': f"{param_name}:{param_type}" if param_type != 'text' else param_name
        }
        
        if param_name not in seen:
            seen.add(param_name)
            unique_matches.append(param_info)
    
    return unique_matches

def has_parameters(content):
    """Check if content has any parameters"""
    return len(extract_parameters_from_content(content)) > 0

def get_template_parameters(db, page_template_id):
    """Get all parameters for a page template"""
    cursor = db.cursor()
    cursor.execute('''
        SELECT parameter_name, parameter_value 
        FROM page_template_parameters 
        WHERE page_template_id = ?
    ''', (page_template_id,))
    return {row['parameter_name']: row['parameter_value'] for row in cursor.fetchall()}

def save_template_parameters(db, page_template_id, parameters):
    """Save parameters for a page template"""
    cursor = db.cursor()
    
    # Delete existing parameters
    cursor.execute('DELETE FROM page_template_parameters WHERE page_template_id = ?', (page_template_id,))
    
    # Insert new parameters
    for param_name, param_value in parameters.items():
        cursor.execute('''
            INSERT INTO page_template_parameters (page_template_id, parameter_name, parameter_value)
            VALUES (?, ?, ?)
        ''', (page_template_id, param_name, param_value))
    
    db.commit()

@bp.route('/pages', methods=['GET', 'POST'])
@login_required
def pages():
    """List all pages"""
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_category' and (request.args.get('type') or 'page') == 'blog':
            # Add a new blog category
            title = (request.form.get('new_category') or '').strip()
            if title:
                base_slug = slugify(title) or 'category'
                # Ensure unique slug by appending -2, -3, ... if needed
                slug = base_slug
                attempt = 2
                # Determine next sort order
                cursor.execute('SELECT COALESCE(MAX(sort_order), 0) AS maxo FROM blog_categories')
                next_order = (cursor.fetchone()['maxo'] or 0) + 1
                # Try insert, handle unique slug race by retrying with incremented suffix
                while True:
                    try:
                        # Primary insert using (title, slug, sort_order)
                        cursor.execute('INSERT INTO blog_categories (title, slug, sort_order) VALUES (?, ?, ?)', (title or slug, slug, next_order))
                        db.commit()
                        flash('Category added', 'success')
                        break
                    except sqlite3.IntegrityError as e:
                        msg = str(e)
                        # If slug unique constraint, increment and retry
                        if 'UNIQUE' in msg and 'slug' in msg:
                            slug = f"{base_slug}-{attempt}"
                            attempt += 1
                            continue
                        # If legacy schema requires name NOT NULL, insert including name column
                        if 'NOT NULL' in msg and 'blog_categories.name' in msg:
                            try:
                                cursor.execute('INSERT INTO blog_categories (name, title, slug, sort_order) VALUES (?, ?, ?, ?)', (title or slug, title or slug, slug, next_order))
                                db.commit()
                                flash('Category added', 'success')
                                break
                            except Exception as e2:
                                db.rollback()
                                flash(f'Failed to add category: {str(e2)}', 'error')
                                break
                        db.rollback()
                        flash(f'Failed to add category: {msg}', 'error')
                        break
                    except Exception as e:
                        db.rollback()
                        flash(f'Failed to add category: {str(e)}', 'error')
                        break
            return redirect(url_for('pages.pages', type='blog'))
        if action == 'delete_category' and (request.args.get('type') or 'page') == 'blog':
            try:
                category_id = int(request.form.get('category_id'))
                # Remove mappings first to ensure clean delete regardless of FK settings
                cursor.execute('DELETE FROM page_blog_categories WHERE category_id = ?', (category_id,))
                cursor.execute('DELETE FROM blog_categories WHERE id = ?', (category_id,))
                db.commit()
                flash('Category deleted', 'success')
            except Exception:
                flash('Failed to delete category', 'error')
            return redirect(url_for('pages.pages', type='blog'))
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

            # Preserve the current page type context after import
            current_type = request.args.get('type', 'page')
            return redirect(url_for('pages.pages', type=current_type))

    # Filter by page type (defaults to 'page')
    page_type = request.args.get('type') or 'page'
    if page_type == 'blog':
        # Load blog pages first and fetch before running another query on the same cursor
        cursor.execute('''
            SELECT p.*, g.title AS template_group_title
            FROM pages p
            LEFT JOIN template_groups g ON g.id = p.template_group_id
            WHERE p.type = ?
            ORDER BY p.created_at DESC
        ''', (page_type,))
        pages_list = cursor.fetchall()
        # Load blog categories for management UI
        cursor.execute("SELECT id, COALESCE(NULLIF(title, ''), slug) as title, slug, sort_order FROM blog_categories ORDER BY sort_order, title")
        blog_categories = cursor.fetchall()
    else:
        cursor.execute('''
            SELECT p.*, g.title AS template_group_title
            FROM pages p
            LEFT JOIN template_groups g ON g.id = p.template_group_id
            WHERE p.type = 'page'
            ORDER BY p.created_at DESC
        ''')
        pages_list = cursor.fetchall()
        blog_categories = []

    return render_template('pages/pages.html', pages=pages_list, page_type=page_type, blog_categories=blog_categories)

@bp.route('/pages/export')
@login_required
def export_pages():
    """Export all pages to JSON (optionally filtered by type)"""
    db = get_db()
    cursor = db.cursor()
    page_type = request.args.get('type')

    # Get all pages with their templates
    base_query = '''
        SELECT
            p.id, p.title, p.slug, p.published, p.mode, p.created_at, p.updated_at, p.template_group_id, p.type, p.author, p.published_date,
            pt.id as pt_id, pt.template_id, pt.title as pt_title, pt.custom_content, pt.use_default, pt.sort_order,
            t.title as template_title, t.slug as template_slug, t.category, t.default_parameters,
            tg.title as template_group_title
        FROM pages p
        LEFT JOIN page_templates pt ON p.id = pt.page_id
        LEFT JOIN page_template_defs t ON pt.template_id = t.id
        LEFT JOIN template_groups tg ON p.template_group_id = tg.id
    '''
    if page_type:
        cursor.execute(base_query + ' WHERE p.type = ? ORDER BY p.id, pt.sort_order', (page_type,))
    else:
        cursor.execute(base_query + ' ORDER BY p.id, pt.sort_order')

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
                'mode': row['mode'] if 'mode' in row.keys() else 'simple',
                'type': row['type'] if 'type' in row.keys() else 'page',
                'author': row['author'] if 'author' in row.keys() else None,
                'published_date': row['published_date'] if 'published_date' in row.keys() else None,
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
                'templates': [],
                'template_group_id': row['template_group_id'],
                'template_group_title': row['template_group_title']
            }

        if row['pt_id']:  # Only add if there's a page template
            # Get parameters for this template
            cursor.execute('''
                SELECT parameter_name, parameter_value 
                FROM page_template_parameters 
                WHERE page_template_id = ?
            ''', (row['pt_id'],))
            parameters = {row['parameter_name']: row['parameter_value'] for row in cursor.fetchall()}
            
            pages_data[page_id]['templates'].append({
                'id': row['pt_id'],
                'template_id': row['template_id'],
                'template_title': row['template_title'],
                'template_slug': row['template_slug'],
                'title': row['pt_title'],
                'custom_content': row['custom_content'] or '',
                'use_default': row['use_default'],
                'sort_order': row['sort_order'],
                'parameters': parameters,
                'default_parameters': row['default_parameters'] or '{}'
            })

    # Convert to list
    export_data = list(pages_data.values())

    # Return JSON response
    from flask import Response
    response = Response(
        response=json.dumps(export_data, indent=2, default=str),
        status=200,
        mimetype='application/json'
    )
    filename = f"pages_export_{page_type}.json" if page_type else 'pages_export.json'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

@bp.route('/pages/export/selected', methods=['POST'])
@login_required
def export_selected_pages():
    """Export selected pages to JSON"""
    selected_page_ids = request.form.getlist('selected_pages')

    if not selected_page_ids:
        flash('No pages selected for export', 'warning')
        return redirect(url_for('pages.pages'))

    db = get_db()
    cursor = db.cursor()

    # Convert to integers for SQL query
    page_ids = [int(pid) for pid in selected_page_ids]

    # Get selected pages with their templates
    placeholders = ','.join('?' * len(page_ids))
    cursor.execute(f'''
        SELECT
            p.id, p.title, p.slug, p.published, p.mode, p.created_at, p.updated_at, p.template_group_id,
            pt.id as pt_id, pt.template_id, pt.title as pt_title, pt.custom_content, pt.use_default, pt.sort_order,
            t.title as template_title, t.slug as template_slug, t.category, t.default_parameters,
            tg.title as template_group_title
        FROM pages p
        LEFT JOIN page_templates pt ON p.id = pt.page_id
        LEFT JOIN page_template_defs t ON pt.template_id = t.id
        LEFT JOIN template_groups tg ON p.template_group_id = tg.id
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
                'mode': row['mode'] if 'mode' in row.keys() else 'simple',
                'type': row['type'] if 'type' in row.keys() else 'page',
                'author': row['author'] if 'author' in row.keys() else None,
                'published_date': row['published_date'] if 'published_date' in row.keys() else None,
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
                'templates': [],
                'template_group_id': row['template_group_id'],
                'template_group_title': row['template_group_title']
            }

        if row['pt_id']:  # Only add if there's a page template
            # Get parameters for this template
            cursor.execute('''
                SELECT parameter_name, parameter_value 
                FROM page_template_parameters 
                WHERE page_template_id = ?
            ''', (row['pt_id'],))
            parameters = {row['parameter_name']: row['parameter_value'] for row in cursor.fetchall()}
            
            pages_data[page_id]['templates'].append({
                'id': row['pt_id'],
                'template_id': row['template_id'],
                'template_title': row['template_title'],
                'template_slug': row['template_slug'],
                'title': row['pt_title'],
                'custom_content': row['custom_content'] or '',
                'use_default': row['use_default'],
                'sort_order': row['sort_order'],
                'parameters': parameters,
                'default_parameters': row['default_parameters'] or '{}'
            })

    # Convert to list
    export_data = list(pages_data.values())

    # Return JSON response
    from flask import Response
    response = Response(
        response=json.dumps(export_data, indent=2, default=str),
        status=200,
        mimetype='application/json'
    )
    response.headers['Content-Disposition'] = f'attachment; filename=selected_pages_export.json'
    return response

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
                # Delete parameters first (due to foreign key constraints)
                cursor.execute('''
                    DELETE FROM page_template_parameters 
                    WHERE page_template_id IN (
                        SELECT id FROM page_templates WHERE page_id = ?
                    )
                ''', (existing_page['id'],))
                cursor.execute('DELETE FROM page_templates WHERE page_id = ?', (existing_page['id'],))
                cursor.execute('DELETE FROM pages WHERE id = ?', (existing_page['id'],))

            # Try to find template group by title if specified
            template_group_id = None
            if 'template_group_title' in page_data and page_data['template_group_title']:
                cursor.execute('SELECT id FROM template_groups WHERE title = ?', (page_data['template_group_title'],))
                row = cursor.fetchone()
                if row:
                    template_group_id = row['id']

            # Insert new page
            cursor.execute('''
                INSERT INTO pages (title, slug, published, mode, type, template_group_id, author, published_date, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                page_data['title'],
                page_data['slug'],
                page_data.get('published', 0),
                page_data.get('mode', 'simple'),
                page_data.get('type', 'page'),
                template_group_id,
                page_data.get('author'),
                page_data.get('published_date'),
                page_data.get('created_at', '2024-01-01T00:00:00'),
                page_data.get('updated_at', '2024-01-01T00:00:00')
            ))

            page_id = cursor.lastrowid

            # Insert page templates
            if 'templates' in page_data:
                for template_data in page_data['templates']:
                    # Prefer mapping by slug; fallback to ID only if slug missing
                    template_id = None
                    template_slug = template_data.get('template_slug')
                    if template_slug:
                        cursor.execute('SELECT id FROM page_template_defs WHERE slug = ?', (template_slug,))
                        row = cursor.fetchone()
                        if row:
                            template_id = row['id']
                    if template_id is None and 'template_id' in template_data:
                        cursor.execute('SELECT id FROM page_template_defs WHERE id = ?', (template_data['template_id'],))
                        row = cursor.fetchone()
                        if row:
                            template_id = row['id']

                    if template_id is not None:
                        cursor.execute('''
                            INSERT INTO page_templates (page_id, template_id, title, custom_content, use_default, sort_order)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (
                            page_id,
                            template_id,
                            template_data.get('title', ''),
                            template_data.get('custom_content', ''),
                            template_data.get('use_default', 1),
                            template_data.get('sort_order', 0)
                        ))
                        
                        # Get the page template ID for parameter insertion
                        page_template_id = cursor.lastrowid
                        
                        # Import parameters if they exist
                        if 'parameters' in template_data and template_data['parameters']:
                            for param_name, param_value in template_data['parameters'].items():
                                cursor.execute('''
                                    INSERT INTO page_template_parameters (page_template_id, parameter_name, parameter_value)
                                    VALUES (?, ?, ?)
                                ''', (page_template_id, param_name, param_value))
                    else:
                        print(f"Warning: Template not found (slug={template_slug}, id={template_data.get('template_id')}). Skipping for page {page_data.get('slug')}")

            imported_count += 1

        except Exception as e:
            print(f"Error importing page {page_data.get('slug', 'unknown')}: {str(e)}")
            continue

    return imported_count

@bp.route('/pages/add', methods=['GET', 'POST'])
@login_required
def add_page():
    """Add new page"""
    db = get_db()
    cursor = db.cursor()
    default_type = request.args.get('type') or 'page'

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        slug_input = request.form.get('slug', '').strip()
        template_group_id = request.form.get('template_group_id', type=int)

        if not title:
            entity_label = 'Blog' if default_type == 'blog' else 'Page'
            flash(f'{entity_label} title is required', 'error')
            return redirect(url_for('pages.add_page', type=default_type))

        # Generate slug if not provided
        if not slug_input:
            slug_input = slugify(title)

        # Check if slug already exists
        cursor.execute('SELECT id FROM pages WHERE slug = ?', (slug_input,))
        if cursor.fetchone():
            entity_label = 'Blog' if default_type == 'blog' else 'Page'
            flash(f'{entity_label} with this slug already exists', 'error')
            return redirect(url_for('pages.add_page', type=default_type))

        # Insert new page with default values for blog fields
        page_type = default_type if default_type in ('page', 'blog') else 'page'
        if page_type == 'blog':
            # Set default author to current user's name and published_date to current date for blogs
            from flask import session
            username = session.get('username', 'admin')
            cursor.execute('SELECT name FROM users WHERE username = ?', (username,))
            user_row = cursor.fetchone()
            user_name = user_row['name'] if user_row and user_row['name'] else username
            cursor.execute('INSERT INTO pages (title, slug, mode, template_group_id, type, author, published_date) VALUES (?, ?, ?, ?, ?, ?, date("now"))', 
                         (title, slug_input, 'simple', template_group_id, page_type, user_name))
        else:
            cursor.execute('INSERT INTO pages (title, slug, mode, template_group_id, type) VALUES (?, ?, ?, ?, ?)', 
                         (title, slug_input, 'simple', template_group_id, page_type))
        page_id = cursor.lastrowid

        # If a template group was selected, add its blocks to the page
        if template_group_id:
            cursor.execute('''
                SELECT d.id, d.title, d.default_parameters, tgb.sort_order
                FROM template_group_blocks tgb
                JOIN page_template_defs d ON d.id = tgb.template_id
                WHERE tgb.group_id = ?
                ORDER BY tgb.sort_order
            ''', (template_group_id,))
            group_blocks = cursor.fetchall()

            for block in group_blocks:
                # Insert block into page
                cursor.execute('''
                    INSERT INTO page_templates (page_id, template_id, title, sort_order)
                    VALUES (?, ?, ?, ?)
                ''', (page_id, block['id'], block['title'], block['sort_order']))

                # Get the new page template ID
                page_template_id = cursor.lastrowid

                # Create default parameters if they exist
                try:
                    import json
                    default_parameters = json.loads(block['default_parameters'] or '{}')
                    if default_parameters:
                        for param_name, param_value in default_parameters.items():
                            cursor.execute('''
                                INSERT INTO page_template_parameters (page_template_id, parameter_name, parameter_value)
                                VALUES (?, ?, ?)
                            ''', (page_template_id, param_name, param_value))
                except (json.JSONDecodeError, TypeError):
                    # Invalid JSON or empty parameters, skip
                    pass
        else:
            # Fallback: add default template group if no template group selected
            if default_type == 'blog':
                cursor.execute("SELECT id FROM template_groups WHERE is_default_blog = 1 LIMIT 1")
            else:
                cursor.execute("SELECT id FROM template_groups WHERE is_default_page = 1 LIMIT 1")
            
            default_group = cursor.fetchone()
            if default_group:
                # Add blocks from the default template group
                cursor.execute('''
                    SELECT d.id, d.title, d.default_parameters, tgb.sort_order
                    FROM template_group_blocks tgb
                    JOIN page_template_defs d ON d.id = tgb.template_id
                    WHERE tgb.group_id = ?
                    ORDER BY tgb.sort_order
                ''', (default_group['id'],))
                group_blocks = cursor.fetchall()

                for block in group_blocks:
                    # Insert block into page
                    cursor.execute('''
                        INSERT INTO page_templates (page_id, template_id, title, sort_order)
                        VALUES (?, ?, ?, ?)
                    ''', (page_id, block['id'], block['title'], block['sort_order']))

                    # Get the new page template ID
                    page_template_id = cursor.lastrowid

                    # Create default parameters if they exist
                    try:
                        import json
                        default_parameters = json.loads(block['default_parameters'] or '{}')
                        if default_parameters:
                            for param_name, param_value in default_parameters.items():
                                cursor.execute('''
                                    INSERT INTO page_template_parameters (page_template_id, parameter_name, parameter_value)
                                    VALUES (?, ?, ?)
                                ''', (page_template_id, param_name, param_value))
                    except (json.JSONDecodeError, TypeError):
                        # Invalid JSON or empty parameters, skip
                        pass

        db.commit()
        entity_label = 'Blog' if default_type == 'blog' else 'Page'
        flash(f'{entity_label} created successfully', 'success')
        return redirect(url_for('pages.edit_page', page_id=page_id))

    # Load available template groups
    cursor.execute('SELECT id, title FROM template_groups ORDER BY title')
    template_groups = cursor.fetchall()
    
    # Find the default template group for preselection
    default_template_id = None
    if default_type == 'blog':
        cursor.execute('SELECT id FROM template_groups WHERE is_default_blog = 1 LIMIT 1')
        default_template = cursor.fetchone()
        if default_template:
            default_template_id = default_template['id']
    else:
        cursor.execute('SELECT id FROM template_groups WHERE is_default_page = 1 LIMIT 1')
        default_template = cursor.fetchone()
        if default_template:
            default_template_id = default_template['id']

    return render_template('pages/add.html', template_groups=template_groups, page_type=default_type, default_template_id=default_template_id)

@bp.route('/pages/<int:page_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_page(page_id):
    """Edit existing page"""
    db = get_db()
    cursor = db.cursor()

    # Get page info
    cursor.execute('SELECT * FROM pages WHERE id = ?', (page_id,))
    page = cursor.fetchone()

    if not page:
        flash('Page not found', 'error')
        return redirect(url_for('pages.pages'))

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'toggle_mode':
            # Toggle between simple and advanced mode
            current_mode = page['mode'] if 'mode' in page.keys() else 'simple'
            new_mode = 'advanced' if current_mode == 'simple' else 'simple'
            cursor.execute('UPDATE pages SET mode = ? WHERE id = ?', (new_mode, page_id))
            db.commit()
            flash(f'Switched to {new_mode.title()} mode', 'success')
            return redirect(url_for('pages.edit_page', page_id=page_id))

        elif action == 'remove_featured':
            # Remove featured image from blog post
            page_type = page['type'] if 'type' in page.keys() else 'page'
            if page_type == 'blog':
                # Get current featured image paths to delete files
                current_png = page['featured_png'] if 'featured_png' in page.keys() else None
                current_webp = page['featured_webp'] if 'featured_webp' in page.keys() else None
                
                # Remove featured image paths from database
                cursor.execute('UPDATE pages SET featured_png = NULL, featured_webp = NULL WHERE id = ?', (page_id,))
                
                # Delete image files if they exist (both full size and thumbnails)
                if current_png or current_webp:
                    try:
                        import os
                        from ..db import PUB_DIR
                        if current_png:
                            # Delete full size PNG
                            png_file = os.path.join(PUB_DIR, current_png.lstrip('/'))
                            if os.path.exists(png_file):
                                os.remove(png_file)
                            # Delete thumbnail PNG
                            thumb_png_file = png_file.replace('.png', '-thumb.png')
                            if os.path.exists(thumb_png_file):
                                os.remove(thumb_png_file)
                        if current_webp:
                            # Delete full size WebP
                            webp_file = os.path.join(PUB_DIR, current_webp.lstrip('/'))
                            if os.path.exists(webp_file):
                                os.remove(webp_file)
                            # Delete thumbnail WebP
                            thumb_webp_file = webp_file.replace('.webp', '-thumb.webp')
                            if os.path.exists(thumb_webp_file):
                                os.remove(thumb_webp_file)
                    except Exception:
                        pass  # Ignore file deletion errors
                
                db.commit()
                flash('Featured image removed successfully', 'success')
            return redirect(url_for('pages.edit_page', page_id=page_id))

        elif action == 'save':
            # Update page title and slug
            page_title = request.form.get('page_title', '').strip()
            page_slug = request.form.get('page_slug', '').strip()
            # Blog container flag
            is_blog_container = 1 if request.form.get('is_blog_container') == 'on' else 0
            # Excerpt (blog only)
            page_excerpt = request.form.get('page_excerpt', '').strip()
            # Author and published date (blog only)
            page_author = request.form.get('page_author', '').strip()
            page_published_date = request.form.get('page_published_date', '').strip()
            # Custom CSS (pages and blogs)
            page_custom_css = request.form.get('page_custom_css', '').strip()
            
            if not page_title:
                flash('Page title is required', 'error')
                return redirect(url_for('pages.edit_page', page_id=page_id))
            
            if not page_slug:
                flash('Page slug is required', 'error')
                return redirect(url_for('pages.edit_page', page_id=page_id))
            
            # Check if slug already exists (excluding current page)
            cursor.execute('SELECT id FROM pages WHERE slug = ? AND id != ?', (page_slug, page_id))
            if cursor.fetchone():
                flash('Page with this slug already exists', 'error')
                return redirect(url_for('pages.edit_page', page_id=page_id))
            
            # Handle featured image upload (blogs only)
            featured_png = None
            featured_webp = None
            try:
                page_type = page['type'] if 'type' in page.keys() else 'page'
                if page_type == 'blog' and 'featured_image' in request.files:
                    file = request.files.get('featured_image')
                    if file and file.filename:
                        from PIL import Image
                        import uuid, os
                        from ..db import PUB_DIR
                        img = Image.open(file.stream).convert('RGB')
                        
                        # Create unique filename
                        unique = f"featured-{uuid.uuid4().hex[:10]}"
                        out_dir = os.path.join(PUB_DIR, 'blog', 'content')
                        os.makedirs(out_dir, exist_ok=True)
                        
                        # Save full size images (max 1600x1600)
                        full_img = img.copy()
                        full_img.thumbnail((1600, 1600))
                        png_path = os.path.join(out_dir, f"{unique}.png")
                        webp_path = os.path.join(out_dir, f"{unique}.webp")
                        full_img.save(png_path, format='PNG', optimize=True)
                        full_img.save(webp_path, format='WEBP', quality=85, method=6)
                        
                        # Generate thumbnail (max 300x300)
                        thumb_img = img.copy()
                        thumb_img.thumbnail((300, 300))
                        thumb_png_path = os.path.join(out_dir, f"{unique}-thumb.png")
                        thumb_webp_path = os.path.join(out_dir, f"{unique}-thumb.webp")
                        thumb_img.save(thumb_png_path, format='PNG', optimize=True)
                        thumb_img.save(thumb_webp_path, format='WEBP', quality=85, method=6)
                        
                        featured_png = f"/blog/content/{unique}.png"
                        featured_webp = f"/blog/content/{unique}.webp"
                        flash(f'Featured image uploaded successfully: {unique}', 'success')
            except Exception as e:
                flash(f'Failed to upload featured image: {str(e)}', 'error')

            # Update page title, slug, blog container flag, excerpt, author, published_date and featured image paths
            if featured_png or featured_webp:
                cursor.execute('UPDATE pages SET title = ?, slug = ?, is_blog_container = ?, excerpt = ?, author = ?, published_date = ?, custom_css = ?, featured_png = ?, featured_webp = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', 
                             (page_title, page_slug, is_blog_container, page_excerpt, page_author, page_published_date, page_custom_css, featured_png, featured_webp, page_id))
            else:
                cursor.execute('UPDATE pages SET title = ?, slug = ?, is_blog_container = ?, excerpt = ?, author = ?, published_date = ?, custom_css = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', 
                             (page_title, page_slug, is_blog_container, page_excerpt, page_author, page_published_date, page_custom_css, page_id))
            
            # Update page templates
            cursor.execute('SELECT pt.id, pt.template_id, pt.use_default, pt.sort_order FROM page_templates pt WHERE pt.page_id = ? ORDER BY pt.sort_order', (page_id,))
            existing_templates = cursor.fetchall()

            for pt in existing_templates:
                template_key = f'template_{pt["id"]}'
                title_key = f'title_{pt["id"]}'
                use_default = request.form.get(f'use_default_{pt["id"]}') == 'on'
                custom_content = request.form.get(template_key, '')
                custom_title = request.form.get(title_key, '')
                sort_order = request.form.get(f'sort_order_{pt["id"]}', 0)

                # In Simple mode, preserve existing content and only update parameters
                current_page_mode = page['mode'] if 'mode' in page.keys() else 'simple'
                if current_page_mode == 'simple':
                    # In Simple mode, ensure use_default is set to 1 if no custom content
                    if not custom_content.strip():
                        cursor.execute('UPDATE page_templates SET title = ?, use_default = 1, sort_order = ? WHERE id = ?',
                                     (custom_title, sort_order, pt['id']))
                    else:
                        cursor.execute('UPDATE page_templates SET title = ?, custom_content = ?, use_default = 0, sort_order = ? WHERE id = ?',
                                     (custom_title, custom_content, sort_order, pt['id']))
                else:
                    # Advanced mode: update everything
                    if use_default:
                        # When using default, don't save custom_content - always use current default template
                        cursor.execute('UPDATE page_templates SET title = ?, custom_content = NULL, use_default = ?, sort_order = ? WHERE id = ?',
                                     (custom_title, use_default, sort_order, pt['id']))
                    else:
                        # When using custom content, save the custom content
                        cursor.execute('UPDATE page_templates SET title = ?, custom_content = ?, use_default = ?, sort_order = ? WHERE id = ?',
                                     (custom_title, custom_content, use_default, sort_order, pt['id']))
                
                # Handle nested block parameters (works in both modes)
                if current_page_mode == 'simple':
                    # In Simple mode, get current template content to check for parameters
                    cursor.execute('SELECT custom_content, use_default FROM page_templates WHERE id = ?', (pt['id'],))
                    current_template = cursor.fetchone()
                    if current_template:
                        if current_template['use_default']:
                            # Use default content from template definition
                            cursor.execute('SELECT content FROM page_template_defs WHERE id = ?', (pt['template_id'],))
                            template_def = cursor.fetchone()
                            content_to_check = template_def['content'] if template_def else ''
                        else:
                            # Use custom content
                            content_to_check = current_template['custom_content'] or ''
                    else:
                        content_to_check = ''
                else:
                    # Advanced mode: use appropriate content based on use_default
                    if use_default:
                        # When using default, always use current default template content for parameters
                        cursor.execute('SELECT content FROM page_template_defs WHERE id = ?', (pt['template_id'],))
                        template_def = cursor.fetchone()
                        content_to_check = template_def['content'] if template_def else ''
                    else:
                        # When using custom content, use the custom content from form
                        content_to_check = custom_content if custom_content else ''
                
                if content_to_check and has_parameters(content_to_check):
                    parameters = {}
                    param_info_list = extract_parameters_from_content(content_to_check)
                    for param_info in param_info_list:
                        param_key = f'param_{pt["id"]}_{param_info["name"]}'
                        param_value = request.form.get(param_key, '')
                        parameters[param_info["name"]] = param_value
                    save_template_parameters(db, pt['id'], parameters)

            # If blog page, save categories mapping
            current_page_type = page['type'] if 'type' in page.keys() else 'page'
            if current_page_type == 'blog':
                cursor.execute('DELETE FROM page_blog_categories WHERE page_id = ?', (page_id,))
                selected = request.form.getlist('category_ids')
                for cid in selected:
                    try:
                        cursor.execute('INSERT INTO page_blog_categories (page_id, category_id) VALUES (?, ?)', (page_id, int(cid)))
                    except Exception:
                        continue

            db.commit()
            flash('Page saved successfully', 'success')

        elif action == 'publish':
            # Generate static HTML
            generate_page_html(page_id)
            cursor.execute('UPDATE pages SET published = 1 WHERE id = ?', (page_id,))
            db.commit()
            
            # Generate sitemap after successful publication
            try:
                from ..services.publisher import generate_sitemap
                generate_sitemap()
            except Exception:
                pass  # Don't fail the publish if sitemap generation fails
            
            flash('Page published successfully', 'success')

        elif action == 'add_template':
            # Add new template block to page
            template_id = request.form.get('template_id')
            
            if template_id:
                # Get template info for default title and parameters
                cursor.execute('SELECT title, default_parameters FROM page_template_defs WHERE id = ?', (template_id,))
                template_info = cursor.fetchone()
                default_title = template_info['title'] if template_info else 'Untitled Block'
                default_parameters_json = template_info['default_parameters'] if template_info else '{}'
                
                # Get next sort order
                cursor.execute('SELECT COALESCE(MAX(sort_order), 0) as maxo FROM page_templates WHERE page_id = ?', (page_id,))
                max_order_row = cursor.fetchone()
                next_order = (max_order_row['maxo'] or 0) + 1
                
                # Insert new page template (allow multiple instances of same template)
                cursor.execute('''
                    INSERT INTO page_templates (page_id, template_id, title, use_default, sort_order)
                    VALUES (?, ?, ?, 1, ?)
                ''', (page_id, template_id, default_title, next_order))
                
                # Get the new page template ID
                page_template_id = cursor.lastrowid
                
                # Create default parameters if they exist
                try:
                    import json
                    default_parameters = json.loads(default_parameters_json)
                    if default_parameters:
                        for param_name, param_value in default_parameters.items():
                            cursor.execute('''
                                INSERT INTO page_template_parameters (page_template_id, parameter_name, parameter_value)
                                VALUES (?, ?, ?)
                            ''', (page_template_id, param_name, param_value))
                except (json.JSONDecodeError, TypeError):
                    # Invalid JSON or empty parameters, skip
                    pass
                
                db.commit()
                flash('Template block added successfully', 'success')
            else:
                flash('Please select a template to add', 'error')

        elif action == 'remove_template':
            # Remove template block from page
            page_template_id = request.form.get('page_template_id')
            if page_template_id:
                # Delete the template block (system blocks are now allowed to be deleted)
                cursor.execute('DELETE FROM page_templates WHERE id = ? AND page_id = ?', (page_template_id, page_id))
                db.commit()
                flash('Template block removed successfully', 'success')
            else:
                flash('Invalid template ID', 'error')

        # Redirect based on action and page type
        if action == 'save':
            # After saving, stay on the same edit page
            return redirect(url_for('pages.edit_page', page_id=page_id))
        else:
            # For other actions (add_template, remove_template, toggle_mode), stay on edit page
            return redirect(url_for('pages.edit_page', page_id=page_id))

    # Only ensure default templates are present if this is a new page with no templates
    cursor.execute('SELECT COUNT(*) as count FROM page_templates WHERE page_id = ?', (page_id,))
    template_count = cursor.fetchone()['count']
    
    if template_count == 0:
        # This is a new page, add all default templates
        cursor.execute("SELECT id FROM page_template_defs WHERE is_default = 1 ORDER BY sort_order")
        default_ids = [row['id'] for row in cursor.fetchall()]

        if default_ids:
            next_order = 1
            for tid in default_ids:
                # Get template title for default
                cursor.execute('SELECT title FROM page_template_defs WHERE id = ?', (tid,))
                template_info = cursor.fetchone()
                default_title = template_info['title'] if template_info else 'Untitled Block'
                
                cursor.execute('''
                    INSERT INTO page_templates (page_id, template_id, title, use_default, sort_order)
                    VALUES (?, ?, ?, 1, ?)
                ''', (page_id, tid, default_title, next_order))
                next_order += 1
            db.commit()

    # Get page templates
    cursor.execute('''
        SELECT pt.id, pt.template_id, pt.title as custom_title, pt.custom_content, pt.use_default, pt.sort_order,
               t.title, t.slug, t.content as default_content, t.category
        FROM page_templates pt
        JOIN page_template_defs t ON pt.template_id = t.id
        WHERE pt.page_id = ?
        ORDER BY pt.sort_order
    ''', (page_id,))
    page_templates = cursor.fetchall()
    
    # Add parameters to each page template
    page_templates_with_params = []
    for pt in page_templates:
        # Convert Row to dict to allow modifications
        pt_dict = dict(pt)
        pt_dict['parameters'] = get_template_parameters(db, pt['id'])
        content_to_check = pt['custom_content'] or pt['default_content']
        pt_dict['has_parameters'] = has_parameters(content_to_check)
        pt_dict['parameter_info'] = extract_parameters_from_content(content_to_check)
        # Keep backward compatibility
        pt_dict['parameter_names'] = [param['name'] for param in pt_dict['parameter_info']]
        page_templates_with_params.append(pt_dict)
    
    page_templates = page_templates_with_params

    # Get all available page templates for the dropdown
    cursor.execute('SELECT id, title, slug, category FROM page_template_defs ORDER BY category, title')
    available_templates = cursor.fetchall()

    # Load template group label for this page
    cursor.execute('SELECT title FROM template_groups WHERE id = ?', (page['template_group_id'],))
    grp = cursor.fetchone()
    page_template_label = grp['title'] if grp else None

    # If blog page, load categories and selected
    blog_categories = []
    selected_categories = []
    current_page_type = page['type'] if 'type' in page.keys() else 'page'
    if current_page_type == 'blog':
        cursor.execute("SELECT id, COALESCE(NULLIF(title, ''), slug) as title FROM blog_categories ORDER BY sort_order, title")
        blog_categories = cursor.fetchall()
        cursor.execute('SELECT category_id FROM page_blog_categories WHERE page_id = ?', (page_id,))
        selected_categories = [row['category_id'] for row in cursor.fetchall()]

    # Get base_url from settings
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('base_url',))
    base_url_row = cursor.fetchone()
    base_url = base_url_row['value'] if base_url_row else 'http://localhost:5000'

    return render_template('pages/edit.html', page=page, page_templates=page_templates, available_templates=available_templates, page_template_label=page_template_label, blog_categories=blog_categories, selected_categories=selected_categories, base_url=base_url)

@bp.route('/pages/<int:page_id>/delete', methods=['POST'])
@login_required
def delete_page(page_id):
    """Delete page"""
    db = get_db()
    cursor = db.cursor()

    # Check if page exists
    cursor.execute('SELECT title, type FROM pages WHERE id = ?', (page_id,))
    page = cursor.fetchone()

    if not page:
        flash('Page not found', 'error')
        return redirect(url_for('pages.pages'))

    # Delete page (cascade will delete page_templates)
    cursor.execute('DELETE FROM pages WHERE id = ?', (page_id,))
    db.commit()

    flash(f'Page "{page["title"]}" deleted successfully', 'success')
    
    # Redirect based on page type
    page_type = page['type'] if 'type' in page.keys() else 'page'
    if page_type == 'blog':
        return redirect(url_for('pages.pages', type='blog'))
    else:
        return redirect(url_for('pages.pages', type='page'))

@bp.route('/pages/delete-all', methods=['POST'])
@login_required
def delete_all_pages():
    """Delete all pages"""
    db = get_db()
    cursor = db.cursor()

    # Get count of pages before deletion
    cursor.execute('SELECT COUNT(*) FROM pages')
    page_count = cursor.fetchone()[0]

    if page_count == 0:
        flash('No pages to delete', 'info')
        return redirect(url_for('pages.pages'))

    # Delete all pages (cascade will delete page_templates and page_template_parameters)
    cursor.execute('DELETE FROM pages')
    db.commit()

    flash(f'All {page_count} pages deleted successfully', 'success')
    return redirect(url_for('pages.pages'))

@bp.route('/pages/<int:page_id>/duplicate', methods=['POST'])
@login_required
def duplicate_page(page_id):
    """Duplicate page"""
    db = get_db()
    cursor = db.cursor()

    # Get the original page
    cursor.execute('SELECT * FROM pages WHERE id = ?', (page_id,))
    original_page = cursor.fetchone()

    if not original_page:
        flash('Page not found', 'error')
        return redirect(url_for('pages.pages'))

    # Generate new title and slug
    new_title = f"{original_page['title']} (Copy)"
    new_slug = f"{original_page['slug']}-copy"
    
    # Ensure slug is unique
    counter = 1
    while True:
        cursor.execute('SELECT id FROM pages WHERE slug = ?', (new_slug,))
        if not cursor.fetchone():
            break
        new_slug = f"{original_page['slug']}-copy-{counter}"
        counter += 1

    # Create the new page
    cursor.execute('''
        INSERT INTO pages (title, slug, published, mode, created_at, updated_at)
        VALUES (?, ?, 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ''', (new_title, new_slug, original_page['mode'] if 'mode' in original_page.keys() else 'simple'))
    
    new_page_id = cursor.lastrowid

    # Get all page templates from the original page
    cursor.execute('''
        SELECT pt.id, pt.template_id, pt.title, pt.custom_content, pt.use_default, pt.sort_order
        FROM page_templates pt
        WHERE pt.page_id = ?
        ORDER BY pt.sort_order
    ''', (page_id,))
    original_templates = cursor.fetchall()

    # Duplicate all page templates
    for template in original_templates:
        cursor.execute('''
            INSERT INTO page_templates (page_id, template_id, title, custom_content, use_default, sort_order)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (new_page_id, template['template_id'], template['title'], 
              template['custom_content'], template['use_default'], template['sort_order']))
        
        new_template_id = cursor.lastrowid
        
        # Get parameters for the original template
        cursor.execute('''
            SELECT parameter_name, parameter_value
            FROM page_template_parameters
            WHERE page_template_id = ?
        ''', (template['id'],))
        parameters = cursor.fetchall()
        
        # Duplicate parameters
        for param in parameters:
            cursor.execute('''
                INSERT INTO page_template_parameters (page_template_id, parameter_name, parameter_value)
                VALUES (?, ?, ?)
            ''', (new_template_id, param['parameter_name'], param['parameter_value']))

    db.commit()
    flash(f'Page "{original_page["title"]}" duplicated successfully as "{new_title}"', 'success')
    return redirect(url_for('pages.edit_page', page_id=new_page_id))

@bp.route('/pages/<int:page_id>/preview')
@login_required
def preview_page(page_id):
    """Preview page with proper CSS and JS support"""
    # Generate preview HTML and save it temporarily
    html_content = generate_page_html(page_id, preview=True)
    if isinstance(html_content, tuple):  # Error case
        flash(html_content[0], 'error')
        return redirect(url_for('pages.pages'))

    # Save preview to a temporary file in pub directory
    import tempfile
    import os
    from ..db import PUB_DIR
    
    # Create a temporary preview file
    preview_filename = f'preview_{page_id}_{session.get("csrf_token", "temp")}.html'
    preview_dir = os.path.join(PUB_DIR, 'preview')
    os.makedirs(preview_dir, exist_ok=True)
    preview_path = os.path.join(preview_dir, preview_filename)
    
    try:
        # Rewrite absolute image paths to relative paths for preview
        # This fixes the issue where /img/image.jpg should be ./img/image.jpg in preview
        html_content = html_content.replace('src="/img/', 'src="./img/')
        html_content = html_content.replace('href="/img/', 'href="./img/')
        
        with open(preview_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
    except Exception as e:
        flash(f'Error creating preview: {str(e)}', 'error')
        return redirect(url_for('pages.pages'))
    
    # Clean up old preview files for this user
    cleanup_old_previews(page_id, preview_filename)
    
    # Redirect to the preview file served from pub directory
    from flask import redirect, url_for
    return redirect(f'/pub/preview/{preview_filename}')

@bp.route('/pages/<int:page_id>/publish', methods=['POST'])
@login_required
def publish_page(page_id):
    """Publish page"""
    result = generate_page_html(page_id)

    db = get_db()
    cursor = db.cursor()

    if isinstance(result, str):  # Success case - filename returned
        cursor.execute('UPDATE pages SET published = 1 WHERE id = ?', (page_id,))
        db.commit()
        # If this is a blog post, republish all blog container pages that are already published
        try:
            cursor.execute('SELECT type FROM pages WHERE id = ?', (page_id,))
            row = cursor.fetchone()
            page_type = row['type'] if row and 'type' in row.keys() else None
            if page_type == 'blog':
                cursor.execute('SELECT id FROM pages WHERE is_blog_container = 1 AND published = 1')
                containers = cursor.fetchall()
                for c in containers:
                    try:
                        generate_page_html(c['id'])
                    except Exception:
                        continue
        except Exception:
            pass
        
        # Generate sitemap after successful publication
        try:
            from ..services.publisher import generate_sitemap
            generate_sitemap()
        except Exception:
            pass  # Don't fail the publish if sitemap generation fails
        
        flash('Page published successfully', 'success')
    else:  # Error case
        flash('Failed to publish page', 'error')

    # If publish came from the list view, stay on list; otherwise go back to edit
    if request.form.get('from_list') == '1':
        # Preserve the current page type context after publishing
        current_type = request.form.get('page_type', 'page')
        return redirect(url_for('pages.pages', type=current_type))
    return redirect(url_for('pages.edit_page', page_id=page_id))

@bp.route('/pages/republish-all', methods=['POST'])
@login_required
def republish_all_pages():
    """Re-publish all pages to update them with latest template changes (optionally filtered by type)"""
    db = get_db()
    cursor = db.cursor()
    page_type = request.args.get('type')
    
    # Get all published pages
    if page_type:
        cursor.execute('SELECT id, title, slug FROM pages WHERE published = 1 AND type = ?', (page_type,))
    else:
        cursor.execute('SELECT id, title, slug FROM pages WHERE published = 1')
    published_pages = cursor.fetchall()
    
    if not published_pages:
        flash('No published pages found to republish', 'warning')
        return redirect(url_for('pages.pages', type=page_type))
    
    republished_count = 0
    errors = []
    
    for page in published_pages:
        try:
            # Generate HTML for the page
            generate_page_html(page['id'])
            republished_count += 1
        except Exception as e:
            errors.append(f"Page '{page['title']}': {str(e)}")
    
    # Generate sitemap after republishing
    try:
        from ..services.publisher import generate_sitemap
        generate_sitemap()
    except Exception:
        pass  # Don't fail the republish if sitemap generation fails
    
    if errors:
        flash(f'Republished {republished_count} pages. Errors: {"; ".join(errors)}', 'warning')
    else:
        label = 'blogs' if page_type == 'blog' else 'pages'
        flash(f'Successfully republished {republished_count} {label}', 'success')
    
    return redirect(url_for('pages.pages', type=page_type))

@bp.route('/pages/<int:page_id>/ai', methods=['POST'])
@login_required
def ai_generate_content(page_id):
    from flask import jsonify
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM pages WHERE id = ?', (page_id,))
    page = cursor.fetchone()
    if not page:
        return jsonify({'error': 'Page not found'}), 404

    prompt = request.form.get('prompt', '').strip()
    mode = request.form.get('mode', 'content')
    target_field = request.form.get('target_field', '')
    include_full_html = request.form.get('include_full_html') == '1'
    guidance = request.form.get('guidance', '').strip()

    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400

    try:
        from ..services.mcp import call_ai_model, MCPClientError
        context = None
        if include_full_html or mode == 'code':
            cursor.execute('''
                SELECT pt.custom_content, pt.use_default, t.content as default_content
                FROM page_templates pt
                JOIN page_template_defs t ON pt.template_id = t.id
                WHERE pt.page_id = ?
                ORDER BY pt.sort_order
            ''', (page_id,))
            blocks = cursor.fetchall()
            html_parts = []
            for block in blocks:
                content = block['default_content'] if block['use_default'] else block['custom_content']
                if content:
                    html_parts.append(content)
            context = '\n\n'.join(html_parts)
        if guidance:
            prompt = f"{prompt}\n\nGuidance: {guidance}"
        result = call_ai_model(prompt, mode=mode, context=context)
    except MCPClientError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify({'result': result, 'target_field': target_field})
