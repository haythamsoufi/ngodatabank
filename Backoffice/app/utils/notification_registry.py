"""
Canonical NotificationType catalog for the admin Notifications registry page.

Keeps grouped descriptions aligned with NotificationType enum (app.models.enums).
When adding enum members, extend NOTIFICATION_TYPE_REGISTRY_SPECS accordingly.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Ordered catalog rows: stable sort uses this list order within each group in the UI.
NOTIFICATION_TYPE_REGISTRY_SPECS: List[Dict[str, str]] = [
    {
        "group": "Assignments",
        "type_key": "assignment_created",
        "description": (
            "Created when the user gains a new form assignment requiring action."
        ),
    },
    {
        "group": "Assignments",
        "type_key": "assignment_submitted",
        "description": (
            "Created when someone submits an assignment the user participates in "
            "(e.g., focal point reviewers)."
        ),
    },
    {
        "group": "Assignments",
        "type_key": "assignment_approved",
        "description": (
            "Created when an assignment submission is approved relevant to the user."
        ),
    },
    {
        "group": "Assignments",
        "type_key": "assignment_reopened",
        "description": (
            "Created when a previously submitted assignment is reopened for edits."
        ),
    },
    {
        "group": "Assignments",
        "type_key": "self_report_created",
        "description": (
            "Created when self-report flows generate a notification tied to assignments."
        ),
    },
    {
        "group": "Assignments",
        "type_key": "deadline_reminder",
        "description": (
            "Reminder before or near an assignment deadline for assigned users."
        ),
    },
    {
        "group": "Forms & submissions",
        "type_key": "public_submission_received",
        "description": (
            "Signals new public-channel submissions reviewers or admins should handle."
        ),
    },
    {
        "group": "Forms & submissions",
        "type_key": "form_updated",
        "description": (
            "Form structure or applicability changed in a way that affects the recipient."
        ),
    },
    {
        "group": "Documents & access",
        "type_key": "document_uploaded",
        "description": (
            "A document linked to workflows the user participates in was uploaded."
        ),
    },
    {
        "group": "Documents & access",
        "type_key": "user_added_to_country",
        "description": (
            "Sent when the user gains access to a country or organisational scope."
        ),
    },
    {
        "group": "Documents & access",
        "type_key": "access_request_received",
        "description": (
            "Notifies approvers/reviewers of a new country or access request submission."
        ),
    },
    {
        "group": "Templates",
        "type_key": "template_updated",
        "description": (
            "Published when template definition changes relevant to downstream users."
        ),
    },
    {
        "group": "System & admin",
        "type_key": "admin_message",
        "description": (
            "Custom notification from the Notifications Center (email/push broadcasts)."
        ),
    },
]


def validate_registry_specs() -> None:
    """Raise AssertionError if registry keys diverge from NotificationType."""
    from app.models.enums import NotificationType

    spec_keys = {s["type_key"] for s in NOTIFICATION_TYPE_REGISTRY_SPECS}
    enum_keys = {nt.value for nt in NotificationType}
    missing = enum_keys - spec_keys
    extra = spec_keys - enum_keys
    assert not missing and not extra, (
        f"notification_registry mismatch: missing={sorted(missing)} extra={sorted(extra)}"
    )


validate_registry_specs()


def build_registry_rows(ttl_resolver, priority_resolver) -> List[Dict[str, Any]]:
    """
    Rows for the admin template / CSV.

    ttl_resolver(str) -> int  (effective TTL days from config)
    priority_resolver(str) -> str  (default priority from settings)
    """
    rows: List[Dict[str, Any]] = []
    for spec in NOTIFICATION_TYPE_REGISTRY_SPECS:
        tk = spec["type_key"]
        rows.append(
            {
                "group": spec["group"],
                "type_key": tk,
                "description": spec["description"],
                "ttl_days": ttl_resolver(tk),
                "default_priority": priority_resolver(tk),
            }
        )
    return rows

