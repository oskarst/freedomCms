#!/usr/bin/env python3
"""
Page publishing service for Devall CMS
"""

import os
from jinja2 import Template
from markupsafe import Markup
from ..db import get_db, PUB_DIR

def generate_page_html(page_id, preview=False):
    """Generate static HTML for a page"""
    db = get_db()
    cursor = db.cursor()

    # Get page info
    cursor.execute('SELECT * FROM pages WHERE id = ?', (page_id,))
    page = cursor.fetchone()

    if not page:
        return "Page not found", 404

    # Get page templates with parameters
    cursor.execute('''
        SELECT pt.id, pt.custom_content, pt.use_default, t.content as default_content, t.slug
        FROM page_templates pt
        JOIN page_template_defs t ON pt.template_id = t.id
        WHERE pt.page_id = ?
        ORDER BY pt.sort_order
    ''', (page_id,))
    page_templates = cursor.fetchall()

    # Build HTML content
    html_content = ''
    for pt in page_templates:
        # Use the content based on user's choice (use_default flag)
        if pt['use_default']:
            content = pt['default_content']
        else:
            content = pt['custom_content']
        
        # Check if this template has parameters and replace them
        cursor.execute('''
            SELECT parameter_name, parameter_value 
            FROM page_template_parameters 
            WHERE page_template_id = ?
        ''', (pt['id'],))
        parameters = {row['parameter_name']: row['parameter_value'] for row in cursor.fetchall()}
        
        # Replace parameters with actual content
        if content and '{{' in content and parameters:
            for param_name, param_value in parameters.items():
                # Handle various parameter formats
                content = content.replace(f'{{{{ {param_name} }}}}', param_value)
                content = content.replace(f'{{{{{param_name}}}}}', param_value)  # Handle without spaces
                content = content.replace(f'{{{{ {param_name.strip()} }}}}', param_value)  # Handle with extra spaces
                content = content.replace(f'{{{{{param_name.strip()}}}}}', param_value)  # Handle without spaces and extra spaces
        
        html_content += content

    if preview:
        # Return HTML directly for preview
        return html_content
    else:
        # Save to file
        os.makedirs(PUB_DIR, exist_ok=True)
        filename = os.path.join(PUB_DIR, f'{page["slug"]}.html')

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return filename

def generate_blog_post_html(post_id, preview=False):
    raise NotImplementedError('Blog feature has been removed')

def generate_blog_index_pages(per_page=10):
    raise NotImplementedError('Blog feature has been removed')
