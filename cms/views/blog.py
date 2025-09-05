#!/usr/bin/env python3
"""
Blog blueprint: CRUD for posts, publishing posts and index with pagination
"""

import os
from flask import Blueprint, request, redirect, url_for, render_template, flash
from ..auth import login_required, admin_required
from ..db import get_db, PUB_DIR
from ..utils import slugify
from ..services.publisher import generate_blog_post_html, generate_blog_index_pages

bp = Blueprint('blog', __name__)

@bp.route('/blog')
@login_required
@admin_required
def blog_list():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM blog_posts ORDER BY created_at DESC')
    posts = cursor.fetchall()
    cursor.execute('SELECT COUNT(*) as cnt FROM blog_categories')
    cat_count = cursor.fetchone()['cnt']
    return render_template('blog/list.html', posts=posts, cat_count=cat_count)

@bp.route('/blog/categories', methods=['GET', 'POST'])
@login_required
@admin_required
def blog_categories():
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form.get('name', '').strip()
            slug = request.form.get('slug', '').strip() or slugify(name)
            if not name:
                flash('Category name is required', 'error')
            else:
                cursor.execute('SELECT id FROM blog_categories WHERE slug = ?', (slug,))
                if cursor.fetchone():
                    flash('Category with this slug already exists', 'error')
                else:
                    cursor.execute('INSERT INTO blog_categories (name, slug) VALUES (?, ?)', (name, slug))
                    db.commit()
                    flash('Category added', 'success')
        elif action == 'delete':
            cid = request.form.get('category_id')
            cursor.execute('DELETE FROM blog_categories WHERE id = ?', (cid,))
            db.commit()
            flash('Category deleted', 'success')
        return redirect(url_for('blog.blog_categories'))

    cursor.execute('SELECT * FROM blog_categories ORDER BY name')
    categories = cursor.fetchall()
    return render_template('blog/categories.html', categories=categories)

