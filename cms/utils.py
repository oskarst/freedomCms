#!/usr/bin/env python3
"""
Utility functions for Devall CMS
"""

import re
from datetime import datetime

def slugify(text):
    """Convert text to URL-friendly slug"""
    # Convert to lowercase
    text = text.lower()
    # Replace spaces and special characters with hyphens
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    # Remove multiple hyphens
    text = re.sub(r'-+', '-', text)
    # Remove leading/trailing hyphens
    text = text.strip('-')
    return text

def now_iso():
    """Get current datetime in ISO format"""
    return datetime.now().isoformat()

def fetch_settings(cursor):
    """Fetch all settings as a dictionary"""
    cursor.execute('SELECT key, value FROM settings')
    settings_rows = cursor.fetchall()
    return {row['key']: row['value'] for row in settings_rows}
