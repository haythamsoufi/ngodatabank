"""
Shared mappings from Flask endpoints / legacy log text to canonical activity types.

Used by activity middleware (when logging) and analytics (when displaying old rows
that still have generic type ``request`` and ``Performed …`` descriptions).
"""

from __future__ import annotations

import re
from typing import Dict, Optional

# POST requests: last segment of ``request.endpoint`` (after the dot) → activity_type
POST_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE: Dict[str, str] = {
    # Push / mobile
    "register_device": "device_registered",
    "unregister_device": "device_unregistered",
    # System settings (admin)
    "manage_settings": "settings_updated",
    # Access (main blueprint)
    "request_country_access": "country_access_requested",
    # Dashboard / country selection (common POSTs that are not form submit)
    "select_country": "country_selected",
    "reopen_assignment": "form_reopened",
    "approve_assignment": "form_approved",
}

# Optional: full ``endpoint`` string when the segment alone is ambiguous (rare)
POST_FULL_ENDPOINT_TO_ACTIVITY_TYPE: Dict[str, str] = {
    # Same keys as segments are resolved via segment map; add overrides here if needed.
}

# Legacy rows stored description ``Performed Title Case`` — map title fragment → activity_type
LEGACY_PERFORMED_TITLE_TO_ACTIVITY_TYPE: Dict[str, str] = {
    "Manage Settings": "settings_updated",
    "Register Device": "device_registered",
    "Unregister Device": "device_unregistered",
    "Request Country Access": "country_access_requested",
    "Select Country": "country_selected",
    "Reopen Assignment": "form_reopened",
    "Approve Assignment": "form_approved",
}

# Short, natural sentences for audit descriptions (middleware + analytics fallback)
ACTIVITY_TYPE_DESCRIPTIONS: Dict[str, str] = {
    "device_registered": "Registered a mobile device for push notifications",
    "device_unregistered": "Unregistered a mobile device from push notifications",
    "settings_updated": "Updated system settings",
    "country_access_requested": "Requested access to a country workspace",
    "country_selected": "Selected a country workspace",
}


def endpoint_last_segment(endpoint: Optional[str]) -> str:
    if not endpoint:
        return ""
    return endpoint.rsplit(".", 1)[-1] if "." in endpoint else endpoint


def strip_endpoint_verb_prefix(segment: str) -> str:
    if not segment:
        return ""
    return re.sub(r"^(api_|get_|post_|put_|delete_|fetch_)", "", segment, flags=re.I)


def resolve_post_activity_type(endpoint: Optional[str]) -> Optional[str]:
    """Return a specific activity type for a POST request, or None to use generic rules."""
    if not endpoint:
        return None
    full = POST_FULL_ENDPOINT_TO_ACTIVITY_TYPE.get(endpoint)
    if full:
        return full
    seg = endpoint_last_segment(endpoint)
    cleaned = strip_endpoint_verb_prefix(seg)
    return (
        POST_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE.get(cleaned)
        or POST_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE.get(seg)
    )


def infer_activity_type_from_legacy_description(description: Optional[str]) -> Optional[str]:
    """Map old ``Performed X`` text to a canonical activity type."""
    if not description or not description.startswith("Performed "):
        return None
    tail = description[len("Performed ") :].strip()
    return LEGACY_PERFORMED_TITLE_TO_ACTIVITY_TYPE.get(tail)


def description_for_activity_type(activity_type: str) -> Optional[str]:
    """Return a natural-language description for a canonical activity type, if known."""
    return ACTIVITY_TYPE_DESCRIPTIONS.get(activity_type)