@bp.route('/blog/add', methods=['GET', 'POST'])
@login_required
@admin_required
def blog_add():
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        slug = request.form.get('slug', '').strip() or slugify(title)
        content = request.form.get('content', '')
        excerpt = request.form.get('excerpt', '')
        featured_image_url = request.form.get('featured_image_url', '').strip()
        featured = request.form.get('featured') == 'on'
        category_ids = request.form.getlist('categories')

        if not title:
            flash('Title is required', 'error')
            return redirect(url_for('blog.blog_add'))

        cursor.execute('SELECT id FROM blog_posts WHERE slug = ?', (slug,))
        if cursor.fetchone():
            flash('A post with this slug already exists', 'error')
            return redirect(url_for('blog.blog_add'))

        cursor.execute('''
            INSERT INTO blog_posts (title, slug, content, excerpt, featured_image_url, featured)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, slug, content, excerpt, featured_image_url, int(featured)))
        post_id = cursor.lastrowid

        # Categories
        for cid in category_ids:
            cursor.execute('INSERT OR IGNORE INTO blog_post_categories (post_id, category_id) VALUES (?, ?)', (post_id, int(cid)))

        # Attach blog templates from submitted form (or defaults if not provided)
        cursor.execute("SELECT id, content, sort_order FROM blog_template_defs WHERE is_default = 1 ORDER BY sort_order")
        blog_defaults = cursor.fetchall()
        for idx, t in enumerate(blog_defaults):
            tid = t['id']
            use_default = request.form.get(f'bt_use_default_{tid}') == 'on'
            custom_content = request.form.get(f'bt_template_{tid}', '')
            cursor.execute('INSERT INTO blog_post_templates (post_id, template_id, custom_content, use_default, sort_order) VALUES (?, ?, ?, ?, ?)',
                           (post_id, tid, custom_content, int(use_default), idx))

        db.commit()
        flash('Blog post created', 'success')
        return redirect(url_for('blog.blog_edit', post_id=post_id))

    cursor.execute('SELECT * FROM blog_categories ORDER BY name')
    categories = cursor.fetchall()
    # Load default blog templates to display on add form
    cursor.execute("SELECT id, title, slug, content FROM blog_template_defs WHERE is_default = 1 ORDER BY sort_order")
    blog_templates = cursor.fetchall()
    return render_template('blog/add.html', categories=categories, blog_templates=blog_templates)

@bp.route('/blog/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def blog_edit(post_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT * FROM blog_posts WHERE id = ?', (post_id,))
    post = cursor.fetchone()
    if not post:
        flash('Post not found', 'error')
        return redirect(url_for('blog.blog_list'))

    # Ensure blog templates exist in DB (seed if missing)
    cursor.execute("SELECT COUNT(*) as cnt FROM blog_template_defs")
    bt_cnt = cursor.fetchone()['cnt']
    # (seeding is handled in init_db for blog_template_defs)

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save':
            title = request.form.get('title', '').strip()
            slug = request.form.get('slug', '').strip() or slugify(title)
            content = request.form.get('content', '')
            excerpt = request.form.get('excerpt', '')
            featured_image_url = request.form.get('featured_image_url', '').strip()
            featured = request.form.get('featured') == 'on'
            category_ids = [int(x) for x in request.form.getlist('categories')]

            if not title:
                flash('Title is required', 'error')
                return redirect(url_for('blog.blog_edit', post_id=post_id))

            # Ensure slug uniqueness except current
            cursor.execute('SELECT id FROM blog_posts WHERE slug = ? AND id != ?', (slug, post_id))
            if cursor.fetchone():
                flash('A post with this slug already exists', 'error')
                return redirect(url_for('blog.blog_edit', post_id=post_id))

            cursor.execute('''
                UPDATE blog_posts SET title = ?, slug = ?, content = ?, excerpt = ?, featured_image_url = ?, featured = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (title, slug, content, excerpt, featured_image_url, int(featured), post_id))

            # Update categories
            cursor.execute('DELETE FROM blog_post_categories WHERE post_id = ?', (post_id,))
            for cid in category_ids:
                cursor.execute('INSERT OR IGNORE INTO blog_post_categories (post_id, category_id) VALUES (?, ?)', (post_id, cid))

            # Update blog template blocks
            cursor.execute('SELECT id, template_id FROM blog_post_templates WHERE post_id = ?', (post_id,))
            bt_rows = cursor.fetchall()
            for bt in bt_rows:
                use_default = request.form.get(f'bt_use_default_{bt["template_id"]}') == 'on'
                custom_content = request.form.get(f'bt_template_{bt["template_id"]}', '')
                sort_order = request.form.get(f'sort_order_{bt["template_id"]}', None)
                if sort_order is not None:
                    try:
                        sort_order = int(sort_order)
                    except ValueError:
                        sort_order = None
                if sort_order is None:
                    cursor.execute('UPDATE blog_post_templates SET custom_content = ?, use_default = ? WHERE id = ?', (custom_content, int(use_default), bt['id']))
                else:
                    cursor.execute('UPDATE blog_post_templates SET custom_content = ?, use_default = ?, sort_order = ? WHERE id = ?', (custom_content, int(use_default), sort_order, bt['id']))

            db.commit()
            flash('Post saved', 'success')
        elif action == 'publish':
            generate_blog_post_html(post_id)
            cursor.execute('UPDATE blog_posts SET published = 1 WHERE id = ?', (post_id,))
            db.commit()
            flash('Post published', 'success')
        return redirect(url_for('blog.blog_edit', post_id=post_id))

    # Ensure post has all default BLOG templates
    cursor.execute('SELECT template_id FROM blog_post_templates WHERE post_id = ?', (post_id,))
    existing_bt = {row['template_id'] for row in cursor.fetchall()}
    cursor.execute("SELECT id FROM templates WHERE is_default = 1 AND slug LIKE 'blog_%' ORDER BY sort_order")
    blog_defaults = [row['id'] for row in cursor.fetchall()]
    if blog_defaults:
        cursor.execute('SELECT COALESCE(MAX(sort_order), 0) as maxo FROM blog_post_templates WHERE post_id = ?', (post_id,))
        maxo = cursor.fetchone()['maxo'] or 0
        to_add = [tid for tid in blog_defaults if tid not in existing_bt]
        for offset, tid in enumerate(to_add, start=1):
            cursor.execute('INSERT INTO blog_post_templates (post_id, template_id, use_default, sort_order) VALUES (?, ?, 1, ?)', (post_id, tid, maxo + offset))
        if to_add:
            db.commit()

    cursor.execute('SELECT * FROM blog_categories ORDER BY name')
    categories = cursor.fetchall()
    cursor.execute('SELECT category_id FROM blog_post_categories WHERE post_id = ?', (post_id,))
    selected = {row['category_id'] for row in cursor.fetchall()}
    # Load templates assigned to post
    cursor.execute('''
        SELECT bt.id, bt.template_id, bt.custom_content, bt.use_default, bt.sort_order,
               t.title, t.slug, t.content as default_content
        FROM blog_post_templates bt
        JOIN blog_template_defs t ON bt.template_id = t.id
        WHERE bt.post_id = ?
        ORDER BY bt.sort_order
    ''', (post_id,))
    post_templates = cursor.fetchall()

    return render_template('blog/edit.html', post=post, categories=categories, selected_categories=selected, post_templates=post_templates)

@bp.route('/blog/<int:post_id>/preview')
@login_required
@admin_required
def blog_preview(post_id):
    html_content = generate_blog_post_html(post_id, preview=True)
    if isinstance(html_content, tuple):
        flash(html_content[0], 'error')
        return redirect(url_for('blog.blog_list'))
    from flask import Response
    return Response(html_content, mimetype='text/html')

@bp.route('/blog/<int:post_id>/delete', methods=['POST'])
@login_required
@admin_required
def blog_delete(post_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT title FROM blog_posts WHERE id = ?', (post_id,))
    post = cursor.fetchone()
    if not post:
        flash('Post not found', 'error')
        return redirect(url_for('blog.blog_list'))
    cursor.execute('DELETE FROM blog_posts WHERE id = ?', (post_id,))
    db.commit()
    flash(f'Post "{post["title"]}" deleted', 'success')
    return redirect(url_for('blog.blog_list'))

@bp.route('/blog/generate-index', methods=['POST'])
@login_required
@admin_required
def blog_generate_index():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', ('blog_posts_per_page',))
    row = cursor.fetchone()
    per_page = int(row['value']) if row and row['value'].isdigit() else 10
    generate_blog_index_pages(per_page)
    flash('Blog index generated', 'success')
    return redirect(url_for('blog.blog_list'))


