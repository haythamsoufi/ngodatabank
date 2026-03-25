# -*- coding: utf-8 -*-
"""
Shared request utilities for JSON/AJAX detection.
Centralizes is_json_request to replace ad-hoc X-Requested-With / request.is_json checks.
"""
from flask import request

from app.utils.api_helpers import get_json_safe


def is_json_request():
    """True if the current request expects a JSON response (API/AJAX)."""
    accept = request.headers.get("Accept", "")
    content_type = request.headers.get("Content-Type", "")
    path = request.path or ""
    # Broader admin API detection: /admin/ with 'api' in path
    is_admin_api = path.startswith("/admin/") and "api" in path
    return (
        request.is_json
        or (content_type.startswith("application/json") if content_type else False)
        or "application/json" in accept
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.args.get("ajax") == "1"
        or path.startswith("/admin/api/")
        or path.startswith("/admin/users/api/")
        or path.startswith("/admin/users/rbac/api/")
        or is_admin_api
    )


def _is_json_body():
    """True when the request body is JSON (based on Content-Type, not AJAX headers)."""
    content_type = request.headers.get("Content-Type", "")
    return request.is_json or content_type.startswith("application/json")


def get_json_or_form(default=None):
    """
    Return parsed JSON body or request.form as dict depending on request type.
    Use when a route accepts both JSON and form-encoded bodies.
    Always returns a dict (ImmutableMultiDict.to_dict() for form data).

    Uses Content-Type to decide format, not X-Requested-With / is_json_request(),
    so FormData submissions from AJAX calls are correctly read from request.form.
    """
    if _is_json_body():
        return get_json_safe(default) or {}
    return request.form.to_dict()


def parse_ids_from_request(key: str = "ids") -> list[int]:
    """
    Parse a list of integer IDs from the current request.

    Accepts either JSON body {key: [1, 2, 3]} or form-encoded key="1,2,3".
    Returns deduplicated list preserving order. Invalid values are skipped.
    """
    ids: list[int] = []
    if is_json_request():
        payload = get_json_safe() or {}
        raw_ids = payload.get(key) or []
        if isinstance(raw_ids, list):
            for v in raw_ids:
                try:
                    ids.append(int(v))
                except (TypeError, ValueError):
                    continue
    else:
        ids_str = (request.form.get(key) or "").strip()
        if ids_str:
            for part in ids_str.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    ids.append(int(part))
                except (TypeError, ValueError):
                    continue
    seen: set[int] = set()
    return [i for i in ids if i not in seen and not seen.add(i)]
