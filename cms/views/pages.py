#!/usr/bin/env python3
"""
Pages blueprint for Devall CMS
"""

import json
import re
from flask import Blueprint, request, redirect, url_for, render_template, flash, session
from ..auth import login_required
from ..db import get_db
from ..utils import slugify
from ..services.publisher import generate_page_html

bp = Blueprint('pages', __name__)

def extract_parameters_from_content(content):
    """Extract parameter names from template content like {{ Content1 }}, {{ Title }}, etc."""
    if not content:
        return []
    
    # Find all {{ parameter_name }} patterns
    pattern = r'\{\{\s*([^}]+)\s*\}\}'
    matches = re.findall(pattern, content)
    
    # Remove duplicates and return unique parameter names
    return list(set(matches))

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
        ORDER BY parameter_name
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

            return redirect(url_for('pages.pages'))

    cursor.execute('SELECT * FROM pages ORDER BY created_at DESC')
    pages_list = cursor.fetchall()

    return render_template('pages/pages.html', pages=pages_list)

@bp.route('/pages/export')
@login_required
def export_pages():
    """Export all pages to JSON"""
    db = get_db()
    cursor = db.cursor()

    # Get all pages with their templates
    cursor.execute('''
        SELECT
            p.id, p.title, p.slug, p.published, p.created_at, p.updated_at,
            pt.id as pt_id, pt.template_id, pt.title as pt_title, pt.custom_content, pt.use_default, pt.sort_order,
            t.title as template_title, t.slug as template_slug
        FROM pages p
        LEFT JOIN page_templates pt ON p.id = pt.page_id
        LEFT JOIN page_template_defs t ON pt.template_id = t.id
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
                'parameters': parameters
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
    response.headers['Content-Disposition'] = 'attachment; filename=pages_export.json'
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
            p.id, p.title, p.slug, p.published, p.created_at, p.updated_at,
            pt.id as pt_id, pt.template_id, pt.title as pt_title, pt.custom_content, pt.use_default, pt.sort_order,
            t.title as template_title, t.slug as template_slug
        FROM pages p
        LEFT JOIN page_templates pt ON p.id = pt.page_id
        LEFT JOIN page_template_defs t ON pt.template_id = t.id
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
                'parameters': parameters
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

            # Insert new page
            cursor.execute('''
                INSERT INTO pages (title, slug, published, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                page_data['title'],
                page_data['slug'],
                page_data.get('published', 0),
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

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        slug_input = request.form.get('slug', '').strip()

        if not title:
            flash('Page title is required', 'error')
            return redirect(url_for('pages.add_page'))

        # Generate slug if not provided
        if not slug_input:
            slug_input = slugify(title)

        # Check if slug already exists
        cursor.execute('SELECT id FROM pages WHERE slug = ?', (slug_input,))
        if cursor.fetchone():
            flash('Page with this slug already exists', 'error')
            return redirect(url_for('pages.add_page'))

        # Insert new page
        cursor.execute('INSERT INTO pages (title, slug) VALUES (?, ?)', (title, slug_input))
        page_id = cursor.lastrowid

        # Get all default PAGE templates and create page templates
        cursor.execute("SELECT id, sort_order FROM page_template_defs WHERE is_default = 1 ORDER BY sort_order")
        default_templates = cursor.fetchall()

        for template in default_templates:
            # Get template title
            cursor.execute('SELECT title FROM page_template_defs WHERE id = ?', (template['id'],))
            template_info = cursor.fetchone()
            default_title = template_info['title'] if template_info else 'Untitled Block'
            
            cursor.execute('''
                INSERT INTO page_templates (page_id, template_id, title, sort_order)
                VALUES (?, ?, ?, ?)
            ''', (page_id, template['id'], default_title, template['sort_order']))

        db.commit()
        flash('Page created successfully', 'success')
        return redirect(url_for('pages.edit_page', page_id=page_id))

    return render_template('pages/add.html')

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

        if action == 'save':
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

                cursor.execute('UPDATE page_templates SET title = ?, custom_content = ?, use_default = ?, sort_order = ? WHERE id = ?',
                             (custom_title, custom_content, use_default, sort_order, pt['id']))
                
                # Handle nested block parameters
                if custom_content and has_parameters(custom_content):
                    parameters = {}
                    param_names = extract_parameters_from_content(custom_content)
                    for param_name in param_names:
                        param_key = f'param_{pt["id"]}_{param_name}'
                        param_value = request.form.get(param_key, '')
                        parameters[param_name] = param_value
                    save_template_parameters(db, pt['id'], parameters)

            db.commit()
            flash('Page saved successfully', 'success')

        elif action == 'publish':
            # Generate static HTML
            generate_page_html(page_id)
            cursor.execute('UPDATE pages SET published = 1 WHERE id = ?', (page_id,))
            db.commit()
            flash('Page published successfully', 'success')

        elif action == 'add_template':
            # Add new template block to page
            template_id = request.form.get('template_id')
            
            if template_id:
                # Get template info for default title
                cursor.execute('SELECT title FROM page_template_defs WHERE id = ?', (template_id,))
                template_info = cursor.fetchone()
                default_title = template_info['title'] if template_info else 'Untitled Block'
                
                # Get next sort order
                cursor.execute('SELECT COALESCE(MAX(sort_order), 0) as maxo FROM page_templates WHERE page_id = ?', (page_id,))
                max_order_row = cursor.fetchone()
                next_order = (max_order_row['maxo'] or 0) + 1
                
                # Insert new page template (allow multiple instances of same template)
                cursor.execute('''
                    INSERT INTO page_templates (page_id, template_id, title, use_default, sort_order)
                    VALUES (?, ?, ?, 1, ?)
                ''', (page_id, template_id, default_title, next_order))
                db.commit()
                flash('Template block added successfully', 'success')
            else:
                flash('Please select a template to add', 'error')

        elif action == 'remove_template':
            # Remove template block from page
            page_template_id = request.form.get('page_template_id')
            if page_template_id:
                # Check if it's a system template (don't allow removal)
                cursor.execute('''
                    SELECT t.category FROM page_templates pt
                    JOIN page_template_defs t ON pt.template_id = t.id
                    WHERE pt.id = ? AND pt.page_id = ?
                ''', (page_template_id, page_id))
                template_info = cursor.fetchone()
                if template_info and template_info['category'] == 'system':
                    flash('Cannot remove system template blocks', 'error')
                else:
                    cursor.execute('DELETE FROM page_templates WHERE id = ? AND page_id = ?', (page_template_id, page_id))
                    db.commit()
                    flash('Template block removed successfully', 'success')
            else:
                flash('Invalid template ID', 'error')

        return redirect(url_for('pages.edit_page', page_id=page_id))

    # Ensure page has all default PAGE templates
    cursor.execute('SELECT template_id FROM page_templates WHERE page_id = ?', (page_id,))
    existing_ids = {row['template_id'] for row in cursor.fetchall()}

    cursor.execute("SELECT id FROM page_template_defs WHERE is_default = 1 ORDER BY sort_order")
    default_ids = [row['id'] for row in cursor.fetchall()]

    if default_ids:
        cursor.execute('SELECT COALESCE(MAX(sort_order), 0) as maxo FROM page_templates WHERE page_id = ?', (page_id,))
        max_order_row = cursor.fetchone()
        next_order = (max_order_row['maxo'] or 0) + 1
        to_insert = [tid for tid in default_ids if tid not in existing_ids]
        for tid in to_insert:
            # Get template title for default
            cursor.execute('SELECT title FROM page_template_defs WHERE id = ?', (tid,))
            template_info = cursor.fetchone()
            default_title = template_info['title'] if template_info else 'Untitled Block'
            
            cursor.execute('''
                INSERT INTO page_templates (page_id, template_id, title, use_default, sort_order)
                VALUES (?, ?, ?, 1, ?)
            ''', (page_id, tid, default_title, next_order))
            next_order += 1
        if to_insert:
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
        pt_dict['parameter_names'] = extract_parameters_from_content(content_to_check)
        page_templates_with_params.append(pt_dict)
    
    page_templates = page_templates_with_params

    # Get all available page templates for the dropdown
    cursor.execute('SELECT id, title, slug, category FROM page_template_defs ORDER BY category, title')
    available_templates = cursor.fetchall()

    return render_template('pages/edit.html', page=page, page_templates=page_templates, available_templates=available_templates)

@bp.route('/pages/<int:page_id>/delete', methods=['POST'])
@login_required
def delete_page(page_id):
    """Delete page"""
    db = get_db()
    cursor = db.cursor()

    # Check if page exists
    cursor.execute('SELECT title FROM pages WHERE id = ?', (page_id,))
    page = cursor.fetchone()

    if not page:
        flash('Page not found', 'error')
        return redirect(url_for('pages.pages'))

    # Delete page (cascade will delete page_templates)
    cursor.execute('DELETE FROM pages WHERE id = ?', (page_id,))
    db.commit()

    flash(f'Page "{page["title"]}" deleted successfully', 'success')
    return redirect(url_for('pages.pages'))

@bp.route('/pages/<int:page_id>/preview')
@login_required
def preview_page(page_id):
    """Preview page"""
    html_content = generate_page_html(page_id, preview=True)
    if isinstance(html_content, tuple):  # Error case
        flash(html_content[0], 'error')
        return redirect(url_for('pages.pages'))

    from flask import Response
    return Response(html_content, mimetype='text/html')

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
        flash('Page published successfully', 'success')
    else:  # Error case
        flash('Failed to publish page', 'error')

    # If publish came from the list view, stay on list; otherwise go back to edit
    if request.form.get('from_list') == '1':
        return redirect(url_for('pages.pages'))
    return redirect(url_for('pages.edit_page', page_id=page_id))
