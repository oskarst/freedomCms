#!/usr/bin/env python3
"""
Users blueprint for Devall CMS
"""

from flask import Blueprint, request, redirect, url_for, render_template, flash, session
from ..auth import login_required, admin_required
from ..db import get_db, hash_password, check_password

bp = Blueprint('users', __name__)

@bp.route('/users')
@login_required
@admin_required
def users():
    """List all users"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT id, username, email, role, created_at, active FROM users ORDER BY username')
    users_list = cursor.fetchall()

    return render_template('users/users.html', users=users_list)

@bp.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    """Add new user"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        email = request.form.get('email', '').strip()
        name = request.form.get('name', '').strip()
        role = request.form.get('role', 'admin')

        if not username or not password:
            flash('Username and password are required', 'error')
            return redirect(url_for('users.add_user'))

        db = get_db()
        cursor = db.cursor()

        # Check if username already exists
        cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            flash('Username already exists', 'error')
            return redirect(url_for('users.add_user'))

        # Create user
        cursor.execute('INSERT INTO users (username, password_hash, email, name, role) VALUES (?, ?, ?, ?, ?)',
                     (username, hash_password(password), email, name, role))
        db.commit()

        flash('User created successfully', 'success')
        return redirect(url_for('users.users'))

    return render_template('users/add.html')

@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edit existing user"""
    db = get_db()
    cursor = db.cursor()

    # Get user info
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()

    if not user:
        flash('User not found', 'error')
        return redirect(url_for('users.users'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        email = request.form.get('email', '').strip()
        name = request.form.get('name', '').strip()
        role = request.form.get('role', user['role'])
        active = request.form.get('active') == 'on'

        if not username:
            flash('Username is required', 'error')
            return redirect(url_for('users.edit_user', user_id=user_id))

        # Check if username already exists (excluding current user)
        cursor.execute('SELECT id FROM users WHERE username = ? AND id != ?', (username, user_id))
        if cursor.fetchone():
            flash('Username already exists', 'error')
            return redirect(url_for('users.edit_user', user_id=user_id))

        # Update user
        if password:
            cursor.execute('UPDATE users SET username = ?, password_hash = ?, email = ?, name = ?, role = ?, active = ? WHERE id = ?',
                         (username, hash_password(password), email, name, role, active, user_id))
        else:
            cursor.execute('UPDATE users SET username = ?, email = ?, name = ?, role = ?, active = ? WHERE id = ?',
                         (username, email, name, role, active, user_id))

        db.commit()
        flash('User updated successfully', 'success')
        return redirect(url_for('users.users'))

    return render_template('users/edit.html', user=user)

@bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Delete user"""
    # Prevent deletion of current user
    if session.get('user_id') == user_id:
        flash('Cannot delete your own account', 'error')
        return redirect(url_for('users.users'))

    db = get_db()
    cursor = db.cursor()

    # Check if user exists
    cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()

    if not user:
        flash('User not found', 'error')
        return redirect(url_for('users.users'))

    # Delete user
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()

    flash(f'User "{user["username"]}" deleted successfully', 'success')
    return redirect(url_for('users.users'))

@bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    """Toggle user active status"""
    # Prevent deactivation of current user
    if session.get('user_id') == user_id:
        flash('Cannot deactivate your own account', 'error')
        return redirect(url_for('users.users'))

    db = get_db()
    cursor = db.cursor()

    # Toggle active status
    cursor.execute('UPDATE users SET active = NOT active WHERE id = ?', (user_id,))
    db.commit()

    flash('User status updated successfully', 'success')
    return redirect(url_for('users.users'))
