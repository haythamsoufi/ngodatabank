import logging
import os
import re

logger = logging.getLogger(__name__)
from typing import Dict, Iterable, List, Optional, Set, Tuple

import click
from flask.cli import with_appcontext

from app.extensions import db
from app.models.rbac import RbacPermission, RbacRole, RbacRolePermission
from app.utils.transactions import atomic


def _discover_permission_codes() -> Set[str]:
    """
    Best-effort discovery of permission codes used by the codebase.

    We intentionally scope discovery to common call sites:
    - permission_required('...')
    - permission_required_any('...', ...)
    - has_rbac_permission(..., '...')
    - has_permission('...') in templates
    """
    app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    scan_dirs = [
        os.path.join(app_dir, "routes"),
        os.path.join(app_dir, "services"),
        os.path.join(app_dir, "utils"),
        os.path.join(app_dir, "templates"),
    ]

    permission_codes: Set[str] = set()
    dotted_code_re = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")

    # Patterns that capture *one* permission code
    capture_patterns = [
        re.compile(r"permission_required\(\s*['\"]([^'\"]+)['\"]\s*\)"),
        re.compile(r"has_rbac_permission\(\s*[^,]+,\s*['\"]([^'\"]+)['\"]"),
        re.compile(r"has_permission\(\s*['\"]([^'\"]+)['\"]\s*(?:,|\))"),
    ]

    # permission_required_any('a', 'b', ...) => extract all quoted strings in the arg list
    any_pattern = re.compile(r"permission_required_any\(([^)]*)\)")
    quoted_re = re.compile(r"['\"]([^'\"]+)['\"]")

    for base in scan_dirs:
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if not (fn.endswith(".py") or fn.endswith(".html")):
                    continue
                path = os.path.join(root, fn)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except Exception as e:
                    logger.debug("Could not read %s: %s", path, e)
                    continue

                for pat in capture_patterns:
                    for m in pat.finditer(content):
                        code = (m.group(1) or "").strip()
                        if code and dotted_code_re.match(code):
                            permission_codes.add(code)

                for m in any_pattern.finditer(content):
                    arg_str = m.group(1) or ""
                    for q in quoted_re.findall(arg_str):
                        code = (q or "").strip()
                        if code and dotted_code_re.match(code):
                            permission_codes.add(code)

    # Minimal safety net for core workflow permissions (in case discovery is incomplete)
    permission_codes.update(
        {
            "assignment.view",
            "assignment.enter",
            "assignment.submit",
            "assignment.approve",
            "assignment.reopen",
            "assignment.documents.upload",
        }
    )
    return permission_codes


def _upsert_permissions(codes: Iterable[str]) -> Tuple[int, int]:
    """Create missing permissions; update empty name/description. Returns (created, updated)."""
    created = 0
    updated = 0
    for code in sorted(set(codes)):
        if not code:
            continue
        perm = RbacPermission.query.filter_by(code=code).first()
        if not perm:
            db.session.add(RbacPermission(code=code, name=code, description=code))
            created += 1
            continue
        # Keep existing human-friendly names, but backfill if missing
        changed = False
        if not getattr(perm, "name", None):
            perm.name = code
            changed = True
        if getattr(perm, "description", None) is None:
            perm.description = code
            changed = True
        if changed:
            updated += 1
    return created, updated


def _get_role_id(code: str, *, name: Optional[str] = None, description: Optional[str] = None) -> int:
    role = RbacRole.query.filter_by(code=code).first()
    if role:
        return int(role.id)
    role = RbacRole(code=code, name=name or code, description=description)
    db.session.add(role)
    db.session.flush()
    return int(role.id)


