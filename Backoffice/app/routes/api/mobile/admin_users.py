# Backoffice/app/routes/api/mobile/admin_users.py
"""Admin user management routes: list, detail, update, activate/deactivate, RBAC roles."""

from flask import request, current_app
from flask_login import current_user

from app import db
from app.utils.api_helpers import get_json_safe
from app.utils.api_pagination import validate_pagination_params
from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import (
    mobile_ok, mobile_bad_request, mobile_not_found,
    mobile_server_error, mobile_paginated,
)
from app.utils.sql_utils import safe_ilike_pattern
from app.routes.api.mobile import mobile_bp


@mobile_bp.route('/admin/users', methods=['GET'])
@mobile_auth_required(permission='admin.users.view')
def list_users():
    """Paginated user list (admin)."""
    from app.models import User
    from app.services.authorization_service import AuthorizationService

    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=200)
    search = request.args.get('search', '').strip()

    query = User.query
    if search:
        pattern = safe_ilike_pattern(search)
        query = query.filter(
            db.or_(User.email.ilike(pattern), User.name.ilike(pattern))
        )
    query = query.order_by(User.name.asc().nullslast(), User.email.asc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    users = []
    for u in paginated.items:
        users.append({
            'id': u.id,
            'email': u.email,
            'name': u.name,
            'title': u.title,
            'active': u.is_active,
            'is_admin': AuthorizationService.is_admin(u),
        })

    return mobile_paginated(
        items=users,
        total=paginated.total,
        page=paginated.page,
        per_page=paginated.per_page,
    )


@mobile_bp.route('/admin/users/<int:user_id>', methods=['GET'])
@mobile_auth_required(permission='admin.users.view')
def get_user(user_id):
    """User detail (admin)."""
    from app.models import User
    from app.models.core import UserEntityPermission
    from app.services.authorization_service import AuthorizationService

    user = User.query.get(user_id)
    if not user:
        return mobile_not_found('User not found')

    entity_perms = UserEntityPermission.query.filter_by(user_id=user_id).all()

    return mobile_ok(data={
        'user': {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'title': user.title,
            'active': user.is_active,
            'is_admin': AuthorizationService.is_admin(user),
            'entity_permissions': [
                {'entity_type': p.entity_type, 'entity_id': p.entity_id}
                for p in entity_perms
            ],
        },
    })


@mobile_bp.route('/admin/users/<int:user_id>', methods=['PUT', 'PATCH'])
@mobile_auth_required(permission='admin.users.edit')
def update_user(user_id):
    """Update user profile fields and/or RBAC roles (admin)."""
    from app.models import User
    from app.services.authorization_service import AuthorizationService

    user = User.query.get(user_id)
    if not user:
        return mobile_not_found('User not found')

    data = get_json_safe()
    if 'name' in data:
        user.name = data['name'] or None
    if 'title' in data:
        user.title = data['title'] or None

    if 'rbac_role_ids' in data:
        from app.models.rbac import RbacRole, RbacUserRole
        if not AuthorizationService.is_system_manager(current_user):
            sm_role = RbacRole.query.filter_by(code='system_manager').first()
            if sm_role and sm_role.id in (data['rbac_role_ids'] or []):
                return mobile_bad_request('Only system managers can assign the system_manager role.')

        RbacUserRole.query.filter_by(user_id=user_id).delete()
        for role_id in (data['rbac_role_ids'] or []):
            role = RbacRole.query.get(role_id)
            if role:
                db.session.add(RbacUserRole(user_id=user_id, role_id=role_id))

    try:
        db.session.flush()
        return mobile_ok(message='User updated')
    except Exception as e:
        current_app.logger.error("update_user: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/users/<int:user_id>/activate', methods=['POST'])
@mobile_auth_required(permission='admin.users.deactivate')
def activate_user(user_id):
    """Activate a user account (admin)."""
    from app.models import User
    from app.services.authorization_service import AuthorizationService

    user = User.query.get(user_id)
    if not user:
        return mobile_not_found('User not found')
    if user.id == current_user.id:
        return mobile_bad_request('You cannot activate your own account')
    if not AuthorizationService.is_system_manager(current_user) and AuthorizationService.is_admin(user):
        return mobile_bad_request('Only a System Manager can modify an admin user')

    user.active = True
    user.deactivated_at = None
    try:
        db.session.flush()
        return mobile_ok(message='User activated')
    except Exception as e:
        current_app.logger.error("activate_user: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/users/<int:user_id>/deactivate', methods=['POST'])
@mobile_auth_required(permission='admin.users.deactivate')
def deactivate_user(user_id):
    """Deactivate a user account (admin)."""
    from app.models import User
    from app.services.authorization_service import AuthorizationService

    user = User.query.get(user_id)
    if not user:
        return mobile_not_found('User not found')
    if user.id == current_user.id:
        return mobile_bad_request('You cannot deactivate your own account')
    if not AuthorizationService.is_system_manager(current_user) and AuthorizationService.is_admin(user):
        return mobile_bad_request('Only a System Manager can modify an admin user')

    user.active = False
    user.deactivated_at = db.func.now()
    try:
        db.session.flush()
        return mobile_ok(message='User deactivated')
    except Exception as e:
        current_app.logger.error("deactivate_user: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/users/rbac-roles', methods=['GET'])
@mobile_auth_required(permission='admin.users.view')
def list_rbac_roles():
    """List available RBAC roles."""
    from app.models.rbac import RbacRole
    roles = RbacRole.query.order_by(RbacRole.name.asc()).all()
    return mobile_ok(data={
        'roles': [
            {'id': r.id, 'code': r.code, 'name': r.name, 'description': r.description}
            for r in roles
        ],
    })
