#!/usr/bin/env python3
"""
Page publishing service for Devall CMS
"""

import os
from jinja2 import Template
from markupsafe import Markup
from datetime import datetime
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
                    href = f'{base_url}/{container_slug}.html?category={c["slug"]}'
                    items.append(f'<li><a href="{href}">{c["title"]}</a></li>')
                html = '<ul>' + ''.join(items) + '</ul>'
            else:
                html = '<ul></ul>'
            content_out = content_out.replace('{{blog:categories}}', html)

        # {{blog:latest}} -> UL of all published blog posts ordered by date (newest first)
        if '{{blog:latest}}' in content_out:
            # Get base_url and blog_latest_template from settings
            cursor.execute('SELECT value FROM settings WHERE key = ?', ('base_url',))
            base_url_row = cursor.fetchone()
            base_url = base_url_row['value'] if base_url_row else 'http://localhost:5000'
            
            cursor.execute('SELECT value FROM settings WHERE key = ?', ('blog_latest_template',))
            template_row = cursor.fetchone()
            blog_template = template_row['value'] if template_row else '<ul class="blog-latest">\n{items}\n</ul>'
            
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
                    # Prepare all available attributes for the template
                    post_attrs = {
                        'title': r['title'] or r['slug'],
                        'slug': r['slug'],
                        'href': f'{base_url}/blog/{r["slug"]}.html',
                        'excerpt': (r['excerpt'] or '').strip() if 'excerpt' in r.keys() else '',
                        'author': r['author'] if 'author' in r.keys() and r['author'] else '',
                        'published_date': r['published_date'] if 'published_date' in r.keys() and r['published_date'] else '',
                        'featured_png': r['featured_png'] if 'featured_png' in r.keys() and r['featured_png'] else '',
                        'featured_webp': r['featured_webp'] if 'featured_webp' in r.keys() and r['featured_webp'] else '',
                    }
                    
                    # Generate featured image HTML if available
                    featured_img = ''
                    if post_attrs['featured_png']:
                        img_path = post_attrs['featured_png']
                        featured_img = f'<img src="{base_url}{img_path}" alt="{post_attrs["title"]}" class="blog-featured-image" style="max-width: 200px; height: auto; margin-bottom: 8px;">'
                    elif post_attrs['featured_webp']:
                        img_path = post_attrs['featured_webp']
                        featured_img = f'<img src="{base_url}{img_path}" alt="{post_attrs["title"]}" class="blog-featured-image" style="max-width: 200px; height: auto; margin-bottom: 8px;">'
                    
                    # Build metadata HTML
                    metadata = []
                    if post_attrs['author']:
                        metadata.append(f'<span class="blog-author">By {post_attrs["author"]}</span>')
                    if post_attrs['published_date']:
                        metadata.append(f'<span class="blog-date">{post_attrs["published_date"]}</span>')
                    metadata_html = f'<div class="blog-meta">{" | ".join(metadata)}</div>' if metadata else ''
                    
                    # Add computed fields to attributes
                    post_attrs.update({
                        'featured_image': featured_img,
                        'metadata': metadata_html,
                        'base_url': base_url
                    })
                    
                    # Create default item template if none specified in blog_template
                    if '{items}' in blog_template:
                        # Use the outer template structure and create default item content
                        if featured_img and post_attrs['excerpt']:
                            item_html = f'<li class="blog-latest-item"><span class="blog-featured-image">{featured_img}</span><a href="{post_attrs["href"]}">{post_attrs["title"]}</a>{metadata_html}<div class="excerpt">{post_attrs["excerpt"]}</div></li>'
                        elif featured_img:
                            item_html = f'<li class="blog-latest-item"><span class="blog-featured-image">{featured_img}</span><a href="{post_attrs["href"]}">{post_attrs["title"]}</a>{metadata_html}</li>'
                        elif post_attrs['excerpt']:
                            item_html = f'<li class="blog-latest-item"><a href="{post_attrs["href"]}">{post_attrs["title"]}</a>{metadata_html}<div class="excerpt">{post_attrs["excerpt"]}</div></li>'
                        else:
                            item_html = f'<li class="blog-latest-item"><a href="{post_attrs["href"]}">{post_attrs["title"]}</a>{metadata_html}</li>'
                        items.append(item_html)
                    else:
                        # Use the template as-is with parameter substitution
                        item_html = blog_template
                        for key, value in post_attrs.items():
                            # Replace both single and double brace syntax for compatibility
                            # Order matters: process double braces first to avoid conflicts
                            item_html = item_html.replace(f'{{{{ {key} }}}}', str(value))
                            item_html = item_html.replace(f'{{{{{key}}}}}', str(value))
                            item_html = item_html.replace(f'{{{key}}}', str(value))
                        items.append(item_html)
                
                # Generate final HTML
                if '{items}' in blog_template:
                    html = blog_template.replace('{items}', ''.join(items))
                else:
                    # Template contains only li elements, wrap them with ul
                    html = f'<ul class="blog-latest">{"".join(items)}</ul>'
            else:
                # Empty state - use template structure if it has {items}, otherwise empty ul
                if '{items}' in blog_template:
                    html = blog_template.replace('{items}', '')
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
                href = f'{base_url}/blog/{r["slug"]}.html'
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

