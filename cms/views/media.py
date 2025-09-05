#!/usr/bin/env python3
"""
Media blueprint for Devall CMS
"""

import os
from io import BytesIO
from flask import Blueprint, request, redirect, url_for, render_template, flash
from ..auth import login_required, admin_required
from ..db import get_db, PUB_DIR
from ..utils import slugify

try:
    from PIL import Image
except Exception:
    Image = None

bp = Blueprint('media', __name__)

IMAGES_DIR = os.path.join(PUB_DIR, 'content', 'images')

@bp.route('/media', methods=['GET', 'POST'])
@login_required
@admin_required
def media_list():
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'upload':
            file = request.files.get('image')
            title = request.form.get('title', '').strip()
            alt = request.form.get('alt', '').strip()
            if not file or file.filename == '':
                flash('Please select an image to upload', 'error')
                return redirect(url_for('media.media_list'))
            if Image is None:
                flash('Pillow is not installed. Cannot process images.', 'error')
                return redirect(url_for('media.media_list'))
            os.makedirs(IMAGES_DIR, exist_ok=True)

            # Derive base filename and extension
            filename = os.path.basename(file.filename)
            name, ext = os.path.splitext(filename)
            ext = ext.lower()
            base = slugify(name) or 'image'

            # Ensure unique base
            candidate = base
            counter = 1
            while True:
                original_path = os.path.join(IMAGES_DIR, f"{candidate}{ext}")
                if not os.path.exists(original_path):
                    break
                counter += 1
                candidate = f"{base}-{counter}"
            base = candidate
            original_path = os.path.join(IMAGES_DIR, f"{base}{ext}")

            # Save original
            file.save(original_path)

            # Read size settings
            cursor.execute('SELECT key, value FROM settings WHERE key IN ("media_small_width","media_medium_width","media_large_width")')
            width_map = {row['key']: int(row['value']) for row in cursor.fetchall()}
            small_w = width_map.get('media_small_width', 320)
            medium_w = width_map.get('media_medium_width', 640)
            large_w = width_map.get('media_large_width', 1024)

            # Generate resized variants
            small_path = os.path.join(IMAGES_DIR, f"{base}_small{ext}")
            medium_path = os.path.join(IMAGES_DIR, f"{base}_medium{ext}")
            large_path = os.path.join(IMAGES_DIR, f"{base}_large{ext}")

            try:
                with Image.open(original_path) as img:
                    img = img.convert('RGB') if ext.lower() in ('.jpg', '.jpeg', '.webp') else img
                    def save_resized(target_w, out_path):
                        im = img.copy()
                        im.thumbnail((target_w, target_w*10), Image.LANCZOS)
                        im.save(out_path)
                    save_resized(small_w, small_path)
                    save_resized(medium_w, medium_path)
                    save_resized(large_w, large_path)
            except Exception as e:
                flash(f'Failed to resize image: {str(e)}', 'error')
                # Cleanup on error
                for p in [original_path, small_path, medium_path, large_path]:
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass
                return redirect(url_for('media.media_list'))

            # Insert DB record
            cursor.execute('''
                INSERT INTO media (filename, ext, title, alt, original_path, small_path, medium_path, large_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (base, ext, title, alt, original_path, small_path, medium_path, large_path))
            db.commit()
            flash('Image uploaded', 'success')
            return redirect(url_for('media.media_list'))

        elif action == 'delete':
            media_id = request.form.get('media_id')
            cursor.execute('SELECT * FROM media WHERE id = ?', (media_id,))
            row = cursor.fetchone()
            if row:
                for p in [row['original_path'], row['small_path'], row['medium_path'], row['large_path']]:
                    try:
                        if p and os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass
                cursor.execute('DELETE FROM media WHERE id = ?', (media_id,))
                db.commit()
                flash('Image deleted', 'success')
            return redirect(url_for('media.media_list'))

    cursor.execute('SELECT * FROM media ORDER BY created_at DESC')
    items = cursor.fetchall()
    # Build URLs relative to pub
    def to_url(path):
        if not path:
            return ''
        # Normalize path separators
        p = path.replace('\\', '/')
        pub = PUB_DIR.replace('\\', '/').strip('/')
        if p.startswith(pub + '/'):
            return '/' + p
        # Fallback: prefix with /pub
        if p.startswith('/'):
            return '/' + pub + p
        return '/' + pub + '/' + p
    media_items = []
    for it in items:
        media_items.append({
            'id': it['id'],
            'title': it['title'] or it['filename'],
            'alt': it['alt'] or it['title'] or it['filename'],
            'orig': to_url(it['original_path']),
            'small': to_url(it['small_path']),
            'medium': to_url(it['medium_path']),
            'large': to_url(it['large_path']),
            'filename': f"{it['filename']}{it['ext']}"
        })

    # Read widths for building example tags
    cursor.execute('SELECT key, value FROM settings WHERE key IN ("media_small_width","media_medium_width","media_large_width")')
    widths = {row['key']: row['value'] for row in cursor.fetchall()}

    return render_template('media/list.html', media=media_items, widths=widths)

@bp.route('/media/list.json')
@login_required
@admin_required
def media_list_json():
    db = get_db()
    cursor = db.cursor()

    cursor.execute('SELECT * FROM media ORDER BY created_at DESC')
    items = cursor.fetchall()

    def to_url(path):
        if not path:
            return ''
        p = path.replace('\\', '/')
        pub = PUB_DIR.replace('\\', '/').strip('/')
        if p.startswith(pub + '/'):
            return '/' + p
        if p.startswith('/'):
            return '/' + pub + p
        return '/' + pub + '/' + p

    media_items = []
    for it in items:
        media_items.append({
            'id': it['id'],
            'title': it['title'] or it['filename'],
            'alt': it['alt'] or it['title'] or it['filename'],
            'original': to_url(it['original_path']),
            'small': to_url(it['small_path']),
            'medium': to_url(it['medium_path']),
            'large': to_url(it['large_path']),
        })

    from flask import jsonify
    return jsonify({'media': media_items})