def _ensure_role_permissions(role_code: str, perm_codes: Iterable[str]) -> int:
    """Ensure role-permission links exist. Returns number of links created."""
    role_id = _get_role_id(role_code)
    # Resolve permission ids in bulk
    perm_rows = (
        RbacPermission.query.with_entities(RbacPermission.id, RbacPermission.code)
        .filter(RbacPermission.code.in_(list(set(perm_codes))))
        .all()
    )
    perm_id_by_code: Dict[str, int] = {str(code): int(pid) for pid, code in perm_rows if pid and code}

    created = 0
    for code in set(perm_codes):
        pid = perm_id_by_code.get(code)
        if not pid:
            continue
        exists = (
            RbacRolePermission.query.filter_by(role_id=role_id, permission_id=pid).first()
            is not None
        )
        if exists:
            continue
        db.session.add(RbacRolePermission(role_id=role_id, permission_id=pid))
        created += 1
    return created


def _build_baseline_role_map(all_codes: Set[str]) -> Dict[str, Set[str]]:
    """Baseline role -> permissions mapping (prefix-driven, resilient to new permissions)."""
    admin_codes = {c for c in all_codes if c.startswith("admin.")}

    def _by_prefix(prefix: str) -> Set[str]:
        return {c for c in all_codes if c.startswith(prefix)}

    role_map: Dict[str, Set[str]] = {
        # Assignment roles
        "assignment_viewer": {"assignment.view"},
        "assignment_editor_submitter": {"assignment.view", "assignment.enter", "assignment.submit", "assignment.documents.upload"},
        "assignment_approver": {"assignment.view", "assignment.approve", "assignment.reopen"},

        # Admin roles
        "admin_full": set(admin_codes),
        "admin_users_manager": _by_prefix("admin.users.") | _by_prefix("admin.access_requests.") | {"admin.users.roles.assign", "admin.users.grants.manage"},
        "admin_templates_manager": _by_prefix("admin.templates."),
        "admin_assignments_manager": _by_prefix("admin.assignments."),
        "admin_countries_manager": _by_prefix("admin.countries.") | {"admin.organization.manage"},
        "admin_indicator_bank_manager": _by_prefix("admin.indicator_bank."),
        "admin_content_manager": {"admin.resources.manage", "admin.publications.manage", "admin.documents.manage"},
        "admin_settings_manager": {"admin.settings.manage"},
        "admin_api_manager": {"admin.api.manage"},
        "admin_plugins_manager": {"admin.plugins.manage"},
        "admin_data_explorer_data_table": {"admin.data_explore.data_table"},
        "admin_data_explorer_analysis": {"admin.data_explore.analysis"},
        "admin_data_explorer_compliance": {"admin.data_explore.compliance"},
        "admin_analytics_viewer": {"admin.analytics.view"},
        "admin_audit_viewer": {"admin.audit.view"},
    }

    # admin_core: conservative "essentials" set (mostly view)
    admin_core_defaults = {
        "admin.users.view",
        "admin.access_requests.view",
        "admin.templates.view",
        "admin.assignments.view",
        "admin.countries.view",
        "admin.indicator_bank.view",
        "admin.analytics.view",
        "admin.audit.view",
        "admin.data_explore.data_table",
        "admin.data_explore.analysis",
        "admin.data_explore.compliance",
    }
    role_map["admin_core"] = {c for c in admin_core_defaults if c in all_codes}

    return role_map


def register_rbac_commands(app) -> None:
    """Register RBAC CLI commands."""

    @app.cli.group("rbac")
    def rbac_group():
        """RBAC utilities (seed permissions, etc.)."""
        pass

    @rbac_group.command("seed")
    @with_appcontext
    def rbac_seed():
        """Seed RBAC permissions and baseline role-permission links (idempotent)."""
        codes = _discover_permission_codes()
        if not codes:
            click.echo("No permission codes discovered; nothing to seed.")
            return

        role_map = _build_baseline_role_map(codes)

        with atomic(remove_session=True):
            created_perms, updated_perms = _upsert_permissions(codes)

            created_links = 0
            for role_code, perm_codes in role_map.items():
                if not perm_codes:
                    continue
                created_links += _ensure_role_permissions(role_code, perm_codes)

        click.echo(f"RBAC seed complete.")
        click.echo(f"- Permissions: {created_perms} created, {updated_perms} updated")
        click.echo(f"- Role-permission links: {created_links} created")
