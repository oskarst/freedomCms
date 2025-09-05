#!/usr/bin/env python3
"""
File Manager blueprint for managing files inside PUB_DIR
"""

import os
import pathlib
from flask import Blueprint, request, redirect, url_for, render_template, flash, send_from_directory
from ..auth import login_required, admin_required
from ..db import PUB_DIR

bp = Blueprint('files', __name__)


def _safe_join_pub(rel_path: str) -> str:
    base = os.path.abspath(PUB_DIR)
    target = os.path.abspath(os.path.join(base, rel_path or ''))
    if not target.startswith(base):
        raise ValueError('Path is outside of PUB_DIR')
    return target


def _rel_from_pub(abs_path: str) -> str:
    base = os.path.abspath(PUB_DIR)
    absn = os.path.abspath(abs_path)
    if not absn.startswith(base):
        return ''
    rel = os.path.relpath(absn, base)
    return '' if rel == '.' else rel


@bp.route('/files', methods=['GET', 'POST'])
@login_required
@admin_required
def list_dir():
    # Actions: new_folder, rename, delete (file/folder), upload
    rel_path = request.args.get('path', '').strip()
    try:
        current_dir = _safe_join_pub(rel_path)
    except ValueError:
        flash('Invalid path', 'error')
        return redirect(url_for('files.list_dir'))

    os.makedirs(current_dir, exist_ok=True)

    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'new_folder':
                name = request.form.get('folder_name', '').strip()
                if not name:
                    raise ValueError('Folder name required')
                new_dir = _safe_join_pub(os.path.join(rel_path, name))
                os.makedirs(new_dir, exist_ok=True)
                flash('Folder created', 'success')
            elif action == 'rename':
                old_name = request.form.get('old_name', '').strip()
                new_name = request.form.get('new_name', '').strip()
                if not old_name or not new_name:
                    raise ValueError('Both old and new names are required')
                src = _safe_join_pub(os.path.join(rel_path, old_name))
                dst = _safe_join_pub(os.path.join(rel_path, new_name))
                os.rename(src, dst)
                flash('Renamed successfully', 'success')
            elif action == 'delete':
                target_name = request.form.get('target_name', '').strip()
                target = _safe_join_pub(os.path.join(rel_path, target_name))
                if os.path.isdir(target):
                    # recursive delete
                    import shutil
                    shutil.rmtree(target)
                elif os.path.isfile(target):
                    os.remove(target)
                flash('Deleted', 'success')
            elif action == 'upload':
                f = request.files.get('file')
                if not f or f.filename == '':
                    raise ValueError('Select a file to upload')
                dest = _safe_join_pub(os.path.join(rel_path, f.filename))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                f.save(dest)
                flash('File uploaded', 'success')
        except Exception as e:
            flash(str(e), 'error')
        return redirect(url_for('files.list_dir', path=rel_path))

    # Build listing
    entries = []
    try:
        for name in sorted(os.listdir(current_dir)):
            ap = os.path.join(current_dir, name)
            rel = os.path.join(rel_path, name) if rel_path else name
            entries.append({
                'name': name,
                'rel': rel,
                'is_dir': os.path.isdir(ap),
                'size': os.path.getsize(ap) if os.path.isfile(ap) else None,
                'mtime': os.path.getmtime(ap),
            })
    except FileNotFoundError:
        entries = []

    # Breadcrumbs
    crumbs = []
    accum = ''
    if rel_path:
        for part in pathlib.PurePosixPath(rel_path).parts:
            accum = f"{accum}/{part}" if accum else part
            crumbs.append({'name': part, 'path': accum})

    return render_template('filemanager/list.html', entries=entries, rel_path=rel_path, breadcrumbs=crumbs)


@bp.route('/files/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_file():
    rel_path = request.args.get('path', '').strip()
    try:
        abs_path = _safe_join_pub(rel_path)
    except ValueError:
        flash('Invalid path', 'error')
        return redirect(url_for('files.list_dir'))

    if not os.path.isfile(abs_path):
        flash('File not found', 'error')
        return redirect(url_for('files.list_dir'))

    if request.method == 'POST':
        if request.form.get('action') == 'save':
            content = request.form.get('content', '')
            try:
                with open(abs_path, 'w', encoding='utf-8') as fh:
                    fh.write(content)
                flash('File saved', 'success')
            except Exception as e:
                flash(str(e), 'error')
        elif request.form.get('action') == 'delete':
            try:
                os.remove(abs_path)
                flash('File deleted', 'success')
                parent = os.path.dirname(rel_path)
                return redirect(url_for('files.list_dir', path=parent))
            except Exception as e:
                flash(str(e), 'error')
        return redirect(url_for('files.edit_file', path=rel_path))

    # Load content (text only)
    content = ''
    try:
        with open(abs_path, 'r', encoding='utf-8') as fh:
            content = fh.read()
    except Exception:
        content = ''

    return render_template('filemanager/edit.html', rel_path=rel_path, content=content)


