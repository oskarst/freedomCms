#!/usr/bin/env python3
"""
Settings blueprint for Devall CMS
"""

from flask import Blueprint, request, redirect, url_for, render_template, flash
from ..auth import login_required, admin_required
from ..db import get_db

bp = Blueprint('settings', __name__)

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    """Settings page"""
    db = get_db()
    cursor = db.cursor()

    if request.method == 'POST':
        # Handle checkbox settings (they need special handling)
        cursor.execute('SELECT key FROM settings WHERE key IN (?, ?)', ('hide_system_blocks', 'admin_theme'))
        existing_keys = [row['key'] for row in cursor.fetchall()]

        # First, reset checkbox settings to '0' if not submitted
        for key in existing_keys:
            if key == 'hide_system_blocks':
                cursor.execute('UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?',
                             ('0', key))

        # Then update all submitted settings
        for key, value in request.form.items():
            if key.startswith('setting_'):
                setting_key = key[8:]  # Remove 'setting_' prefix
                cursor.execute('UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?',
                             (value, setting_key))

        db.commit()
        flash('Settings updated successfully', 'success')
        return redirect(url_for('settings.settings'))

    cursor.execute('SELECT * FROM settings ORDER BY key')
    settings_list = cursor.fetchall()

    return render_template('settings/settings.html', settings=settings_list)
