#!/usr/bin/env python3
"""
AI Templates blueprint for Devall CMS
Handles conversion of HTML templates to CMS templates using AI
"""

import json
from datetime import datetime
from flask import Blueprint, request, redirect, url_for, render_template, flash, Response, jsonify
from ..auth import login_required, admin_required
from ..db import get_db
from ..services.mcp import call_ai_model, MCPClientError
from ..views.templates_ import import_template_groups

bp = Blueprint('ai_templates', __name__)

@bp.route('/templates/ai')
@login_required
@admin_required
def ai_templates_list():
    """List all AI templates"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        SELECT id, name, status, json_template, created_at, updated_at
        FROM ai_templates
        ORDER BY created_at DESC
    ''')
    templates = cursor.fetchall()

    return render_template('templates/ai_templates.html', templates=templates)

@bp.route('/templates/ai/add', methods=['GET', 'POST'])
@login_required
@admin_required
def ai_templates_add():
    """Add new AI template"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        html_content = request.form.get('html_content', '').strip()

        if not name or not html_content:
            flash('Template name and HTML content are required', 'error')
            return render_template('templates/ai_templates_add.html', name=name, html_content=html_content)

        db = get_db()
        cursor = db.cursor()

        try:
            cursor.execute('''
                INSERT INTO ai_templates (name, html_content, status)
                VALUES (?, ?, 'draft')
            ''', (name, html_content))
            db.commit()

            template_id = cursor.lastrowid
            flash(f'AI Template "{name}" created successfully', 'success')
            return redirect(url_for('ai_templates.ai_templates_edit', template_id=template_id))
        except Exception as e:
            db.rollback()
            flash(f'Error creating template: {str(e)}', 'error')
            return render_template('templates/ai_templates_add.html', name=name, html_content=html_content)

    return render_template('templates/ai_templates_add.html')

