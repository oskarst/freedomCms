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

    cursor.execute('SELECT name, html_content FROM ai_templates WHERE id = ?', (template_id,))
    template = cursor.fetchone()

    if not template:
        return jsonify({'error': 'Template not found'}), 404

    html_content = template['html_content']
    template_name = template['name']

    # Get the conversion prompt from settings
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('ai_template_conversion_prompt',))
    prompt_template_row = cursor.fetchone()
    prompt_template = prompt_template_row['value'] if prompt_template_row else ''

    # If no custom prompt in settings, use default
    if not prompt_template:
        prompt_template = '''You are converting an HTML template into a CMS template structure. The CMS uses a block-based system where templates are composed of reusable blocks.

Example CMS Template JSON Structure (THIS IS JUST AN EXAMPLE FORMAT - DO NOT COPY THE CONTENT):
{example_json}

IMPORTANT CONVERSION GUIDELINES:

1. STRUCTURE: Break the HTML into logical blocks (header, meta tags, navigation, hero, content sections, footer, closing tags)

2. BLOCK CATEGORIES:
   - "system" = Structural/non-editable blocks (DOCTYPE, <head>, </head>, <body>, </body>, CSS/JS includes)
   - "content" = Editable content sections (navigation, hero, features, articles, footer content)

3. BLOCK SLUGS:
   - MUST prefix ALL block slugs with "{template_prefix}-" for uniqueness
   - Examples: "{template_prefix}-header", "{template_prefix}-hero", "{template_prefix}-footer"
   - Use descriptive names after the prefix

4. PARAMETERS:
   - Identify dynamic/editable text and replace with {{{{parameter_name}}}} placeholders
   - Add these parameters to default_parameters object with default values
   - Common parameters: {{{{title}}}}, {{{{description}}}}, {{{{button_text}}}}, {{{{content:wysiwyg}}}}
   - Use ":wysiwyg" suffix for rich text content (e.g., {{{{content:wysiwyg}}}})

5. SPECIAL VARIABLES:
   - Use {{{{config:base_url}}}} for site base URL references
   - Use {{{{page:featured:webp}}}} for featured images
   - Use {{{{page_title}}}}, {{{{page_description}}}} for page-specific meta

6. HTML VALIDITY: Ensure blocks assemble into valid HTML when concatenated in order

7. SORT ORDER: Blocks should have sequential sort_order for proper assembly

Template Name: {template_name}
Template Slug Prefix: {template_prefix}

HTML Template to Convert:
{html_content}

Return ONLY a valid JSON array (like the example) with the HTML properly converted into blocks. Include title, slug, description, and all blocks with proper categorization and parameters.'''

    # Use real-world example JSON structure from actual CMS templates
    example_json = [
        {
            "title": "Example Template",
            "slug": "example-template",
            "description": "Template showing block structure",
            "is_default": 0,
            "is_default_page": 0,
            "is_default_blog": 0,
            "blocks": [
                {
                    "title": "Base Header",
                    "slug": "example-base-header",
                    "category": "system",
                    "content": "<!doctype html>\r\n<html lang=\"en\">\r\n<head>",
                    "default_parameters": {}
                },
                {
                    "title": "Meta Tags",
                    "slug": "example-meta",
                    "category": "system",
                    "content": "<meta charset=\"utf-8\">\r\n<title>{{page_title}}</title>\r\n<meta name=\"description\" content=\"{{page_description}}\"/>\r\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
                    "default_parameters": {
                        "page_title": "Page Title",
                        "page_description": "Page description"
                    }
                },
                {
                    "title": "Header Close",
                    "slug": "example-header-close",
                    "category": "system",
                    "content": "<link rel=\"stylesheet\" href=\"{{config:base_url}}/css/styles.css\">\r\n</head>\r\n<body>",
                    "default_parameters": {}
                },
                {
                    "title": "Navigation Menu",
                    "slug": "example-menu",
                    "category": "content",
                    "content": "<nav>\r\n<ul class=\"menu\">\r\n<li><a href=\"{{config:base_url}}/\">Home</a></li>\r\n<li><a href=\"#about\">About</a></li>\r\n</ul>\r\n</nav>",
                    "default_parameters": {}
                },
                {
                    "title": "Content Start",
                    "slug": "example-content-start",
                    "category": "system",
                    "content": "<div class=\"main-container\">",
                    "default_parameters": {}
                },
                {
                    "title": "Hero Section",
                    "slug": "example-hero",
                    "category": "content",
                    "content": "<section class=\"hero\">\r\n<h1>{{hero_title}}</h1>\r\n<p>{{slogan}}</p>\r\n</section>",
                    "default_parameters": {
                        "hero_title": "Welcome",
                        "slogan": "Your tagline here"
                    }
                },
                {
                    "title": "Content Paragraph",
                    "slug": "example-content-paragraph",
                    "category": "content",
                    "content": "<section>\r\n<h3>{{Title}}</h3>\r\n<p>{{Content:wysiwyg}}</p>\r\n<a class=\"btn\" href=\"#contacts\">{{Button Text}}</a>\r\n</section>",
                    "default_parameters": {
                        "Title": "Section Title",
                        "Content": "Content goes here",
                        "Button Text": "Get Started"
                    }
                },
                {
                    "title": "Content End",
                    "slug": "example-content-end",
                    "category": "system",
                    "content": "</div>",
                    "default_parameters": {}
                },
                {
                    "title": "Footer",
                    "slug": "example-footer",
                    "category": "content",
                    "content": "<footer>\r\n<p>&copy; 2025 {{company_name}}</p>\r\n</footer>",
                    "default_parameters": {
                        "company_name": "Your Company"
                    }
                },
                {
                    "title": "Body Close",
                    "slug": "example-body-close",
                    "category": "system",
                    "content": "<script src=\"{{config:base_url}}/js/scripts.js\"></script>\r\n</body>\r\n</html>",
                    "default_parameters": {}
                }
            ]
        }
    ]

    # Generate slug prefix from template name
    template_prefix = template_name.lower().replace(' ', '-').replace('_', '-')
    # Remove special characters and multiple dashes
    import re
    template_prefix = re.sub(r'[^a-z0-9-]', '', template_prefix)
    template_prefix = re.sub(r'-+', '-', template_prefix).strip('-')

    # Create AI prompt by substituting placeholders
    prompt = prompt_template.format(
        example_json=json.dumps(example_json, indent=2),
        html_content=html_content,
        template_name=template_name,
        template_prefix=template_prefix
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
