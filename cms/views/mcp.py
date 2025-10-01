#!/usr/bin/env python3
"""
External MCP (Model Context Protocol) API for Devall CMS.
"""

import json
from flask import Blueprint, request, jsonify
from ..services.mcp import call_ai_model, MCPClientError, get_ai_settings

bp = Blueprint('mcp', __name__)


def _verify_token(req) -> bool:
    settings = get_ai_settings()
    expected = settings.get('api_token')
    if not expected:
        return False
    token = (req.headers.get('Authorization') or '').replace('Bearer', '').strip()
    return token == expected


@bp.route('/prompt', methods=['POST'])
def mcp_prompt():
    if not _verify_token(request):
        return jsonify({'error': 'Unauthorized'}), 401

    payload = request.get_json(silent=True) or {}
    prompt = payload.get('prompt', '').strip()
    mode = payload.get('mode', 'content')
    context = payload.get('context')

    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400

    try:
        result = call_ai_model(prompt, mode=mode, context=context)
    except MCPClientError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify({'result': result})