@bp.route('/templates/ai/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def ai_templates_edit(template_id: int):
    """Edit AI template"""
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        html_content = request.form.get('html_content', '').strip()

        if not name or not html_content:
            flash('Template name and HTML content are required', 'error')
            cursor.execute('SELECT * FROM ai_templates WHERE id = ?', (template_id,))
            template = cursor.fetchone()
            return render_template('templates/ai_templates_edit.html', template=template)

        try:
            cursor.execute('''
                UPDATE ai_templates
                SET name = ?, html_content = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (name, html_content, template_id))
            db.commit()

            flash(f'AI Template "{name}" updated successfully', 'success')
            return redirect(url_for('ai_templates.ai_templates_list'))
        except Exception as e:
            db.rollback()
            flash(f'Error updating template: {str(e)}', 'error')

    cursor.execute('SELECT * FROM ai_templates WHERE id = ?', (template_id,))
    template = cursor.fetchone()

    if not template:
        flash('Template not found', 'error')
        return redirect(url_for('ai_templates.ai_templates_list'))

    return render_template('templates/ai_templates_edit.html', template=template)

@bp.route('/templates/ai/<int:template_id>/delete', methods=['POST'])
@login_required
@admin_required
def ai_templates_delete(template_id: int):
    """Delete AI template"""
    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute('DELETE FROM ai_templates WHERE id = ?', (template_id,))
        db.commit()
        flash('AI Template deleted successfully', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Error deleting template: {str(e)}', 'error')

    return redirect(url_for('ai_templates.ai_templates_list'))

@bp.route('/templates/ai/<int:template_id>/download')
@login_required
@admin_required
def ai_templates_download(template_id: int):
    """Download AI template as JSON"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT name, json_template FROM ai_templates WHERE id = ?', (template_id,))
    template = cursor.fetchone()

    if not template:
        flash('Template not found', 'error')
        return redirect(url_for('ai_templates.ai_templates_list'))

    if not template['json_template']:
        flash('Template has not been converted yet', 'error')
        return redirect(url_for('ai_templates.ai_templates_list'))

    # Return JSON file
    response = Response(
        template['json_template'],
        mimetype='application/json',
        headers={
            'Content-Disposition': f'attachment; filename={template["name"].replace(" ", "_")}.json'
        }
    )
    return response

@bp.route('/templates/ai/<int:template_id>/convert', methods=['POST'])
@login_required
@admin_required
def ai_templates_convert(template_id: int):
    """Convert HTML to CMS template using AI"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT html_content FROM ai_templates WHERE id = ?', (template_id,))
    template = cursor.fetchone()

    if not template:
        return jsonify({'error': 'Template not found'}), 404

    html_content = template['html_content']

    # Get the conversion prompt from settings
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('ai_template_conversion_prompt',))
    prompt_template_row = cursor.fetchone()
    prompt_template = prompt_template_row['value'] if prompt_template_row else ''

    # If no custom prompt in settings, use default
    if not prompt_template:
        prompt_template = '''I have this JSON structure for a CMS template below. Convert the current HTML template into similar template that would work with this CMS. Add parameters where dynamic text might be.

Example CMS Template JSON Structure:
{example_json}

Guidelines:
1. Break the HTML into logical blocks (header, navigation, content sections, footer, etc.)
2. Each block should be a separate item in the "blocks" array
3. Use "system" category for structural elements (DOCTYPE, head, closing tags)
4. Use "content" category for editable content sections
5. For dynamic content, add parameters in the default_parameters object
6. Create descriptive titles and slugs for each block
7. Ensure the template is valid HTML when blocks are assembled in order
8. Add sort_order to maintain proper block sequence

HTML Template to Convert:
{html_content}

Return ONLY a valid JSON object in the same structure as the example, with the HTML properly converted into blocks.'''

    # Get example template structure from existing templates
    cursor.execute('''
        SELECT g.title, g.slug, g.description, g.is_default_page, g.is_default_blog,
               d.title as block_title, d.slug as block_slug, d.category,
               d.content as block_content, d.default_parameters
        FROM template_groups g
        LEFT JOIN template_group_blocks tgb ON tgb.group_id = g.id
        LEFT JOIN page_template_defs d ON d.id = tgb.template_id
        WHERE g.id = (SELECT id FROM template_groups LIMIT 1)
        ORDER BY tgb.sort_order
        LIMIT 3
    ''')
    example_blocks = cursor.fetchall()

    # Build example JSON structure
    example_json = {
        "title": "Example Template",
        "slug": "example-template",
        "description": "Example template description",
        "is_default_page": 0,
        "is_default_blog": 0,
        "blocks": []
    }

    for block in example_blocks:
        if block['block_title']:
            example_json['blocks'].append({
                "title": block['block_title'],
                "slug": block['block_slug'],
                "category": block['category'],
                "content": block['block_content'][:200] + "..." if len(block['block_content']) > 200 else block['block_content'],
                "default_parameters": json.loads(block['default_parameters'] or '{}')
            })

    # Create AI prompt by substituting placeholders
    prompt = prompt_template.format(
        example_json=json.dumps(example_json, indent=2),
        html_content=html_content
    )

    try:
        # Call AI model
        result = call_ai_model(prompt, mode='code')

        # Parse and validate JSON
        try:
            template_json = json.loads(result)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks if present
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0].strip()
            elif '```' in result:
                result = result.split('```')[1].split('```')[0].strip()
            template_json = json.loads(result)

        # Ensure it's in array format for import
        if not isinstance(template_json, list):
            template_json = [template_json]

        # Save the converted JSON
        cursor.execute('''
            UPDATE ai_templates
            SET json_template = ?, status = 'converted', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (json.dumps(template_json, indent=2), template_id))
        db.commit()

        return jsonify({
            'success': True,
            'message': 'Template converted successfully',
            'template': template_json
        })

    except MCPClientError as e:
        return jsonify({'error': str(e)}), 500
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Invalid JSON response from AI: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'Conversion failed: {str(e)}'}), 500

@bp.route('/templates/ai/<int:template_id>/import', methods=['POST'])
@login_required
@admin_required
def ai_templates_import(template_id: int):
    """Import AI template into the system"""
    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT json_template FROM ai_templates WHERE id = ?', (template_id,))
    template = cursor.fetchone()

    if not template:
        flash('Template not found', 'error')
        return redirect(url_for('ai_templates.ai_templates_list'))

    if not template['json_template']:
        flash('Template has not been converted yet', 'error')
        return redirect(url_for('ai_templates.ai_templates_list'))

    try:
        # Parse JSON
        import_data = json.loads(template['json_template'])

        # Use existing import functionality
        imported_count = import_template_groups(import_data, False, cursor)
        db.commit()

        flash(f'Successfully imported {imported_count} template(s) into the system', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Import failed: {str(e)}', 'error')

    return redirect(url_for('ai_templates.ai_templates_list'))
