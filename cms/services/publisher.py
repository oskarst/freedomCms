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

    # Helper: replace special tokens within a content string
    def replace_special_tokens(raw_content: str) -> str:
        if not raw_content or '{{' not in raw_content:
            return raw_content

        content_out = raw_content

        # First handle simple conditionals like {{if page:featured}}...{{/if}}
        # Supported keys: page:featured, page:excerpt, page:title
        import re as _re
        def _evaluate_condition(key: str) -> bool:
            key = key.strip().lower()
            if key == 'page:featured':
                return bool((page['featured_png'] or page['featured_webp']) if 'featured_png' in page.keys() or 'featured_webp' in page.keys() else False)
            if key == 'page:excerpt':
                return bool((page['excerpt'] or '').strip() if 'excerpt' in page.keys() else False)
            if key == 'page:title':
                return bool((page['title'] or '').strip())
            return False

        # Apply conditionals iteratively until none remain
        pattern = _re.compile(r"\{\{\s*if\s+([^}]+)\s*\}\}(.*?)\{\{\s*/if\s*\}\}", _re.DOTALL | _re.IGNORECASE)
        while True:
            m = pattern.search(content_out)
            if not m:
                break
            cond_key = m.group(1)
            inner = m.group(2)
            replacement = inner if _evaluate_condition(cond_key) else ''
            content_out = content_out[:m.start()] + replacement + content_out[m.end():]

        # Page-level tokens
        # {{page:title}}
        content_out = content_out.replace('{{page:title}}', page['title'] or '')
        # {{page:excerpt}}
        content_out = content_out.replace('{{page:excerpt}}', (page['excerpt'] or '') if 'excerpt' in page.keys() else '')
        # {{page:featured:png}} and {{page:featured:webp}}
        featured_png_url = ''
        featured_webp_url = ''
        if 'featured_png' in page.keys() and page['featured_png']:
            featured_png_url = page['featured_png']
        if 'featured_webp' in page.keys() and page['featured_webp']:
            featured_webp_url = page['featured_webp']
        
        # Get base_url from settings to prepend to featured image URLs
        cursor.execute('SELECT value FROM settings WHERE key = ?', ('base_url',))
        base_url_row = cursor.fetchone()
        base_url = base_url_row['value'] if base_url_row else 'http://localhost:5000'
        
        content_out = content_out.replace('{{page:featured:png}}', f"{base_url}{featured_png_url}")
        content_out = content_out.replace('{{page:featured:webp}}', f"{base_url}{featured_webp_url}")

        # Config tokens
        # {{config:base_url}}
        if '{{config:base_url}}' in content_out:
            cursor.execute('SELECT value FROM settings WHERE key = ?', ('base_url',))
            row = cursor.fetchone()
            base_url = row['value'] if row and 'value' in row.keys() else 'http://localhost:5000'
            content_out = content_out.replace('{{config:base_url}}', base_url)

        # Blog tokens
        # {{blog:categories}} -> UL of categories with links to blog container page
        if '{{blog:categories}}' in content_out:
            # Find blog container page (first one)
            cursor.execute('SELECT slug FROM pages WHERE is_blog_container = 1 ORDER BY id LIMIT 1')
            row = cursor.fetchone()
            container_slug = row['slug'] if row and 'slug' in row.keys() else 'index'

            # Load categories
            cursor.execute("""
                SELECT id, COALESCE(NULLIF(title, ''), slug) as title, slug
                FROM blog_categories
                ORDER BY sort_order, title
            """)
            cats = cursor.fetchall()
            if cats:
                items = []
                for c in cats:
                    href = f'/{container_slug}.html?category={c["slug"]}'
                    items.append(f'<li><a href="{href}">{c["title"]}</a></li>')
                html = '<ul>' + ''.join(items) + '</ul>'
            else:
                html = '<ul></ul>'
            content_out = content_out.replace('{{blog:categories}}', html)

        # {{blog:latest}} -> UL of all published blog posts ordered by date (newest first)
        if '{{blog:latest}}' in content_out:
            # Get base_url from settings
            cursor.execute('SELECT value FROM settings WHERE key = ?', ('base_url',))
            base_url_row = cursor.fetchone()
            base_url = base_url_row['value'] if base_url_row else 'http://localhost:5000'
            
            cursor.execute(
                """
                SELECT title, slug, excerpt, featured_png, featured_webp, author, published_date
                FROM pages
                WHERE type = 'blog' AND published = 1
                ORDER BY COALESCE(published_date, created_at) DESC
                """
            )
            posts = cursor.fetchall()
            if posts:
                items = []
                for r in posts:
                    href = f'/blog/{r["slug"]}.html'
                    title = r['title'] or r['slug']
                    excerpt = (r['excerpt'] or '').strip() if 'excerpt' in r.keys() else ''
                    
                    # Check for featured image
                    featured_img = ''
                    if 'featured_png' in r.keys() and r['featured_png']:
                        # Use PNG version, fallback to WebP
                        img_path = r['featured_png']
                        featured_img = f'<img src="{base_url}{img_path}" alt="{title}" class="blog-featured-image" style="max-width: 200px; height: auto; margin-bottom: 8px;">'
                    elif 'featured_webp' in r.keys() and r['featured_webp']:
                        img_path = r['featured_webp']
                        featured_img = f'<img src="{base_url}{img_path}" alt="{title}" class="blog-featured-image" style="max-width: 200px; height: auto; margin-bottom: 8px;">'
                    
                    # Get author and published date
                    author = r['author'] if 'author' in r.keys() and r['author'] else None
                    published_date = r['published_date'] if 'published_date' in r.keys() and r['published_date'] else None
                    
                    # Build metadata (author and date)
                    metadata = []
                    if author:
                        metadata.append(f'<span class="blog-author">By {author}</span>')
                    if published_date:
                        metadata.append(f'<span class="blog-date">{published_date}</span>')
                    metadata_html = f'<div class="blog-meta">{" | ".join(metadata)}</div>' if metadata else ''
                    
                    # Build the list item with featured image, metadata, and excerpt if they exist
                    if featured_img and excerpt:
                        items.append(f'<li class="blog-latest-item"><span class="blog-featured-image">{featured_img}</span><a href="{href}">{title}</a>{metadata_html}<div class="excerpt">{excerpt}</div></li>')
                    elif featured_img:
                        items.append(f'<li class="blog-latest-item"><span class="blog-featured-image">{featured_img}</span><a href="{href}">{title}</a>{metadata_html}</li>')
                    elif excerpt:
                        items.append(f'<li class="blog-latest-item"><a href="{href}">{title}</a>{metadata_html}<div class="excerpt">{excerpt}</div></li>')
                    else:
                        items.append(f'<li class="blog-latest-item"><a href="{href}">{title}</a>{metadata_html}</li>')
                html = '<ul class="blog-latest">' + ''.join(items) + '</ul>'
            else:
                html = '<ul class="blog-latest"></ul>'
            content_out = content_out.replace('{{blog:latest}}', html)

        # {{blog:category:[id]}} -> UL of posts within category id
        # support also {{blog:category:id}}
        def _replace_category_posts(match):
            cat_id_raw = match.group(1) or ''
            cat_id = None
            try:
                cat_id = int(cat_id_raw.strip())
            except Exception:
                return ''
            # Load posts within category
            cursor.execute("""
                SELECT p.title, p.slug
                FROM pages p
                JOIN page_blog_categories pc ON pc.page_id = p.id
                WHERE p.type = 'blog' AND pc.category_id = ?
                ORDER BY p.created_at DESC
            """, (cat_id,))
            posts = cursor.fetchall()
            if not posts:
                return '<ul></ul>'
            items = []
            for r in posts:
                # Blog posts are published under /blog/slug.html
                href = f'/blog/{r["slug"]}.html'
                items.append(f'<li><a href="{href}">{r["title"]}</a></li>')
            return '<ul>' + ''.join(items) + '</ul>'

        # [id] or :id pattern
        # {{blog:category:[123]}} or {{blog:category:123}}
        content_out = _re.sub(r"\{\{\s*blog:category:\[(\d+)\]\s*\}\}", _replace_category_posts, content_out)
        content_out = _re.sub(r"\{\{\s*blog:category:(\d+)\s*\}\}", _replace_category_posts, content_out)

        return content_out

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
        if content and '{{' in content:
            # First replace user-defined parameters
            if parameters:
                for param_name, param_value in parameters.items():
                    content = content.replace(f'{{{{ {param_name} }}}}', param_value)
                    content = content.replace(f'{{{{{param_name}}}}}', param_value)
                    content = content.replace(f'{{{{ {param_name.strip()} }}}}', param_value)
                    content = content.replace(f'{{{{{param_name.strip()}}}}}', param_value)
            # Then replace special tokens (blog/page)
            content = replace_special_tokens(content)
        
        html_content += content

    if preview:
        # Return HTML directly for preview
        return html_content
    else:
        # Save to file
        # Blog posts go under pub/blog/, other pages in pub/
        if 'type' in page.keys() and page['type'] == 'blog':
            out_dir = os.path.join(PUB_DIR, 'blog')
            os.makedirs(out_dir, exist_ok=True)
            filename = os.path.join(out_dir, f'{page["slug"]}.html')
        else:
            os.makedirs(PUB_DIR, exist_ok=True)
            filename = os.path.join(PUB_DIR, f'{page["slug"]}.html')

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return filename

