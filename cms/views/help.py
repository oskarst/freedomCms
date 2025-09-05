#!/usr/bin/env python3
"""
Help blueprint for Devall CMS
"""

from flask import Blueprint, render_template
from ..auth import login_required, admin_required

bp = Blueprint('help', __name__)

@bp.route('/help')
@login_required
@admin_required
def help_index():
    return render_template('help/index.html')


