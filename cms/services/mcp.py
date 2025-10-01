#!/usr/bin/env python3
"""
MCP (Model Content Provider) integration helpers for Devall CMS.
"""

import requests
import json
from datetime import datetime
from typing import Optional, Dict, Any
from flask import current_app
from ..db import get_db

# Cost tracking constants
DEFAULT_COST_PER_CALL = 0.02  # USD per request if API does not provide cost

class MCPClientError(Exception):
    """Custom exception for MCP client errors."""


def get_ai_settings() -> Dict[str, Optional[str]]:
    """Fetch MCP AI settings from the database."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT key, value FROM settings WHERE key IN (?, ?, ?, ?, ?)', (
        'ai_provider',
        'ai_api_key',
        'ai_api_url',
        'ai_model',
        'ai_monthly_budget',
    ))
    rows = cursor.fetchall()
    settings = {row['key']: row['value'] for row in rows}
    return {
        'provider': settings.get('ai_provider'),
        'api_key': settings.get('ai_api_key'),
        'api_url': settings.get('ai_api_url'),
        'monthly_budget': settings.get('ai_monthly_budget'),
        'model': settings.get('ai_model'),
    }


def _get_usage_stats(cursor) -> Dict[str, float]:
    """Retrieve current month's AI usage stats."""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month_key TEXT NOT NULL,
            total_requests INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0.0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('SELECT month_key, total_requests, total_cost FROM ai_usage ORDER BY month_key DESC LIMIT 1')
    row = cursor.fetchone()
    if not row:
        return {'month_key': None, 'total_requests': 0, 'total_cost': 0.0}
    return {
        'month_key': row['month_key'],
        'total_requests': row['total_requests'],
        'total_cost': row['total_cost'] or 0.0,
    }


def _reset_usage_if_needed(cursor, current_month_key: str):
    stats = _get_usage_stats(cursor)
    if stats['month_key'] == current_month_key:
        return stats
    cursor.execute('INSERT INTO ai_usage (month_key, total_requests, total_cost) VALUES (?, 0, 0.0)', (current_month_key,))
    return {'month_key': current_month_key, 'total_requests': 0, 'total_cost': 0.0}


def call_ai_model(prompt: str, *, mode: str = 'content', context: Optional[str] = None) -> str:
    """Call configured AI model with a prompt while enforcing monthly budget."""
    settings = get_ai_settings()
    api_url = settings.get('api_url')
    api_key = settings.get('api_key')
    monthly_budget_raw = settings.get('monthly_budget')

    if not api_url or not api_key:
        raise MCPClientError('AI model is not configured in Settings.')

    try:
        monthly_budget = float(monthly_budget_raw) if monthly_budget_raw else 0.0
    except ValueError:
        monthly_budget = 0.0

    db = get_db()
    cursor = db.cursor()
    now = datetime.utcnow()
    current_month_key = f"{now.year}-{now.month:02d}"
    usage_stats = _reset_usage_if_needed(cursor, current_month_key)

    if monthly_budget > 0 and usage_stats['total_cost'] >= monthly_budget:
        raise MCPClientError('Monthly AI budget has been reached. Increase the limit in Settings if needed.')

    payload: Dict[str, Any] = {}
    if settings.get('provider', '').lower() == 'openai':
        payload = {
            'model': settings.get('model') or 'gpt-4o-mini',
            'messages': [
                {
                    'role': 'system',
                    'content': 'You are an assistant that helps build CMS content and HTML templates. Always return only the raw result with no introductions, explanations, or follow-up text.'
                },
            ],
        }
        if context:
            payload['messages'].append({'role': 'system', 'content': f'Context HTML:\n{context}'})
        payload['messages'].append({'role': 'user', 'content': f"{prompt}\n\nReturn only the raw content with no introductions, no closing remarks, and absolutely no markdown fences."})

        if mode == 'code':
            payload['response_format'] = {'type': 'json_schema', 'json_schema': {
                'name': 'code_response',
                'schema': {
                    'type': 'object',
                    'properties': {
                        'code': {'type': 'string', 'description': 'HTML or code output.'}
                    },
                    'required': ['code'],
                    'additionalProperties': False
                }
            }}
    else:
        payload = {
            'prompt': f"{prompt}\n\nRespond with only the raw content, no explanations, no introductory/closing remarks, and no markdown fences.",
            'mode': mode,
        }
        if context:
            payload['context'] = context

    current_app.logger.info('AI prompt dispatched', extra={
        'ai_mode': mode,
        'prompt_preview': prompt[:200],
        'has_context': bool(context),
        'context_preview': (context[:200] if context else None)
    })

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        current_app.logger.exception('MCP request failed')
        raise MCPClientError(f'Failed to reach AI model: {exc}') from exc
    except ValueError as exc:
        raise MCPClientError('AI response returned invalid JSON.') from exc

    result: Optional[str] = None
    if settings.get('provider', '').lower() == 'openai':
        choices = data.get('choices') if isinstance(data, dict) else None
        if choices:
            message = choices[0].get('message') if choices[0] else None
            if message:
                content = message.get('content')
                if isinstance(content, list):
                    result = ''.join(part.get('text', '') for part in content if part.get('type') == 'text')
                elif isinstance(content, str):
                    result = content
        if result and mode == 'code' and isinstance(result, str):
            try:
                parsed = json.loads(result)
                if isinstance(parsed, dict) and 'code' in parsed:
                    result = parsed['code']
            except json.JSONDecodeError:
                pass
    else:
        result = data.get('result') if isinstance(data, dict) else None

    if not result:
        raise MCPClientError('AI response did not contain result text.')

    # Normalize result: strip Markdown fences if present
    if isinstance(result, str):
        trimmed = result.strip()
        if trimmed.startswith('```') and trimmed.endswith('```'):
            inner = trimmed[3:-3].strip()
            newline_index = inner.find('\n')
            if newline_index != -1 and inner[:newline_index].strip().isalpha():
                inner = inner[newline_index + 1:].strip()
            result = inner

    # Extract cost if provided
    cost = data.get('cost') if isinstance(data, dict) else None
    try:
        cost_value = float(cost) if cost is not None else DEFAULT_COST_PER_CALL
    except (TypeError, ValueError):
        cost_value = DEFAULT_COST_PER_CALL

    cursor.execute(
        'UPDATE ai_usage SET total_requests = total_requests + 1, total_cost = total_cost + ?, last_updated = CURRENT_TIMESTAMP WHERE month_key = ?',
        (cost_value, current_month_key)
    )
    db.commit()

    if monthly_budget > 0 and usage_stats['total_cost'] + cost_value > monthly_budget:
        current_app.logger.warning('AI budget exceeded on latest request (budget=%s, total=%s).', monthly_budget, usage_stats['total_cost'] + cost_value)

    return str(result)
