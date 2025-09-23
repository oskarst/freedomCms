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
    """List all templates (template groups) and handle import"""
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
                    imported_count = import_template_groups(import_data, overwrite_existing, cursor)
                    db.commit()
                    flash(f'Successfully imported {imported_count} template(s)', 'success')
                except Exception as e:
                    db.rollback()
                    flash(f'Import failed: {str(e)}', 'error')
            else:
                flash('Please select a valid JSON file', 'error')

            return redirect(url_for('templates_.templates'))

    cursor.execute('''
        SELECT g.*, COUNT(tgb.id) as blocks_count
        FROM template_groups g
        LEFT JOIN template_group_blocks tgb ON tgb.group_id = g.id
        GROUP BY g.id
        ORDER BY g.created_at DESC
    ''')
    groups = cursor.fetchall()
    return render_template('templates/templates.html', groups=groups)

@bp.route('/templates/blocks')
@login_required
@admin_required
def blocks():
    """List all template blocks with global order management"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT d.*, COUNT(CASE WHEN pt.use_default = 0 THEN 1 END) as override_count
        FROM page_template_defs d
        LEFT JOIN page_templates pt ON d.id = pt.template_id
        GROUP BY d.id
        ORDER BY d.sort_order
    ''')
    blocks_list = cursor.fetchall()
    return render_template('templates/blocks.html', blocks=blocks_list)

@bp.route('/templates/blocks/<int:template_id>/move/<direction>', methods=['POST'])
@login_required
@admin_required
def move_block(template_id: int, direction: str):
    """Move a template block up or down in global order"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id, sort_order FROM page_template_defs WHERE id = ?', (template_id,))
    current = cursor.fetchone()
    if not current:
        flash('Template block not found', 'error')
        return redirect(url_for('templates_.blocks'))

    if direction == 'up':
        cursor.execute('SELECT id, sort_order FROM page_template_defs WHERE sort_order < ? ORDER BY sort_order DESC LIMIT 1', (current['sort_order'],))
        neighbor = cursor.fetchone()
    else:
        cursor.execute('SELECT id, sort_order FROM page_template_defs WHERE sort_order > ? ORDER BY sort_order ASC LIMIT 1', (current['sort_order'],))
        neighbor = cursor.fetchone()

    if neighbor:
        cursor.execute('UPDATE page_template_defs SET sort_order = ? WHERE id = ?', (neighbor['sort_order'], current['id']))
        cursor.execute('UPDATE page_template_defs SET sort_order = ? WHERE id = ?', (current['sort_order'], neighbor['id']))
        db.commit()
        flash('Block order updated', 'success')
    else:
        flash('Cannot move further', 'warning')
    return redirect(url_for('templates_.blocks'))

