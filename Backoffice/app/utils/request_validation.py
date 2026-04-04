from __future__ import annotations

from typing import Iterable, Optional

from flask import current_app, request

from app.utils.api_responses import json_bad_request
from werkzeug.exceptions import Forbidden
from flask_wtf.csrf import CSRFError

from app.extensions import csrf


UNSAFE_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def enforce_csrf_json(*, methods: Optional[Iterable[str]] = None):
    """
    Enforce CSRF for JSON/AJAX endpoints and return a JSON response on failure.

    This is intended for session-cookie (Flask-Login) routes that accept JSON
    and use unsafe HTTP methods. It returns a (json, status) tuple on failure,
    or None when CSRF validation passes / is not required.
    """
    allowed_methods = {m.upper() for m in (methods or UNSAFE_HTTP_METHODS)}
    if request.method.upper() not in allowed_methods:
        return None

    try:
        csrf.protect()
        return None
    except CSRFError as exc:
        # Log without leaking token contents
        current_app.logger.warning(
            "CSRF validation failed for %s (%s): %s",
            request.path,
            request.method,
            getattr(exc, "description", "CSRF validation failed"),
        )
        return json_bad_request(
            getattr(exc, "description", None) or "CSRF token missing or invalid",
            success=False,
            error="CSRF validation failed",
            message=getattr(exc, "description", None) or "CSRF token missing or invalid",
        )


def enforce_api_or_csrf_protection() -> None:
    """
    Require CSRF for browser session requests, or accept ``X-Mobile-Auth`` when it
    matches an **active database-managed API key** (same plaintext as
    ``Authorization: Bearer`` for /api/v1).
    """
    from app.utils.api_authentication import validate_plaintext_db_api_key_for_mobile_auth

    incoming_token = (request.headers.get("X-Mobile-Auth") or "").strip() or None

    if incoming_token:
        if validate_plaintext_db_api_key_for_mobile_auth(incoming_token):
            return

        current_app.logger.warning(
            "Rejected X-Mobile-Auth from %s for %s: not a valid DB API key",
            request.remote_addr,
            request.path,
        )
        raise Forbidden("Invalid mobile authentication token.")

    try:
        csrf.protect()
    except CSRFError as exc:
        current_app.logger.warning(
            "CSRF validation failed for notifications endpoint: %s", exc.description
        )
        raise