def generate_sitemap():
    """Generate sitemap.xml with all published pages and blog posts"""
    db = get_db()
    cursor = db.cursor()
    
    # Get base_url from settings
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('base_url',))
    base_url_row = cursor.fetchone()
    base_url = base_url_row['value'] if base_url_row else 'http://localhost:5000'
    
    # Remove trailing slash from base_url if present
    base_url = base_url.rstrip('/')
    
    # Get all published pages and blog posts
    cursor.execute('''
        SELECT slug, type, updated_at, published_date
        FROM pages 
        WHERE published = 1 
        ORDER BY 
            CASE WHEN type = 'page' THEN 1 ELSE 2 END,
            COALESCE(published_date, updated_at, created_at) DESC
    ''')
    pages = cursor.fetchall()
    
    # Generate sitemap XML
    sitemap_content = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
'''
    
    for page in pages:
        slug = page['slug']
        page_type = page['type']
        updated_at = page['updated_at']
        published_date = page['published_date']
        
        # Determine URL path
        if page_type == 'blog':
            url_path = f'/blog/{slug}.html'
        else:
            url_path = f'/{slug}.html'
        
        # Use published_date if available, otherwise use updated_at
        lastmod = published_date if published_date else updated_at
        
        # Format lastmod date (ensure it's in YYYY-MM-DD format)
        if lastmod:
            try:
                # Parse the date and reformat it
                if 'T' in lastmod:
                    lastmod_date = datetime.fromisoformat(lastmod.replace('Z', '+00:00')).date()
                else:
                    lastmod_date = datetime.strptime(lastmod, '%Y-%m-%d').date()
                lastmod_str = lastmod_date.strftime('%Y-%m-%d')
            except:
                # Fallback to current date if parsing fails
                lastmod_str = datetime.now().strftime('%Y-%m-%d')
        else:
            lastmod_str = datetime.now().strftime('%Y-%m-%d')
        
        # Set priority based on page type
        if page_type == 'blog':
            priority = '0.8'
            changefreq = 'weekly'
        else:
            priority = '1.0'
            changefreq = 'monthly'
        
        sitemap_content += f'''  <url>
    <loc>{base_url}{url_path}</loc>
    <lastmod>{lastmod_str}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>{priority}</priority>
  </url>
'''
    
    sitemap_content += '</urlset>'
    
    # Write sitemap to pub directory
    sitemap_path = os.path.join(PUB_DIR, 'sitemap.xml')
    with open(sitemap_path, 'w', encoding='utf-8') as f:
        f.write(sitemap_content)
    
    return sitemap_path

