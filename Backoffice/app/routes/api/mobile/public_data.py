# Backoffice/app/routes/api/mobile/public_data.py
"""Public data routes: country map, sectors, indicator bank (public), quiz.

These wrap the same data served by /api/v1 but under the mobile prefix so
Flutter can use a single base URL and auth mechanism.  Routes that require
no authentication use @mobile_auth_required without a permission check.
"""

from flask import request, current_app

from app.utils.api_pagination import validate_pagination_params
from app.utils.mobile_auth import mobile_auth_required
from app import db
from app.utils.mobile_responses import (
    mobile_ok, mobile_bad_request, mobile_server_error, mobile_paginated,
)
from app.utils.sql_utils import safe_ilike_pattern
from app.routes.api.mobile import mobile_bp


@mobile_bp.route('/data/countrymap', methods=['GET'])
@mobile_auth_required
def countrymap():
    """Country map data (mirrors /api/v1/countrymap)."""
    from app.models import Country

    locale = request.args.get('locale', 'en')
    countries = Country.query.order_by(Country.name.asc()).all()

    items = []
    for c in countries:
        name = c.name
        if locale != 'en' and hasattr(c, f'name_{locale}'):
            name = getattr(c, f'name_{locale}', None) or c.name
        items.append({
            'id': c.id,
            'name': name,
            'iso2': getattr(c, 'iso2', None),
            'iso3': getattr(c, 'iso3', None),
            'region': getattr(c, 'region', None),
        })

    return mobile_ok(data={'countries': items}, meta={'total': len(items)})


@mobile_bp.route('/data/sectors-subsectors', methods=['GET'])
@mobile_auth_required
def sectors_subsectors():
    """List sectors and subsectors (mirrors /api/v1/sectors-subsectors)."""
    from app.models import Sector, SubSector

    sectors = Sector.query.order_by(Sector.name.asc()).all()
    subsectors = SubSector.query.order_by(SubSector.name.asc()).all()

    return mobile_ok(data={
        'sectors': [{'id': s.id, 'name': s.name} for s in sectors],
        'subsectors': [
            {'id': s.id, 'name': s.name, 'sector_id': getattr(s, 'sector_id', None)}
            for s in subsectors
        ],
    })


@mobile_bp.route('/data/indicator-bank', methods=['GET'])
@mobile_auth_required
def public_indicator_bank():
    """Public indicator bank listing (mirrors /api/v1/indicator-bank)."""
    from app.models import IndicatorBank

    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=200)
    search = request.args.get('search', '').strip()
    sector_id = request.args.get('sector_id', type=int)
    indicator_type = request.args.get('type')

    query = IndicatorBank.query.filter(
        db.or_(IndicatorBank.archived == False, IndicatorBank.archived.is_(None))  # noqa: E712
    )
    if search:
        query = query.filter(IndicatorBank.name.ilike(safe_ilike_pattern(search)))
    if indicator_type:
        query = query.filter(IndicatorBank.type == indicator_type)

    paginated = query.order_by(IndicatorBank.name.asc()).paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for i in paginated.items:
        items.append({
            'id': i.id,
            'name': i.name,
            'definition': getattr(i, 'definition', None),
            'type': getattr(i, 'type', None),
            'unit': getattr(i, 'unit', None),
        })

    return mobile_paginated(items=items, total=paginated.total, page=paginated.page, per_page=paginated.per_page)


@mobile_bp.route('/data/indicator-suggestions', methods=['POST'])
@mobile_auth_required
def submit_indicator_suggestion():
    """Submit an indicator suggestion (mirrors /api/v1/indicator-suggestions)."""
    from app.utils.api_helpers import get_json_safe
    from app.models import IndicatorSuggestion

    data = get_json_safe()
    name = (data.get('name') or '').strip()
    if not name:
        return mobile_bad_request('Indicator name is required')

    try:
        suggestion = IndicatorSuggestion(
            name=name,
            definition=data.get('definition', ''),
            submitted_by=data.get('submitted_by', ''),
            email=data.get('email', ''),
        )
        db.session.add(suggestion)
        db.session.flush()
        return mobile_ok(message='Indicator suggestion submitted', data={'id': suggestion.id})
    except Exception as e:
        current_app.logger.error("submit_indicator_suggestion: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/data/quiz/leaderboard', methods=['GET'])
@mobile_auth_required
def quiz_leaderboard():
    """Quiz leaderboard (mirrors /api/v1/quiz/leaderboard)."""
    from app.models import QuizScore

    limit = request.args.get('limit', 20, type=int)

    scores = QuizScore.query.order_by(
        QuizScore.score.desc(), QuizScore.created_at.asc()
    ).limit(min(limit, 100)).all()

    items = []
    for s in scores:
        items.append({
            'id': s.id,
            'user_name': s.user_name,
            'score': s.score,
            'total_questions': getattr(s, 'total_questions', None),
            'created_at': s.created_at.isoformat() if s.created_at else None,
        })

    return mobile_ok(data={'leaderboard': items}, meta={'total': len(items)})


@mobile_bp.route('/data/quiz/submit-score', methods=['POST'])
@mobile_auth_required
def submit_quiz_score():
    """Submit a quiz score (mirrors /api/v1/quiz/submit-score)."""
    from app.utils.api_helpers import get_json_safe
    from app.models import QuizScore

    data = get_json_safe()
    user_name = (data.get('user_name') or '').strip()
    score = data.get('score')

    if not user_name or score is None:
        return mobile_bad_request('user_name and score are required')

    try:
        quiz_score = QuizScore(
            user_name=user_name,
            score=score,
            total_questions=data.get('total_questions'),
        )
        db.session.add(quiz_score)
        db.session.flush()
        return mobile_ok(message='Score submitted', data={'id': quiz_score.id})
    except Exception as e:
        current_app.logger.error("submit_quiz_score: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()
