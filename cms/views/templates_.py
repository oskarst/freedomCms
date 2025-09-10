#!/usr/bin/env python3
"""
Templates blueprint for Devall CMS
"""

import json
from flask import Blueprint, request, redirect, url_for, render_template, flash, Response
from ..auth import login_required, admin_required
from ..db import get_db
from ..services.publisher import generate_page_html
from ..utils import slugify

bp = Blueprint('templates_', __name__)

@bp.route('/templates', methods=['GET', 'POST'])
@login_required
@admin_required
def templates():
    """List all templates"""
    db = get_db()
    cursor = db.cursor()

    # Handle import action
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'import':
            import_file = request.files.get('import_file')
            overwrite_existing = request.form.get('overwrite_existing') == 'on'

            if import_file and import_file.filename.endswith('.json'):
                try:
                    import_data = json.load(import_file)
                    imported_count = import_templates(import_data, overwrite_existing, cursor)
                    db.commit()
                    flash(f'Successfully imported {imported_count} template block(s)', 'success')
                except Exception as e:
                    db.rollback()
                    flash(f'Import failed: {str(e)}', 'error')
            else:
                flash('Please select a valid JSON file', 'error')

            return redirect(url_for('templates_.templates'))
    # Tab filtering: page | blog (using split master tables)
    active_tab = request.args.get('tab', 'page')
    if active_tab == 'page':
        cursor.execute('''
            SELECT t.*,
                   COUNT(CASE WHEN pt.use_default = 0 THEN 1 END) as override_count
            FROM page_template_defs t
            LEFT JOIN page_templates pt ON t.id = pt.template_id
            GROUP BY t.id
            ORDER BY t.sort_order
        ''')
    elif active_tab == 'blog':
        cursor.execute('''
            SELECT t.*,
                   COUNT(CASE WHEN bt.use_default = 0 THEN 1 END) as override_count
            FROM blog_template_defs t
            LEFT JOIN blog_post_templates bt ON t.id = bt.template_id
            GROUP BY t.id
            ORDER BY t.sort_order
        ''')
    templates_list = cursor.fetchall()

    return render_template('templates/templates.html', templates=templates_list, active_tab=active_tab)