@bp.route('/templates/blocks/<int:template_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_block(template_id: int):
    """Delete a template block definition"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT title FROM page_template_defs WHERE id = ?', (template_id,))
    row = cursor.fetchone()
    if not row:
        flash('Template block not found', 'error')
        return redirect(url_for('templates_.blocks'))
    cursor.execute('DELETE FROM page_template_defs WHERE id = ?', (template_id,))
    db.commit()
    flash(f'Template block "{row["title"]}" deleted', 'success')
    return redirect(url_for('templates_.blocks'))

@bp.route('/templates/blocks/<int:template_id>/duplicate', methods=['POST'])
@login_required
@admin_required
def duplicate_block(template_id: int):
    """Duplicate a template block"""
    db = get_db()
    cursor = db.cursor()
    
    # Get the original template block
    cursor.execute('SELECT * FROM page_template_defs WHERE id = ?', (template_id,))
    original_block = cursor.fetchone()
    
    if not original_block:
        flash('Template block not found', 'error')
        return redirect(url_for('templates_.blocks'))
    
    # Create new title and slug
    new_title = f"{original_block['title']} (Copy)"
    new_slug = slugify(new_title)
    
    # Ensure unique slug
    counter = 1
    base_slug = new_slug
    while True:
        cursor.execute('SELECT id FROM page_template_defs WHERE slug = ?', (new_slug,))
        if not cursor.fetchone():
            break
        new_slug = f"{base_slug}-{counter}"
        counter += 1
    
    # Get the next sort order
    cursor.execute('SELECT MAX(sort_order) FROM page_template_defs')
    max_sort = cursor.fetchone()[0] or 0
    new_sort_order = max_sort + 1
    
    # Insert new template block
    cursor.execute('''
        INSERT INTO page_template_defs (title, slug, category, content, is_default, sort_order, default_parameters)
        VALUES (?, ?, ?, ?, 0, ?, ?)
    ''', (new_title, new_slug, original_block['category'], original_block['content'], new_sort_order, original_block['default_parameters']))
    
    db.commit()
    flash(f'Template block "{original_block["title"]}" duplicated as "{new_title}"', 'success')
    return redirect(url_for('templates_.blocks'))

@bp.route('/templates/blocks/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_template():
    """Add new template block (global)"""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', 'content')
        content = request.form.get('content', '').strip()
        slug_input = request.form.get('slug', '').strip()
        is_default = request.form.get('is_default') == 'on'
        default_parameters = request.form.get('default_parameters', '{}').strip()

        if not title or not content:
            flash('Title and content are required', 'error')
            return redirect(url_for('templates_.add_template'))

        if not slug_input:
            slug_input = slugify(title)

        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id FROM page_template_defs WHERE slug = ?', (slug_input,))
        if cursor.fetchone():
            flash('Template with this slug already exists', 'error')
            return redirect(url_for('templates_.add_template'))

        cursor.execute('SELECT COALESCE(MAX(sort_order), 0) FROM page_template_defs')
        max_order = cursor.fetchone()[0] or 0
        cursor.execute('''
            INSERT INTO page_template_defs (title, slug, category, content, is_default, sort_order, default_parameters)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, slug_input, category, content, is_default, max_order + 1, default_parameters))

        if is_default:
            template_id = cursor.lastrowid
            cursor.execute('SELECT id FROM pages')
            rows = cursor.fetchall()
            for page in rows:
                cursor.execute('SELECT COALESCE(MAX(sort_order), 0) FROM page_templates WHERE page_id = ?', (page['id'],))
                mo = cursor.fetchone()[0] or 0
                cursor.execute('INSERT INTO page_templates (page_id, template_id, sort_order) VALUES (?, ?, ?)', (page['id'], template_id, mo + 1))

        db.commit()
        flash('Template block created successfully', 'success')
        next_url = request.args.get('next') or request.form.get('next')
        return redirect(next_url or url_for('templates_.blocks'))

    return render_template('templates/add.html')

@bp.route('/templates/groups/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_template_group():
    """Add a new template (group of blocks)"""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        slug_input = request.form.get('slug', '').strip()
        description = request.form.get('description', '').strip()
        is_default_page = request.form.get('is_default_page') == 'on'
        is_default_blog = request.form.get('is_default_blog') == 'on'
        
        if not title:
            flash('Title is required', 'error')
            return redirect(url_for('templates_.add_template_group'))
        if not slug_input:
            slug_input = slugify(title)
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id FROM template_groups WHERE slug = ?', (slug_input,))
        if cursor.fetchone():
            flash('Template with this slug already exists', 'error')
            return redirect(url_for('templates_.add_template_group'))
        
        # If setting as default, ensure no other template is default for the same type
        if is_default_page:
            cursor.execute('UPDATE template_groups SET is_default_page = 0')
        if is_default_blog:
            cursor.execute('UPDATE template_groups SET is_default_blog = 0')
        
        cursor.execute('INSERT INTO template_groups (title, slug, description, is_default_page, is_default_blog) VALUES (?, ?, ?, ?, ?)',
                       (title, slug_input, description, is_default_page, is_default_blog))
        db.commit()
        flash('Template created', 'success')
        return redirect(url_for('templates_.templates'))
    return render_template('templates/group_add.html')

@bp.route('/templates/groups/<int:group_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_template_group(group_id: int):
    """Edit template group details and membership"""
    db = get_db()
    cursor = db.cursor()

    # Load group
    cursor.execute('SELECT * FROM template_groups WHERE id = ?', (group_id,))
    group = cursor.fetchone()
    if not group:
        flash('Template not found', 'error')
        return redirect(url_for('templates_.templates'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_info':
            title = request.form.get('title', '').strip()
            slug_input = request.form.get('slug', '').strip()
            description = request.form.get('description', '').strip()
            is_default_page = request.form.get('is_default_page') == 'on'
            is_default_blog = request.form.get('is_default_blog') == 'on'
            
            if not title:
                flash('Title is required', 'error')
                return redirect(url_for('templates_.edit_template_group', group_id=group_id))
            if not slug_input:
                slug_input = slugify(title)
            # Unique slug check excluding current
            cursor.execute('SELECT id FROM template_groups WHERE slug = ? AND id != ?', (slug_input, group_id))
            if cursor.fetchone():
                flash('Another template with this slug exists', 'error')
                return redirect(url_for('templates_.edit_template_group', group_id=group_id))
            
            # If setting as default, ensure no other template is default for the same type
            if is_default_page:
                cursor.execute('UPDATE template_groups SET is_default_page = 0')
            if is_default_blog:
                cursor.execute('UPDATE template_groups SET is_default_blog = 0')
            
            cursor.execute('UPDATE template_groups SET title = ?, slug = ?, description = ?, is_default_page = ?, is_default_blog = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                           (title, slug_input, description, is_default_page, is_default_blog, group_id))
            db.commit()
            flash('Template info updated', 'success')
            return redirect(url_for('templates_.edit_template_group', group_id=group_id))
        elif action == 'add_block':
            template_id = request.form.get('template_id', type=int)
            duplicate = request.form.get('duplicate') == 'on'
            if not template_id:
                flash('Select a block to add', 'error')
                return redirect(url_for('templates_.edit_template_group', group_id=group_id))

            # If duplicate checked, create a new block definition copied from selected
            if duplicate:
                cursor.execute('SELECT title, slug, category, content, default_parameters FROM page_template_defs WHERE id = ?', (template_id,))
                src = cursor.fetchone()
                if not src:
                    flash('Selected block not found', 'error')
                    return redirect(url_for('templates_.edit_template_group', group_id=group_id))

                # Generate a unique slug: original-slug-copy[-n]
                base_slug = (src['slug'] or 'block') + '-copy'
                new_slug = base_slug
                counter = 1
                while True:
                    cursor.execute('SELECT 1 FROM page_template_defs WHERE slug = ?', (new_slug,))
                    if not cursor.fetchone():
                        break
                    counter += 1
                    new_slug = f"{base_slug}-{counter}"

                new_title = f"{src['title']} (Copy)"
                # Determine global sort order for defs
                cursor.execute('SELECT COALESCE(MAX(sort_order), 0) FROM page_template_defs')
                max_order = cursor.fetchone()[0] or 0

                cursor.execute('''
                    INSERT INTO page_template_defs (title, slug, category, content, is_default, sort_order, default_parameters)
                    VALUES (?, ?, ?, ?, 0, ?, ?)
                ''', (new_title, new_slug, src['category'], src['content'], max_order + 1, src['default_parameters'] or '{}'))
                template_id = cursor.lastrowid

            # Determine next sort order within this group
            cursor.execute('SELECT COALESCE(MAX(sort_order), 0) FROM template_group_blocks WHERE group_id = ?', (group_id,))
            next_order = (cursor.fetchone()[0] or 0) + 1
            cursor.execute('INSERT INTO template_group_blocks (group_id, template_id, sort_order) VALUES (?, ?, ?)',
                           (group_id, template_id, next_order))
            db.commit()
            flash('Block added to template', 'success')
            return redirect(url_for('templates_.edit_template_group', group_id=group_id))
        elif action == 'remove_block':
            membership_id = request.form.get('membership_id', type=int)
            cursor.execute('DELETE FROM template_group_blocks WHERE id = ? AND group_id = ?', (membership_id, group_id))
            db.commit()
            flash('Block removed from template', 'success')
            return redirect(url_for('templates_.edit_template_group', group_id=group_id))
        elif action == 'create_block':
            # Create a new template block and add it to this group
            title = request.form.get('title', '').strip()
            slug_input = request.form.get('slug', '').strip()
            category = request.form.get('category', 'content')
            content = request.form.get('content', '').strip()
            is_default = request.form.get('is_default') == 'on'
            default_parameters = request.form.get('default_parameters', '{}').strip()

            if not title or not content:
                flash('Title and content are required for new block', 'error')
                return redirect(url_for('templates_.edit_template_group', group_id=group_id))

            if not slug_input:
                slug_input = slugify(title)

            # Ensure unique slug
            cursor.execute('SELECT id FROM page_template_defs WHERE slug = ?', (slug_input,))
            if cursor.fetchone():
                flash('A template block with this slug already exists', 'error')
                return redirect(url_for('templates_.edit_template_group', group_id=group_id))

            # Determine sort order for block definitions
            cursor.execute('SELECT COALESCE(MAX(sort_order), 0) FROM page_template_defs')
            max_order = cursor.fetchone()[0] or 0

            # Insert block definition
            cursor.execute('''
                INSERT INTO page_template_defs (title, slug, category, content, is_default, sort_order, default_parameters)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (title, slug_input, category, content, is_default, max_order + 1, default_parameters))

            new_block_id = cursor.lastrowid

            # If default, add to all existing pages
            if is_default:
                cursor.execute('SELECT id FROM pages')
                rows = cursor.fetchall()
                for page in rows:
                    cursor.execute('SELECT COALESCE(MAX(sort_order), 0) FROM page_templates WHERE page_id = ?', (page['id'],))
                    mo = cursor.fetchone()[0] or 0
                    cursor.execute('INSERT INTO page_templates (page_id, template_id, sort_order) VALUES (?, ?, ?)', (page['id'], new_block_id, mo + 1))

            # Add new block into this group at the end
            cursor.execute('SELECT COALESCE(MAX(sort_order), 0) FROM template_group_blocks WHERE group_id = ?', (group_id,))
            next_order = (cursor.fetchone()[0] or 0) + 1
            cursor.execute('INSERT INTO template_group_blocks (group_id, template_id, sort_order) VALUES (?, ?, ?)', (group_id, new_block_id, next_order))

            db.commit()
            flash('New block created and added to template', 'success')
            return redirect(url_for('templates_.edit_template_group', group_id=group_id))
        elif action in ('move_up', 'move_down'):
            membership_id = request.form.get('membership_id', type=int)
            # Get current
            cursor.execute('SELECT id, sort_order FROM template_group_blocks WHERE id = ? AND group_id = ?', (membership_id, group_id))
            current = cursor.fetchone()
            if not current:
                return redirect(url_for('templates_.edit_template_group', group_id=group_id))
            if action == 'move_up':
                cursor.execute('''
                    SELECT id, sort_order FROM template_group_blocks
                    WHERE group_id = ? AND sort_order < ?
                    ORDER BY sort_order DESC LIMIT 1
                ''', (group_id, current['sort_order']))
                neighbor = cursor.fetchone()
            else:
                cursor.execute('''
                    SELECT id, sort_order FROM template_group_blocks
                    WHERE group_id = ? AND sort_order > ?
                    ORDER BY sort_order ASC LIMIT 1
                ''', (group_id, current['sort_order']))
                neighbor = cursor.fetchone()
            if neighbor:
                cursor.execute('UPDATE template_group_blocks SET sort_order = ? WHERE id = ?', (neighbor['sort_order'], current['id']))
                cursor.execute('UPDATE template_group_blocks SET sort_order = ? WHERE id = ?', (current['sort_order'], neighbor['id']))
                db.commit()
            return redirect(url_for('templates_.edit_template_group', group_id=group_id))

    # Load available blocks and membership
    cursor.execute('''
        SELECT 
            tgb.id as membership_id,
            tgb.sort_order,
            d.id as template_id,
            d.title,
            d.slug,
            d.category,
            COALESCE(SUM(CASE WHEN pt.use_default = 0 THEN 1 END), 0) AS override_count
        FROM template_group_blocks tgb
        JOIN page_template_defs d ON d.id = tgb.template_id
        LEFT JOIN page_templates pt ON pt.template_id = d.id
        WHERE tgb.group_id = ?
        GROUP BY tgb.id
        ORDER BY tgb.sort_order
    ''', (group_id,))
    group_blocks = cursor.fetchall()

    cursor.execute('SELECT id, title, slug, category, sort_order FROM page_template_defs ORDER BY sort_order, title')
    all_blocks = cursor.fetchall()

    return render_template('templates/group_edit.html', group=group, group_blocks=group_blocks, all_blocks=all_blocks)

@bp.route('/templates/groups/<int:group_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_template_group(group_id: int):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT title FROM template_groups WHERE id = ?', (group_id,))
    row = cursor.fetchone()
    if not row:
        flash('Template not found', 'error')
        return redirect(url_for('templates_.templates'))
    cursor.execute('DELETE FROM template_groups WHERE id = ?', (group_id,))
    db.commit()
    flash(f'Template "{row["title"]}" deleted', 'success')
    return redirect(url_for('templates_.templates'))

@bp.route('/templates/groups/<int:group_id>/duplicate', methods=['POST'])
@login_required
@admin_required
def duplicate_template_group(group_id: int):
    """Duplicate a template group with all its blocks"""
    db = get_db()
    cursor = db.cursor()
    
    # Get the original template group
    cursor.execute('SELECT * FROM template_groups WHERE id = ?', (group_id,))
    original_group = cursor.fetchone()
    
    if not original_group:
        flash('Template group not found', 'error')
        return redirect(url_for('templates_.templates'))
    
    # Create new title and slug
    new_title = f"{original_group['title']} (Copy)"
    new_slug = slugify(new_title)
    
    # Ensure unique slug
    counter = 1
    base_slug = new_slug
    while True:
        cursor.execute('SELECT id FROM template_groups WHERE slug = ?', (new_slug,))
        if not cursor.fetchone():
            break
        new_slug = f"{base_slug}-{counter}"
        counter += 1
    
    # Insert new template group
    cursor.execute('''
        INSERT INTO template_groups (title, slug, description, is_default, is_default_page, is_default_blog)
        VALUES (?, ?, ?, 0, 0, 0)
    ''', (new_title, new_slug, original_group['description']))
    new_group_id = cursor.lastrowid
    
    # Get all blocks from the original group
    cursor.execute('''
        SELECT d.id, d.title, d.slug, d.category, d.content, d.default_parameters, tgb.sort_order
        FROM template_group_blocks tgb
        JOIN page_template_defs d ON tgb.template_id = d.id
        WHERE tgb.group_id = ?
        ORDER BY tgb.sort_order
    ''', (group_id,))
    original_blocks = cursor.fetchall()
    
    # Duplicate each block and add to new group
    for block in original_blocks:
        # Create new block title and slug
        new_block_title = f"{block['title']} (Copy)"
        new_block_slug = slugify(new_block_title)
        
        # Ensure unique block slug
        counter = 1
        base_block_slug = new_block_slug
        while True:
            cursor.execute('SELECT id FROM page_template_defs WHERE slug = ?', (new_block_slug,))
            if not cursor.fetchone():
                break
            new_block_slug = f"{base_block_slug}-{counter}"
            counter += 1
        
        # Insert new block
        cursor.execute('''
            INSERT INTO page_template_defs (title, slug, category, content, is_default, sort_order, default_parameters)
            VALUES (?, ?, ?, ?, 0, ?, ?)
        ''', (new_block_title, new_block_slug, block['category'], block['content'], block['sort_order'], block['default_parameters']))
        new_block_id = cursor.lastrowid
        
        # Add block to new group
        cursor.execute('''
            INSERT INTO template_group_blocks (group_id, template_id, sort_order)
            VALUES (?, ?, ?)
        ''', (new_group_id, new_block_id, block['sort_order']))
    
    db.commit()
    flash(f'Template group "{original_group["title"]}" duplicated as "{new_title}"', 'success')
    return redirect(url_for('templates_.templates'))

@bp.route('/templates/export/all')
@login_required
@admin_required
def export_all_groups():
    """Export all template groups with their blocks to JSON"""
    db = get_db()
    cursor = db.cursor()

    # Get all template groups with their blocks
    cursor.execute('''
        SELECT
            g.id, g.title, g.slug, g.description, g.is_default, g.created_at, g.updated_at,
            g.is_default_page, g.is_default_blog,
            tgb.sort_order as block_sort_order,
            d.id as block_id, d.title as block_title, d.slug as block_slug, d.category, d.content, d.default_parameters, d.sort_order as block_def_sort_order
        FROM template_groups g
        LEFT JOIN template_group_blocks tgb ON g.id = tgb.group_id
        LEFT JOIN page_template_defs d ON tgb.template_id = d.id
        ORDER BY g.id, tgb.sort_order
    ''')
    rows = cursor.fetchall()

    # Group by template
    templates_data = {}
    for row in rows:
        template_id = row['id']

        if template_id not in templates_data:
            templates_data[template_id] = {
            'id': row['id'],
            'title': row['title'],
            'slug': row['slug'],
                'description': row['description'],
            'is_default': row['is_default'],
            'is_default_page': row['is_default_page'],
            'is_default_blog': row['is_default_blog'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
                'blocks': []
            }

        if row['block_id']:  # Only add if there's a block
            templates_data[template_id]['blocks'].append({
                'id': row['block_id'],
                'title': row['block_title'],
                'slug': row['block_slug'],
                'category': row['category'],
                'content': row['content'] or '',
                'default_parameters': row['default_parameters'] or '{}',
                'sort_order': row['block_sort_order'],
                'block_def_sort_order': row['block_def_sort_order']
            })

    # Convert to list
    export_data = list(templates_data.values())

    data = json.dumps(export_data, indent=2, default=str)
    return Response(data, mimetype='application/json', headers={
        'Content-Disposition': 'attachment; filename=templates_export.json'
    })

@bp.route('/templates/export/selected', methods=['POST'])
@login_required
@admin_required
def export_selected_groups():
    """Export selected template groups with their blocks to JSON"""
    selected_ids = request.form.getlist('selected_groups')

    if not selected_ids:
        flash('No templates selected for export', 'warning')
        return redirect(url_for('templates_.templates'))

    db = get_db()
    cursor = db.cursor()

    # Convert to integers
    group_ids = [int(gid) for gid in selected_ids]
    placeholders = ','.join('?' * len(group_ids))

    # Get selected template groups with their blocks
    cursor.execute(f'''
        SELECT
            g.id, g.title, g.slug, g.description, g.is_default, g.created_at, g.updated_at,
            g.is_default_page, g.is_default_blog,
            tgb.sort_order as block_sort_order,
            d.id as block_id, d.title as block_title, d.slug as block_slug, d.category, d.content, d.default_parameters, d.sort_order as block_def_sort_order
        FROM template_groups g
        LEFT JOIN template_group_blocks tgb ON g.id = tgb.group_id
        LEFT JOIN page_template_defs d ON tgb.template_id = d.id
        WHERE g.id IN ({placeholders})
        ORDER BY g.id, tgb.sort_order
    ''', group_ids)
    rows = cursor.fetchall()

    # Group by template
    templates_data = {}
    for row in rows:
        template_id = row['id']

        if template_id not in templates_data:
            templates_data[template_id] = {
            'id': row['id'],
            'title': row['title'],
            'slug': row['slug'],
                'description': row['description'],
            'is_default': row['is_default'],
            'is_default_page': row['is_default_page'],
            'is_default_blog': row['is_default_blog'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
                'blocks': []
            }

        if row['block_id']:  # Only add if there's a block
            templates_data[template_id]['blocks'].append({
                'id': row['block_id'],
                'title': row['block_title'],
                'slug': row['block_slug'],
                'category': row['category'],
                'content': row['content'] or '',
                'default_parameters': row['default_parameters'] or '{}',
                'sort_order': row['block_sort_order'],
                'block_def_sort_order': row['block_def_sort_order']
            })

    # Convert to list
    export_data = list(templates_data.values())

    data = json.dumps(export_data, indent=2, default=str)
    return Response(data, mimetype='application/json', headers={
        'Content-Disposition': 'attachment; filename=selected_templates_export.json'
    })

def import_template_groups(import_data, overwrite_existing, cursor):
    """Import template groups with their blocks from JSON data"""
    imported_count = 0

    if not isinstance(import_data, list):
        raise ValueError('Invalid JSON format - expected array of template groups')

    for template_data in import_data:
        try:
            slug = template_data.get('slug') or slugify(template_data.get('title', ''))
            if not slug:
                continue

            # Check existing template group by slug
            cursor.execute('SELECT id FROM template_groups WHERE slug = ?', (slug,))
            existing = cursor.fetchone()

            if existing and not overwrite_existing:
                continue

            if existing and overwrite_existing:
                # Remove existing template group and its blocks
                template_id = existing['id']
                cursor.execute('DELETE FROM template_group_blocks WHERE group_id = ?', (template_id,))
                cursor.execute('DELETE FROM template_groups WHERE id = ?', (template_id,))

            # If setting as default, ensure no other template is default for the same type
            if template_data.get('is_default_page'):
                cursor.execute('UPDATE template_groups SET is_default_page = 0')
            if template_data.get('is_default_blog'):
                cursor.execute('UPDATE template_groups SET is_default_blog = 0')

            # Insert template group
            cursor.execute('''
                INSERT INTO template_groups (title, slug, description, is_default, is_default_page, is_default_blog)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                template_data.get('title') or slug,
                slug,
                template_data.get('description', ''),
                template_data.get('is_default', 0),
                template_data.get('is_default_page', 0),
                template_data.get('is_default_blog', 0)
            ))

            new_group_id = cursor.lastrowid

            # Import blocks for this template group
            if 'blocks' in template_data and template_data['blocks']:
                for block_data in template_data['blocks']:
                    # Check if block already exists by slug
                    block_slug = block_data.get('slug') or slugify(block_data.get('title', ''))
                    cursor.execute('SELECT id FROM page_template_defs WHERE slug = ?', (block_slug,))
                    existing_block = cursor.fetchone()

                    block_id = None
                    if existing_block:
                        # Use existing block
                        block_id = existing_block['id']
                        # Update sort_order if provided in import data
                        if 'block_def_sort_order' in block_data:
                            cursor.execute('UPDATE page_template_defs SET sort_order = ? WHERE id = ?', 
                                         (block_data['block_def_sort_order'], block_id))
                    else:
                        # Create new block
                        cursor.execute('''
                            INSERT INTO page_template_defs (title, slug, category, content, is_default, sort_order, default_parameters)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            block_data.get('title') or block_slug,
                            block_slug,
                            block_data.get('category', 'content'),
                            block_data.get('content', ''),
                            block_data.get('is_default', 0),  # Blocks in templates are typically not default
                            block_data.get('block_def_sort_order', 0),  # Use imported sort_order
                            block_data.get('default_parameters', '{}')
                        ))
                        block_id = cursor.lastrowid

                    # Add block to template group
                    if block_id:
                        cursor.execute('''
                            INSERT INTO template_group_blocks (group_id, template_id, sort_order)
                            VALUES (?, ?, ?)
                        ''', (
                            new_group_id,
                            block_id,
                            block_data.get('sort_order', 0)
                        ))

            imported_count += 1
        except Exception as e:
            print(f"Error importing template '{template_data.get('title', 'unknown')}': {str(e)}")
            continue

    return imported_count

@bp.route('/templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_template(template_id):
    """Edit existing template block"""
    db = get_db()
    cursor = db.cursor()

    # Get template info
    cursor.execute('SELECT * FROM page_template_defs WHERE id = ?', (template_id,))
    template = cursor.fetchone()

    if not template:
        flash('Template block not found', 'error')
        return redirect(url_for('templates_.templates'))

    # Get pages that override this template
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
        cursor.execute('SELECT id FROM page_template_defs WHERE slug = ? AND id != ?', (slug_input or slugify(title), template_id))
        if cursor.fetchone():
            flash('Template block with this slug already exists', 'error')
            return redirect(url_for('templates_.edit_template', template_id=template_id))

        # Update template
        cursor.execute('''
            UPDATE page_template_defs
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
            cursor.execute('DELETE FROM page_templates WHERE template_id = ?', (template_id,))

        db.commit()

        # Optional redirect back path
        next_url = request.args.get('next') or request.form.get('next')

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
            except Exception as e:
                # Log the error but continue republishing other pages
                print(f"Error republishing page {p['id']}: {str(e)}")
                continue

        flash('Template block updated successfully', 'success')
        if republished_count:
            flash(f'Republished {republished_count} page(s) using this template', 'info')
        if next_url:
            return redirect(next_url)
        return redirect(url_for('templates_.templates'))

    return render_template('templates/edit.html', template=template, overriding_pages=overriding_pages)