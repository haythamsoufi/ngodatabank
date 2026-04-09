# Backoffice/app/routes/api/mobile/admin_org.py
"""Admin organization routes: NS branches, sub-branches, structure."""

from flask import request, current_app

from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import mobile_ok, mobile_not_found, mobile_server_error
from app.routes.api.mobile import mobile_bp


@mobile_bp.route('/admin/org/branches/<int:country_id>', methods=['GET'])
@mobile_auth_required
def list_branches(country_id):
    """List NS branches for a country."""
    from app.models.core import NSBranch

    branches = NSBranch.query.filter_by(country_id=country_id).order_by(NSBranch.name.asc()).all()
    return mobile_ok(data={
        'branches': [
            {'id': b.id, 'name': b.name, 'code': getattr(b, 'code', None)}
            for b in branches
        ],
    })


@mobile_bp.route('/admin/org/subbranches/<int:branch_id>', methods=['GET'])
@mobile_auth_required
def list_subbranches(branch_id):
    """List NS sub-branches for a branch."""
    from app.models.core import NSSubBranch

    subbranches = NSSubBranch.query.filter_by(branch_id=branch_id).order_by(NSSubBranch.name.asc()).all()
    return mobile_ok(data={
        'subbranches': [
            {'id': s.id, 'name': s.name, 'code': getattr(s, 'code', None), 'branch_id': s.branch_id}
            for s in subbranches
        ],
    })


@mobile_bp.route('/admin/org/structure', methods=['GET'])
@mobile_auth_required(permission='admin.organization.manage')
def org_structure():
    """Full organization entity tree."""
    from app.models import Country
    from app.models.core import NSBranch, NSSubBranch

    try:
        countries_q = Country.query.order_by(Country.name.asc()).all()
        branches_q = NSBranch.query.all()
        subbranches_q = NSSubBranch.query.all()

        branches_by_country = {}
        for b in branches_q:
            branches_by_country.setdefault(b.country_id, []).append({
                'id': b.id, 'name': b.name, 'code': getattr(b, 'code', None),
            })

        subbranches_by_branch = {}
        for s in subbranches_q:
            subbranches_by_branch.setdefault(s.branch_id, []).append({
                'id': s.id, 'name': s.name, 'code': getattr(s, 'code', None),
            })

        structure = []
        for c in countries_q:
            country_branches = branches_by_country.get(c.id, [])
            for branch in country_branches:
                branch['subbranches'] = subbranches_by_branch.get(branch['id'], [])
            structure.append({
                'id': c.id,
                'name': c.name,
                'branches': country_branches,
            })

        return mobile_ok(data={'structure': structure}, meta={'total_countries': len(structure)})
    except Exception as e:
        current_app.logger.error("org_structure: %s", e, exc_info=True)
        return mobile_server_error()