@bp.route('/templates/export')
@login_required
@admin_required
def export_templates():
    """Export all template blocks to JSON"""
    db = get_db()
    cursor = db.cursor()
    tab = request.args.get('tab', 'page')
    table = 'page_template_defs' if tab == 'page' else 'blog_template_defs'
    cursor.execute(f'SELECT id, title, slug, category, content, is_default, sort_order, created_at, updated_at, default_parameters FROM {table} ORDER BY sort_order')
    rows = cursor.fetchall()

    export_data = [
        {
            'id': row['id'],
            'title': row['title'],
            'slug': row['slug'],
            'category': row['category'],
            'content': row['content'] or '',
            'is_default': row['is_default'],
            'sort_order': row['sort_order'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'default_parameters': row['default_parameters'] or '{}'
        }
        for row in rows
    ]

    data = json.dumps(export_data, indent=2, default=str)
    return Response(data, mimetype='application/json', headers={
        'Content-Disposition': 'attachment; filename=templates_export.json'
    })

@bp.route('/templates/export/selected', methods=['POST'])
@login_required
@admin_required
def export_selected_templates():
    """Export selected template blocks to JSON"""
    selected_ids = request.form.getlist('selected_templates')

    if not selected_ids:
        flash('No templates selected for export', 'warning')
        return redirect(url_for('templates_.templates'))

    db = get_db()
    tab = request.args.get('tab', 'page')
    table = 'page_template_defs' if tab == 'page' else 'blog_template_defs'
    cursor = get_db().cursor()
    ids = [int(tid) for tid in selected_ids]
    placeholders = ','.join('?' * len(ids))
    cursor.execute(f'SELECT id, title, slug, category, content, is_default, sort_order, created_at, updated_at, default_parameters FROM {table} WHERE id IN ({placeholders}) ORDER BY sort_order', ids)
    rows = cursor.fetchall()

    export_data = [
        {
            'id': row['id'],
            'title': row['title'],
            'slug': row['slug'],
            'category': row['category'],
            'content': row['content'] or '',
            'is_default': row['is_default'],
            'sort_order': row['sort_order'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'default_parameters': row['default_parameters'] or '{}'
        }
        for row in rows
    ]

    data = json.dumps(export_data, indent=2, default=str)
    return Response(data, mimetype='application/json', headers={
        'Content-Disposition': 'attachment; filename=selected_templates_export.json'
    })

def import_templates(import_data, overwrite_existing, cursor):
    """Import template blocks from JSON data"""
    imported_count = 0

    if not isinstance(import_data, list):
        raise ValueError('Invalid JSON format - expected array of templates')

    for t in import_data:
        try:
            slug = t.get('slug') or slugify(t.get('title', ''))
            if not slug:
                continue

            # Determine table by type flag (default page)
            ttype = t.get('template_type') or t.get('type') or 'page'
            table = 'page_template_defs' if ttype == 'page' else 'blog_template_defs'
            # Check existing by slug
            cursor.execute(f'SELECT id FROM {table} WHERE slug = ?', (slug,))
            existing = cursor.fetchone()

            if existing and not overwrite_existing:
                continue

            if existing and overwrite_existing:
                # Remove existing template and any references
                template_id = existing['id']
                if table == 'page_template_defs':
                    cursor.execute('DELETE FROM page_templates WHERE template_id = ?', (template_id,))
                else:
                    cursor.execute('DELETE FROM blog_post_templates WHERE template_id = ?', (template_id,))
                cursor.execute(f'DELETE FROM {table} WHERE id = ?', (template_id,))

            # Determine sort order
            sort_order = t.get('sort_order')
            if sort_order is None:
                cursor.execute(f'SELECT COALESCE(MAX(sort_order), 0) FROM {table}')
                sort_order = (cursor.fetchone()[0] or 0) + 1

            # Insert template
            cursor.execute(f'''
                INSERT INTO {table} (title, slug, category, content, is_default, sort_order, default_parameters)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                t.get('title') or slug,
                slug,
                t.get('category', 'content'),
                t.get('content', ''),
                t.get('is_default', 1),
                sort_order,
                t.get('default_parameters', '{}')
            ))

            new_template_id = cursor.lastrowid

            # If default, add to all existing items
            if t.get('is_default', 1):
                if table == 'page_template_defs':
                    cursor.execute('SELECT id FROM pages')
                    items = cursor.fetchall()
                    for it in items:
                        cursor.execute('SELECT COALESCE(MAX(sort_order), 0) FROM page_templates WHERE page_id = ?', (it['id'],))
                        max_order = cursor.fetchone()[0] or 0
                        cursor.execute('INSERT INTO page_templates (page_id, template_id, sort_order) VALUES (?, ?, ?)', (it['id'], new_template_id, max_order + 1))
                else:
                    cursor.execute('SELECT id FROM blog_posts')
                    items = cursor.fetchall()
                    for it in items:
                        cursor.execute('SELECT COALESCE(MAX(sort_order), 0) FROM blog_post_templates WHERE post_id = ?', (it['id'],))
                        max_order = cursor.fetchone()[0] or 0
                        cursor.execute('INSERT INTO blog_post_templates (post_id, template_id, sort_order) VALUES (?, ?, ?)', (it['id'], new_template_id, max_order + 1))

            imported_count += 1
        except Exception:
            continue

    return imported_count

@bp.route('/templates/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_template():
    """Add new template"""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', 'content')
        content = request.form.get('content', '').strip()
        slug_input = request.form.get('slug', '').strip()
        is_default = request.form.get('is_default') == 'on'
        default_parameters = request.form.get('default_parameters', '{}').strip()
        ttype = request.form.get('template_type', request.args.get('tab', 'page'))
        table = 'page_template_defs' if ttype == 'page' else 'blog_template_defs'

        if not title or not content:
            flash('Title and content are required', 'error')
            return redirect(url_for('templates_.add_template'))

        # Generate slug if not provided
        if not slug_input:
            slug_input = slugify(title)

        db = get_db()
        cursor = db.cursor()

        # Check if slug already exists
        cursor.execute(f'SELECT id FROM {table} WHERE slug = ?', (slug_input,))
        if cursor.fetchone():
            flash('Template with this slug already exists', 'error')
            return redirect(url_for('templates_.add_template'))

        # Get max sort order
        cursor.execute(f'SELECT MAX(sort_order) FROM {table}')
        max_order = cursor.fetchone()[0] or 0

        # Create template
        cursor.execute(f'''
            INSERT INTO {table} (title, slug, category, content, is_default, sort_order, default_parameters)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, slug_input, category, content, is_default, max_order + 1, default_parameters))

        if is_default:
            template_id = cursor.lastrowid
            if table == 'page_template_defs':
                cursor.execute('SELECT id FROM pages')
                rows = cursor.fetchall()
                for page in rows:
                    cursor.execute('SELECT COALESCE(MAX(sort_order), 0) FROM page_templates WHERE page_id = ?', (page['id'],))
                    mo = cursor.fetchone()[0] or 0
                    cursor.execute('INSERT INTO page_templates (page_id, template_id, sort_order) VALUES (?, ?, ?)', (page['id'], template_id, mo + 1))
            else:
                cursor.execute('SELECT id FROM blog_posts')
                rows = cursor.fetchall()
                for post in rows:
                    cursor.execute('SELECT COALESCE(MAX(sort_order), 0) FROM blog_post_templates WHERE post_id = ?', (post['id'],))
                    mo = cursor.fetchone()[0] or 0
                    cursor.execute('INSERT INTO blog_post_templates (post_id, template_id, sort_order) VALUES (?, ?, ?)', (post['id'], template_id, mo + 1))

        db.commit()
        flash('Template created successfully', 'success')
        return redirect(url_for('templates_.templates'))

    return render_template('templates/add.html')

@bp.route('/templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_template(template_id):
    """Edit existing template"""
    db = get_db()
    cursor = db.cursor()

    # Get template info
    tab = request.args.get('tab', 'page')
    table = 'page_template_defs' if tab == 'page' else 'blog_template_defs'
    cursor.execute(f'SELECT * FROM {table} WHERE id = ?', (template_id,))
    template = cursor.fetchone()

    if not template:
        flash('Template not found', 'error')
        return redirect(url_for('templates_.templates'))

    # Get pages that override this template
    overriding_pages = []
    if tab == 'page':
        cursor.execute('''
            SELECT p.id, p.title, p.slug
            FROM pages p
            JOIN page_templates pt ON p.id = pt.page_id
            WHERE pt.template_id = ? AND pt.use_default = 0
            ORDER BY p.title
        ''', (template_id,))
        overriding_pages = cursor.fetchall()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', template['category'])
        content = request.form.get('content', '').strip()
        slug_input = request.form.get('slug', '').strip()
        is_default = request.form.get('is_default') == 'on'
        default_parameters = request.form.get('default_parameters', '{}').strip()

        if not title or not content:
            flash('Title and content are required', 'error')
            return redirect(url_for('templates_.edit_template', template_id=template_id))

        # Check if slug already exists (excluding current template)
        cursor.execute(f'SELECT id FROM {table} WHERE slug = ? AND id != ?', (slug_input or slugify(title), template_id))
        if cursor.fetchone():
            flash('Template with this slug already exists', 'error')
            return redirect(url_for('templates_.edit_template', template_id=template_id))

        # Update template
        cursor.execute(f'''
            UPDATE {table}
            SET title = ?, slug = ?, category = ?, content = ?, is_default = ?, default_parameters = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (title, slug_input or slugify(title), category, content, is_default, default_parameters, template_id))

        # Handle default status change
        if is_default and not template['is_default']:
            # Add to existing pages
            cursor.execute('SELECT id FROM pages')
            pages = cursor.fetchall()

            # Get max sort order for existing pages
            for page in pages:
                cursor.execute('SELECT MAX(sort_order) FROM page_templates WHERE page_id = ?', (page['id'],))
                max_order = cursor.fetchone()[0] or 0

                cursor.execute('''
                    INSERT INTO page_templates (page_id, template_id, sort_order)
                    VALUES (?, ?, ?)
                ''', (page['id'], template_id, max_order + 1))

        elif not is_default and template['is_default']:
            # Remove from existing pages
            if tab == 'page':
                cursor.execute('DELETE FROM page_templates WHERE template_id = ?', (template_id,))
            else:
                cursor.execute('DELETE FROM blog_post_templates WHERE template_id = ?', (template_id,))

        db.commit()

        # Republish all published pages that use this template
        republished_count = 0
        cursor.execute('''
            SELECT DISTINCT p.id, p.published
            FROM pages p
            JOIN page_templates pt ON p.id = pt.page_id
            WHERE pt.template_id = ?
        ''', (template_id,))
        affected_pages = cursor.fetchall()

        for p in affected_pages:
            try:
                if p['published']:
                    generate_page_html(p['id'])
                    republished_count += 1
            except Exception:
                # Continue republishing other pages even if one fails
                continue

        flash('Template updated successfully', 'success')
        if republished_count:
            flash(f'Republished {republished_count} page(s) using this template', 'info')
        return redirect(url_for('templates_.templates'))

    return render_template('templates/edit.html', template=template, overriding_pages=overriding_pages)

@bp.route('/templates/<int:template_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_template(template_id):
    """Delete template"""
    db = get_db()
    cursor = db.cursor()

    # Get template info for confirmation
    tab = request.args.get('tab', 'page')
    table = 'page_template_defs' if tab == 'page' else 'blog_template_defs'
    cursor.execute(f'SELECT title FROM {table} WHERE id = ?', (template_id,))
    template = cursor.fetchone()

    if not template:
        flash('Template not found', 'error')
        return redirect(url_for('templates_.templates'))

    # Delete template (cascade will delete page_templates)
    cursor.execute(f'DELETE FROM {table} WHERE id = ?', (template_id,))
    db.commit()

    flash(f'Template "{template["title"]}" deleted successfully', 'success')
    return redirect(url_for('templates_.templates'))

@bp.route('/templates/<int:template_id>/move/<direction>', methods=['POST'])
@login_required
@admin_required
def move_template(template_id, direction):
    """Move template up or down in order"""
    db = get_db()
    cursor = db.cursor()

    # Get current template
    tab = request.args.get('tab', 'page')
    table = 'page_template_defs' if tab == 'page' else 'blog_template_defs'
    cursor.execute(f'SELECT sort_order FROM {table} WHERE id = ?', (template_id,))
    current = cursor.fetchone()

    if not current:
        flash('Template not found', 'error')
        return redirect(url_for('templates_.templates'))

    # Should we also reorder existing pages?
    reorder_pages = request.form.get('reorder_pages') == '1'

    # Same table, no cross-group jumps

    if direction == 'up':
        # Find the previous template
        cursor.execute(f'SELECT id, sort_order FROM {table} WHERE sort_order < ? ORDER BY sort_order DESC LIMIT 1',
                     (current['sort_order'],))
        prev_template = cursor.fetchone()

        if prev_template:
            # Swap sort orders
            cursor.execute(f'UPDATE {table} SET sort_order = ? WHERE id = ?', (prev_template['sort_order'], template_id))
            cursor.execute(f'UPDATE {table} SET sort_order = ? WHERE id = ?', (current['sort_order'], prev_template['id']))
            
            # Optionally update page-specific orders (may override custom per-page ordering)
            if reorder_pages:
                if table == 'page_template_defs':
                    cursor.execute('UPDATE page_templates SET sort_order = ? WHERE template_id = ?', (prev_template['sort_order'], template_id))
                    cursor.execute('UPDATE page_templates SET sort_order = ? WHERE template_id = ?', (current['sort_order'], prev_template['id']))
                else:
                    cursor.execute('UPDATE blog_post_templates SET sort_order = ? WHERE template_id = ?', (prev_template['sort_order'], template_id))
                    cursor.execute('UPDATE blog_post_templates SET sort_order = ? WHERE template_id = ?', (current['sort_order'], prev_template['id']))

    elif direction == 'down':
        # Find the next template
        cursor.execute(f'SELECT id, sort_order FROM {table} WHERE sort_order > ? ORDER BY sort_order ASC LIMIT 1',
                     (current['sort_order'],))
        next_template = cursor.fetchone()

        if next_template:
            # Swap sort orders
            cursor.execute(f'UPDATE {table} SET sort_order = ? WHERE id = ?', (next_template['sort_order'], template_id))
            cursor.execute(f'UPDATE {table} SET sort_order = ? WHERE id = ?', (current['sort_order'], next_template['id']))
            
            # Optionally update page-specific orders
            if reorder_pages:
                if table == 'page_template_defs':
                    cursor.execute('UPDATE page_templates SET sort_order = ? WHERE template_id = ?', (next_template['sort_order'], template_id))
                    cursor.execute('UPDATE page_templates SET sort_order = ? WHERE template_id = ?', (current['sort_order'], next_template['id']))
                else:
                    cursor.execute('UPDATE blog_post_templates SET sort_order = ? WHERE template_id = ?', (next_template['sort_order'], template_id))
                    cursor.execute('UPDATE blog_post_templates SET sort_order = ? WHERE template_id = ?', (current['sort_order'], next_template['id']))

    db.commit()
    if reorder_pages:
        flash('Template order updated. Reordered blocks across pages.', 'info')
    else:
        flash('Template order updated. Note: existing pages may have different block order.', 'warning')
    return redirect(url_for('templates_.templates'))

@bp.route('/templates/republish-all-pages', methods=['POST'])
@login_required
@admin_required
def republish_all_pages():
    """Re-publish all pages to update them with latest template changes"""
    db = get_db()
    cursor = db.cursor()
    
    # Get all published pages
    cursor.execute('SELECT id, title, slug FROM pages WHERE published = 1')
    published_pages = cursor.fetchall()
    
    if not published_pages:
        flash('No published pages found to republish', 'warning')
        return redirect(url_for('templates_.templates'))
    
    republished_count = 0
    errors = []
    
    for page in published_pages:
        try:
            # Generate HTML for the page
            generate_page_html(db, page['id'])
            republished_count += 1
        except Exception as e:
            errors.append(f"Page '{page['title']}': {str(e)}")
    
    if errors:
        flash(f'Republished {republished_count} pages. Errors: {"; ".join(errors)}', 'warning')
    else:
        flash(f'Successfully republished {republished_count} pages', 'success')
    
    return redirect(url_for('templates_.templates'))
