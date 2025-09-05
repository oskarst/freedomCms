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

    # Get page templates
    cursor.execute('''
        SELECT pt.custom_content, pt.use_default, t.content as default_content, t.slug
        FROM page_templates pt
        JOIN page_template_defs t ON pt.template_id = t.id
        WHERE pt.page_id = ?
        ORDER BY pt.sort_order
    ''', (page_id,))
    page_templates = cursor.fetchall()

    # Build HTML content
    html_content = ''
    for pt in page_templates:
        content = pt['default_content'] if pt['use_default'] else pt['custom_content']
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
    """Generate static HTML for a single blog post using its assigned blog templates.
    Supports simple Jinja-style variables like {{ title }} and {{ content }} inside template blocks.
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT * FROM blog_posts WHERE id = ?', (post_id,))
    post = cursor.fetchone()
    if not post:
        return 'Post not found', 404

    # Load blog post template blocks in order
    cursor.execute('''
        SELECT bt.custom_content, bt.use_default, t.content as default_content, t.slug
        FROM blog_post_templates bt
        JOIN blog_template_defs t ON bt.template_id = t.id
        WHERE bt.post_id = ?
        ORDER BY bt.sort_order
    ''', (post_id,))
    blocks = cursor.fetchall()

    # Context for template rendering
    context = {
        'title': post['title'],
        'content': post['content'] or '',
        'excerpt': post['excerpt'] or '',
        'featured_image_url': post['featured_image_url'] or '',
        'post': post,
    }

    html = ''
    for b in blocks:
        # Fallback to default content if custom content is empty
        use_default = b['use_default'] or not (b['custom_content'] and b['custom_content'].strip())
        raw = b['default_content'] if use_default else b['custom_content']
        try:
            rendered = Template(raw).render(**context)
        except Exception:
            rendered = raw
        html += rendered

    # If no blocks found (legacy posts), fallback to minimal system templates + content
    if not blocks:
        cursor.execute('SELECT slug, content FROM blog_template_defs WHERE slug IN ("base_header","meta","header_close") ORDER BY sort_order')
        sys_t = cursor.fetchall()
        for t in sys_t:
            html += t['content']
        html += f"<div class=\"container py-4\"><h1>{post['title']}</h1><div class=\"mt-3\">{post['content'] or ''}</div></div>"

    if preview:
        return html

    # Write to pub/blog/<slug>.html
    blog_dir = os.path.join(PUB_DIR, 'blog')
    os.makedirs(blog_dir, exist_ok=True)
    filename = os.path.join(blog_dir, f"{post['slug']}.html")
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)
    return filename

def generate_blog_index_pages(per_page=10):
    """Generate blog index pages using blog templates.
    Uses: blog_base_header, blog_meta, blog_header_close, blog_menu,
    blog_index_content (rendered with posts/categories), blog_footer, blog_body_close.
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT * FROM blog_posts WHERE published = 1 ORDER BY created_at DESC')
    posts = cursor.fetchall()

    # Categories and featured posts
    cursor.execute('SELECT * FROM blog_categories ORDER BY name')
    categories = cursor.fetchall()
    cursor.execute('SELECT * FROM blog_posts WHERE featured = 1 AND published = 1 ORDER BY created_at DESC LIMIT 5')
    featured = cursor.fetchall()

    # Read customizable slugs from settings
    cursor.execute('SELECT key, value FROM settings WHERE key LIKE "blog_index_%_slug"')
    slug_settings = {row['key']: row['value'] for row in cursor.fetchall()}
    slugs = {
        'base_header': slug_settings.get('blog_index_base_header_slug', 'blog_base_header'),
        'meta': slug_settings.get('blog_index_meta_slug', 'blog_meta'),
        'header_close': slug_settings.get('blog_index_header_close_slug', 'blog_header_close'),
        'menu': slug_settings.get('blog_index_menu_slug', 'blog_menu'),
        'content': slug_settings.get('blog_index_content_slug', 'blog_index_content'),
        'footer': slug_settings.get('blog_index_footer_slug', 'blog_footer'),
        'body_close': slug_settings.get('blog_index_body_close_slug', 'blog_body_close'),
    }
    # Fetch selected slugs in current templates.sort_order
    selected_slugs = (
        slugs['base_header'], slugs['meta'], slugs['header_close'],
        slugs['menu'], slugs['content'], slugs['footer'], slugs['body_close'],
    )
    placeholders = ','.join(['?'] * len(selected_slugs))
    cursor.execute(
        f'SELECT slug, content FROM templates WHERE slug IN ({placeholders}) ORDER BY sort_order',
        selected_slugs,
    )
    ordered_templates = cursor.fetchall()

    blog_dir = os.path.join(PUB_DIR, 'blog')
    os.makedirs(blog_dir, exist_ok=True)

    # Pagination
    pages = [posts[i:i+per_page] for i in range(0, len(posts), per_page)] or [[]]
    for idx, page_posts in enumerate(pages, start=1):
        html = ''

        # Build posts and categories HTML for template variables
        post_items = []
        for p in page_posts:
            img = ''
            if p['featured_image_url']:
                img = f'<img class="img-fluid mb-2" src="{p["featured_image_url"]}" alt="{p["title"]}">'
            item = f'''<div class="mb-4">{img}<h3><a href="/blog/{p['slug']}.html">{p['title']}</a></h3><p class="text-muted">{(p['excerpt'] or '')}</p></div>'''
            post_items.append(item)
        posts_html = ''.join(post_items)

        categories_html = ''.join([f'<li><a href="#" class="link-dark">{c["name"]}</a></li>' for c in categories])

        # Pagination links appended to posts
        if len(pages) > 1:
            links = []
            for i in range(1, len(pages)+1):
                href = '/blog/index.html' if i == 1 else f'/blog/index_page{i}.html'
                active = 'active fw-bold' if i == idx else ''
                links.append(f'<a class="me-2 {active}" href="{href}">{i}</a>')
            posts_html += '<div class="mt-3">' + '\n'.join(links) + '</div>'

        # Render templates in the configured order; special-case index content
        from jinja2 import Template as _T
        has_body_close = False
        for t in ordered_templates:
            if t['slug'] == slugs['content']:
                index_content = t['content'] or ''
                if index_content:
                    try:
                        html += _T(index_content).render(posts=Markup(posts_html), categories=Markup(categories_html))
                    except Exception:
                        html += index_content
                        html += posts_html
                        html += '<div class="mt-4"><ul>' + categories_html + '</ul></div>'
                else:
                    html += f'<div class="container py-4"><div class="row"><div class="col-lg-8">{posts_html}</div><div class="col-lg-4"><ul>{categories_html}</ul></div></div></div>'
            else:
                html += t['content'] or ''
            if t['slug'] == slugs['body_close']:
                has_body_close = True

        # Ensure closing tags if body_close not present
        if not has_body_close:
            html += '</body></html>'

        # Write
        filename = os.path.join(blog_dir, 'index.html' if idx == 1 else f'index_page{idx}.html')
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)

    return True
