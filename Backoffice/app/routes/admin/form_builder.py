from app.utils.transactions import request_transaction_rollback
from contextlib import suppress
# File: Backoffice/app/routes/admin/form_builder.py
from app.utils.datetime_helpers import utcnow
from app.utils.advanced_validation import validate_upload_extension_and_mime
from app.utils.file_parsing import EXCEL_EXTENSIONS
"""
Form Builder Module - Template, Section, and Form Item Management
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, session
from flask_login import current_user
from flask_babel import _
from flask_wtf import FlaskForm
from werkzeug.datastructures import ImmutableMultiDict
from app import db, csrf
from app.models import (
    FormTemplate, FormSection, FormItem, FormItemType, FormPage, IndicatorBank,
    QuestionType, Sector, SubSector, LookupList, LookupListRow,
    TemplateShare, User, FormTemplateVersion, AssignedForm
)
from app.models.core import Country
from app.models.organization import NationalSociety
from app.forms.form_builder import (
    FormTemplateForm, FormSectionForm, IndicatorForm, QuestionForm, DocumentFieldForm
)
from app.routes.admin.shared import (
    admin_required,
    admin_permission_required,
    permission_required,
    system_manager_required,
    get_localized_sector_name,
    get_localized_subsector_name,
    check_template_access,
)
from app.utils.request_utils import is_json_request
from app.utils.api_authentication import get_user_allowed_template_ids
from app.utils.user_analytics import log_admin_action
from app.utils.template_excel_service import TemplateExcelService
from app.utils.kobo_xls_import_service import KoboXlsImportService
from app.utils.kobo_data_import_service import KoboDataImportService
from app.utils.error_handling import handle_view_exception, handle_json_view_exception
from app.services.section_duplication_service import SectionDuplicationService
from app.services.item_duplication_service import ItemDuplicationService
from flask import send_file
from werkzeug.utils import secure_filename
from sqlalchemy import func, cast, String, select, inspect, literal
from config.config import Config
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import json_forbidden, json_bad_request, json_not_found, json_ok, json_server_error, json_form_errors
from datetime import datetime
import json
import re

bp = Blueprint("form_builder", __name__, url_prefix="/admin")

# Removed _handle_template_translations and _populate_template_translations
# Template no longer has name/name_translations fields - only versions do


def _parse_version_translations_from_form(json_key: str, explicit_prefix: str) -> dict:
    """
    Parse version translations from form: JSON hidden field + explicit code inputs.

    Args:
        json_key: Form key for JSON (e.g. 'name_translations', 'description_translations')
        explicit_prefix: Prefix for code-based inputs (e.g. 'name', 'description') -> name_fr, description_fr

    Returns:
        Dict mapping ISO language code -> translated string.
    """
    translations_by_code = {}
    supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))

    with suppress((TypeError, json.JSONDecodeError)):
        raw_json = request.form.get(json_key)
        if raw_json:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if isinstance(k, str) and isinstance(v, str) and v.strip():
                        code = k.strip().lower().split('_', 1)[0]
                        if code in supported_codes:
                            translations_by_code[code] = v.strip()

    for code in supported_codes:
        if code == 'en':
            continue
        raw_val = request.form.get(f'{explicit_prefix}_{code}')
        if isinstance(raw_val, str) and raw_val.strip():
            translations_by_code[code] = raw_val.strip()

    return translations_by_code


def _handle_version_translations(version, form):
    """Normalize and save version name translations using ISO codes (e.g., 'fr')."""
    translations_by_code = _parse_version_translations_from_form('name_translations', 'name')
    version.name_translations = translations_by_code if translations_by_code else None


def _handle_version_description_translations(version, form):
    """Normalize and save version description translations using ISO codes (e.g., 'fr')."""
    translations_by_code = _parse_version_translations_from_form('description_translations', 'description')
    version.description_translations = translations_by_code if translations_by_code else None

def _populate_version_translations(form, version):
    """Populate WTForm fields from stored ISO code keyed translations in version."""
    # No static per-language WTForms fields; translations are handled via JSON hidden field in templates.
    return

def _populate_version_description_translations(form, version):
    """Populate WTForm description fields from stored ISO code keyed translations in version."""
    # No static per-language WTForms fields; translations are handled via JSON hidden field in templates.
    return

def get_translation_value(translations_dict, language_key, default=''):
    """Helper function to get translation value from a translations dictionary"""
    if translations_dict and hasattr(translations_dict, 'get'):
        return translations_dict.get(language_key, default)
    return default


# === FormTemplate Management Routes ===
@bp.route("/templates", methods=["GET"])
@permission_required('admin.templates.view')
def manage_templates():
    from app.utils.form_localization import get_localized_template_name, get_localized_indicator_type, get_localized_indicator_unit
    from flask_babel import gettext as _gettext, ngettext as _ngettext
    from flask_babel import gettext as _gettext, ngettext as _ngettext

    # System managers can see all templates regardless of ownership and sharing
    from app.services.authorization_service import AuthorizationService
    if AuthorizationService.is_system_manager(current_user):
        templates_query = FormTemplate.query.options(
            db.joinedload(FormTemplate.owned_by_user),
            db.joinedload(FormTemplate.shared_with).joinedload(TemplateShare.shared_with_user),
            db.joinedload(FormTemplate.published_version)
        )
    else:
        # Filter templates based on ownership and sharing permissions
        # Users can see templates they own or templates shared with them
        # Use efficient UNION query instead of loading all templates
        allowed_template_ids = get_user_allowed_template_ids(current_user.id)

        if not allowed_template_ids:
            # User has no access to any templates
            templates_query = FormTemplate.query.filter(literal(False))
        else:
            templates_query = FormTemplate.query.options(
                db.joinedload(FormTemplate.owned_by_user),
                db.joinedload(FormTemplate.shared_with).joinedload(TemplateShare.shared_with_user),
                db.joinedload(FormTemplate.published_version)
            ).filter(FormTemplate.id.in_(allowed_template_ids))

    templates = templates_query.all()
    # Sort by name (from published version) in Python since it's a property
    templates.sort(key=lambda t: t.name if t.name else "")
    # Sort by name (from published version) in Python since it's a property
    templates.sort(key=lambda t: t.name if t.name else "")

    # Compute counts of saved data referencing each template's item IDs to warn on delete
    from app.models.form_items import FormItem
    from app.models.forms import FormData, RepeatGroupData, DynamicIndicatorData, FormSection
    from sqlalchemy import func

    # FormData counts per template via join on FormItem
    formdata_counts_rows = (
        db.session.query(FormItem.template_id, func.count(FormData.id))
        .join(FormData, FormData.form_item_id == FormItem.id)
        .group_by(FormItem.template_id)
        .all()
    )
    formdata_counts = {tpl_id: count for tpl_id, count in formdata_counts_rows}

    # RepeatGroupData counts per template via join on FormItem
    repeat_counts_rows = (
        db.session.query(FormItem.template_id, func.count(RepeatGroupData.id))
        .join(RepeatGroupData, RepeatGroupData.form_item_id == FormItem.id)
        .group_by(FormItem.template_id)
        .all()
    )
    repeat_counts = {tpl_id: count for tpl_id, count in repeat_counts_rows}

    # DynamicIndicatorData counts per template via section -> template
    dynamic_counts_rows = (
        db.session.query(FormSection.template_id, func.count(DynamicIndicatorData.id))
        .join(DynamicIndicatorData, DynamicIndicatorData.section_id == FormSection.id)
        .group_by(FormSection.template_id)
        .all()
    )
    dynamic_counts = {tpl_id: count for tpl_id, count in dynamic_counts_rows}

    # Combine into total counts per template id
    template_data_counts = {}
    for t in templates:
        template_id = t.id
        template_data_counts[template_id] = (
            int(formdata_counts.get(template_id, 0))
            + int(repeat_counts.get(template_id, 0))
            + int(dynamic_counts.get(template_id, 0))
        )

    # Compute version counts per template to avoid N+1 queries
    from app.models.forms import FormTemplateVersion
    version_counts_rows = (
        db.session.query(FormTemplateVersion.template_id, func.count(FormTemplateVersion.id))
        .group_by(FormTemplateVersion.template_id)
        .all()
    )
    template_version_counts = {tpl_id: count for tpl_id, count in version_counts_rows}

    # Detect duplicate template names (using localized names)
    template_name_counts = {}
    for template in templates:
        template_name = get_localized_template_name(template) if template else None
        name_key = template_name if template_name else (template.name if template.name else 'Unnamed Template')
        template_name_counts[name_key] = template_name_counts.get(name_key, 0) + 1

    # Create a list of names that appear multiple times (convert to list for JSON serialization)
    duplicate_template_names = [name for name, count in template_name_counts.items() if count > 1]

    # Return JSON for API requests (mobile app)
    if is_json_request():
        templates_data = []
        for template in templates:
            template_name = get_localized_template_name(template) if template else None
            add_to_self_report = False
            if template.published_version:
                add_to_self_report = template.published_version.get_effective_add_to_self_report() or False
            else:
                # Fallback to first version if no published version
                first_version = template.versions.order_by('created_at').first()
                if first_version:
                    add_to_self_report = first_version.get_effective_add_to_self_report() or False

            templates_data.append({
                'id': template.id,
                'name': template.name or 'Unnamed Template',
                'localized_name': template_name if template_name != template.name else None,
                'add_to_self_report': add_to_self_report,
                'created_at': template.created_at.isoformat() if hasattr(template, 'created_at') and template.created_at else None,
                'data_count': template_data_counts.get(template.id, 0),
                'has_published_version': template.published_version is not None,
            })
        return json_ok(templates=templates_data, count=len(templates_data))

    return render_template(
        "admin/templates/templates.html",
        templates=templates,
        title="Manage Form Templates",
        get_localized_template_name=get_localized_template_name,
        template_data_counts=template_data_counts,
        template_version_counts=template_version_counts,
        duplicate_template_names=duplicate_template_names,
    )


@bp.route("/templates/import_kobo_xls", methods=["POST"])
@permission_required('admin.templates.create')
def import_kobo_xls():
    """Create a new template by importing a Kobo Toolbox XLSForm (.xlsx or .xls) file."""
    import os
    handle_sharing = _handle_template_sharing  # capture before any _ assignment

    if 'kobo_file' not in request.files and 'excel_file' not in request.files:
        flash(_("No file provided for Kobo import."), "danger")
        return redirect(url_for("form_builder.new_template"))

    kobo_file = request.files.get('kobo_file') or request.files.get('excel_file')
    if not kobo_file or kobo_file.filename == '':
        flash(_("No file selected for Kobo import."), "danger")
        return redirect(url_for("form_builder.new_template"))

    valid, error_msg, ext = validate_upload_extension_and_mime(kobo_file, EXCEL_EXTENSIONS)
    if not valid:
        flash(_(error_msg or "Invalid file type. Please upload an Excel file (.xlsx or .xls) in Kobo XLSForm format."), "danger")
        return redirect(url_for("form_builder.new_template"))

    template_name = request.form.get('name', '').strip() or None
    owned_by = request.form.get('owned_by', type=int) or current_user.id
    shared_admin_ids = request.form.getlist('shared_with_admins')
    shared_admin_ids = [int(x) for x in shared_admin_ids if x]

    try:
        result = KoboXlsImportService.import_kobo_xls(
            kobo_file,
            template_name=template_name,
            owned_by=owned_by,
        )
    except Exception as e:
        current_app.logger.error(f"Kobo import failed: {e}", exc_info=True)
        flash(_("Kobo import failed."), "danger")
        return redirect(url_for("form_builder.new_template"))

    if not result['success']:
        flash(_("Kobo import failed: %(message)s", message=result.get('message', 'Unknown error')), "danger")
        if result.get('errors'):
            for err in result['errors'][:3]:
                flash(err, "warning")
        return redirect(url_for("form_builder.new_template"))

    template_id = result['template_id']
    if shared_admin_ids:
        template = FormTemplate.query.get(template_id)
        if template:
            handle_sharing(template, shared_admin_ids, current_user.id)

    counts = result.get('created_counts', {})
    name = result.get('message', '').split("'")[1] if "'" in result.get('message', '') else 'Template'
    flash(
        _("Template '%(name)s' created with %(sections)d sections and %(items)d items. You can edit it in the form builder.", name=name, sections=counts.get('sections', 0), items=counts.get('items', 0)),
        "success",
    )
    if result.get('warnings'):
        for w in result['warnings'][:3]:
            flash(w, "info")

    return redirect(url_for("form_builder.edit_template", template_id=result['template_id']))


# ---------------------------------------------------------------------------
# KoBo Data Import Wizard (import submission data from KoBo data exports)
# ---------------------------------------------------------------------------

@bp.route("/kobo-data-import", methods=["GET"])
@admin_required
@system_manager_required
def kobo_data_import():
    """Render the KoBo data import wizard page."""
    from app.utils.form_localization import get_localized_template_name

    countries = Country.query.filter_by(status='Active').order_by(Country.name).all()

    templates = FormTemplate.query.all()

    template_choices = []
    for t in templates:
        name = get_localized_template_name(t)
        if name:
            template_choices.append({'id': t.id, 'name': name})
    template_choices.sort(key=lambda x: x['name'].lower())

    return render_template(
        "admin/templates/kobo_data_import.html",
        title="Import KoBo Data",
        countries=countries,
        template_choices=template_choices,
    )


@bp.route("/kobo-data-import/analyze", methods=["POST"])
@admin_required
@system_manager_required
def kobo_data_import_analyze():
    """Analyze an uploaded KoBo data export Excel file (AJAX)."""
    import os, uuid, tempfile
    from flask import jsonify

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file provided'}), 400

    f = request.files['file']
    if not f or f.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400

    valid, error_msg, ext = validate_upload_extension_and_mime(f, EXCEL_EXTENSIONS)
    if not valid:
        return jsonify({'success': False, 'message': error_msg or 'Invalid file type'}), 400

    file_bytes = f.read()
    if len(file_bytes) > 50 * 1024 * 1024:
        return jsonify({'success': False, 'message': 'File too large (max 50 MB)'}), 400

    result = KoboDataImportService.analyze(file_bytes)

    if result.get('success'):
        upload_dir = os.path.join(current_app.instance_path, 'tmp')
        os.makedirs(upload_dir, exist_ok=True)
        file_id = str(uuid.uuid4())
        tmp_path = os.path.join(upload_dir, f'{file_id}.xlsx')
        with open(tmp_path, 'wb') as tf:
            tf.write(file_bytes)
        session['kobo_data_import_file'] = tmp_path
        session['kobo_data_import_id'] = file_id
        result['file_id'] = file_id

    return jsonify(result)


@bp.route("/kobo-data-import/match-entities", methods=["POST"])
@admin_required
@system_manager_required
def kobo_data_import_match():
    """Try to match entity names to countries (AJAX).

    If entity_column_index is provided, extracts all unique values from the
    stored temp file so matching covers every entity (not just samples).
    """
    import os
    from flask import jsonify

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400

    entity_names = data.get('entity_names', [])
    entity_col_idx = data.get('entity_column_index')

    if entity_col_idx is not None:
        tmp_path = session.get('kobo_data_import_file')
        if tmp_path and os.path.exists(tmp_path):
            try:
                with open(tmp_path, 'rb') as f:
                    file_bytes = f.read()
                entity_names = KoboDataImportService.extract_unique_entities(
                    file_bytes,
                    int(entity_col_idx),
                    submission_filter=data.get('submission_filter', 'all'),
                    validation_status_column_index=data.get('validation_status_column_index'),
                )
            except Exception:
                pass

    if not entity_names:
        return jsonify({
            'success': False,
            'message': (
                'No entity names found. Your submission filter may exclude every row, or the export may be '
                'missing _validation_status. Try “All rows” or re-export with validation metadata.'
            ),
        }), 400

    mapping = KoboDataImportService.try_match_entities(entity_names)

    countries = Country.query.filter_by(status='Active').order_by(Country.name).all()
    country_list = [{'id': c.id, 'name': c.name} for c in countries]

    return jsonify({
        'success': True,
        'entity_mapping': mapping,
        'countries': country_list,
    })


@bp.route("/kobo-data-import/preview", methods=["POST"])
@admin_required
@system_manager_required
def kobo_data_import_preview():
    """Return a preview of the mapped data for the AG Grid table (AJAX)."""
    import os
    from flask import jsonify

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': 'No configuration provided'}), 400

    file_id = data.get('file_id')
    stored_id = session.get('kobo_data_import_id')
    tmp_path = session.get('kobo_data_import_file')

    if not file_id or file_id != stored_id or not tmp_path or not os.path.exists(tmp_path):
        return jsonify({'success': False, 'message': 'Upload session expired. Please re-upload the file.'}), 400

    try:
        with open(tmp_path, 'rb') as f:
            file_bytes = f.read()
    except Exception as e:
        return jsonify({'success': False, 'message': f'Cannot read uploaded file: {e}'}), 500

    from app.utils.kobo_data_import_service import KoboDataImportService
    result = KoboDataImportService.generate_preview(
        file_bytes,
        entity_column_index=data.get('entity_column_index'),
        columns_to_import=data.get('columns_to_import', []),
        entity_mapping=data.get('entity_mapping', {}),
        duplicate_strategy=data.get('duplicate_strategy', 'latest'),
        submission_time_column_index=data.get('submission_time_column_index'),
        submission_filter=data.get('submission_filter', 'all'),
        validation_status_column_index=data.get('validation_status_column_index'),
        max_rows=data.get('max_rows', 100),
        existing_template_id=data.get('existing_template_id'),
        column_to_item_mapping=data.get('column_to_item_mapping'),
    )
    return jsonify(result)


@bp.route("/kobo-data-import/template-structure", methods=["POST"])
@admin_required
@system_manager_required
def kobo_data_import_template_structure():
    """Return sections and items for an existing template (AJAX)."""
    from flask import jsonify
    from app.utils.form_localization import get_localized_template_name

    data = request.get_json(silent=True)
    if not data or not data.get('template_id'):
        return jsonify({'success': False, 'message': 'template_id is required'}), 400

    template_id = int(data['template_id'])
    template = FormTemplate.query.get(template_id)
    if not template:
        return jsonify({'success': False, 'message': 'Template not found'}), 404

    version = template.published_version
    if not version:
        version = template.versions.order_by(FormTemplateVersion.version_number.desc()).first()
    if not version:
        return jsonify({'success': False, 'message': 'Template has no version'}), 400

    sections = FormSection.query.filter_by(
        template_id=template.id, version_id=version.id
    ).order_by(FormSection.order).all()

    result_sections = []
    all_items = []
    for sec in sections:
        items = FormItem.query.filter_by(
            section_id=sec.id, template_id=template.id, version_id=version.id
        ).order_by(FormItem.order).all()
        item_list = []
        for item in items:
            opts = list(item.allowed_disaggregation_options or [])
            has_slice_opts = any(o in opts for o in ('sex', 'age', 'sex_age'))
            item_info = {
                'id': item.id,
                'label': item.label or '',
                'type': item.type or item.item_type or '',
                'section_id': sec.id,
                'section_name': sec.name or 'Unnamed',
                'is_indicator': item.is_indicator,
                'unit': item.unit,
                'supports_disaggregation': bool(item.supports_disaggregation),
                'allowed_disaggregation_options': opts,
                'effective_sex_categories': list(item.effective_sex_categories) if item.is_indicator else [],
                'effective_age_groups': list(item.effective_age_groups) if item.is_indicator else [],
                'indirect_reach': bool(item.indirect_reach) if item.is_indicator else False,
                'show_disagg_mapping': bool(
                    item.is_indicator and item.supports_disaggregation and has_slice_opts
                ),
            }
            item_list.append(item_info)
            all_items.append(item_info)
        result_sections.append({
            'id': sec.id,
            'name': sec.name or 'Unnamed',
            'order': sec.order,
            'items': item_list,
        })

    return jsonify({
        'success': True,
        'template_id': template.id,
        'template_name': get_localized_template_name(template, version=version),
        'version_id': version.id,
        'sections': result_sections,
        'items': all_items,
    })


@bp.route("/kobo-data-import/map-columns", methods=["POST"])
@admin_required
@system_manager_required
def kobo_data_import_map_columns():
    """Auto-map KoBo columns to an existing template's items (AJAX)."""
    from flask import jsonify

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400

    kobo_columns = data.get('kobo_columns', [])
    template_items = data.get('template_items', [])

    if not kobo_columns or not template_items:
        return jsonify({'success': False, 'message': 'kobo_columns and template_items are required'}), 400

    mappings = KoboDataImportService.map_columns_to_template(kobo_columns, template_items)
    matched = sum(1 for m in mappings if m['item_id'] is not None)

    return jsonify({
        'success': True,
        'mappings': mappings,
        'matched_count': matched,
        'total_columns': len(mappings),
    })


@bp.route("/kobo-data-import/execute", methods=["POST"])
@admin_required
@system_manager_required
def kobo_data_import_execute():
    """Execute the KoBo data import (AJAX)."""
    import os
    from flask import jsonify

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': 'No configuration provided'}), 400

    file_id = data.get('file_id')
    stored_id = session.get('kobo_data_import_id')
    tmp_path = session.get('kobo_data_import_file')

    if not file_id or file_id != stored_id or not tmp_path or not os.path.exists(tmp_path):
        return jsonify({'success': False, 'message': 'Upload session expired. Please re-upload the file.'}), 400

    try:
        with open(tmp_path, 'rb') as f:
            file_bytes = f.read()
    except Exception as e:
        return jsonify({'success': False, 'message': f'Cannot read uploaded file: {e}'}), 500

    sub_time_idx = None
    if data.get('submission_time_column_index') is not None:
        sub_time_idx = data['submission_time_column_index']

    vs_idx = data.get('validation_status_column_index')
    if vs_idx is not None:
        try:
            vs_idx = int(vs_idx)
        except (TypeError, ValueError):
            vs_idx = None

    config = {
        'template_name': data.get('template_name', 'KoBo Data Import'),
        'period_name': data.get('period_name', 'Imported'),
        'entity_column_index': data.get('entity_column_index'),
        'columns_to_import': data.get('columns_to_import', []),
        'entity_mapping': data.get('entity_mapping', {}),
        'create_template': data.get('create_template', True),
        'import_data': data.get('import_data', True),
        'owned_by': current_user.id,
        'duplicate_strategy': data.get('duplicate_strategy', 'latest'),
        'submission_time_column_index': sub_time_idx,
        'submission_filter': data.get('submission_filter', 'all'),
        'validation_status_column_index': vs_idx,
        'existing_template_id': data.get('existing_template_id'),
        'column_to_item_mapping': data.get('column_to_item_mapping', {}),
    }

    result = KoboDataImportService.execute_import(file_bytes, config)

    # Clean up temp file
    try:
        os.remove(tmp_path)
        session.pop('kobo_data_import_file', None)
        session.pop('kobo_data_import_id', None)
    except Exception:
        pass

    if result.get('success'):
        log_admin_action('kobo_data_import', {
            'template_id': result.get('template_id'),
            'counts': result.get('counts'),
        })

    return jsonify(result)


@bp.route("/templates/new", methods=["GET", "POST"])
@permission_required('admin.templates.create')
def new_template():
    from app.utils.form_localization import get_localized_template_name

    form = FormTemplateForm()

    # Get available templates for cloning (same logic as manage_templates)
    # System managers can clone from any template
    from app.services.authorization_service import AuthorizationService
    if AuthorizationService.is_system_manager(current_user):
        templates_query = FormTemplate.query.options(
            db.joinedload(FormTemplate.owned_by_user),
            db.joinedload(FormTemplate.shared_with).joinedload(TemplateShare.shared_with_user)
        )
    else:
        # Use efficient UNION query instead of loading all templates
        allowed_template_ids = get_user_allowed_template_ids(current_user.id)

        if not allowed_template_ids:
            # User has no access to any templates
            templates_query = FormTemplate.query.filter(literal(False))
        else:
            templates_query = FormTemplate.query.options(
                db.joinedload(FormTemplate.owned_by_user),
                db.joinedload(FormTemplate.shared_with).joinedload(TemplateShare.shared_with_user)
            ).filter(FormTemplate.id.in_(allowed_template_ids))
    # Note: Can't order by FormTemplate.name in SQL since it's a property
    # Will sort in Python after loading

    available_templates = templates_query.all()

    # Preselect current user as template owner for new templates
    if request.method == 'GET':
        form.owned_by.data = current_user.id

        # Handle cloning from existing template
        clone_from_id = request.args.get('clone_from')
        if clone_from_id:
            with suppress((ValueError, TypeError)):  # Invalid clone_from_id, ignore
                clone_from_id = int(clone_from_id)
                source_template = FormTemplate.query.get(clone_from_id)
                if source_template and check_template_access(clone_from_id, current_user.id):
                    # Pre-populate form with source template data (use published version)
                    source_version = source_template.published_version if source_template.published_version else source_template.versions.order_by('created_at').first()
                    if source_version:
                        form.name.data = f"{source_version.name} (Copy)" if source_version.name else "New Template (Copy)"
                        form.description.data = source_version.description or ""
                        form.add_to_self_report.data = source_version.add_to_self_report
                        form.display_order_visible.data = source_version.display_order_visible
                        form.is_paginated.data = source_version.is_paginated
                        form.enable_export_pdf.data = source_version.enable_export_pdf
                        form.enable_export_excel.data = source_version.enable_export_excel
                        form.enable_import_excel.data = source_version.enable_import_excel
                        form.enable_ai_validation.data = source_version.enable_ai_validation
                    else:
                        # Fallback if no version exists (shouldn't happen normally, use defaults)
                        form.name.data = "New Template (Copy)"
                        form.description.data = ""
                        form.add_to_self_report.data = False
                        form.display_order_visible.data = False
                        form.is_paginated.data = False
                        form.enable_export_pdf.data = False
                        form.enable_export_excel.data = False
                        form.enable_import_excel.data = False
                        form.enable_ai_validation.data = False
                    form.owned_by.data = current_user.id  # New template owned by current user

                    # Handle name translations from version
                    if source_version and source_version.name_translations:
                        # Populate the hidden field for translations
                        pass  # Will be handled by JavaScript

    # Check if this is an Excel import request (bypasses normal form validation but still needs required fields)
    import_from_excel = request.form.get('import_from_excel')

    if import_from_excel:
        # For Excel import, name can come from Excel file
        # Use form values if provided, otherwise Excel will populate them
        new_name = request.form.get('name', '').strip()

        # If name is provided, check for uniqueness (Excel import will override if it has a name)
        if new_name:
            existing_version = FormTemplateVersion.query.filter_by(
                name=new_name,
                status='published'
            ).join(FormTemplate, FormTemplateVersion.template_id == FormTemplate.id).filter(
                FormTemplate.id.isnot(None)
            ).first()
            if existing_version:
                flash(f"Error: A form template with the name '{new_name}' already exists.", "danger")
                return render_template(
                    "admin/templates/new_template.html",
                    form=form,
                    title="Create New Form Template",
                    available_templates=available_templates,
                    get_localized_template_name=get_localized_template_name
                )

        # Create template with data from form (using request.form for Excel import)
        # Use placeholder values if not provided - Excel import will update them
        add_to_self_report = request.form.get('add_to_self_report') == 'y'
        display_order_visible = request.form.get('display_order_visible') == 'y'
        is_paginated = request.form.get('is_paginated') == 'y'
        enable_export_pdf = request.form.get('enable_export_pdf') == 'y'
        enable_export_excel = request.form.get('enable_export_excel') == 'y'
        enable_import_excel = request.form.get('enable_import_excel') == 'y'
        enable_ai_validation = request.form.get('enable_ai_validation') == 'y'
        description = request.form.get('description', '')
        owned_by = request.form.get('owned_by', type=int) or current_user.id

        # Create template record (no config fields here; all are stored per-version)
        template = FormTemplate(
            created_by=current_user.id,
            owned_by=owned_by
        )

        db.session.add(template)
        db.session.flush()

        # Create initial version
        # Use placeholder name if not provided - Excel import will update it
        placeholder_name = new_name if new_name else "Imported Template"
        now = utcnow()
        initial_version = FormTemplateVersion(
            template_id=template.id,
            version_number=1,
            status='draft',
            name=placeholder_name,
            description=description,
            add_to_self_report=add_to_self_report,
            display_order_visible=display_order_visible,
            is_paginated=is_paginated,
            enable_export_pdf=enable_export_pdf,
            enable_export_excel=enable_export_excel,
            enable_import_excel=enable_import_excel,
            enable_ai_validation=enable_ai_validation,
            created_by=current_user.id,
            updated_by=current_user.id,
            created_at=now,
            updated_at=now
        )

        # Handle name translations from hidden fields
        name_translations_json = request.form.get('name_translations', '{}')
        with suppress((json.JSONDecodeError, TypeError)):
            name_translations = json.loads(name_translations_json) if name_translations_json else {}
            if name_translations:
                initial_version.name_translations = name_translations

        # Handle individual translation fields
        translations = {}
        for code in current_app.config.get('SUPPORTED_LANGUAGES', []):
            if code != 'en':
                trans_value = request.form.get(f'name_{code}', '').strip()
                if trans_value:
                    translations[code] = trans_value
        if translations:
            if initial_version.name_translations:
                initial_version.name_translations.update(translations)
            else:
                initial_version.name_translations = translations

        db.session.add(initial_version)
        db.session.flush()

        # Store version ID and template ID in variables before any commit operations
        # This prevents "not persistent" errors if operations commit the session
        version_id = initial_version.id
        template_id = template.id
        version_name_before_import = initial_version.name or "Imported Template"

        # Handle template sharing
        shared_admin_ids = request.form.getlist('shared_with_admins')
        if shared_admin_ids:
            shared_admin_ids = [int(id) for id in shared_admin_ids if id]
            # Pass version name to avoid accessing template.name which might trigger relationship queries
            _handle_template_sharing(template, shared_admin_ids, current_user.id, template_name=version_name_before_import)

        try:
            db.session.flush()

            # Handle Excel import
            if 'excel_file' not in request.files:
                flash(_("No Excel file provided for import."), "danger")
                return redirect(url_for("form_builder.edit_template", template_id=template_id))

            excel_file = request.files['excel_file']

            if excel_file.filename == '':
                flash(_("No Excel file selected for import."), "danger")
                return redirect(url_for("form_builder.edit_template", template_id=template_id))

            # SECURITY: Validate file extension and MIME type
            valid, error_msg, ext = validate_upload_extension_and_mime(excel_file, EXCEL_EXTENSIONS)
            if not valid:
                flash(_(error_msg or "Invalid file type. Please upload an Excel file (.xlsx or .xls)."), "danger")
                if ext:
                    current_app.logger.warning(f"Rejected Excel import - MIME type mismatch (ext: {ext})")
                return redirect(url_for("form_builder.edit_template", template_id=template_id))

            # IMPORTANT:
            # Commit the newly created template + initial version BEFORE we start the import.
            # The import service rolls back on errors; without this commit, a failed import
            # would rollback the template itself and cause a 404 on redirect to edit.
            try:
                db.session.commit()
            except Exception as commit_error:
                handle_view_exception(
                    commit_error,
                    "Error creating template.",
                    log_message=f"Error committing template before Excel import: {commit_error}",
                )
                return render_template(
                    "admin/templates/new_template.html",
                    form=form,
                    title="Create New Form Template",
                    available_templates=available_templates,
                    get_localized_template_name=get_localized_template_name
                )

            # Import template structure from Excel
            result = TemplateExcelService.import_template(template_id, excel_file, version_id)

            if result['success']:
                # Import succeeded - re-query version to get updated name from Excel import
                # Use a fresh query in case the import service committed
                try:
                    initial_version = FormTemplateVersion.query.get(version_id)
                    template_name = initial_version.name if initial_version and initial_version.name else version_name_before_import
                except Exception as query_error:
                    # If query fails (e.g., session was rolled back), use fallback name
                    current_app.logger.warning(f"Could not re-query version after import: {query_error}")
                    template_name = version_name_before_import

                created_counts = result.get('created_counts', {})
                pages_count = created_counts.get('pages', 0)
                sections_count = created_counts.get('sections', 0)
                items_count = created_counts.get('items', 0)

                # Log admin action for Excel import
                try:
                    log_admin_action(
                        action_type='template_import_excel',
                        description=f"Created template '{template_name}' and imported structure from Excel "
                                  f"(Pages: {pages_count}, Sections: {sections_count}, Items: {items_count})",
                        target_type='form_template',
                        target_id=template_id,
                        target_description=f"Template ID: {template_id}, Imported from Excel",
                        risk_level='medium'
                    )
                except Exception as log_error:
                    current_app.logger.error(f"Error logging Excel import: {log_error}")

                if result.get('errors'):
                    error_msg = _("Template created and Excel import completed with %(pages)d pages, %(sections)d sections, and %(items)d items. Some errors occurred: %(errors)s", pages=pages_count, sections=sections_count, items=items_count, errors=', '.join(result['errors'][:3]))
                    flash(error_msg, "warning")
                else:
                    flash(_("Template '%(name)s' created and Excel import completed: %(pages)d pages, %(sections)d sections, and %(items)d items imported.", name=template_name, pages=pages_count, sections=sections_count, items=items_count), "success")
            else:
                # Import failed - the import service may have rolled back the session
                # Rollback our session to ensure clean state
                try:
                    db.session.rollback()
                except Exception as e:
                    current_app.logger.debug("Rollback after Excel import failure: %s", e)

                error_msg = result.get('message', _('Unknown error during Excel import'))
                flash(_("Template created but Excel import failed: %(error)s", error=error_msg), "warning")
                if result.get('errors'):
                    current_app.logger.error(f"Excel import errors: {result['errors']}")

                # Even if import failed, template was created, so redirect to edit page
                # The template exists but may be incomplete

            return redirect(url_for("form_builder.edit_template", template_id=template_id))

        except Exception as e:
            handle_view_exception(
                e,
                "Error creating template.",
                log_message=f"Error creating template with Excel import: {e}"
            )
            return render_template(
                "admin/templates/new_template.html",
                form=form,
                title="Create New Form Template",
                available_templates=available_templates,
                get_localized_template_name=get_localized_template_name
            )

    if form.validate_on_submit():
        add_to_self_report = form.add_to_self_report.data

        # Check for name uniqueness across all published versions
        new_name = form.name.data.strip()
        if new_name:
            # Check if any published version has this name
            # Explicitly specify the join condition to avoid ambiguous foreign key error
            existing_version = FormTemplateVersion.query.filter_by(
                name=new_name,
                status='published'
            ).join(FormTemplate, FormTemplateVersion.template_id == FormTemplate.id).filter(
                FormTemplate.id.isnot(None)  # This will be None for new template
            ).first()
            if existing_version:
                flash(f"Error: A form template with the name '{new_name}' already exists.", "danger")
                return render_template(
                    "admin/templates/new_template.html",
                    form=form,
                    title="Create New Form Template",
                    available_templates=available_templates,
                    get_localized_template_name=get_localized_template_name
                )

        # Create template (no properties - all are now in versions)
        template = FormTemplate(
            created_by=current_user.id,
            owned_by=form.owned_by.data if form.owned_by.data else current_user.id
        )

        db.session.add(template)
        db.session.flush()  # Flush to get template ID

        # Create initial version with name and translations
        now = utcnow()
        initial_version = FormTemplateVersion(
            template_id=template.id,
            version_number=1,
            status='draft',
            name=new_name,
            description=form.description.data,
            add_to_self_report=add_to_self_report,
            display_order_visible=form.display_order_visible.data,
            is_paginated=form.is_paginated.data,
            enable_export_pdf=form.enable_export_pdf.data,
            enable_export_excel=form.enable_export_excel.data,
            enable_import_excel=form.enable_import_excel.data,
            enable_ai_validation=form.enable_ai_validation.data,
            created_by=current_user.id,
            updated_by=current_user.id,
            created_at=now,
            updated_at=now
        )

        # Handle version name and description translations
        _handle_version_translations(initial_version, form)
        _handle_version_description_translations(initial_version, form)

        db.session.add(initial_version)
        db.session.flush()

        # Store version name and ID in variables before any commit operations
        # This prevents "not persistent" errors if log_admin_action commits the session
        version_name = initial_version.name
        version_id = initial_version.id
        template_id = template.id

        # Handle template sharing - get values from form data since we're using checkboxes
        # Pass template name directly to avoid accessing template.name property which queries versions
        shared_admin_ids = request.form.getlist(form.shared_with_admins.name)
        current_app.logger.debug(f"Template creation - shared_admin_ids from form: {shared_admin_ids}")
        if shared_admin_ids:
            # Convert string IDs to integers
            shared_admin_ids = [int(id) for id in shared_admin_ids if id]
            current_app.logger.debug(f"Template creation - processed shared_admin_ids: {shared_admin_ids}")
            # Pass version name to avoid accessing template.name which might trigger relationship queries
            _handle_template_sharing(template, shared_admin_ids, current_user.id, template_name=version_name)

        try:
            db.session.flush()

            # Log admin action for template creation
            # Use stored variables to avoid accessing initial_version after potential commit
            try:
                log_admin_action(
                    action_type='template_create',
                    description=f"Created new template '{version_name}'",
                    target_type='form_template',
                    target_id=template_id,
                    target_description=f"Template ID: {template_id}",
                    risk_level='medium'
                )
            except Exception as log_error:
                current_app.logger.error(f"Error logging template creation: {log_error}")

            flash(f"Form Template '{version_name}' created. You can now add sections and items.", "success")
            return redirect(url_for("form_builder.edit_template", template_id=template_id))
        except Exception as e:
            handle_view_exception(
                e,
                GENERIC_ERROR_MESSAGE,
                log_message=f"Error creating new template: {e}"
            )

    return render_template(
        "admin/templates/new_template.html",
        form=form,
        title="Create New Form Template",
        available_templates=available_templates,
        get_localized_template_name=get_localized_template_name
    )

@bp.route("/templates/<int:template_id>/owned-by", methods=["GET"])
@permission_required('admin.templates.view')
def get_template_owned_by(template_id):
    """Return the owned_by user info for a template (used to pre-fill data owner on assignments)."""
    template = FormTemplate.query.get_or_404(template_id)
    if template.owned_by_user:
        return json_ok(
            owned_by_user_id=template.owned_by,
            owned_by_user_name=template.owned_by_user.name,
            owned_by_user_email=template.owned_by_user.email,
        )
    return json_ok(owned_by_user_id=None)


@bp.route("/templates/<int:template_id>/clone-data", methods=["GET"])
@permission_required('admin.templates.view')
def get_template_clone_data(template_id):
    """Get template data for cloning purposes."""
    template = FormTemplate.query.get_or_404(template_id)

    # Check if user has access to this template
    if not check_template_access(template_id, current_user.id):
        return json_forbidden('Access denied')

    # Return template data as JSON
    # Get name from published version or first version
    version = template.published_version if template.published_version else template.versions.order_by('created_at').first()
    version_name = version.name if version and version.name else "Unnamed Template"
    version_translations = version.name_translations if version and version.name_translations else {}

    return json_ok(
        id=template.id,
        name=version_name,
        description=version.description if version else '',
        add_to_self_report=version.add_to_self_report if version else False,
        display_order_visible=version.display_order_visible if version else False,
        is_paginated=version.is_paginated if version else False,
        enable_export_pdf=version.enable_export_pdf if version else False,
        enable_export_excel=version.enable_export_excel if version else False,
        enable_import_excel=version.enable_import_excel if version else False,
        enable_ai_validation=version.enable_ai_validation if version else False,
        name_translations=version_translations,
    )

@bp.route("/templates/edit/<int:template_id>", methods=["GET", "POST"])
@permission_required('admin.templates.edit')
def edit_template(template_id):
    template = FormTemplate.query.get_or_404(template_id)

    # Check if user has access to this template (owner or shared with)
    if not check_template_access(template_id, current_user.id):
        flash("Access denied. You don't have permission to edit this template.", "warning")
        return redirect(url_for("form_builder.manage_templates"))
    # Don't use obj=template since template.name is now a property - populate manually
    # IMPORTANT: do not pre-populate from DB on POST, otherwise submitted values (e.g. description)
    # get overwritten before validation/save.
    form = FormTemplateForm()

    # Determine which version to display: explicit version_id (GET or POST) > published by default
    requested_version_id = None
    try:
        version_param = request.args.get('version_id') or (request.form.get('version_id') if request.method == 'POST' else None)
        requested_version_id = int(version_param) if version_param else None
    except Exception as e:
        current_app.logger.debug("version_id parse failed: %s", e)
        requested_version_id = None

    selected_version = None
    if requested_version_id:
        selected_version = FormTemplateVersion.query.filter_by(id=requested_version_id, template_id=template.id).first()
    if not selected_version and template.published_version_id:
        selected_version = FormTemplateVersion.query.get(template.published_version_id)
    # Fallback: latest version
    if not selected_version:
        selected_version = FormTemplateVersion.query.filter_by(template_id=template.id).order_by(FormTemplateVersion.created_at.desc()).first()

    # Safety net: if the template has no versions at all, create a draft version on the fly
    if not selected_version:
        selected_version = _get_or_create_draft_version(template, current_user.id)

    # Ensure we have fresh data from the database (in case of recent updates)
    if selected_version:
        db.session.refresh(selected_version)

    # Check if form was submitted (either via submit button or hidden field)
    # The submit field name is 'submit' and value is 'Save Template'
    is_template_details_submit = (
        request.method == 'POST' and
        request.form.get('submit') == 'Save Template'
    )

    # Populate fields from version (all properties are now version-specific) only for initial render.
    # On POST, Flask-WTF already binds request.form; repopulating here would clobber submitted data.
    if request.method == 'GET' and selected_version:
        form.name.data = selected_version.name if selected_version.name else ""
        form.description.data = selected_version.description or ""
        form.add_to_self_report.data = selected_version.add_to_self_report
        form.display_order_visible.data = selected_version.display_order_visible
        form.is_paginated.data = selected_version.is_paginated
        form.enable_export_pdf.data = selected_version.enable_export_pdf
        form.enable_export_excel.data = selected_version.enable_export_excel
        form.enable_import_excel.data = selected_version.enable_import_excel
        form.enable_ai_validation.data = selected_version.enable_ai_validation

        # Populate translation fields with existing values from version
        _populate_version_translations(form, selected_version)
        _populate_version_description_translations(form, selected_version)

        # Populate sharing fields with existing values
        _populate_template_sharing(form, template)
    section_form = FormSectionForm(prefix="section")

    # Forms for editing modals
    add_indicator_modal_form = IndicatorForm(prefix="add_ind_modal")
    document_field_form = DocumentFieldForm(prefix="doc_field")
    add_question_modal_form = QuestionForm(prefix="add_q_modal")

    # Populate page choices dynamically for the SELECTED version
    page_choices = []
    try:
        pages_for_choices = FormPage.query.filter_by(template_id=template.id, version_id=selected_version.id).all()
        page_choices = [(p.id, p.name) for p in pages_for_choices]
    except Exception as e:
        current_app.logger.warning("Failed to load page choices: %s", e, exc_info=True)
        page_choices = []
    section_form.page_id.choices = page_choices

    # Populate section choices for modal forms (scoped to draft version)
    # Include archived sections in form builder (they will be filtered/hidden in the template)
    all_sections = FormSection.query.filter_by(template_id=template.id, version_id=selected_version.id).order_by(FormSection.order).all()
    section_choices = [(s.id, s.name) for s in all_sections]
    add_indicator_modal_form.section_id.choices = section_choices
    add_question_modal_form.section_id.choices = section_choices
    document_field_form.section_id.choices = section_choices

    if is_template_details_submit:
        # Log form submission details only when VERBOSE_FORM_DEBUG is enabled (never log full form data)
        _template_debug = current_app.config.get('VERBOSE_FORM_DEBUG', False)
        if _template_debug:
            current_app.logger.debug(
                "TEMPLATE_UPDATE: form submission template_id=%s version_id=%s method=%s keys=%s",
                template.id, selected_version.id, request.method, list(request.form.keys())
            )

        # Validate form
        if not form.validate():
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error in {field}: {error}", "danger")
            return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=selected_version.id))

        # Form validation passed, proceed with update
        # Handle version name updates - use raw request form data as primary source
        new_name = request.form.get('name', form.name.data)
        if new_name:
            new_name = new_name.strip()

        # Ensure we have a valid name
        if not new_name or not new_name.strip():
            flash("Template name cannot be empty.", "danger")
            return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=selected_version.id))

        # Check for name uniqueness if this is a published version or if name changed
        is_published_version = (template.published_version_id == selected_version.id)
        if is_published_version or (selected_version.name != new_name):
            # Check if any other published version has this name
            # Explicitly specify the join condition to avoid ambiguous foreign key error
            existing_version = FormTemplateVersion.query.filter_by(
                name=new_name,
                status='published'
            ).join(FormTemplate, FormTemplateVersion.template_id == FormTemplate.id).filter(
                FormTemplate.id != template.id
            ).first()
            if existing_version:
                error_msg = f"Error: Another form template with the name '{new_name}' already exists."
                flash(error_msg, "danger")
                form.name.data = selected_version.name if selected_version.name else ""
                return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=selected_version.id))

        # Update version-specific name and properties
        selected_version.name = new_name if new_name else None
        selected_version.description = form.description.data

        # Boolean fields: Get from form data, with fallback to request.form for unchecked checkboxes
        # WTForms BooleanField returns False when unchecked, but we'll also check raw form data

        # Get is_paginated value - WTForms BooleanField doesn't recognize 'y' as True
        # HTML checkboxes send 'y' when checked, but WTForms only recognizes 'true', 't', 'on', 'yes', '1', '1.0'
        # So we need to check request.form directly for 'y'
        if 'is_paginated' in request.form:
            raw_value = request.form.get('is_paginated')
            # Check for 'y' (HTML checkbox value) or standard True values
            is_paginated_value = raw_value.lower() in ('y', 'yes', 'true', 't', 'on', '1', '1.0')
        else:
            # Checkbox not in form means unchecked
            is_paginated_value = False

        # Handle all boolean fields - check request.form for 'y' value (HTML checkbox sends 'y' when checked)
        # When a checkbox is unchecked, it's NOT in request.form, so we need to explicitly check for its presence
        def get_boolean_from_form(field_name, default_when_missing=False):
            """Get boolean value from form, handling 'y' from HTML checkboxes.

            Args:
                field_name: Name of the form field
                default_when_missing: Value to use when field is NOT in request.form (unchecked checkbox)
            """
            if field_name in request.form:
                # Field is in form (checkbox was checked)
                raw_value = request.form.get(field_name)
                return raw_value.lower() in ('y', 'yes', 'true', 't', 'on', '1', '1.0')
            else:
                # Field is NOT in form (checkbox was unchecked)
                return default_when_missing

        # For boolean fields, when checkbox is unchecked (not in request.form), it should be False
        # The default_when_missing parameter controls what value to use when the field is NOT in the form
        selected_version.add_to_self_report = get_boolean_from_form('add_to_self_report', default_when_missing=False)
        selected_version.display_order_visible = get_boolean_from_form('display_order_visible', default_when_missing=False)
        selected_version.is_paginated = is_paginated_value
        selected_version.enable_export_pdf = get_boolean_from_form('enable_export_pdf', default_when_missing=False)
        selected_version.enable_export_excel = get_boolean_from_form('enable_export_excel', default_when_missing=False)
        selected_version.enable_import_excel = get_boolean_from_form('enable_import_excel', default_when_missing=False)
        selected_version.enable_ai_validation = get_boolean_from_form('enable_ai_validation', default_when_missing=False)



        # Update template ownership if changed
        if form.owned_by.data and form.owned_by.data != template.owned_by:
            template.owned_by = form.owned_by.data

        # Handle version name and description translations
        _handle_version_translations(selected_version, form)
        _handle_version_description_translations(selected_version, form)

        # Handle template sharing - get values from form data since we're using checkboxes
        shared_admin_ids = request.form.getlist(form.shared_with_admins.name)
        current_app.logger.debug(f"Template edit - shared_admin_ids from form: {shared_admin_ids}")
        if shared_admin_ids:
            # Convert string IDs to integers
            shared_admin_ids = [int(id) for id in shared_admin_ids if id]
        else:
            shared_admin_ids = []
        current_app.logger.debug(f"Template edit - processed shared_admin_ids: {shared_admin_ids}")
        _handle_template_sharing(template, shared_admin_ids, current_user.id)

        try:
            # Handle pages data
            if selected_version.is_paginated:
                before_pages = FormPage.query.filter_by(template_id=template.id, version_id=selected_version.id).count()
                current_app.logger.debug(
                    f"VERSIONING_DEBUG: edit_template - updating pages for version {selected_version.id}; "
                    f"pages before={before_pages}"
                )
                # Update pages for the active version (draft or published)
                _handle_template_pages(template, request.form, version_id=selected_version.id)
                _update_version_timestamp(selected_version.id, current_user.id)
                after_pages = FormPage.query.filter_by(template_id=template.id, version_id=selected_version.id).count()
                current_app.logger.debug(
                    f"VERSIONING_DEBUG: edit_template - updated pages for version {selected_version.id}; "
                    f"pages after={after_pages}"
                )
            db.session.flush()

            # Refresh the version object to ensure we have the latest data
            db.session.refresh(selected_version)

            # Double-check by querying from database
            db.session.expire(selected_version)
            db.session.refresh(selected_version)

            # Verify persisted value when verbose debug is enabled
            if _template_debug:
                db_version = FormTemplateVersion.query.get(selected_version.id)
                if db_version and db_version.is_paginated != selected_version.is_paginated:
                    current_app.logger.warning(
                        "TEMPLATE_UPDATE: is_paginated mismatch object=%s db=%s",
                        selected_version.is_paginated, db_version.is_paginated
                    )

            # Log admin action for audit trail
            try:
                log_admin_action(
                    action_type='template_update',
                    description=f"Updated template '{selected_version.name}'",
                    target_type='form_template',
                    target_id=template.id,
                    target_description=f"Template ID: {template.id}, Version ID: {selected_version.id}",
                    risk_level='medium'
                )
            except Exception as log_error:
                current_app.logger.error(f"Error logging template update: {log_error}")

            success_msg = f"Form Template '{selected_version.name}' updated successfully."

            flash(success_msg, "success")
            # Preserve the currently selected version after saving
            return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=selected_version.id))
        except Exception as e:
            request_transaction_rollback()
            error_msg = "Error updating form template."
            current_app.logger.error(f"Error updating template {template_id}: {e}", exc_info=True)
            db.session.refresh(template)
            form = FormTemplateForm(obj=template)

    # Build template data for JavaScript scoped to the selected version
    template_data = _build_template_data_for_js(template, version_id=selected_version.id)

    # Sanitize template_data to avoid collisions with helper function names
    # If any plugin or upstream builder inadvertently adds these keys, ensure
    # our callable helpers are not overridden in the Jinja context.
    try:
        reserved_helper_keys = {
            'get_localized_template_name',
            'get_localized_indicator_type',
            'get_localized_indicator_unit',
            # Prevent collisions with Flask-Babel translation functions
            '_', 'gettext', 'ngettext',
        }
        for _key in list(template_data.keys()):
            if _key in reserved_helper_keys:
                current_app.logger.warning(
                    f"Removing conflicting key from template_data: {_key}"
                )
                template_data.pop(_key, None)
    except Exception as _e:
        current_app.logger.error(
            f"Error sanitizing template_data for helper collisions: {_e}",
            exc_info=True,
        )

    # Get custom field types from plugins for the form builder
    custom_field_types = []
    if current_app.form_integration:
        custom_field_types = current_app.form_integration.get_custom_field_types_for_builder()

    from app.utils.form_localization import get_localized_template_name, get_localized_indicator_type, get_localized_indicator_unit
    from flask_babel import gettext as _gettext, ngettext as _ngettext
    # Important: Pass template_data first so that callable helpers below cannot be overridden
    # by any accidentally conflicting keys inside template_data.
    # Pages list for server-side rendering (use selected version)
    draft_pages = FormPage.query.filter_by(template_id=template.id, version_id=selected_version.id).order_by(FormPage.order).all()

    # Compute data counts for warning prompts in the builder UI
    from sqlalchemy import func
    from app.models.forms import FormData, RepeatGroupData, RepeatGroupInstance, DynamicIndicatorData

    # Item-level counts (FormData + RepeatGroupData) for items in this template
    item_counts_fd_rows = (
        db.session.query(FormItem.id, func.count(FormData.id))
        .join(FormData, FormData.form_item_id == FormItem.id)
        .filter(FormItem.template_id == template.id)
        .group_by(FormItem.id)
        .all()
    )
    item_counts_rd_rows = (
        db.session.query(FormItem.id, func.count(RepeatGroupData.id))
        .join(RepeatGroupData, RepeatGroupData.form_item_id == FormItem.id)
        .filter(FormItem.template_id == template.id)
        .group_by(FormItem.id)
        .all()
    )
    item_data_counts = {}
    for item_id, count in item_counts_fd_rows:
        item_data_counts[item_id] = item_data_counts.get(item_id, 0) + int(count)
    for item_id, count in item_counts_rd_rows:
        item_data_counts[item_id] = item_data_counts.get(item_id, 0) + int(count)

    # Section-level counts: aggregate counts for items in each section (+ dynamic indicator data + repeat instances per section)
    sec_counts_fd_rows = (
        db.session.query(FormItem.section_id, func.count(FormData.id))
        .join(FormData, FormData.form_item_id == FormItem.id)
        .filter(FormItem.template_id == template.id)
        .group_by(FormItem.section_id)
        .all()
    )
    sec_counts_rd_rows = (
        db.session.query(FormItem.section_id, func.count(RepeatGroupData.id))
        .join(RepeatGroupData, RepeatGroupData.form_item_id == FormItem.id)
        .filter(FormItem.template_id == template.id)
        .group_by(FormItem.section_id)
        .all()
    )
    # Dynamic indicator data is tied directly to section_id
    section_ids_subq = select(FormSection.id).filter_by(template_id=template.id).scalar_subquery()
    dyn_counts_rows = (
        db.session.query(DynamicIndicatorData.section_id, func.count(DynamicIndicatorData.id))
        .filter(DynamicIndicatorData.section_id.in_(section_ids_subq))
        .group_by(DynamicIndicatorData.section_id)
        .all()
    )
    # Repeat group instances are tied directly to section_id
    repeat_instance_counts_rows = (
        db.session.query(RepeatGroupInstance.section_id, func.count(RepeatGroupInstance.id))
        .filter(RepeatGroupInstance.section_id.in_(section_ids_subq))
        .group_by(RepeatGroupInstance.section_id)
        .all()
    )
    section_data_counts = {}
    for sec_id, count in sec_counts_fd_rows:
        section_data_counts[sec_id] = section_data_counts.get(sec_id, 0) + int(count)
    for sec_id, count in sec_counts_rd_rows:
        section_data_counts[sec_id] = section_data_counts.get(sec_id, 0) + int(count)
    for sec_id, count in dyn_counts_rows:
        section_data_counts[sec_id] = section_data_counts.get(sec_id, 0) + int(count)
    for sec_id, count in repeat_instance_counts_rows:
        section_data_counts[sec_id] = section_data_counts.get(sec_id, 0) + int(count)

    # Versions list for UI
    # PERFORMANCE: Pre-fetch all users to avoid N+1 queries
    versions = FormTemplateVersion.query.filter_by(template_id=template.id).order_by(FormTemplateVersion.created_at.desc()).all()

    # Collect all unique user IDs
    user_ids = set()
    for v in versions:
        if hasattr(v, 'updated_by') and v.updated_by:
            user_ids.add(v.updated_by)

    # Fetch all users in a single query
    users_by_id = {}
    if user_ids:
        users = User.query.filter(User.id.in_(user_ids)).all()
        users_by_id = {user.id: user for user in users}

    versions_for_ui = []
    for v in versions:
        # Get updated_by user info from pre-fetched dict
        updated_by_user = None
        if hasattr(v, 'updated_by') and v.updated_by:
            updated_by_user = users_by_id.get(v.updated_by)

        versions_for_ui.append({
            'id': v.id,
            'version_number': v.version_number if hasattr(v, 'version_number') else None,
            'status': v.status,
            'comment': v.comment or '',
            'created_at': v.created_at,
            'updated_at': v.updated_at if hasattr(v, 'updated_at') else v.created_at,
            'updated_by': updated_by_user,
            'updated_by_name': updated_by_user.name if updated_by_user and updated_by_user.name else (updated_by_user.email if updated_by_user else None),
            'is_published': (template.published_version_id == v.id)
        })
    has_draft = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first() is not None

    # Get active version number for display
    active_version_number = None
    if selected_version:
        active_version_number = selected_version.version_number if hasattr(selected_version, 'version_number') else None

    # Check if template has any archived items or sections
    has_archived_items = FormItem.query.filter_by(template_id=template.id, archived=True).first() is not None
    has_archived_sections = FormSection.query.filter_by(template_id=template.id, archived=True).first() is not None
    has_archived_items = has_archived_items or has_archived_sections

    # Integrity guardrails: block deploy if any indicator items are missing a valid indicator bank reference
    invalid_indicator_items_count = (
        FormItem.query
        .filter_by(template_id=template.id, version_id=selected_version.id, item_type='indicator')
        .filter(FormItem.indicator_bank_id.is_(None))
        .count()
    )

    return render_template("forms/form_builder/form_builder.html",
                           **template_data,
                           title=f"Edit Form Template: {template.name}",
                           active_version_number=active_version_number,
                           template=template,
                           form=form,
                           section_form=section_form,
                           add_indicator_modal_form=add_indicator_modal_form,
                           document_field_form=document_field_form,
                           add_question_modal_form=add_question_modal_form,
                           active_version_id=selected_version.id,
                           has_draft=has_draft,
                           published_version_id=template.published_version_id,
                           draft_pages=draft_pages,
                           versions_for_ui=versions_for_ui,
                           selected_version=selected_version,
                           selected_version_comment=selected_version.comment or '',
                           selected_version_is_draft=(selected_version.status == 'draft'),
                           selected_version_status=selected_version.status,

                           # Re-inject gettext helpers explicitly to avoid any shadowing
                           _=_gettext,
                           gettext=_gettext,
                           ngettext=_ngettext,
                           get_localized_template_name=get_localized_template_name,
                           get_localized_indicator_type=get_localized_indicator_type,
                           get_localized_indicator_unit=get_localized_indicator_unit,
                           custom_field_types=custom_field_types,
                           item_data_counts=item_data_counts,
                           section_data_counts=section_data_counts,
                           has_archived_items=has_archived_items,
                           invalid_indicator_items_count=invalid_indicator_items_count)

@bp.route("/templates/<int:template_id>/delete-info", methods=["GET"])
@admin_permission_required('admin.templates.delete')
def get_template_delete_info(template_id):
    """Get detailed information about what will be deleted when deleting a template."""
    from app.services.authorization_service import AuthorizationService

    template = FormTemplate.query.get_or_404(template_id)

    # Template owner or system manager can view delete info
    if template.owned_by != current_user.id and not AuthorizationService.is_system_manager(current_user):
        return json_forbidden('Access denied. Only the template owner can view this information.')

    # Get assignments
    assigned_forms = template.assigned_forms.all()
    assignments_list = []
    for af in assigned_forms:
        public_submissions_count = af.public_submissions.count() if hasattr(af, 'public_submissions') else 0
        assignments_list.append({
            'id': af.id,
            'period_name': af.period_name,
            'public_submissions_count': public_submissions_count
        })

    # Get data counts (reuse logic from manage_templates)
    from app.models.form_items import FormItem
    from app.models.forms import FormData, RepeatGroupData, DynamicIndicatorData, FormSection, RepeatGroupInstance
    from sqlalchemy import func

    item_ids_subq = select(FormItem.id).filter_by(template_id=template.id).scalar_subquery()
    section_ids_subq = select(FormSection.id).filter_by(template_id=template.id).scalar_subquery()

    formdata_count = db.session.query(func.count(FormData.id)).filter(FormData.form_item_id.in_(item_ids_subq)).scalar() or 0
    repeat_data_count = db.session.query(func.count(RepeatGroupData.id)).filter(RepeatGroupData.form_item_id.in_(item_ids_subq)).scalar() or 0
    repeat_instances_count = db.session.query(func.count(RepeatGroupInstance.id)).filter(RepeatGroupInstance.section_id.in_(section_ids_subq)).scalar() or 0
    dynamic_data_count = db.session.query(func.count(DynamicIndicatorData.id)).filter(DynamicIndicatorData.section_id.in_(section_ids_subq)).scalar() or 0

    total_data_count = formdata_count + repeat_data_count + repeat_instances_count + dynamic_data_count

    # Get template structure counts
    versions_count = FormTemplateVersion.query.filter_by(template_id=template.id).count()
    pages_count = FormPage.query.filter_by(template_id=template.id).count()
    sections_count = FormSection.query.filter_by(template_id=template.id).count()
    items_count = FormItem.query.filter_by(template_id=template.id).count()

    # Get version details
    versions = FormTemplateVersion.query.filter_by(template_id=template.id).order_by(FormTemplateVersion.created_at.desc()).all()
    versions_list = []
    for v in versions:
        versions_list.append({
            'id': v.id,
            'version_number': v.version_number if hasattr(v, 'version_number') else None,
            'status': v.status,
            'created_at': v.created_at.isoformat() if v.created_at else None
        })

    return json_ok(
        template_id=template.id,
        template_name=template.name,
        assignments=assignments_list,
        assignments_count=len(assignments_list),
        data_counts={
            'form_data': formdata_count,
            'repeat_data': repeat_data_count,
            'repeat_instances': repeat_instances_count,
            'dynamic_data': dynamic_data_count,
            'total': total_data_count,
        },
        structure_counts={
            'versions': versions_count,
            'pages': pages_count,
            'sections': sections_count,
            'items': items_count,
        },
        versions=versions_list,
    )

@bp.route("/templates/delete/<int:template_id>", methods=["POST"])
@admin_permission_required('admin.templates.delete')
def delete_template(template_id):
    from app.services.authorization_service import AuthorizationService

    template = FormTemplate.query.get_or_404(template_id)

    # Template owner or system manager can delete the template
    if template.owned_by != current_user.id and not AuthorizationService.is_system_manager(current_user):
        flash("Access denied. Only the template owner can delete this template.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    # Check if deletion is confirmed (from the modal)
    confirmed = request.form.get('confirmed', 'false').lower() == 'true'

    if not confirmed:
        # Return JSON error for AJAX requests, or redirect for form submissions
        if is_json_request():
            return json_bad_request('Deletion not confirmed. Please use the confirmation modal.')
        flash("Deletion not confirmed. Please use the confirmation modal.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    try:
        # Debug counts prior to delete
        total_versions = template.versions.count() if hasattr(template, 'versions') else 0
        total_pages = template.pages.count() if hasattr(template, 'pages') else 0
        total_sections = template.sections.count() if hasattr(template, 'sections') else 0
        current_app.logger.debug(
            f"VERSIONING_DEBUG: delete_template - template_id={template_id} pre-delete: "
            f"versions={total_versions}, pages={total_pages}, sections={total_sections}"
        )
        # Delete template sharing records first
        TemplateShare.query.filter_by(template_id=template.id).delete(synchronize_session=False)

        # Delete assignments (which will cascade to public submissions and entity statuses)
        from app.models.assignments import AssignedForm
        assignments_deleted = AssignedForm.query.filter_by(template_id=template.id).delete(synchronize_session=False)
        current_app.logger.debug(f"VERSIONING_DEBUG: delete_template - deleted {assignments_deleted} assignments")

        # Unpublish to avoid FK constraints
        template.published_version_id = None
        db.session.flush()

        # Manually delete children and dependent data in safe order (works even without DB ON DELETE)
        from app.models.form_items import FormItem
        from app.models.forms import (
            FormPage,
            FormSection,
            FormTemplateVersion,
            FormData,
            RepeatGroupInstance,
            RepeatGroupData,
            DynamicIndicatorData,
        )

        # Subqueries for dependent deletes
        item_ids_subq = select(FormItem.id).filter_by(template_id=template.id).scalar_subquery()
        section_ids_subq = select(FormSection.id).filter_by(template_id=template.id).scalar_subquery()

        # Delete data rows that reference this template's items/sections first to avoid FK violations
        formdata_deleted = FormData.query.filter(FormData.form_item_id.in_(item_ids_subq)).delete(synchronize_session=False)
        repeat_data_deleted = RepeatGroupData.query.filter(RepeatGroupData.form_item_id.in_(item_ids_subq)).delete(synchronize_session=False)
        repeat_instances_deleted = RepeatGroupInstance.query.filter(RepeatGroupInstance.section_id.in_(section_ids_subq)).delete(synchronize_session=False)
        dynamic_data_deleted = DynamicIndicatorData.query.filter(DynamicIndicatorData.section_id.in_(section_ids_subq)).delete(synchronize_session=False)

        # Now remove the structural records
        items_deleted = FormItem.query.filter_by(template_id=template.id).delete(synchronize_session=False)
        sections_deleted = FormSection.query.filter_by(template_id=template.id).delete(synchronize_session=False)
        pages_deleted = FormPage.query.filter_by(template_id=template.id).delete(synchronize_session=False)
        versions_deleted = FormTemplateVersion.query.filter_by(template_id=template.id).delete(synchronize_session=False)

        current_app.logger.debug(
            f"VERSIONING_DEBUG: delete_template - manual cascade deletes -> "
            f"formdata={formdata_deleted}, repeat_data={repeat_data_deleted}, "
            f"repeat_instances={repeat_instances_deleted}, dynamic_data={dynamic_data_deleted}, "
            f"items={items_deleted}, sections={sections_deleted}, pages={pages_deleted}, versions={versions_deleted}"
        )

        # Capture template name before deletion for logging
        template_name = template.name

        db.session.delete(template)
        db.session.flush()
        current_app.logger.info(
            f"VERSIONING_DEBUG: delete_template - deleted template_id={template_id} "
            f"(assignments={assignments_deleted}, items={items_deleted}, sections={sections_deleted}, pages={pages_deleted}, versions={versions_deleted})"
        )

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='template_delete',
                description=f"Deleted template '{template_name}' and all structure (assignments={assignments_deleted}, items={items_deleted}, sections={sections_deleted}, data entries={formdata_deleted + repeat_data_deleted + dynamic_data_deleted})",
                target_type='form_template',
                target_id=template_id,
                target_description=f"Template ID: {template_id}",
                risk_level='medium'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging template deletion: {log_error}")

        flash(f"Form Template '{template_name}' and its structure deleted.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error deleting template {template_id}: {e}", exc_info=True)
    return redirect(url_for("form_builder.manage_templates"))

@bp.route("/templates/duplicate/<int:template_id>", methods=["POST"])
@permission_required('admin.templates.duplicate')
def duplicate_template(template_id):
    """Duplicate a form template including its published structure into a new template owned by the current user.

    - Generates a unique name by appending "(Copy)" (and a counter if needed)
    - Copies template flags and translations
    - Creates a published version in the new template and clones pages/sections/items from the source published version
    """
    # Validate access to source
    source_template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(source_template.id, current_user.id):
        flash("Access denied. You don't have permission to duplicate this template.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    # Get source version name for copying
    source_version = source_template.published_version if source_template.published_version else source_template.versions.order_by('created_at').first()
    source_name = source_version.name if source_version and source_version.name else "Unnamed Template"

    # Determine base name and ensure uniqueness (check published versions)
    base_copy_name = f"{source_name} (Copy)"
    new_name = base_copy_name
    suffix = 2
    while FormTemplateVersion.query.filter_by(name=new_name, status='published').first() is not None:
        new_name = f"{base_copy_name} {suffix}"
        suffix += 1

    # Create the new template record (no properties - all are now in versions)
    new_template = FormTemplate(
        created_by=current_user.id,
        owned_by=current_user.id
    )

    try:
        db.session.add(new_template)
        db.session.flush()  # obtain ID

        # Source version already retrieved above, but ensure we have it
        if not source_version:
            if source_template.published_version_id:
                source_version = FormTemplateVersion.query.get(source_template.published_version_id)
            if not source_version:
                source_version = FormTemplateVersion.query.filter_by(template_id=source_template.id).order_by(FormTemplateVersion.created_at.desc()).first()

        # Always create a published version on the new template
        # Use the new template name for the version (not the source version name)
        # This ensures consistency: new template name = new version name
        new_published = FormTemplateVersion(
            template_id=new_template.id,
            version_number=1,
            status='published',
            based_on_version_id=None,
            created_by=current_user.id,
            updated_by=current_user.id,
            comment=f"Cloned from template {source_template.id}",
            name=new_name,  # Use the unique name we generated
            name_translations=source_version.name_translations.copy() if source_version and source_version.name_translations else None,  # Copy from source version
            description=source_version.description if source_version else None,
            description_translations=source_version.description_translations.copy() if source_version and source_version.description_translations else None,  # Copy description translations
            add_to_self_report=source_version.add_to_self_report if source_version else None,
            display_order_visible=source_version.display_order_visible if source_version else None,
            is_paginated=source_version.is_paginated if source_version else None,
            enable_export_pdf=source_version.enable_export_pdf if source_version else None,
            enable_export_excel=source_version.enable_export_excel if source_version else None,
            enable_import_excel=source_version.enable_import_excel if source_version else None,
            enable_ai_validation=source_version.enable_ai_validation if source_version else False
        )
        db.session.add(new_published)
        db.session.flush()

        if source_version:
            _clone_template_structure_between_templates(
                source_template_id=source_template.id,
                source_version_id=source_version.id,
                target_template_id=new_template.id,
                target_version_id=new_published.id
            )

        # Point new template to its published version
        new_template.published_version_id = new_published.id

        db.session.flush()

        # Audit log
        with suppress(Exception):
            log_admin_action(
                action_type='template_duplicate',
                description=f"Duplicated template '{source_name}' to '{new_name}'",
                target_type='form_template',
                target_id=new_template.id,
                target_description=f"Source ID: {source_template.id}, New ID: {new_template.id}",
                risk_level='low'
            )

        flash(f"Form Template '{source_name}' duplicated as '{new_name}'.", "success")
        return redirect(url_for("form_builder.edit_template", template_id=new_template.id))

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error duplicating template {template_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("form_builder.manage_templates"))

@bp.route("/templates/<int:template_id>/export_excel", methods=["GET"])
@permission_required('admin.templates.export_excel')
def export_template_excel(template_id):
    """Export template structure to Excel file."""
    template = FormTemplate.query.get_or_404(template_id)

    # Check template access
    if not check_template_access(template_id, current_user.id):
        flash("Access denied. You don't have permission to export this template.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    # Get version_id from query parameter (defaults to published or latest)
    version_id = request.args.get('version_id', type=int)

    try:
        # Export template to Excel
        excel_file = TemplateExcelService.export_template(template_id, version_id)

        # Generate filename
        template_name_safe = secure_filename(template.name)
        filename = f"template_{template_name_safe}_{utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

        # Log admin action
        try:
            log_admin_action(
                action_type='template_export',
                description=f"Exported template '{template.name}' to Excel",
                target_type='form_template',
                target_id=template_id,
                target_description=f"Template ID: {template_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging template export: {log_error}")

        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        current_app.logger.error(f"Error exporting template {template_id} to Excel: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template_id))

@bp.route("/templates/<int:template_id>/import_excel", methods=["POST"])
@permission_required('admin.templates.import_excel')
def import_template_excel(template_id):
    """Import template structure from Excel file."""
    template = FormTemplate.query.get_or_404(template_id)

    # Check template access
    if not check_template_access(template_id, current_user.id):
        flash("Access denied. You don't have permission to import into this template.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    # Get version_id from query parameter or form (defaults to active version)
    # Get this early so we can use it in error redirects too
    version_id = request.args.get('version_id', type=int) or request.form.get('version_id', type=int)

    # Validate CSRF token
    csrf_form = FlaskForm()
    if not csrf_form.validate_on_submit():
        flash("Security validation failed. Please try again.", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_id))

    # Check if file was uploaded
    if 'excel_file' not in request.files:
        flash("No Excel file provided.", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_id))

    excel_file = request.files['excel_file']

    if excel_file.filename == '':
        flash("No Excel file selected.", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_id))

    # Validate file extension
    if not excel_file.filename.lower().endswith(('.xlsx', '.xls')):
        flash("Invalid file type. Please upload an Excel file (.xlsx or .xls).", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_id))

    try:
        # Import template from Excel
        result = TemplateExcelService.import_template(template_id, excel_file, version_id)

        # Use the version_id from result (may be new draft if published was selected)
        final_version_id = result.get('version_id', version_id)

        if result['success']:
            # Log admin action
            try:
                log_admin_action(
                    action_type='template_import',
                    description=f"Imported template structure from Excel into '{template.name}' "
                           f"(Pages: {result['created_count']['pages']}, "
                           f"Sections: {result['created_count']['sections']}, "
                           f"Items: {result['created_count']['items']})",
                    target_type='form_template',
                    target_id=template_id,
                    target_description=f"Template ID: {template_id}",
                    risk_level='medium'
                )
            except Exception as log_error:
                current_app.logger.error(f"Error logging template import: {log_error}")

            flash(result['message'], "success")
        else:
            # Show errors
            error_msg = result['message']
            if result.get('errors'):
                error_msg += f" Errors: {', '.join(result['errors'][:5])}"
                if len(result['errors']) > 5:
                    error_msg += f" (and {len(result['errors']) - 5} more)"
            flash(error_msg, "danger")

        # Preserve version_id in redirect (use final_version_id which may be new draft)
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=final_version_id))

    except Exception as e:
        current_app.logger.error(f"Error importing template {template_id} from Excel: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_id))

# === Template Variables Management Routes ===
@bp.route("/templates/<int:template_id>/variables", methods=["GET", "POST"])
@permission_required('admin.templates.edit')
def manage_template_variables(template_id):
    """Get or save template variables."""
    try:
        template = FormTemplate.query.get_or_404(template_id)
    except Exception as e:
        current_app.logger.error(f"Template not found: {template_id}: {e}", exc_info=True)
        return json_not_found('Template not found.')

    # Check template access - return JSON error instead of redirect
    if not check_template_access(template_id, current_user.id):
        return json_forbidden('Access denied. You don\'t have permission to manage variables for this template.')

    # Get version_id from query parameter (for both GET and POST)
    version_id = request.args.get('version_id', type=int)
    if not version_id and request.method == 'POST':
        # Try to get from JSON body
        with suppress(Exception):
            json_data = get_json_safe()
            if json_data and 'version_id' in json_data:
                version_id = json_data.get('version_id', type=int)

    # Determine which version to use
    version = None
    if version_id:
        version = FormTemplateVersion.query.filter_by(id=version_id, template_id=template.id).first()
    if not version and template.published_version_id:
        version = FormTemplateVersion.query.get(template.published_version_id)
    if not version:
        version = FormTemplateVersion.query.filter_by(template_id=template.id).order_by(FormTemplateVersion.created_at.desc()).first()

    if not version:
        return json_not_found('No version found for this template.')

    if request.method == 'GET':
        # Return variables as JSON
        variables = version.variables if version.variables else {}
        return json_ok(variables=variables)

    elif request.method == 'POST':
        # Save variables
        try:
            # Get JSON data - handle both Content-Type: application/json and form data
            variables_data = None
            if is_json_request():
                variables_data = get_json_safe()
            else:
                # Try to parse from form data
                variables_str = request.form.get('variables')
                if variables_str:
                    try:
                        variables_data = json.loads(variables_str)
                    except json.JSONDecodeError:
                        return json_bad_request('Invalid JSON in variables field.')

            if not variables_data:
                return json_bad_request('No data provided. Expected JSON with "variables" key.')

            if 'variables' not in variables_data:
                return json_bad_request('Invalid data format. Expected "variables" key.')

            # Validate variables structure
            variables_dict = variables_data['variables']
            if not isinstance(variables_dict, dict):
                return json_bad_request('Variables must be a dictionary/object.')

            # Save variables
            version.variables = variables_dict
            _update_version_timestamp(version.id, current_user.id)
            db.session.commit()

            # Log admin action
            try:
                log_admin_action(
                    action_type='template_variables_update',
                    description=f"Updated variables for template '{template.name}'",
                    target_type='form_template',
                    target_id=template_id,
                    target_description=f"Template ID: {template_id}, Version ID: {version.id}",
                    risk_level='low'
                )
            except Exception as log_error:
                current_app.logger.error(f"Error logging variables update: {log_error}")

            return json_ok(message='Variables saved successfully.')
        except json.JSONDecodeError as e:
            request_transaction_rollback()
            current_app.logger.error(f"JSON decode error saving variables for template {template_id}: {e}")
            return json_bad_request('Invalid JSON format.')
        except Exception as e:
            return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/templates/<int:template_id>/variables/options", methods=["GET"])
@permission_required('admin.templates.edit')
def get_variable_options(template_id):
    """Get dropdown options for variable configuration (templates, assignments, form items)."""
    template = FormTemplate.query.get_or_404(template_id)

    # Check template access
    if not check_template_access(template_id, current_user.id):
        return json_forbidden('Access denied.')

    try:
        # Get all templates (for source template dropdown)
        # Load templates with published version for sorting
        all_templates = FormTemplate.query.options(
            db.joinedload(FormTemplate.published_version)
        ).all()
        # Sort by name (from published version) in Python since it's a property
        all_templates.sort(key=lambda t: t.name if t.name else "")
        templates_list = [{'id': t.id, 'name': t.name} for t in all_templates]

        # Get all assignments grouped by template
        assignments_by_template = {}
        all_assignments = AssignedForm.query.order_by(AssignedForm.period_name.desc()).all()
        for assignment in all_assignments:
            if assignment.template_id not in assignments_by_template:
                assignments_by_template[assignment.template_id] = []
            assignments_by_template[assignment.template_id].append({
                'id': assignment.id,
                'period_name': assignment.period_name,
                'template_id': assignment.template_id
            })

        # Get source template ID from query parameter (if filtering)
        source_template_id = request.args.get('source_template_id', type=int)

        # Get form items for a specific template (if source_template_id provided)
        form_items_list = []
        if source_template_id:
            # Get published version of source template
            source_template = FormTemplate.query.get(source_template_id)
            if source_template and source_template.published_version_id:
                source_version_id = source_template.published_version_id
                form_items = FormItem.query.filter_by(
                    template_id=source_template_id,
                    version_id=source_version_id,
                    archived=False
                ).order_by(FormItem.order).all()
                form_items_list = [
                    {
                        'id': item.id,
                        'label': item.label,
                        'item_type': item.item_type,
                        'section_id': item.section_id
                    }
                    for item in form_items
                ]

        return json_ok(
            templates=templates_list,
            assignments_by_template=assignments_by_template,
            form_items=form_items_list,
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

# === FormSection Management Routes ===
@bp.route("/templates/<int:template_id>/sections/new", methods=["POST"])
@permission_required('admin.templates.edit')
def new_template_section(template_id):
    template = FormTemplate.query.get_or_404(template_id)
    version_ref = request.form.get('version_id') or request.args.get('version_id')
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ref)
    if access_redirect:
        return access_redirect
    # No auto-draft creation; drafts are created on demand
    form = FormSectionForm(request.form, prefix="section")

    # Determine target version to add the section to
    target_version_id = request.form.get('version_id') or request.args.get('version_id')
    version = None
    if target_version_id:
        try:
            version = FormTemplateVersion.query.filter_by(id=int(target_version_id), template_id=template.id).first()
        except Exception as e:
            current_app.logger.debug("target_version_id parse failed: %s", e)
            version = None
    if not version and template.published_version_id:
        version = FormTemplateVersion.query.get(template.published_version_id)
    if not version:
        version = FormTemplateVersion.query.filter_by(template_id=template.id).order_by(FormTemplateVersion.created_at.desc()).first()

    # Initialize page choices if template is paginated (check version)
    if version and version.is_paginated:
        pages_for_version = FormPage.query.filter_by(template_id=template.id, version_id=version.id).all()
        form.page_id.choices = [(p.id, p.name) for p in pages_for_version]
    else:
        form.page_id.choices = [(None, 'No Pages')]

    if form.validate_on_submit():
        try:
            # Parent section is now explicit (no more decimal-based inference)
            parent_section_id = request.form.get('parent_section_id', type=int)
            parent_section = None
            if parent_section_id:
                parent_section = FormSection.query.filter_by(
                    template_id=template.id,
                    version_id=version.id,
                    id=parent_section_id
                ).first()
                if not parent_section:
                    flash("Invalid parent section selected.", "danger")
                    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version.id))
                # Prevent deeper nesting: only allow top-level sections to be parents
                if parent_section.parent_section_id is not None:
                    flash("Only top-level sections can be selected as a parent section.", "danger")
                    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version.id))

            # Whole-number ordering only (allow 0; only auto-fill when value is missing/empty)
            order_val = form.order.data
            order_missing = order_val is None or (isinstance(order_val, str) and str(order_val).strip() == '')
            if order_missing:
                if parent_section_id:
                    last_sibling = FormSection.query.filter_by(
                        template_id=template.id,
                        version_id=version.id,
                        parent_section_id=parent_section_id
                    ).order_by(FormSection.order.desc()).first()
                    order_val = (int(last_sibling.order) + 1) if last_sibling and last_sibling.order is not None else 1
                else:
                    last_top = FormSection.query.filter_by(
                        template_id=template.id,
                        version_id=version.id,
                        parent_section_id=None
                    ).order_by(FormSection.order.desc()).first()
                    order_val = (int(last_top.order) + 1) if last_top and last_top.order is not None else 1
            else:
                try:
                    order_val = int(float(order_val))
                except Exception as e:
                    current_app.logger.debug("order_val parse failed: %s", e)
                    order_val = 1

            # Get dynamic indicators fields from form object
            section_type = (form.section_type.data.lower() if form.section_type.data else 'standard')
            max_dynamic_indicators = form.max_dynamic_indicators.data
            add_indicator_note = form.add_indicator_note.data

            # Get max_entries for repeat groups
            max_entries = request.form.get('max_entries', type=int)

            current_app.logger.debug(f"Creating section with type: {section_type}, max_dynamic: {max_dynamic_indicators}, max_entries: {max_entries}")
            current_app.logger.debug(f"New section - form relevance_condition data: '{form.relevance_condition.data}'")
            current_app.logger.debug(f"New section - form data keys: {list(request.form.keys())}")

            # Page for paginated templates: subsections always inherit parent's page
            if parent_section_id and parent_section:
                page_id = parent_section.page_id  # subsection: always use parent's page (or None)
            elif version and version.is_paginated and form.page_id.data:
                page_id = form.page_id.data
            else:
                page_id = None

            new_section = FormSection(
                name=form.name.data,
                order=order_val,
                template_id=template_id,
                version_id=version.id,
                parent_section_id=parent_section_id,
                section_type=section_type,
                max_dynamic_indicators=max_dynamic_indicators,
                add_indicator_note=add_indicator_note,
                page_id=page_id,
                relevance_condition=form.relevance_condition.data
            )

            # Set max_entries in config for repeat groups
            if section_type == 'repeat' and max_entries is not None:
                new_section.set_max_entries(max_entries)
            elif section_type == 'repeat':
                # Initialize config as empty dict if not set
                if new_section.config is None:
                    new_section.config = {}

            # Handle name translations - ISO codes only
            if hasattr(form, 'name_translations') and form.name_translations.data:
                try:
                    name_translations = json.loads(form.name_translations.data)
                    supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
                    filtered_translations = {}
                    if isinstance(name_translations, dict):
                        for k, v in name_translations.items():
                            if not (isinstance(k, str) and isinstance(v, str) and v.strip()):
                                continue
                            code = k.strip().lower().split('_', 1)[0]
                            if code in supported_codes:
                                filtered_translations[code] = v.strip()
                    new_section.name_translations = filtered_translations if filtered_translations else None
                except (json.JSONDecodeError, TypeError) as e:
                    current_app.logger.error(f"Error parsing section name translations: {e}")

            db.session.add(new_section)
            _update_version_timestamp(version.id, current_user.id)
            db.session.flush()

            # Log admin action for audit trail
            try:
                log_admin_action(
                    action_type='form_section_create',
                    description=f"Created section '{new_section.name}' in template '{template.name}' (Type: {section_type})",
                    target_type='form_section',
                    target_id=new_section.id,
                    target_description=f"Template ID: {template_id}, Section ID: {new_section.id}, Version ID: {version.id}",
                    risk_level='low'
                )
            except Exception as log_error:
                current_app.logger.error(f"Error logging section creation: {log_error}")

            flash(f"Section '{new_section.name}' added to template.", "success")

        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")
            current_app.logger.error(f"Error adding section to template {template_id}: {e}", exc_info=True)

    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error in {field}: {error}", "danger")

    # Preserve version context after adding a section
    version_id = version.id if version is not None else request.form.get('version_id')
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_id))

@bp.route("/sections/edit/<int:section_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def edit_template_section(section_id):
    section = FormSection.query.get_or_404(section_id)
    template_id = section.template_id
    version_ctx = request.form.get('version_id') or section.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        return access_redirect

    try:
        section.name = request.form.get("section-name", section.name)

        # Parent section (explicit; no decimals). Keep nesting to one level only.
        parent_raw = request.form.get("parent_section_id")
        if parent_raw is not None:
            parent_raw = parent_raw.strip()
            if parent_raw == '':
                section.parent_section_id = None
            else:
                try:
                    new_parent_id = int(parent_raw)
                except Exception as e:
                    current_app.logger.debug("parent_section_id parse failed: %s", e)
                    flash("Invalid parent section selected.", "warning")
                    new_parent_id = None

                if new_parent_id:
                    if new_parent_id == section.id:
                        flash("A section cannot be its own parent.", "danger")
                        new_parent_id = None
                    else:
                        parent_section = FormSection.query.filter_by(
                            template_id=section.template_id,
                            version_id=section.version_id,
                            id=new_parent_id
                        ).first()
                        if not parent_section:
                            flash("Invalid parent section selected.", "danger")
                            new_parent_id = None
                        elif parent_section.parent_section_id is not None:
                            flash("Only top-level sections can be selected as a parent section.", "danger")
                            new_parent_id = None
                        else:
                            # Prevent cycles: disallow selecting a direct child as parent
                            direct_child = FormSection.query.filter_by(parent_section_id=section.id, id=new_parent_id).first()
                            if direct_child:
                                flash("Invalid parent selection (would create a cycle).", "danger")
                                new_parent_id = None

                section.parent_section_id = new_parent_id

        # Handle order
        order_str = request.form.get("section-order")
        if order_str:
            try:
                # Whole-number ordering only
                section.order = int(float(order_str))
            except ValueError:
                flash(f"Invalid order value: {order_str}", "warning")

        # Handle page_id for paginated templates: subsections always inherit parent's page
        version = section.version if section.version else (section.template.published_version if section.template.published_version else None)
        if version and version.is_paginated:
            if section.parent_section_id:
                parent = FormSection.query.get(section.parent_section_id)
                section.page_id = parent.page_id if parent else None  # subsection: always use parent's page
            else:
                page_id = request.form.get("section-page_id")
                section.page_id = int(page_id) if page_id and page_id != 'None' else None

        # Handle name translations - ISO codes only
        name_translations_str = request.form.get("name_translations")
        if name_translations_str:
            try:
                name_translations = json.loads(name_translations_str)
                supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
                filtered_translations = {}
                if isinstance(name_translations, dict):
                    for k, v in name_translations.items():
                        if not (isinstance(k, str) and isinstance(v, str) and v.strip()):
                            continue
                        code = k.strip().lower().split('_', 1)[0]
                        if code in supported_codes:
                            filtered_translations[code] = v.strip()
                section.name_translations = filtered_translations if filtered_translations else None
            except (json.JSONDecodeError, TypeError) as e:
                current_app.logger.error(f"Error parsing section name translations: {e}")

        # Handle section type and dynamic settings
        section_type = request.form.get("section-section_type", "standard")
        section.section_type = section_type.lower() if section_type else 'standard'

        # Handle max_entries for repeat groups
        if section_type.lower() == 'repeat':
            max_entries = request.form.get('max_entries', type=int)
            section.set_max_entries(max_entries)
        else:
            # Clear max_entries if section type is not repeat
            if section.config:
                section.config.pop('max_entries', None)

        # Handle relevance condition for section skip logic
        relevance_condition = request.form.get("relevance_condition")
        current_app.logger.debug(f"Edit section - form data keys: {list(request.form.keys())}")
        current_app.logger.debug(f"Edit section - relevance_condition value: '{relevance_condition}'")

        if relevance_condition and relevance_condition.strip():
            try:
                # Validate that it's valid JSON
                json.loads(relevance_condition)
                section.relevance_condition = relevance_condition
                current_app.logger.debug(f"Edit section - set relevance_condition to: {relevance_condition}")
            except (json.JSONDecodeError, TypeError) as e:
                current_app.logger.error(f"Error parsing section relevance condition: {e}")
                flash("Invalid relevance condition format. Skip logic not saved.", "warning")
                section.relevance_condition = None
        else:
            section.relevance_condition = None
            current_app.logger.debug("Edit section - cleared relevance_condition (empty or None)")

        _update_version_timestamp(section.version_id)
        db.session.flush()

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='form_section_update',
                description=f"Updated section '{section.name}' in template '{section.template.name}'",
                target_type='form_section',
                target_id=section_id,
                target_description=f"Template ID: {template_id}, Section ID: {section_id}, Version ID: {section.version_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging section update: {log_error}")

        # Always set server-side flash message for consistency with other routes
        flash(f"Section '{section.name}' updated successfully.", "success")

        # Always redirect to show flash message; preserve version context
        target_version_id = request.form.get('version_id') or section.version_id
        return redirect(url_for("form_builder.edit_template", template_id=section.template_id, version_id=target_version_id))

    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error updating section {section_id}: {e}", exc_info=True)



    # Preserve version context after section edit failure
    target_version_id = request.form.get('version_id') or section.version_id
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

def _get_descendant_section_ids(parent_section_id):
    """Return list of all descendant section IDs (children, grandchildren, ...) in leaf-first order for safe cascade delete."""
    descendants = []
    to_visit = [parent_section_id]
    while to_visit:
        pid = to_visit.pop()
        children = FormSection.query.filter_by(parent_section_id=pid).order_by(FormSection.id).all()
        for c in children:
            descendants.append(c.id)
            to_visit.append(c.id)
    # Reverse so we delete leaves first (children before their parents)
    return list(reversed(descendants))


def _delete_or_archive_one_section(sec, delete_data, keep_data_delete_section):
    """Delete or archive a single section and its item data. Used for cascade delete."""
    from app.models.forms import FormData, RepeatGroupData, RepeatGroupInstance, DynamicIndicatorData
    from app.models.form_items import FormItem

    items = FormItem.query.filter_by(section_id=sec.id).all()
    section_item_ids = [item.id for item in items]
    if delete_data:
        if section_item_ids:
            FormData.query.filter(FormData.form_item_id.in_(section_item_ids)).delete(synchronize_session=False)
            RepeatGroupData.query.filter(RepeatGroupData.form_item_id.in_(section_item_ids)).delete(synchronize_session=False)
        RepeatGroupInstance.query.filter_by(section_id=sec.id).delete(synchronize_session=False)
        DynamicIndicatorData.query.filter_by(section_id=sec.id).delete(synchronize_session=False)
        db.session.flush()
    if keep_data_delete_section:
        sec.archived = True
        db.session.add(sec)
        for item in items:
            item.archived = True
            db.session.add(item)
        db.session.flush()
    else:
        db.session.delete(sec)
        db.session.flush()


@bp.route("/sections/delete/<int:section_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def delete_template_section(section_id):
    from app.models.forms import FormData, RepeatGroupData, RepeatGroupInstance, DynamicIndicatorData
    from app.models.form_items import FormItem

    section = FormSection.query.get_or_404(section_id)
    template_id = section.template_id
    version_ctx = request.form.get('version_id') or section.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        return access_redirect

    # Check if user wants to delete data, keep data and delete section, or cancel
    delete_data_param = request.form.get('delete_data', 'true')
    delete_data = delete_data_param.lower() == 'true'
    keep_data_delete_section = delete_data_param.lower() == 'false-keep-data'

    # Cascade: delete or archive child sections first (user confirmed via frontend warning)
    descendant_ids = _get_descendant_section_ids(section.id)
    for desc_id in descendant_ids:
        desc_section = FormSection.query.get(desc_id)
        if desc_section:
            _delete_or_archive_one_section(desc_section, delete_data, keep_data_delete_section)

    try:
        version_id = section.version_id

        # Capture section and template names BEFORE any deletion/archival operations
        # to avoid SQLAlchemy session issues when accessing lazy-loaded relationships
        section_label = section.name
        template = FormTemplate.query.get(template_id)
        template_name = template.name if template else "Unknown Template"

        # Count existing data entries for this section
        data_count = 0
        # Count data from items in this section (include archived items for data counting)
        section_item_ids = [item.id for item in FormItem.query.filter_by(section_id=section.id).all()]
        if section_item_ids:
            data_count += FormData.query.filter(FormData.form_item_id.in_(section_item_ids)).count()
            data_count += RepeatGroupData.query.filter(RepeatGroupData.form_item_id.in_(section_item_ids)).count()
        # Count repeat group instances
        data_count += RepeatGroupInstance.query.filter_by(section_id=section.id).count()
        # Count dynamic indicator data
        data_count += DynamicIndicatorData.query.filter_by(section_id=section.id).count()

        # If user wants to keep data but not delete section (cancel), do nothing
        if data_count > 0 and not delete_data and not keep_data_delete_section:
            # This shouldn't happen as the frontend should handle cancel, but just in case
            target_version_id = request.form.get('version_id') or section.version_id
            return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

        # If delete_data is true and data exists, delete it first
        if delete_data and data_count > 0:
            # Delete data from items in this section
            if section_item_ids:
                FormData.query.filter(FormData.form_item_id.in_(section_item_ids)).delete(synchronize_session=False)
                RepeatGroupData.query.filter(RepeatGroupData.form_item_id.in_(section_item_ids)).delete(synchronize_session=False)
            # Delete repeat group instances (which will cascade to their data)
            RepeatGroupInstance.query.filter_by(section_id=section.id).delete(synchronize_session=False)
            # Delete dynamic indicator data
            DynamicIndicatorData.query.filter_by(section_id=section.id).delete(synchronize_session=False)
            db.session.flush()

        # If keep_data_delete_section is true, archive the section and its items instead of deleting
        # This preserves the FK relationships so data can remain
        if keep_data_delete_section:
            # Archive the section
            section.archived = True
            db.session.add(section)

            # Archive all items in this section
            section_items = FormItem.query.filter_by(section_id=section.id).all()
            for item in section_items:
                item.archived = True
                db.session.add(item)

            _update_version_timestamp(version_id)
            db.session.flush()

            # Log admin action for audit trail
            log_admin_action(
                action_type='form_section_delete',
                description=f"Archived section '{section_label}' from template '{template_name}' (data preserved)",
                target_type='form_section',
                target_id=section_id,
                target_description=f"Template ID: {template_id}, Section ID: {section_id}",
                risk_level='medium'
            )
            child_note = f" and {len(descendant_ids)} child section(s)" if descendant_ids else ""
            flash(f"Section '{section_label}'{child_note} archived (removed from template). {data_count} data entries preserved.", "success")
        else:
            # Actually delete the section (items will cascade delete due to relationship cascade)
            db.session.delete(section)
            _update_version_timestamp(version_id)

            try:
                db.session.flush()
            except Exception as fk_error:
                request_transaction_rollback()
                flash(f"Error deleting section '{section_label}'.", "danger")
                current_app.logger.error(f"Error deleting section {section_id}: {fk_error}", exc_info=True)
                target_version_id = request.form.get('version_id') or section.version_id
                return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

            # Log admin action for audit trail
            log_admin_action(
                action_type='form_section_delete',
                description=f"Deleted section '{section_label}' from template '{template_name}'" + (f" (and {data_count} data entries)" if delete_data and data_count > 0 else ""),
                target_type='form_section',
                target_id=section_id,
                target_description=f"Template ID: {template_id}, Section ID: {section_id}",
                risk_level='medium'
            )

            child_note = f" and {len(descendant_ids)} child section(s)" if descendant_ids else ""
            if delete_data and data_count > 0:
                flash(f"Section '{section_label}'{child_note} and {data_count} associated data entries deleted.", "success")
            else:
                flash(f"Section '{section_label}'{child_note} deleted.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error deleting section {section_id}: {e}", exc_info=True)

    # Preserve version context after deletion
    target_version_id = request.form.get('version_id') or section.version_id
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

@bp.route("/sections/duplicate/<int:section_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def duplicate_template_section(section_id):
    """Duplicate a form section including all its items and nested subsections."""
    section = FormSection.query.get_or_404(section_id)
    template_id = section.template_id
    version_id = section.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_id)
    if access_redirect:
        return access_redirect

    try:
        # Use the section duplication service
        new_section, section_id_map = SectionDuplicationService.duplicate_section(
            section_id=section_id,
            user_id=current_user.id
        )

        # Update version timestamp
        _update_version_timestamp(version_id, current_user.id)
        db.session.flush()

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='form_section_duplicate',
                description=f"Duplicated section '{section.name}' in template '{section.template.name}'",
                target_type='form_section',
                target_id=new_section.id,
                target_description=f"Source Section ID: {section_id}, New Section ID: {new_section.id}, Template ID: {template_id}, Version ID: {version_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging section duplication: {log_error}")

        flash(f"Section '{section.name}' duplicated as '{new_section.name}'.", "success")

    except ValueError as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error duplicating section {section_id}: {e}", exc_info=True)
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error duplicating section {section_id}: {e}", exc_info=True)

    # Preserve version context after duplication
    target_version_id = request.form.get('version_id') or version_id
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

@bp.route("/sections/unarchive/<int:section_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def unarchive_section(section_id):
    """Unarchive a form section so it appears in the form again"""
    section = FormSection.query.get_or_404(section_id)
    template_id = section.template_id
    version_id = section.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_id)
    if access_redirect:
        return access_redirect

    try:
        if not section.archived:
            flash("Section is not archived.", "warning")
            target_version_id = request.form.get('version_id') or version_id
            return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

        section_label = section.name
        template_name = section.template.name

        # Unarchive the section
        section.archived = False
        db.session.add(section)

        # Unarchive all items in this section
        from app.models.form_items import FormItem
        section_items = FormItem.query.filter_by(section_id=section.id).all()
        for item in section_items:
            item.archived = False
            db.session.add(item)

        _update_version_timestamp(version_id)
        db.session.flush()

        # Log admin action for audit trail
        log_admin_action(
            action_type='form_section_unarchive',
            description=f"Unarchived section '{section_label}' in template '{template_name}'",
            target_type='form_section',
            target_id=section_id,
            target_description=f"Template ID: {template_id}, Section ID: {section_id}",
            risk_level='low'
        )

        flash(f"Section '{section.name}' has been unarchived and is now visible in the form.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash_message = GENERIC_ERROR_MESSAGE
        flash(flash_message, "danger")
        current_app.logger.error(f"Error unarchiving section {section_id}: {e}", exc_info=True)

    target_version_id = request.form.get('version_id') or version_id
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

@bp.route("/sections/configure-dynamic/<int:section_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def configure_dynamic_section(section_id):
    """Configure settings for a dynamic indicators section."""
    section = FormSection.query.get_or_404(section_id)
    template_id = section.template_id
    version_ctx = request.form.get('version_id') or section.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        return access_redirect

    # Verify this is actually a dynamic indicators section
    if section.section_type != 'dynamic_indicators':
        flash('This section is not a dynamic indicators section.', 'warning')
        target_version_id = request.form.get('version_id') or section.version_id
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

    is_ajax = is_json_request()

    current_app.logger.debug(f"Configuring dynamic section {section_id} (ajax={is_ajax})")
    current_app.logger.debug(f"Form data: {request.form}")

    try:
        # Update max_dynamic_indicators
        max_dynamic_indicators = request.form.get('max_dynamic_indicators')
        if max_dynamic_indicators and max_dynamic_indicators.strip():
            try:
                section.max_dynamic_indicators = int(max_dynamic_indicators)
            except ValueError:
                section.max_dynamic_indicators = None
        else:
            section.max_dynamic_indicators = None

        # Update add_indicator_note
        add_indicator_note = request.form.get('add_indicator_note')
        if add_indicator_note and add_indicator_note.strip():
            section.add_indicator_note = add_indicator_note.strip()
        else:
            section.add_indicator_note = None

        # Update data availability options
        section.allow_data_not_available = request.form.get('allow_data_not_available') == '1'
        section.allow_not_applicable = request.form.get('allow_not_applicable') == '1'

        # Update allowed disaggregation options
        allowed_disagg_options = request.form.getlist('allowed_disaggregation_options')
        # Always save the selected options, even if empty
        section.set_allowed_disaggregation_options(allowed_disagg_options)

        # Update data entry display filters
        data_entry_display_filters = request.form.getlist('data_entry_display_filters')
        section.set_data_entry_display_filters(data_entry_display_filters)

        # Update indicator filters
        # Process the dynamic filter data from the form
        filters = []

        # Get all filter field names from the form
        filter_fields = request.form.getlist(f'filter_field_{section_id}[]')

        for i, field in enumerate(filter_fields):
            if field:  # Only process if a field is selected
                # Get the corresponding values for this filter
                values_key = f'filter_values_{section_id}_{i}[]'
                values = request.form.getlist(values_key)

                if values:  # Only add filter if it has values
                    filter_obj = {
                        'field': field,
                        'values': values
                    }

                    # Check for "primary_only" flag for sector/subsector fields
                    if field in ['sector', 'subsector']:
                        primary_only_key = f'filter_primary_only_{section_id}_{i}'
                        primary_only = request.form.get(primary_only_key) == '1'
                        if primary_only:
                            filter_obj['primary_only'] = True

                    filters.append(filter_obj)

        # Store the filters in the section using the model's setter method
        section.set_indicator_filters(filters if filters else None)

        # Keep backward compatibility - also handle allowed_sectors if provided
        allowed_sectors_list = request.form.getlist('allowed_sectors')
        if allowed_sectors_list:
            section.allowed_sectors = json.dumps(allowed_sectors_list)
        else:
            section.allowed_sectors = None

        _update_version_timestamp(section.version_id)
        db.session.flush()

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='form_section_configure',
                description=f"Configured dynamic section '{section.name}' in template '{section.template.name}' (Max indicators: {section.max_dynamic_indicators})",
                target_type='form_section',
                target_id=section_id,
                target_description=f"Template ID: {template_id}, Section ID: {section_id}, Version ID: {section.version_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging dynamic section configuration: {log_error}")

        # For XHR requests, do not store a server-side flash (it would appear later unexpectedly).
        if not is_ajax:
            flash(f"Dynamic section '{section.name}' configured successfully.", "success")
        else:
            return json_ok(
                section_id=section_id,
                template_id=template_id,
                version_id=request.form.get('version_id') or section.version_id,
                message=f"Dynamic section '{section.name}' saved.",
            )
    except Exception as e:
        request_transaction_rollback()
        if is_ajax:
            return json_server_error("An error occurred. Please try again.", success=False)
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error configuring dynamic section {section_id}: {e}", exc_info=True)

    # Preserve version context after configuring dynamic section
    target_version_id = request.form.get('version_id') or section.version_id
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))


@bp.route("/sections/configure-repeat/<int:section_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def configure_repeat_section(section_id):
    """Configure settings for a repeat group section."""
    section = FormSection.query.get_or_404(section_id)
    template_id = section.template_id
    version_ctx = request.form.get('version_id') or section.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        return access_redirect

    # Verify this is actually a repeat group section
    if section.section_type != 'repeat':
        flash('This section is not a repeat group section.', 'warning')
        target_version_id = request.form.get('version_id') or section.version_id
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

    current_app.logger.debug(f"Configuring repeat section {section_id}")
    current_app.logger.debug(f"Form data: {request.form}")

    try:
        # Update max_entries in config
        max_entries = request.form.get('max_entries')
        if max_entries and max_entries.strip():
            try:
                section.set_max_entries(int(max_entries))
            except ValueError:
                section.set_max_entries(None)
        else:
            section.set_max_entries(None)

        _update_version_timestamp(section.version_id)
        db.session.flush()

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='form_section_configure',
                description=f"Configured repeat section '{section.name}' in template '{section.template.name}' (Max entries: {section.max_entries})",
                target_type='form_section',
                target_id=section_id,
                target_description=f"Template ID: {template_id}, Section ID: {section_id}, Version ID: {section.version_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging repeat section configuration: {log_error}")

        # Always set server-side flash message for consistency with other routes
        flash(f"Repeat section '{section.name}' configured successfully.", "success")
    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error configuring repeat section {section_id}: {e}", exc_info=True)

    # Preserve version context after configuring repeat section
    target_version_id = request.form.get('version_id') or section.version_id
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

# === Form Item Management Routes ===
@bp.route("/templates/<int:template_id>/sections/<int:section_id>/items/new", methods=["POST"])
@permission_required('admin.templates.edit')
def new_section_item(template_id, section_id):
    """Unified route for creating new form items (indicators, questions, document fields, plugin items)"""
    is_ajax = is_json_request()
    template = FormTemplate.query.get_or_404(template_id)
    version_ctx = request.form.get('version_id')
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        if is_ajax:
            # Preserve redirect target so the frontend can handle it deterministically.
            try:
                loc = getattr(access_redirect, 'location', None) or None
            except Exception as e:
                current_app.logger.debug("getattr access_redirect.location failed: %s", e)
                loc = None
            return json_forbidden('Access denied', success=False, redirect_url=loc)
        return access_redirect
    section = FormSection.query.get_or_404(section_id)
    if section.template_id != template.id:
        flash("Section does not belong to the specified template.", "danger")
        target_version_id = version_ctx or section.version_id
        redirect_url = url_for("form_builder.edit_template", template_id=template.id, version_id=target_version_id)
        if is_ajax:
            return json_bad_request("Section does not belong to the specified template.", success=False, errors={'section_id': ["Invalid section for template"]}, redirect_url=redirect_url)
        return redirect(redirect_url)

    item_type = request.form.get('item_type')
    if not item_type:
        flash("Item type is required", "danger")
        target_version_id = request.form.get('version_id') or section.version_id
        redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
        if is_ajax:
            return json_bad_request("Item type is required", success=False, errors={'item_type': ["Item type is required"]}, redirect_url=redirect_url)
        return redirect(redirect_url)

    try:
        form_item = _create_form_item(template, section, request.form, item_type)
        if form_item:
            _update_version_timestamp(form_item.version_id, current_user.id)
            db.session.flush()
            # Log admin action for audit trail
            log_admin_action(
                action_type='form_item_create',
                description=f"Created new {item_type} in template '{template.name}'",
                target_type='form_item',
                target_id=form_item.id,
                target_description=f"Template ID: {template_id}, Item ID: {form_item.id}",
                risk_level='low'
            )

            # Always set server-side flash message for consistency with other routes
            flash_message = f"{item_type.title()} added successfully."
            flash(flash_message, "success")
            target_version_id = request.form.get('version_id') or section.version_id
            redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
            if is_ajax:
                return json_ok(message=flash_message, redirect_url=redirect_url)
        else:
            # Validation failed
            flash_message = f'Failed to create {item_type}. Please check your input.'
            flash(flash_message, "danger")
            target_version_id = request.form.get('version_id') or section.version_id
            redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
            if is_ajax:
                return json_bad_request(flash_message, success=False, errors={'__all__': [flash_message]}, redirect_url=redirect_url)

    except Exception as e:
        request_transaction_rollback()
        flash_message = GENERIC_ERROR_MESSAGE
        flash(flash_message, "danger")
        current_app.logger.error(f"Error adding {item_type} to section {section_id}: {e}", exc_info=True)
        target_version_id = request.form.get('version_id') or section.version_id
        redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
        if is_ajax:
            return json_server_error(flash_message, success=False, errors={'database': [flash_message]}, redirect_url=redirect_url)

    # Preserve version context after adding an item
    target_version_id = request.form.get('version_id') or section.version_id
    redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
    if is_ajax:
        # Fallback: if we reached here, treat as failure (defensive) so the frontend doesn't show Saved.
        return json_bad_request('Failed to create item', success=False, errors={'__all__': ['Failed to create item']}, redirect_url=redirect_url)
    return redirect(redirect_url)

@bp.route("/items/edit/<int:item_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def edit_item(item_id):
    """Unified route for editing form items (indicators, questions, document fields)"""
    is_ajax = is_json_request()
    form_item = FormItem.query.get_or_404(item_id)
    template_id = form_item.template_id
    version_ctx = request.form.get('version_id') or form_item.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        if is_ajax:
            try:
                loc = getattr(access_redirect, 'location', None) or None
            except Exception as e:
                current_app.logger.debug("getattr access_redirect.location failed: %s", e)
                loc = None
            return json_forbidden('Access denied', success=False, redirect_url=loc)
        return access_redirect

    # Prevent editing archived items (users should unarchive them first)
    if form_item.archived:
        msg = "Cannot edit archived items. Please unarchive the item first."
        if is_ajax:
            redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=version_ctx)
            return json_bad_request(msg, success=False, errors={'__all__': [msg]}, redirect_url=redirect_url)
        flash(msg, "warning")
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=version_ctx))

    # Debug logging (keep lightweight; request.form may include large payloads like config JSON)
    try:
        current_app.logger.debug(
            "edit_item called: item_id=%s item_type=%s keys=%s",
            item_id,
            getattr(form_item, 'item_type', None),
            list(request.form.keys())
        )
    except Exception as e:
        current_app.logger.debug("edit_item: debug log failed: %s", e)

    # Use submitted item_type so changing type in the modal (e.g. question -> indicator) is validated and saved
    submitted_item_type = (request.form.get('item_type') or '').strip() or form_item.item_type
    if submitted_item_type not in ('indicator', 'question', 'document_field', 'matrix') and not (submitted_item_type and submitted_item_type.startswith('plugin_')):
        submitted_item_type = form_item.item_type

    # Get the appropriate form class based on submitted item type (allows type change on edit)
    if submitted_item_type == 'indicator':
        from app.forms.form_builder import IndicatorForm
        form_class = IndicatorForm
        # Pass indicator bank choices with units for validation
        all_ib_objects = IndicatorBank.query.order_by(IndicatorBank.name).all()
        indicator_bank_choices_with_unit = []
        for ib in all_ib_objects:
            if ib and hasattr(ib, 'id') and hasattr(ib, 'name') and hasattr(ib, 'type'):
                indicator_bank_choices_with_unit.append({
                    'value': ib.id,
                    'label': f"{ib.name} (Type: {ib.type}, Unit: {ib.unit or 'N/A'})",
                    'unit': ib.unit if ib.unit else ''
                })
        form_kwargs = {'indicator_bank_choices_with_unit': indicator_bank_choices_with_unit}
    elif submitted_item_type == 'question':
        from app.forms.form_builder import QuestionForm
        form_class = QuestionForm
        form_kwargs = {}
    elif submitted_item_type == 'document_field':
        from app.forms.form_builder import DocumentFieldForm
        form_class = DocumentFieldForm
        form_kwargs = {}
    elif submitted_item_type == 'matrix':
        from app.forms.form_builder import MatrixForm
        form_class = MatrixForm
        form_kwargs = {}
    elif submitted_item_type and submitted_item_type.startswith('plugin_'):
        # Handle plugin item types
        from app.forms.form_builder import PluginItemForm  # Use PluginItemForm for plugin items
        form_class = PluginItemForm
        form_kwargs = {}
    else:
        flash(f"Unknown item type: {submitted_item_type or form_item.item_type}", "danger")
        target_version_id = request.form.get('version_id') or form_item.version_id
        return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

    # For edit mode, we're now receiving clean field names (no prefix) from the ItemModal
    # So we need to create a form without prefix and populate it manually
    form = form_class(obj=form_item, **form_kwargs)

    # Populate section choices limited to this version to prevent cross-version reassignment
    template_sections = FormSection.query.filter_by(template_id=template_id, version_id=form_item.version_id).order_by(FormSection.order).all()
    form.section_id.choices = [(s.id, s.name) for s in template_sections]

    # Manually populate form fields from request.form since we're not using prefixes anymore
    if 'section_id' in request.form and request.form['section_id']:
        try:
            form.section_id.data = int(request.form['section_id'])
        except (ValueError, TypeError):
            # If conversion fails, fall back to existing item's section_id
            form.section_id.data = form_item.section_id
    else:
        # If section_id is missing or empty, use the existing item's section_id as fallback
        form.section_id.data = form_item.section_id
    if 'order' in request.form:
        form.order.data = float(request.form['order']) if request.form['order'] else None
    # Checkboxes: when unchecked, browsers omit the key entirely.
    # For edit flows we must treat "missing" as False, otherwise users can't untick a box.
    if hasattr(form, 'is_required'):
        form.is_required.data = ('is_required' in request.form) and (request.form.get('is_required') in ['true', 'on', '1'])
        if 'is_required' in request.form:
            current_app.logger.debug(f"FLASH_DEBUG: Processing is_required: {request.form['is_required']} -> {form.is_required.data}")
    if 'layout_column_width' in request.form:
        # Convert to string since SelectField expects string values
        form.layout_column_width.data = str(request.form['layout_column_width']) if request.form['layout_column_width'] else '12'
    if hasattr(form, 'layout_break_after'):
        form.layout_break_after.data = ('layout_break_after' in request.form) and (request.form.get('layout_break_after') in ['true', 'on', '1'])
        if 'layout_break_after' in request.form:
            current_app.logger.debug(f"FLASH_DEBUG: Processing layout_break_after: {request.form['layout_break_after']} -> {form.layout_break_after.data}")
    if hasattr(form, 'allow_data_not_available'):
        form.allow_data_not_available.data = ('allow_data_not_available' in request.form) and (request.form.get('allow_data_not_available') in ['true', 'on', '1'])
    if hasattr(form, 'allow_not_applicable'):
        form.allow_not_applicable.data = ('allow_not_applicable' in request.form) and (request.form.get('allow_not_applicable') in ['true', 'on', '1'])
    if hasattr(form, 'indirect_reach'):
        form.indirect_reach.data = ('indirect_reach' in request.form) and (request.form.get('indirect_reach') in ['true', 'on', '1'])

    # Handle skip logic fields (common to all item types)
    if 'relevance_condition' in request.form and hasattr(form, 'relevance_condition'):
        form.relevance_condition.data = request.form['relevance_condition'] if request.form['relevance_condition'] != 'null' else None
    if 'validation_condition' in request.form and hasattr(form, 'validation_condition'):
        form.validation_condition.data = request.form['validation_condition'] if request.form['validation_condition'] != 'null' else None
    if 'validation_message' in request.form and hasattr(form, 'validation_message'):
        form.validation_message.data = request.form['validation_message'] if request.form['validation_message'] else None


    # Handle item-specific fields (use submitted_item_type so type change is populated correctly)
    if submitted_item_type == 'indicator':
        if 'label' in request.form and hasattr(form, 'label'):
            form.label.data = request.form['label']
        if 'definition' in request.form and hasattr(form, 'definition'):
            form.definition.data = request.form['definition'] or None
        if 'indicator_bank_id' in request.form:
            form.indicator_bank_id.data = int(request.form['indicator_bank_id']) if request.form['indicator_bank_id'] else None
        if 'allowed_disaggregation_options' in request.form:
            # Handle multiple values for disaggregation options
            disagg_options = request.form.getlist('allowed_disaggregation_options')
            form.allowed_disaggregation_options.data = disagg_options if disagg_options else ["total"]
        if 'age_groups_config' in request.form:
            form.age_groups_config.data = request.form['age_groups_config'] if request.form['age_groups_config'] else None
    elif submitted_item_type == 'question':
        if 'question_type' in request.form and request.form['question_type']:
            form.question_type.data = request.form['question_type']
    elif submitted_item_type == 'matrix':
        # Handle matrix-specific fields
        if 'label' in request.form:
            form.label.data = request.form['label']
        if 'description' in request.form:
            # Use the last non-empty value when multiple 'description' fields are present
            try:
                descriptions = request.form.getlist('description')
                last_non_empty_desc = next((v for v in reversed(descriptions) if str(v).strip()), '') if descriptions else ''
                form.description.data = last_non_empty_desc
            except Exception as e:
                current_app.logger.debug("description getlist fallback failed: %s", e)
                form.description.data = request.form.get('description', '')
        # Website sends 'config'; map it to MatrixForm.matrix_config
        if 'config' in request.form:
            form.matrix_config.data = request.form['config']
        elif 'matrix_config' in request.form:
            form.matrix_config.data = request.form['matrix_config']
        # Note: checkbox fields are handled in the common checkbox parsing above
        # (missing => False), so do not re-parse them here.

    if form.validate_on_submit():
        current_app.logger.info(f"Edit {form_item.item_type.title()} Form validated. Processed form data: {form.data}")

        try:
            # Update common fields
            form_item.section_id = form.section_id.data
            form_item.order = form.order.data if form.order.data is not None else form_item.order

            # If user changed item type in the modal, update it before applying type-specific updates
            if submitted_item_type != form_item.item_type:
                form_item.item_type = submitted_item_type
                # Clear type-specific fields when converting so old type's data is not left behind
                if submitted_item_type == 'indicator':
                    form_item.definition = None
                    form_item.options_json = None
                    form_item.options_translations = None
                    form_item.lookup_list_id = None
                    form_item.list_display_column = None
                    form_item.list_filters_json = None
                elif submitted_item_type == 'question':
                    form_item.indicator_bank_id = None
                    form_item.type = None
                    form_item.unit = None
                    form_item.label_translations = None
                    form_item.definition_translations = None

            # Update item-specific fields based on submitted type
            if submitted_item_type == 'indicator':
                _update_indicator_fields(form_item, form, request.form)
            elif submitted_item_type == 'question':
                _update_question_fields(form_item, form, request.form)
            elif submitted_item_type == 'document_field':
                _update_document_field_fields(form_item, form, request.form)
            elif submitted_item_type == 'matrix':
                _update_matrix_fields(form_item, form, request.form)
            elif submitted_item_type and submitted_item_type.startswith('plugin_'):
                _update_plugin_fields(form_item, form, request.form)

            # Update common config fields
            _update_item_config(form_item, form, request.form)

            # Handle conditions (common to all item types)
            # Note: Some skip-logic fields may not be bound on the WTForm instance; read from request.form
            rel_json = request.form.get('relevance_condition')
            val_json = request.form.get('validation_condition')
            val_msg = request.form.get('validation_message')

            form_item.relevance_condition = rel_json if is_conditions_meaningful(rel_json) else None
            form_item.validation_condition = val_json if is_conditions_meaningful(val_json) else None
            form_item.validation_message = val_msg if val_msg else None

            # Force SQLAlchemy to recognize the config field as modified
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(form_item, 'config')

            _update_version_timestamp(form_item.version_id, current_user.id)
            db.session.flush()

            item_label = form_item.label or f"{form_item.item_type.title()} {item_id}"

            # Log admin action for audit trail
            log_admin_action(
                action_type='form_item_update',
                description=f"Updated form item '{item_label}' in template '{form_item.template.name}'",
                target_type='form_item',
                target_id=item_id,
                target_description=f"Template ID: {template_id}, Item ID: {item_id}",
                risk_level='low'
            )

            # Always set server-side flash message for consistency with other routes
            flash_message = f"{form_item.item_type.title()} '{item_label}' updated successfully."
            target_version_id = request.form.get('version_id') or form_item.version_id
            redirect_url = url_for("form_builder.edit_template", template_id=form_item.template_id, version_id=target_version_id)
            if is_ajax:
                return json_ok(message=flash_message, redirect_url=redirect_url)
            flash(flash_message, "success")
            return redirect(redirect_url)

        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error(f"Error during DB commit for editing {form_item.item_type} {item_id}: {e}", exc_info=True)
            return json_server_error(GENERIC_ERROR_MESSAGE, success=False, errors={'database': [GENERIC_ERROR_MESSAGE]})
    else:
        # Return JSON response with validation errors
        current_app.logger.error(f"Form validation failed for Edit {form_item.item_type.title()} (ID: {item_id}). Errors: {form.errors}")
        return json_form_errors(form, 'Validation failed')

@bp.route("/items/delete/<int:item_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def delete_item(item_id):
    """Unified route for deleting form items (indicators, questions, document fields)"""
    is_ajax = is_json_request()
    from app.models.forms import FormData, RepeatGroupData
    from app.models import SubmittedDocument

    form_item = FormItem.query.get_or_404(item_id)
    template_id = form_item.template_id
    version_ctx = request.form.get('version_id') or form_item.version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        if is_ajax:
            try:
                loc = getattr(access_redirect, 'location', None) or None
            except Exception as e:
                current_app.logger.debug("getattr access_redirect.location failed: %s", e)
                loc = None
            return json_forbidden('Access denied', success=False, redirect_url=loc)
        return access_redirect

    # Check if user wants to delete data, keep data and delete item, or cancel
    delete_data_param = request.form.get('delete_data', 'true')
    delete_data = delete_data_param.lower() == 'true'
    keep_data_delete_item = delete_data_param.lower() == 'false-keep-data'

    try:
        item_type = form_item.item_type.title()
        item_label = form_item.label or f"{item_type} {item_id}"
        template_name = form_item.template.name
        version_id = form_item.version_id

        # Count existing data entries
        data_count = 0
        data_count += FormData.query.filter_by(form_item_id=form_item.id).count()
        data_count += RepeatGroupData.query.filter_by(form_item_id=form_item.id).count()
        if form_item.item_type == 'document_field':
            data_count += SubmittedDocument.query.filter_by(form_item_id=form_item.id).count()

        # If user wants to keep data but not delete item (cancel), do nothing
        if data_count > 0 and not delete_data and not keep_data_delete_item:
            # This shouldn't happen as the frontend should handle cancel, but just in case
            target_version_id = request.form.get('version_id') or form_item.version_id
            redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
            if is_ajax:
                return json_ok(message='Cancelled', redirect_url=redirect_url)
            return redirect(redirect_url)

        # If delete_data is true and data exists, delete it first
        if delete_data and data_count > 0:
            FormData.query.filter_by(form_item_id=form_item.id).delete(synchronize_session=False)
            RepeatGroupData.query.filter_by(form_item_id=form_item.id).delete(synchronize_session=False)
            if form_item.item_type == 'document_field':
                SubmittedDocument.query.filter_by(form_item_id=form_item.id).delete(synchronize_session=False)
            db.session.flush()
        # If keep_data_delete_item is true, archive the item instead of deleting it
        # This preserves the FK relationship so data can remain
        if keep_data_delete_item:
            form_item.archived = True
            db.session.add(form_item)
            _update_version_timestamp(version_id)
            db.session.flush()
        else:
            # Actually delete the item
            db.session.delete(form_item)
            _update_version_timestamp(version_id)
            db.session.flush()

        # Log admin action for audit trail
        if keep_data_delete_item:
            action_desc = f"Archived {item_type.lower()} '{item_label}' from template '{template_name}' (data preserved)"
        else:
            action_desc = f"Deleted {item_type.lower()} '{item_label}' from template '{template_name}'" + (f" (and {data_count} data entries)" if delete_data and data_count > 0 else "")

        log_admin_action(
            action_type='form_item_delete',
            description=action_desc,
            target_type='form_item',
            target_id=item_id,
            target_description=f"Template ID: {template_id}, Item ID: {item_id}",
            risk_level='medium'
        )

        if delete_data and data_count > 0:
            flash_message = f"{item_type} '{item_label}' and {data_count} associated data entries deleted successfully."
        elif keep_data_delete_item and data_count > 0:
            flash_message = f"{item_type} '{item_label}' archived (removed from template). {data_count} data entries preserved."
        else:
            flash_message = f"{item_type} '{item_label}' deleted successfully."
        flash(flash_message, "success")
    except Exception as e:
        request_transaction_rollback()
        flash_message = f"Error deleting {form_item.item_type}."
        flash(flash_message, "danger")
        current_app.logger.error(f"Error deleting {form_item.item_type} {item_id}: {e}", exc_info=True)
        target_version_id = request.form.get('version_id') or form_item.version_id
        redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
        if is_ajax:
            return json_server_error(flash_message, success=False, errors={'database': [flash_message]}, redirect_url=redirect_url)

    # Preserve version context after deleting an item
    target_version_id = request.form.get('version_id') or form_item.version_id
    redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
    if is_ajax:
        return json_ok(message=flash_message, redirect_url=redirect_url)
    return redirect(redirect_url)

@bp.route("/items/duplicate/<int:item_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def duplicate_item(item_id):
    """Duplicate a form item including all its properties."""
    is_ajax = is_json_request()
    form_item = FormItem.query.get_or_404(item_id)
    template_id = form_item.template_id
    version_id = form_item.version_id
    version_ctx = request.form.get('version_id') or version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        if is_ajax:
            try:
                loc = getattr(access_redirect, 'location', None) or None
            except Exception as e:
                current_app.logger.debug("getattr access_redirect.location failed: %s", e)
                loc = None
            return json_forbidden('Access denied', success=False, redirect_url=loc)
        return access_redirect

    try:
        # Use the item duplication service
        new_item = ItemDuplicationService.duplicate_item(
            item_id=item_id,
            user_id=current_user.id
        )

        # Update version timestamp
        _update_version_timestamp(version_id, current_user.id)
        db.session.flush()

        # Log admin action for audit trail
        try:
            item_type = form_item.item_type.title()
            item_label = form_item.label or f"{item_type} {item_id}"
            log_admin_action(
                action_type='form_item_duplicate',
                description=f"Duplicated {item_type.lower()} '{item_label}' in template '{form_item.template.name}'",
                target_type='form_item',
                target_id=new_item.id,
                target_description=f"Source Item ID: {item_id}, New Item ID: {new_item.id}, Template ID: {template_id}, Version ID: {version_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging item duplication: {log_error}")

        item_type = form_item.item_type.title()
        item_label = form_item.label or f"{item_type} {item_id}"
        flash(f"{item_type} '{item_label}' duplicated as '{new_item.label}'.", "success")
        flash_message = f"{item_type} '{item_label}' duplicated as '{new_item.label}'."

    except ValueError as e:
        request_transaction_rollback()
        flash_message = "An error occurred. Please try again."
        flash(flash_message, "danger")
        current_app.logger.error(f"Error duplicating item {item_id}: {e}", exc_info=True)
        if is_ajax:
            target_version_id = request.form.get('version_id') or version_id
            redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
            return json_bad_request(flash_message, success=False, errors={'__all__': [flash_message]}, redirect_url=redirect_url)
    except Exception as e:
        request_transaction_rollback()
        flash_message = "An error occurred. Please try again."
        flash(flash_message, "danger")
        current_app.logger.error(f"Error duplicating item {item_id}: {e}", exc_info=True)
        if is_ajax:
            target_version_id = request.form.get('version_id') or version_id
            redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
            return json_server_error(flash_message, success=False, errors={'database': [flash_message]}, redirect_url=redirect_url)

    # Preserve version context after duplication
    target_version_id = request.form.get('version_id') or version_id
    redirect_url = url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id)
    if is_ajax:
        return json_ok(message=flash_message or 'Item duplicated', redirect_url=redirect_url)
    return redirect(redirect_url)

@bp.route("/items/unarchive/<int:item_id>", methods=["POST"])
@permission_required('admin.templates.edit')
def unarchive_item(item_id):
    """Unarchive a form item so it appears in the form again. Also unarchives parent section if needed."""
    form_item = FormItem.query.get_or_404(item_id)
    template_id = form_item.template_id
    version_id = form_item.version_id
    version_ctx = request.form.get('version_id') or version_id
    access_redirect = _ensure_template_access_or_redirect(template_id, version_ctx)
    if access_redirect:
        return access_redirect

    try:
        if not form_item.archived:
            flash("Item is not archived.", "warning")
            target_version_id = request.form.get('version_id') or version_id
            return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

        item_type = form_item.item_type.title()
        item_label = form_item.label or f"{item_type} {item_id}"
        template_name = form_item.template.name

        # Unarchive the item
        form_item.archived = False
        db.session.add(form_item)

        # Check if the item's section is archived and unarchive it if so
        section = FormSection.query.get(form_item.section_id)
        section_unarchived = False
        if section and section.archived:
            section.archived = False
            db.session.add(section)
            section_unarchived = True

            # Log section unarchive action
            log_admin_action(
                action_type='form_section_unarchive',
                description=f"Auto-unarchived section '{section.name}' in template '{template_name}' (item unarchived)",
                target_type='form_section',
                target_id=section.id,
                target_description=f"Template ID: {template_id}, Section ID: {section.id}",
                risk_level='low'
            )

            # Also check if there's a parent section and unarchive it if needed
            if section.parent_section_id:
                parent_section = FormSection.query.get(section.parent_section_id)
                if parent_section and parent_section.archived:
                    parent_section.archived = False
                    db.session.add(parent_section)

                    # Log parent section unarchive action
                    log_admin_action(
                        action_type='form_section_unarchive',
                        description=f"Auto-unarchived parent section '{parent_section.name}' in template '{template_name}' (child section unarchived)",
                        target_type='form_section',
                        target_id=parent_section.id,
                        target_description=f"Template ID: {template_id}, Section ID: {parent_section.id}",
                        risk_level='low'
                    )

        _update_version_timestamp(version_id)
        db.session.flush()

        # Log admin action for audit trail
        log_admin_action(
            action_type='form_item_unarchive',
            description=f"Unarchived {item_type.lower()} '{item_label}' in template '{template_name}'",
            target_type='form_item',
            target_id=item_id,
            target_description=f"Template ID: {template_id}, Item ID: {item_id}",
            risk_level='low'
        )

        # Prepare flash message
        flash_msg = f"{item_type} '{item_label}' has been unarchived and is now visible in the form."
        if section_unarchived:
            flash_msg += f" The section '{section.name}' has also been unarchived."
        flash(flash_msg, "success")
    except Exception as e:
        request_transaction_rollback()
        flash_message = GENERIC_ERROR_MESSAGE
        flash(flash_message, "danger")
        current_app.logger.error(f"Error unarchiving {form_item.item_type} {item_id}: {e}", exc_info=True)

    target_version_id = request.form.get('version_id') or version_id
    return redirect(url_for("form_builder.edit_template", template_id=template_id, version_id=target_version_id))

# === Versioning actions ===
@bp.route("/templates/<int:template_id>/deploy", methods=["POST"])
@permission_required('admin.templates.publish')
def deploy_template_version(template_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version called for template_id={template_id}, user_id={current_user.id}")
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    try:
        # Determine target version to deploy: prefer explicit version_id from form, fallback to draft
        target_version_id = request.form.get('version_id')
        current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - target_version_id from form: {target_version_id}")
        version = None
        if target_version_id:
            try:
                version = FormTemplateVersion.query.filter_by(id=int(target_version_id), template_id=template.id).first()
                current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - found version by explicit ID: {version.id if version else None}")
            except Exception as e:
                current_app.logger.debug("deploy version_id parse failed: %s", e)
                version = None
        if not version:
            version = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first()
            current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - found draft version: {version.id if version else None}")
        if not version:
            current_app.logger.warning(f"VERSIONING_DEBUG: deploy_template_version - no target version found for template_id={template_id}")
            flash('No target version specified and no draft version found to deploy.', 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id))

        # Block deploy if this version has indicator items missing valid IndicatorBank reference
        invalid_indicator_items = (
            FormItem.query
            .filter_by(template_id=template.id, version_id=version.id, item_type='indicator')
            .filter(FormItem.indicator_bank_id.is_(None))
            .count()
        )
        if invalid_indicator_items and invalid_indicator_items > 0:
            flash(
                f"Cannot deploy this version: {invalid_indicator_items} indicator item(s) have missing/invalid indicator references. "
                f"Open the form builder, fix the items marked with an issue, then try deploying again.",
                "danger",
            )
            return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=version.id))

        # Archive previous published if exists and different
        if template.published_version_id and template.published_version_id != version.id:
            prev = FormTemplateVersion.query.get(template.published_version_id)
            if prev and prev.status == 'published':
                current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - archiving previous published version {prev.id}")
                prev.status = 'archived'
                prev.updated_at = utcnow()

        # Publish target version
        current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - publishing version {version.id}, previous published_version_id={template.published_version_id}")
        version.status = 'published'
        version.updated_at = utcnow()
        template.published_version_id = version.id

        db.session.flush()

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='template_version_deploy',
                description=f"Deployed version {version.version_number if hasattr(version, 'version_number') else version.id} for template '{template.name}'",
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, Version ID: {version.id}",
                risk_level='medium'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging version deployment: {log_error}")

        # Send notifications to users with active assignments for this template
        try:
            from app.utils.notifications import notify_template_updated
            notify_template_updated(template)
        except Exception as e:
            current_app.logger.error(f"Error sending template updated notification: {e}", exc_info=True)
            # Don't fail the deployment if notification fails

        current_app.logger.info(f"VERSIONING_DEBUG: deploy_template_version - successfully deployed version {version.id} for template {template_id}")
        flash('Version deployed successfully.', 'success')
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error deploying version for template {template_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")

    return redirect(url_for("form_builder.edit_template", template_id=template.id))


@bp.route("/templates/<int:template_id>/discard_draft", methods=["POST"])
@permission_required('admin.templates.edit')
def discard_template_draft(template_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft called for template_id={template_id}, user_id={current_user.id}")
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    try:
        draft = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first()
        if not draft:
            current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft - no draft version found for template_id={template_id}")
            flash('No draft version to discard.', 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id))

        current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft - deleting draft version {draft.id} and associated rows")

        # Delete rows in this version
        items_deleted = FormItem.query.filter_by(template_id=template.id, version_id=draft.id).delete(synchronize_session=False)
        sections_deleted = FormSection.query.filter_by(template_id=template.id, version_id=draft.id).delete(synchronize_session=False)
        pages_deleted = FormPage.query.filter_by(template_id=template.id, version_id=draft.id).delete(synchronize_session=False)
        current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft - deleted {items_deleted} items, {sections_deleted} sections, {pages_deleted} pages")

        # Delete version record
        db.session.delete(draft)
        db.session.flush()
        current_app.logger.info(f"VERSIONING_DEBUG: discard_template_draft - successfully discarded draft version {draft.id} for template {template_id}")

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='template_version_discard',
                description=f"Discarded draft version {draft.version_number if hasattr(draft, 'version_number') else draft.id} for template '{template.name}' (items={items_deleted}, sections={sections_deleted}, pages={pages_deleted})",
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, Version ID: {draft.id}",
                risk_level='medium'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging version discard: {log_error}")

        flash('Draft discarded.', 'success')
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error discarding draft for template {template_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")

    return redirect(url_for("form_builder.edit_template", template_id=template.id))


@bp.route("/templates/<int:template_id>/versions/<int:version_id>/delete", methods=["POST"])
@permission_required('admin.templates.delete')
def delete_template_version(template_id, version_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: delete_template_version called for template_id={template_id}, version_id={version_id}, user_id={current_user.id}")
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: delete_template_version - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    try:
        version = FormTemplateVersion.query.filter_by(id=version_id, template_id=template.id).first_or_404()
        current_app.logger.debug(f"VERSIONING_DEBUG: delete_template_version - found version {version_id} with status={version.status}")

        if template.published_version_id == version.id:
            current_app.logger.warning(f"VERSIONING_DEBUG: delete_template_version - attempt to delete published version {version_id}")
            flash('Cannot delete the published version. Deploy another version first.', 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id))

        current_app.logger.debug(f"VERSIONING_DEBUG: delete_template_version - deleting version {version_id} and associated rows")

        # Guard: block deletion if dependent data exists for items/sections in this version
        from app.models import FormItem, FormSection, FormData, RepeatGroupData, RepeatGroupInstance, DynamicIndicatorData
        # Items/sections scoped to this version
        item_ids_subq = select(FormItem.id).filter_by(template_id=template.id, version_id=version.id).scalar_subquery()
        section_ids_subq = select(FormSection.id).filter_by(template_id=template.id, version_id=version.id).scalar_subquery()

        data_counts = 0
        try:
            data_counts += db.session.query(func.count(FormData.id)).filter(FormData.form_item_id.in_(item_ids_subq)).scalar() or 0
            data_counts += db.session.query(func.count(RepeatGroupData.id)).filter(RepeatGroupData.form_item_id.in_(item_ids_subq)).scalar() or 0
            data_counts += db.session.query(func.count(RepeatGroupInstance.id)).filter(RepeatGroupInstance.section_id.in_(section_ids_subq)).scalar() or 0
            data_counts += db.session.query(func.count(DynamicIndicatorData.id)).filter(DynamicIndicatorData.section_id.in_(section_ids_subq)).scalar() or 0
        except Exception as _e:
            current_app.logger.error(f"VERSIONING_DEBUG: delete_template_version - error counting dependent data: {_e}")
            data_counts = None

        if data_counts and data_counts > 0:
            current_app.logger.warning(
                f"VERSIONING_DEBUG: delete_template_version - aborting delete; dependent data rows found: {data_counts}"
            )
            flash('Cannot delete this version because data exists for its items/sections. Remove data or archive the version.', 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id))

        # Delete version-scoped rows
        items_deleted = FormItem.query.filter_by(template_id=template.id, version_id=version.id).delete(synchronize_session=False)
        sections_deleted = FormSection.query.filter_by(template_id=template.id, version_id=version.id).delete(synchronize_session=False)
        pages_deleted = FormPage.query.filter_by(template_id=template.id, version_id=version.id).delete(synchronize_session=False)
        current_app.logger.debug(f"VERSIONING_DEBUG: delete_template_version - deleted {items_deleted} items, {sections_deleted} sections, {pages_deleted} pages")

        # Break inheritance links from other versions pointing to this one
        dependent_versions = FormTemplateVersion.query.filter_by(template_id=template.id, based_on_version_id=version.id).all()
        if dependent_versions:
            current_app.logger.debug(
                f"VERSIONING_DEBUG: delete_template_version - clearing based_on_version_id for {len(dependent_versions)} dependent versions: "
                f"{[v.id for v in dependent_versions]}"
            )
            for dep in dependent_versions:
                dep.based_on_version_id = None

        db.session.delete(version)
        db.session.flush()
        current_app.logger.info(f"VERSIONING_DEBUG: delete_template_version - successfully deleted version {version_id} for template {template_id}")

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='template_version_delete',
                description=f"Deleted version {version.version_number if hasattr(version, 'version_number') else version_id} for template '{template.name}' (items={items_deleted}, sections={sections_deleted})",
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, Version ID: {version_id}",
                risk_level='medium'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging version deletion: {log_error}")

        flash('Version deleted.', 'success')
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error deleting version {version_id} for template {template_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")

    return redirect(url_for("form_builder.edit_template", template_id=template.id))

@bp.route("/templates/<int:template_id>/draft_comment", methods=["POST"])
@permission_required('admin.templates.edit')
def update_draft_comment(template_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: update_draft_comment called for template_id={template_id}, user_id={current_user.id}")
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: update_draft_comment - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    try:
        draft = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first()
        if not draft:
            current_app.logger.debug(f"VERSIONING_DEBUG: update_draft_comment - no draft version found for template_id={template_id}")
            flash('No draft version to update.', 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id))

        new_comment = request.form.get('comment') or None
        current_app.logger.debug(f"VERSIONING_DEBUG: update_draft_comment - updating draft {draft.id} comment from '{draft.comment}' to '{new_comment}'")
        draft.comment = new_comment
        draft.updated_at = utcnow()
        db.session.flush()
        current_app.logger.info(f"VERSIONING_DEBUG: update_draft_comment - successfully updated comment for draft {draft.id}")

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='template_version_comment',
                description=f"Updated comment for draft version {draft.version_number if hasattr(draft, 'version_number') else draft.id} of template '{template.name}'",
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, Version ID: {draft.id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging draft comment update: {log_error}")

        flash('Draft note saved.', 'success')
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error saving draft note for template {template_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
    return redirect(url_for("form_builder.edit_template", template_id=template.id))


@bp.route("/templates/<int:template_id>/versions/new", methods=["POST"])
@permission_required('admin.templates.edit')
def create_draft_version(template_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: create_draft_version called for template_id={template_id}, user_id={current_user.id}")
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: create_draft_version - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))
    try:
        # Get source version ID from form data, or use published version as default
        source_version_id = request.form.get('source_version_id', type=int)
        source_version = None

        if source_version_id:
            source_version = FormTemplateVersion.query.filter_by(id=source_version_id, template_id=template.id).first()
            if not source_version:
                current_app.logger.warning(f"VERSIONING_DEBUG: create_draft_version - specified source_version_id {source_version_id} not found")
                flash('Source version not found.', 'warning')
                return redirect(url_for("form_builder.edit_template", template_id=template.id))

        # If no source version specified, use published version
        if not source_version:
            if template.published_version_id:
                source_version = FormTemplateVersion.query.filter_by(id=template.published_version_id).first()
            else:
                # Find any version as fallback
                source_version = FormTemplateVersion.query.filter_by(template_id=template.id).order_by(FormTemplateVersion.created_at.desc()).first()

            if not source_version:
                current_app.logger.warning(f"VERSIONING_DEBUG: create_draft_version - no version found to clone from for template_id={template_id}")
                flash('No version found to clone from.', 'warning')
                return redirect(url_for("form_builder.edit_template", template_id=template.id))

        # Get the next version number for this template
        max_version = db.session.query(func.max(FormTemplateVersion.version_number)).filter_by(template_id=template.id).scalar()
        next_version_number = (max_version + 1) if max_version else 1

        # Create new draft version based on source version
        current_app.logger.debug(f"VERSIONING_DEBUG: create_draft_version - creating new draft from version {source_version.id}, version_number={next_version_number}")
        now = utcnow()
        draft = FormTemplateVersion(
            template_id=template.id,
            version_number=next_version_number,
            status='draft',
            based_on_version_id=source_version.id,
            created_by=current_user.id,
            updated_by=current_user.id,
            comment=None,
            created_at=now,
            updated_at=now,
            name=source_version.name,  # Copy version-specific name
            name_translations=source_version.name_translations.copy() if source_version.name_translations else None,  # Copy translations
            description_translations=source_version.description_translations.copy() if source_version.description_translations else None  # Copy description translations
        )
        db.session.add(draft)
        db.session.flush()

        # Clone structure from source version
        _clone_template_structure(template.id, source_version.id, draft.id)
        db.session.flush()

        current_app.logger.info(f"VERSIONING_DEBUG: create_draft_version - successfully created draft version {draft.id} for template {template_id} based on version {source_version.id}")

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='template_version_create',
                description=f"Created new draft version {draft.version_number} for template '{template.name}' based on version {source_version.version_number if hasattr(source_version, 'version_number') else source_version.id}",
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, New Version ID: {draft.id}, Source Version ID: {source_version.id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging version creation: {log_error}")

        flash('New version created.', 'success')
        return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=draft.id))
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error creating draft for template {template_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template.id))

@bp.route("/templates/<int:template_id>/versions/<int:version_id>/comment", methods=["POST"])
@permission_required('admin.templates.edit')
def update_version_comment(template_id, version_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: update_version_comment called for template_id={template_id}, version_id={version_id}, user_id={current_user.id}")
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: update_version_comment - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))
    try:
        version = FormTemplateVersion.query.filter_by(id=version_id, template_id=template.id).first_or_404()
        new_comment = request.form.get('comment') or None
        current_app.logger.debug(f"VERSIONING_DEBUG: update_version_comment - updating version {version_id} comment from '{version.comment}' to '{new_comment}'")
        version.comment = new_comment
        version.updated_at = utcnow()
        version.updated_by = current_user.id
        db.session.flush()
        current_app.logger.info(f"VERSIONING_DEBUG: update_version_comment - successfully updated comment for version {version_id}")

        # Log admin action for audit trail
        try:
            log_admin_action(
                action_type='template_version_comment',
                description=f"Updated comment for version {version.version_number if hasattr(version, 'version_number') else version_id} of template '{template.name}'",
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, Version ID: {version_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging version comment update: {log_error}")

        flash('Version note saved.', 'success')
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error saving version note for template {template_id}, version {version_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
    return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=version_id))

# === Helper Functions ===

def _update_version_timestamp(version_id, user_id=None):
    """Update the updated_at timestamp and updated_by for a version when its contents change."""
    if version_id:
        version = FormTemplateVersion.query.get(version_id)
        if version:
            version.updated_at = utcnow()
            if user_id:
                version.updated_by = user_id
            elif current_user and current_user.is_authenticated:
                version.updated_by = current_user.id

def _create_form_item(template, section, form_data, item_type):
    """Unified function for creating form items (indicators, questions, document fields)"""
    # Get the last order for proper sequencing (exclude archived items)
    last_item = FormItem.query.filter_by(section_id=section.id, archived=False).order_by(FormItem.order.desc()).first()
    order = (last_item.order + 1) if last_item else 1

    if item_type == 'indicator':
        return _create_indicator_form_item(template, section, form_data, order)
    elif item_type == 'question':
        return _create_question_form_item(template, section, form_data, order)
    elif item_type == 'document_field':
        return _create_document_field_form_item(template, section, form_data, order)
    elif item_type == 'matrix':
        return _create_matrix_form_item(template, section, form_data, order)
    elif item_type.startswith('plugin_'):
        return _create_plugin_form_item(template, section, form_data, item_type, order)
    else:
        flash(f"Unknown item type: {item_type}", "danger")
        return None

def _update_indicator_fields(indicator, form, request_form):
    """Update indicator-specific fields"""
    # Handle indicator bank change
    if indicator.indicator_bank_id != form.indicator_bank_id.data:
        new_bank_indicator = IndicatorBank.query.get(form.indicator_bank_id.data)
        if new_bank_indicator:
            indicator.label = new_bank_indicator.name
            indicator.type = new_bank_indicator.type
            indicator.unit = new_bank_indicator.unit
            indicator.indicator_bank_id = new_bank_indicator.id

    # Optional overrides: label and definition
    # If custom label is provided and not empty, use it; if empty, revert to indicator bank name
    with suppress(Exception):
        label_val = None

        # Prefer a dedicated indicator override field (sent by the item modal) to avoid ambiguity
        # when multiple inputs share the name `label` (e.g. plugin UI remnants).
        if 'indicator_label_override' in request_form:
            label_val = (request_form.get('indicator_label_override') or '').strip()
        elif 'label' in request_form:
            labels = request_form.getlist('label') if hasattr(request_form, 'getlist') else [request_form.get('label')]
            label_val = next((str(v) for v in reversed(labels) if v is not None), '')
            label_val = label_val.strip() if label_val else ''

        # Only apply when we actually received an override payload.
        if label_val is not None:
            if label_val:
                # Custom label provided
                indicator.label = label_val
            else:
                # Empty custom label - revert to indicator bank name
                if indicator.indicator_bank:
                    indicator.label = indicator.indicator_bank.name

    with suppress(Exception):
        if 'definition' in request_form:
            defs = request_form.getlist('definition') if hasattr(request_form, 'getlist') else [request_form.get('definition')]
            def_val = next((str(v) for v in reversed(defs) if v is not None), '')
            def_val = def_val.strip() if def_val else ''

            if def_val:
                # Custom definition provided
                indicator.definition = def_val
            else:
                # Empty custom definition - keep None so UI/data entry can fall back to bank definition
                indicator.definition = None

    # Translations for label/definition
    # Clear translations if the JSON is empty or contains no valid translations
    with suppress(Exception):
        if 'label_translations' in request_form:
            import json as _json
            lt_raw = request_form['label_translations']
            if lt_raw and lt_raw.strip():
                lt = _json.loads(lt_raw)
                supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
                filtered_translations = {}
                if isinstance(lt, dict):
                    for k, v in lt.items():
                        if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                            continue
                        code = k.strip().lower().split('_', 1)[0]
                        if code in supported_codes:
                            filtered_translations[code] = str(v).strip()
                indicator.label_translations = filtered_translations or None
            else:
                # Empty JSON - clear translations
                indicator.label_translations = None

    with suppress(Exception):
        if 'definition_translations' in request_form:
            import json as _json
            dt_raw = request_form['definition_translations']
            if dt_raw and dt_raw.strip():
                dt = _json.loads(dt_raw)
                supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
                filtered_translations = {}
                if isinstance(dt, dict):
                    for k, v in dt.items():
                        if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                            continue
                        code = k.strip().lower().split('_', 1)[0]
                        if code in supported_codes:
                            filtered_translations[code] = str(v).strip()
                indicator.definition_translations = filtered_translations or None
            else:
                # Empty JSON - clear translations
                indicator.definition_translations = None

    # Handle disaggregation options - get directly from request.form (no prefix needed now)
    allowed_options = request_form.getlist('allowed_disaggregation_options')
    if not allowed_options:
        # Fallback to form data if getlist doesn't work
        allowed_options = form.allowed_disaggregation_options.data

    age_config = form.age_groups_config.data if form.age_groups_config.data and form.age_groups_config.data.strip() else None

    # Check if the unit and type support disaggregation
    from app.utils.indicator_utils import supports_disaggregation
    current_bank_indicator = IndicatorBank.query.get(indicator.indicator_bank_id)
    allows_disaggregation_by_unit = current_bank_indicator and supports_disaggregation(current_bank_indicator.unit, current_bank_indicator.type)

    # Initialize config if it's None
    if indicator.config is None:
        indicator.config = {
            'is_required': False,
            'layout_column_width': 12,
            'layout_break_after': False,
            'allowed_disaggregation_options': ["total"],
            'age_groups_config': None,
            'allow_data_not_available': False,
            'allow_not_applicable': False,
            'indirect_reach': False,
            'default_value': None
        }

    # Default value (optional): can be a literal or a template variable like [var_name]
    with suppress(Exception):
        dv_raw = (request_form.get('default_value') or '').strip()
        if dv_raw:
            indicator.config['default_value'] = dv_raw
        else:
            # Treat empty as "no default"
            if isinstance(indicator.config, dict) and 'default_value' in indicator.config:
                indicator.config['default_value'] = None

    # If the unit does not allow disaggregation, force to total and clear age config
    if not allows_disaggregation_by_unit:
        indicator.config['allowed_disaggregation_options'] = ["total"]
        indicator.config['age_groups_config'] = None
    else:
        # If unit allows disaggregation, save the selected options and age config
        indicator.config['allowed_disaggregation_options'] = allowed_options if allowed_options else ["total"]
        indicator.config['age_groups_config'] = age_config

def _update_question_fields(question, form, request_form):
    """Update question-specific fields"""
    question.definition = form.definition.data

    # For blank/note questions, allow empty label; for others, provide default
    question_label = form.label.data
    if not question_label and form.question_type.data != 'blank':
        question_label = 'Question'  # Only provide default for non-blank questions
    question.label = question_label or ''  # Allow empty label for blank questions

    # Handle question type and unit
    question.type = form.question_type.data
    question.unit = form.unit.data if hasattr(form, 'unit') else None

    # Helper to read possibly-prefixed fields
    field_prefix = f"{form.prefix}-" if getattr(form, 'prefix', None) else ''
    def _fp(name, default=None):
        return request_form.get(f"{field_prefix}{name}", default)

    # Handle manual options vs calculated lists for choice types
    try:
        options_source = _fp('options_source', 'manual')
    except Exception as e:
        current_app.logger.debug("options_source parse failed: %s", e)
        options_source = 'manual'
    is_choice_type = question.type in ['single_choice', 'multiple_choice']

    if is_choice_type and options_source == 'calculated':
        # Calculated list selected – override options_json and populate list fields
        lookup_list_id_raw = _fp('lookup_list_id')

        # Handle plugin lookup lists (including emergency_operations)
        if lookup_list_id_raw and not lookup_list_id_raw.isdigit():
            # This is a plugin lookup list (non-numeric ID)
            question.lookup_list_id = lookup_list_id_raw
            # Display column: provided or default to 'name'
            display_column = _fp('list_display_column')
            if not display_column:
                display_column = 'name'  # Default to first column
            question.list_display_column = display_column
        else:
            # Regular lookup list from database
            lookup_list_id_int = None
            try:
                if lookup_list_id_raw:
                    lookup_list_id_int = int(lookup_list_id_raw)
            except ValueError:
                lookup_list_id_int = None

            lookup_obj = LookupList.query.get(lookup_list_id_int) if lookup_list_id_int else None
            question.lookup_list_id = lookup_list_id_int if lookup_obj else None
            # Display column: provided or default to first column
            display_column = _fp('list_display_column')
            if not display_column and lookup_obj and getattr(lookup_obj, 'columns_config', None):
                try:
                    display_column = lookup_obj.columns_config[0]['name'] if lookup_obj.columns_config else None
                except Exception as e:
                    current_app.logger.debug("columns_config display_column failed: %s", e)
                    display_column = None
            question.list_display_column = display_column

        # Filters JSON
        filters_json_raw = _fp('list_filters_json')
        try:
            question.list_filters_json = json.loads(filters_json_raw) if filters_json_raw else None
        except (json.JSONDecodeError, TypeError):
            question.list_filters_json = None

        # Ensure manual options are cleared when using calculated lists
        question.options_json = None
    else:
        # Manual options (or non-choice type): persist options_json, clear list refs
        options_value = form.options_json.data if hasattr(form, 'options_json') else None
        if options_value and options_value.strip():
            try:
                parsed_options = json.loads(options_value)
            except json.JSONDecodeError:
                parsed_options = None
            question.options_json = parsed_options if isinstance(parsed_options, list) else None
        else:
            question.options_json = None
        # Clear calculated list fields when using manual options or non-choice types
        question.lookup_list_id = None
        question.list_display_column = None
        question.list_filters_json = None

    # Handle translations (label, definition, options) - ISO codes only
    label_translations_raw = _fp('label_translations')
    if label_translations_raw:
        try:
            lt = json.loads(label_translations_raw)
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            filtered_translations = {}
            if isinstance(lt, dict):
                for k, v in lt.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        filtered_translations[code] = str(v).strip()
            question.label_translations = filtered_translations if filtered_translations else None
        except (json.JSONDecodeError, AttributeError, TypeError):
            current_app.logger.warning('Invalid label_translations JSON; skipping')

    definition_translations_raw = _fp('definition_translations')
    if definition_translations_raw:
        try:
            dt = json.loads(definition_translations_raw)
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            filtered_translations = {}
            if isinstance(dt, dict):
                for k, v in dt.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        filtered_translations[code] = str(v).strip()
            question.definition_translations = filtered_translations if filtered_translations else None
        except (json.JSONDecodeError, AttributeError, TypeError):
            current_app.logger.warning('Invalid definition_translations JSON; skipping')

    options_translations_raw = _fp('options_translations_json')
    if options_translations_raw:
        try:
            ot = json.loads(options_translations_raw)
            # Only save if it's a non-empty list
            question.options_translations = ot if isinstance(ot, list) and ot else None
        except (json.JSONDecodeError, TypeError):
            current_app.logger.warning('Invalid options_translations JSON; skipping')

def _update_document_field_fields(document_field, form, request_form):
    """Update document field-specific fields"""
    document_field.label = form.label.data
    document_field.description = form.description.data

    # Update max_documents in config
    if document_field.config is None:
        document_field.config = {}

    # Get max_documents value from form or request
    max_docs_value = None
    if hasattr(form, 'max_documents') and form.max_documents.data:
        max_docs_value = form.max_documents.data
    elif 'max_documents' in request_form:
        try:
            max_docs_str = request_form.get('max_documents')
            if max_docs_str and max_docs_str.strip():
                max_docs_value = int(max_docs_str)
        except (ValueError, TypeError):
            max_docs_value = None

    # Save to config (None means unlimited)
    document_field.config['max_documents'] = max_docs_value

    # Optional: document type
    doc_type_value = None
    # Prefer WTForms field if present
    if hasattr(form, 'document_type') and getattr(form, 'document_type').data:
        try:
            doc_type_value = str(getattr(form, 'document_type').data).strip()
        except Exception as e:
            current_app.logger.debug("document_type form field parse failed: %s", e)
            doc_type_value = None
    elif 'document_type' in request_form:
        try:
            val = request_form.get('document_type')
            doc_type_value = str(val).strip() if val is not None else None
        except Exception as e:
            current_app.logger.debug("document_type request form parse failed: %s", e)
            doc_type_value = None

    # Normalize empty string to None; store under config.document_type
    document_field.config['document_type'] = doc_type_value or None

    # Save display options for upload modal
    document_field.config['show_language'] = request_form.get('show_language') in ['true', 'on', '1', True]
    document_field.config['show_document_type'] = request_form.get('show_document_type') in ['true', 'on', '1', True]
    document_field.config['show_year'] = request_form.get('show_year') in ['true', 'on', '1', True]
    document_field.config['show_public_checkbox'] = request_form.get('show_public_checkbox') in ['true', 'on', '1', True]

    # Save allowed period types
    document_field.config['allow_single_year'] = request_form.get('allow_single_year') in ['true', 'on', '1', True]
    document_field.config['allow_year_range'] = request_form.get('allow_year_range') in ['true', 'on', '1', True]
    document_field.config['allow_month_range'] = request_form.get('allow_month_range') in ['true', 'on', '1', True]

def _update_matrix_fields(matrix_item, form, request_form):
    """Update matrix-specific fields"""
    matrix_item.label = form.label.data
    matrix_item.description = form.description.data

    # Handle matrix configuration
    if hasattr(form, 'matrix_config') and form.matrix_config.data:
        try:
            import json
            matrix_config = json.loads(form.matrix_config.data)

            # Normalize/filter column header translations (name_translations) to supported language codes only
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            supported_codes = [str(c).split('_', 1)[0].lower() for c in (supported_codes or []) if c]

            def _normalize_translation_map(raw_map):
                if not isinstance(raw_map, dict):
                    return None
                cleaned = {}
                for k, v in raw_map.items():
                    if not (isinstance(k, str) and (isinstance(v, str) or v is not None)):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code not in supported_codes:
                        continue
                    text = str(v).strip()
                    if not text:
                        continue
                    cleaned[code] = text
                return cleaned or None

            if isinstance(matrix_config, dict) and isinstance(matrix_config.get('columns'), list):
                for col in matrix_config['columns']:
                    if not isinstance(col, dict):
                        continue
                    if 'name_translations' in col:
                        normalized = _normalize_translation_map(col.get('name_translations'))
                        if normalized:
                            col['name_translations'] = normalized
                        else:
                            # Drop empty/invalid translation maps to keep config compact
                            col.pop('name_translations', None)

            # Ensure the existing config structure is preserved
            if matrix_item.config is None:
                matrix_item.config = {}

            # Handle list library configuration for advanced matrix mode
            if matrix_config.get('row_mode') == 'list_library':
                # Set list library fields
                if 'lookup_list_id' in matrix_config:
                    matrix_item.lookup_list_id = matrix_config['lookup_list_id']
                if 'list_display_column' in matrix_config:
                    matrix_item.list_display_column = matrix_config['list_display_column']
                if 'list_filters' in matrix_config:
                    matrix_item.list_filters_json = json.dumps(matrix_config['list_filters'])
            else:
                # Clear list library fields for manual mode
                matrix_item.lookup_list_id = None
                matrix_item.list_display_column = None
                matrix_item.list_filters_json = None

            # Update only the matrix_config part while preserving other config fields
            matrix_item.config['matrix_config'] = matrix_config

        except (json.JSONDecodeError, TypeError):
            current_app.logger.warning(f"Invalid matrix config JSON: {form.matrix_config.data}")
            # Don't overwrite the entire config, just log the error

    # Handle translations (ISO codes only)
    # MatrixForm may not define translation fields; read directly from request
    if 'label_translations' in request_form and request_form['label_translations']:
        try:
            import json
            parsed_translations = json.loads(request_form['label_translations'])
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            filtered_translations = {}
            if isinstance(parsed_translations, dict):
                for k, v in parsed_translations.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        filtered_translations[code] = str(v).strip()
            matrix_item.label_translations = filtered_translations if filtered_translations else None
        except (json.JSONDecodeError, TypeError):
            current_app.logger.warning(f"Invalid label translations JSON: {request_form['label_translations']}")
            matrix_item.label_translations = None

    if 'description_translations' in request_form and request_form['description_translations']:
        try:
            import json
            parsed_translations = json.loads(request_form['description_translations'])
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            filtered_translations = {}
            if isinstance(parsed_translations, dict):
                for k, v in parsed_translations.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        filtered_translations[code] = str(v).strip()
            matrix_item.description_translations = filtered_translations if filtered_translations else None
        except (json.JSONDecodeError, TypeError):
            current_app.logger.warning(f"Invalid description translations JSON: {request_form['description_translations']}")
            matrix_item.description_translations = None

    # Handle additional configuration fields
    if hasattr(form, 'allow_data_not_available') and hasattr(form.allow_data_not_available, 'data'):
        matrix_item.allow_data_not_available = form.allow_data_not_available.data
    if hasattr(form, 'allow_not_applicable') and hasattr(form.allow_not_applicable, 'data'):
        matrix_item.allow_not_applicable = form.allow_not_applicable.data
    if hasattr(form, 'indirect_reach') and hasattr(form.indirect_reach, 'data'):
        matrix_item.indirect_reach = form.indirect_reach.data

def _update_item_config(form_item, form, request_form):
    """Update common configuration fields for all item types"""
    if form_item.config is None:
        form_item.config = {}

    # Update config fields
    form_item.config['is_required'] = form.is_required.data if hasattr(form, 'is_required') and hasattr(form.is_required, 'data') else False

    # Handle layout_column_width - get from form data directly if form field fails
    layout_width = '12'  # default (string since SelectField expects string values)
    if hasattr(form, 'layout_column_width') and hasattr(form.layout_column_width, 'data') and form.layout_column_width.data:
        layout_width = str(form.layout_column_width.data)
    else:
        # Fallback: try to get from request form directly (no prefix needed now)
        layout_width_raw = request_form.get('layout_column_width')
        if layout_width_raw:
            layout_width = str(layout_width_raw)
        # If no fallback value found, layout_width remains '12' (default)

    form_item.config['layout_column_width'] = layout_width
    form_item.config['layout_break_after'] = form.layout_break_after.data if hasattr(form, 'layout_break_after') and hasattr(form.layout_break_after, 'data') else False
    form_item.config['allow_data_not_available'] = form.allow_data_not_available.data if hasattr(form, 'allow_data_not_available') and hasattr(form.allow_data_not_available, 'data') else False
    form_item.config['allow_not_applicable'] = form.allow_not_applicable.data if hasattr(form, 'allow_not_applicable') and hasattr(form.allow_not_applicable, 'data') else False
    form_item.config['indirect_reach'] = form.indirect_reach.data if hasattr(form, 'indirect_reach') and hasattr(form.indirect_reach, 'data') else False

    # Allow over 100% for percentage items
    # Check direct field first, then fall back to config JSON if present
    allow_over_100 = False
    if 'allow_over_100' in request_form:
        allow_over_100 = request_form.get('allow_over_100') in ['true', 'on', '1']
    elif request_form.get('config'):
        try:
            config_json = json.loads(request_form.get('config'))
            allow_over_100 = config_json.get('allow_over_100', False)
        except (json.JSONDecodeError, TypeError):
            allow_over_100 = False
    form_item.config['allow_over_100'] = bool(allow_over_100)

    # Privacy (dropdown, defaults to organization network / internal visibility)
    try:
        if hasattr(form, 'privacy') and hasattr(form.privacy, 'data') and form.privacy.data:
            _pv = str(form.privacy.data).strip().lower()
        else:
            _pv = (request_form.get('privacy') or '').strip().lower()
        form_item.config['privacy'] = _pv if _pv in ['public', 'ifrc_network'] else 'ifrc_network'
    except Exception as e:
        current_app.logger.debug("form_item privacy parse failed: %s", e)
        form_item.config['privacy'] = 'ifrc_network'

def _update_plugin_fields(plugin_item, form, request_form):
    """Update plugin-specific fields"""
    try:
        # Update basic fields
        if hasattr(form, 'label') and hasattr(form.label, 'data') and form.label.data:
            plugin_item.label = form.label.data

        if hasattr(form, 'description') and hasattr(form.description, 'data') and form.description.data:
            plugin_item.description = form.description.data

        # Update plugin configuration
        if plugin_item.config is None:
            plugin_item.config = {}

        # Update common config fields
        plugin_item.config['is_required'] = form.is_required.data if hasattr(form, 'is_required') and hasattr(form.is_required, 'data') else False

        layout_width = 12
        if hasattr(form, 'layout_column_width') and hasattr(form.layout_column_width, 'data') and form.layout_column_width.data:
            layout_width = int(form.layout_column_width.data)
        elif 'layout_column_width' in request_form:
            layout_width = int(request_form.get('layout_column_width', '12'))

        plugin_item.config['layout_column_width'] = layout_width
        plugin_item.config['layout_break_after'] = form.layout_break_after.data if hasattr(form, 'layout_break_after') and hasattr(form.layout_break_after, 'data') else False
        plugin_item.config['allow_data_not_available'] = form.allow_data_not_available.data if hasattr(form, 'allow_data_not_available') and hasattr(form.allow_data_not_available, 'data') else False
        plugin_item.config['allow_not_applicable'] = form.allow_not_applicable.data if hasattr(form, 'allow_not_applicable') and hasattr(form.allow_not_applicable, 'data') else False
        plugin_item.config['indirect_reach'] = form.indirect_reach.data if hasattr(form, 'indirect_reach') and hasattr(form.indirect_reach, 'data') else False

        # Allow over 100% for percentage items
        # Check direct field first, then fall back to config JSON if present
        allow_over_100 = False
        if 'allow_over_100' in request_form:
            allow_over_100 = request_form.get('allow_over_100') in ['true', 'on', '1']
        elif request_form.get('config'):
            try:
                config_json = json.loads(request_form.get('config'))
                allow_over_100 = config_json.get('allow_over_100', False)
            except (json.JSONDecodeError, TypeError):
                allow_over_100 = False
        plugin_item.config['allow_over_100'] = bool(allow_over_100)

        # Privacy for plugin items (edit path)
        try:
            if hasattr(form, 'privacy') and hasattr(form.privacy, 'data') and form.privacy.data:
                _pv = str(form.privacy.data).strip().lower()
            else:
                _pv = (request_form.get('privacy') or '').strip().lower()
            plugin_item.config['privacy'] = _pv if _pv in ['public', 'ifrc_network'] else 'ifrc_network'
        except Exception as e:
            current_app.logger.debug("privacy field parse failed: %s", e)
            plugin_item.config['privacy'] = 'ifrc_network'

        # Update plugin-specific configuration if available
        if 'plugin_config' in request_form:
            try:
                plugin_config = json.loads(request_form['plugin_config'])
                plugin_item.config['plugin_config'] = plugin_config
            except (json.JSONDecodeError, TypeError):
                current_app.logger.warning(f"Invalid plugin config JSON for {plugin_item.item_type}")

        current_app.logger.info(f"Updated plugin fields for {plugin_item.item_type}")

    except Exception as e:
        current_app.logger.error(f"Error updating plugin fields for {plugin_item.item_type}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "warning")

# Utility function to check if conditions are meaningful (not empty)
def is_conditions_meaningful(conditions_json):
    """
    Check if conditions JSON contains meaningful conditions.
    Returns False if conditions is empty, None, or contains empty conditions array.
    """
    if not conditions_json:
        return False

    try:
        conditions_data = json.loads(conditions_json) if isinstance(conditions_json, str) else conditions_json
        if not isinstance(conditions_data, dict):
            return False

        conditions_array = conditions_data.get('conditions', [])
        if not isinstance(conditions_array, list) or len(conditions_array) == 0:
            return False

        return True
    except (json.JSONDecodeError, TypeError, AttributeError):
        return False

def _get_or_create_draft_version(template: FormTemplate, user_id: int) -> FormTemplateVersion:
    """Return existing draft version for template or create one.

    Behavior:
    - Brand-new templates (no versions and no rows): create a single draft (v1) and return it.
    - Legacy templates (rows exist with NULL version_id): create a published baseline, stamp rows,
      then create a draft cloned from published and return it.
    - Otherwise: if a draft exists, return it; if not, create a draft from the published version.
    """
    current_app.logger.debug(f"VERSIONING_DEBUG: _get_or_create_draft_version called for template_id={template.id}, user_id={user_id}")
    draft = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first()
    if draft:
        current_app.logger.debug(f"VERSIONING_DEBUG: _get_or_create_draft_version - existing draft version {draft.id} found, returning it")
        return draft

    # Detect brand-new template state: no versions and no structural rows
    total_versions_for_template = FormTemplateVersion.query.filter_by(template_id=template.id).count()
    if total_versions_for_template == 0:
        pages_without_version = FormPage.query.filter_by(template_id=template.id, version_id=None).count()
        sections_without_version = FormSection.query.filter_by(template_id=template.id, version_id=None).count()
        items_without_version = FormItem.query.filter_by(template_id=template.id, version_id=None).count()

        if pages_without_version == 0 and sections_without_version == 0 and items_without_version == 0:
            # Brand-new template: create only a draft version (v1)
            now = utcnow()
            draft = FormTemplateVersion(
                template_id=template.id,
                version_number=1,
                status='draft',
                based_on_version_id=None,
                created_by=user_id,
                updated_by=user_id,
                comment=None,
                created_at=now,
                updated_at=now,
                name="Unnamed Template",  # Default name for new template
                name_translations=None,
                description=None,  # Default for new template
                add_to_self_report=False,  # Default for new template
                display_order_visible=False,  # Default for new template
                is_paginated=False,  # Default for new template
                enable_export_pdf=False,  # Default for new template
                enable_export_excel=False,  # Default for new template
                enable_import_excel=False,  # Default for new template
                enable_ai_validation=False  # Default for new template
            )
            db.session.add(draft)
            db.session.flush()
            current_app.logger.info(f"VERSIONING_DEBUG: _get_or_create_draft_version - created initial draft version {draft.id} for new template {template.id}")
            return draft

    # Ensure there is a published version (backfill migration should have created it)
    published = None
    if template.published_version_id:
        published = FormTemplateVersion.query.get(template.published_version_id)
        current_app.logger.debug(f"VERSIONING_DEBUG: _get_or_create_draft_version - found published version {published.id if published else None}")
    if not published:
        # As a safety net, create a published version and stamp current rows
        current_app.logger.warning(f"VERSIONING_DEBUG: _get_or_create_draft_version - no published version found, auto-creating one for template_id={template.id}")
        # Get the next version number for this template
        max_version = db.session.query(func.max(FormTemplateVersion.version_number)).filter_by(template_id=template.id).scalar()
        next_version_number = (max_version + 1) if max_version else 1

        now = utcnow()
        # Get name from first version if exists, otherwise use default
        first_version = template.versions.order_by('created_at').first()
        version_name = first_version.name if first_version and first_version.name else "Unnamed Template"
        version_translations = first_version.name_translations.copy() if first_version and first_version.name_translations else None
        version_desc_translations = first_version.description_translations.copy() if first_version and first_version.description_translations else None

        published = FormTemplateVersion(
            template_id=template.id,
            version_number=next_version_number,
            status='published',
            comment='Auto-created published baseline',
            created_by=user_id,
            updated_by=user_id,
            created_at=now,
            updated_at=now,
            name=version_name,
            name_translations=version_translations,
            description_translations=version_desc_translations
        )
        db.session.add(published)
        db.session.flush()
        # Stamp any rows missing version_id
        pages_updated = FormPage.query.filter_by(template_id=template.id, version_id=None).update({'version_id': published.id})
        sections_updated = FormSection.query.filter_by(template_id=template.id, version_id=None).update({'version_id': published.id})
        items_updated = FormItem.query.filter_by(template_id=template.id, version_id=None).update({'version_id': published.id})
        current_app.logger.debug(f"VERSIONING_DEBUG: _get_or_create_draft_version - auto-created published version {published.id}, stamped {pages_updated} pages, {sections_updated} sections, {items_updated} items")
        template.published_version_id = published.id
        db.session.flush()

    # Get the next version number for this template
    max_version = db.session.query(func.max(FormTemplateVersion.version_number)).filter_by(template_id=template.id).scalar()
    next_version_number = (max_version + 1) if max_version else 1

    # Create a new draft based on published and clone structure
    current_app.logger.debug(f"VERSIONING_DEBUG: _get_or_create_draft_version - creating new draft version based on published version {published.id}, version_number={next_version_number}")
    now = utcnow()
    draft = FormTemplateVersion(
        template_id=template.id,
        version_number=next_version_number,
        status='draft',
        based_on_version_id=published.id,
        created_by=user_id,
        updated_by=user_id,
        comment=None,
        created_at=now,
        updated_at=now,
        name=published.name,
        name_translations=published.name_translations.copy() if published.name_translations else None,
        description=published.description,
        description_translations=published.description_translations.copy() if published.description_translations else None,
        add_to_self_report=published.add_to_self_report,
        display_order_visible=published.display_order_visible,
        is_paginated=published.is_paginated,
        enable_export_pdf=published.enable_export_pdf,
        enable_export_excel=published.enable_export_excel,
        enable_import_excel=published.enable_import_excel,
        enable_ai_validation=published.enable_ai_validation
    )
    db.session.add(draft)
    db.session.flush()
    current_app.logger.debug(f"VERSIONING_DEBUG: _get_or_create_draft_version - cloning structure from version {published.id} to draft {draft.id}")
    _clone_template_structure(template.id, published.id, draft.id)
    db.session.flush()
    current_app.logger.info(f"VERSIONING_DEBUG: _get_or_create_draft_version - successfully created draft version {draft.id} for template {template.id}")
    return draft

def _deep_copy_json_value(value):
    """Best-effort deep copy for JSON-serializable values."""
    if value is None:
        return None
    try:
        return json.loads(json.dumps(value))
    except Exception as e:
        current_app.logger.debug("_deep_copy_json_value json roundtrip failed: %s", e)
        try:
            import copy as _copy
            return _copy.deepcopy(value)
        except Exception as e:
            current_app.logger.debug("_deep_copy_json_value fallback: %s", e)
            if isinstance(value, dict):
                return value.copy()
            if isinstance(value, list):
                return value.copy()
            return value


def _parse_rule_payload(rule_payload):
    """Parse a stored rule payload; supports double-encoded JSON strings."""
    if rule_payload is None:
        return None
    if isinstance(rule_payload, (dict, list)):
        return _deep_copy_json_value(rule_payload)
    if not isinstance(rule_payload, str):
        return None
    s = rule_payload.strip()
    if not s or s in ("{}", "null"):
        return None
    try:
        parsed = json.loads(s)
    except Exception as e:
        current_app.logger.debug("_parse_rule_payload json.loads failed: %s", e)
        return None
    if isinstance(parsed, str):
        # Some historical rows were double-encoded: "\"{...}\""
        try:
            parsed2 = json.loads(parsed)
            return parsed2
        except Exception as e:
            current_app.logger.debug("_parse_rule_payload double-encoded parse failed: %s", e)
            return None
    return parsed


def _remap_item_ref(raw_ref, id_map):
    """Remap a rule/reference item id using an old->new FormItem.id map.

    Stored rule builder formats seen in production:
    - Standard items: "66" (numeric string)
    - Plugin items/measures: "plugin_123" or "plugin_123_measure_name"
    - Legacy prefixed forms: "question_66", "indicator_66", "document_field_66"
    """
    if raw_ref is None:
        return None
    # Keep rule engine happy: item_id is expected to behave like a string in JS.
    if isinstance(raw_ref, int):
        old = raw_ref
        return str(id_map.get(old, old))
    if not isinstance(raw_ref, str):
        return raw_ref

    ref = raw_ref.strip()
    if not ref:
        return raw_ref

    # Numeric-only id
    if ref.isdigit():
        old = int(ref)
        return str(id_map.get(old, old))

    # Plugin field / plugin measure reference
    m = re.match(r'^(plugin_)(\d+)(_.*)?$', ref)
    if m:
        old = int(m.group(2))
        suffix = m.group(3) or ''
        if old in id_map:
            return f"plugin_{id_map[old]}{suffix}"
        return ref

    # Legacy prefixed ids that should resolve to numeric ids at runtime
    m = re.match(r'^(question_|indicator_|document_field_|matrix_|form_item_)(\d+)$', ref)
    if m:
        old = int(m.group(2))
        return str(id_map.get(old, old))

    return raw_ref


def _remap_ids_in_obj(obj, id_map):
    """Recursively remap known id fields inside a condition/list-filter structure."""
    if isinstance(obj, list):
        for i in range(len(obj)):
            obj[i] = _remap_ids_in_obj(obj[i], id_map)
        return obj
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k in {"item_id", "field_id", "field", "value_field_id"}:
                obj[k] = _remap_item_ref(v, id_map)
            else:
                obj[k] = _remap_ids_in_obj(v, id_map)
        return obj
    return obj


def _remap_rule_payload_to_string(rule_payload, id_map):
    """Return a JSON string with remapped ids, or the original value if unparsable."""
    parsed = _parse_rule_payload(rule_payload)
    if parsed is None:
        return rule_payload
    try:
        remapped = _remap_ids_in_obj(parsed, id_map)
        return json.dumps(remapped)
    except Exception as e:
        current_app.logger.debug("_remap_rule_payload_to_string failed: %s", e)
        return rule_payload


def _clone_template_structure(template_id: int, source_version_id: int, target_version_id: int) -> None:
    """Clone pages, sections, and items from source_version_id to target_version_id preserving order.
    Returns nothing; rows are inserted with new IDs and mapped FKs.
    """
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure called for template_id={template_id}, source_version_id={source_version_id}, target_version_id={target_version_id}")
    # Maps for old->new IDs
    page_id_map = {}
    section_id_map = {}

    # Clone pages
    src_pages = FormPage.query.filter_by(template_id=template_id, version_id=source_version_id).order_by(FormPage.order).all()
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure - cloning {len(src_pages)} pages")
    for p in src_pages:
        new_p = FormPage(
            template_id=template_id,
            version_id=target_version_id,
            name=p.name,
            order=p.order,
            name_translations=p.name_translations
        )
        db.session.add(new_p)
        db.session.flush()
        page_id_map[p.id] = new_p.id
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure - cloned {len(page_id_map)} pages, page_id_map={page_id_map}")

    # Clone sections (two-pass to preserve parents)
    src_sections = FormSection.query.filter_by(template_id=template_id, version_id=source_version_id).order_by(FormSection.order).all()
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure - cloning {len(src_sections)} sections")
    # Create all sections without parent refs first
    section_pairs = []  # (src_section, new_section) for later rule-id remap
    for s in src_sections:
        # Deep copy config to avoid cross-version mutations
        _new_config = _deep_copy_json_value(s.config) if s.config is not None else None

        new_s = FormSection(
            template_id=template_id,
            version_id=target_version_id,
            name=s.name,
            order=s.order,
            parent_section_id=None,  # set later
            page_id=page_id_map.get(s.page_id) if s.page_id else None,
            section_type=s.section_type,
            max_dynamic_indicators=s.max_dynamic_indicators,
            allowed_sectors=s.allowed_sectors,
            indicator_filters=s.indicator_filters,
            allow_data_not_available=s.allow_data_not_available,
            allow_not_applicable=s.allow_not_applicable,
            allowed_disaggregation_options=s.allowed_disaggregation_options,
            data_entry_display_filters=s.data_entry_display_filters,
            add_indicator_note=s.add_indicator_note,
            name_translations=s.name_translations,
            relevance_condition=None,  # Will be set after remapping
            config=_new_config,
            archived=getattr(s, 'archived', False)
        )
        db.session.add(new_s)
        db.session.flush()
        section_id_map[s.id] = new_s.id
        section_pairs.append((s, new_s))

    # Second pass: set parent_section_id now that all new IDs exist
    parent_updates = 0
    for s in src_sections:
        if s.parent_section_id:
            new_id = section_id_map[s.id]
            new_parent_id = section_id_map.get(s.parent_section_id)
            if new_parent_id:
                FormSection.query.filter_by(id=new_id).update({'parent_section_id': new_parent_id})
                parent_updates += 1
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure - cloned {len(section_id_map)} sections, updated {parent_updates} parent relationships, section_id_map={section_id_map}")

    # Clone items (build old->new item id map, then remap rule JSON)
    src_items = FormItem.query.join(FormSection, FormItem.section_id == FormSection.id).\
        filter(FormItem.template_id == template_id, FormItem.version_id == source_version_id).\
        order_by(FormItem.order).all()
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure - cloning {len(src_items)} items")
    items_cloned = 0
    item_pairs = []  # (src_item, new_item) for later rule-id remap
    for it in src_items:
        # Deep copy config to avoid cross-version mutations
        _new_config = _deep_copy_json_value(it.config) if it.config is not None else None

        new_it = FormItem(
            template_id=template_id,
            version_id=target_version_id,
            section_id=section_id_map.get(it.section_id),
            item_type=it.item_type,
            label=it.label,
            order=it.order,
            relevance_condition=None,  # Will be set after remapping
            config=_new_config,
            indicator_bank_id=it.indicator_bank_id,
            type=it.type,
            unit=it.unit,
            validation_condition=None,  # Will be set after remapping
            validation_message=it.validation_message,
            definition=it.definition,
            options_json=_deep_copy_json_value(it.options_json),
        )
        # Copy optional lookup/list fields if exist on model
        with suppress(Exception):
            new_it.lookup_list_id = getattr(it, 'lookup_list_id', None)
            new_it.list_display_column = getattr(it, 'list_display_column', None)
            new_it.list_filters_json = _deep_copy_json_value(getattr(it, 'list_filters_json', None))
            new_it.label_translations = _deep_copy_json_value(getattr(it, 'label_translations', None))
            new_it.definition_translations = _deep_copy_json_value(getattr(it, 'definition_translations', None))
            new_it.options_translations = _deep_copy_json_value(getattr(it, 'options_translations', None))
            new_it.description_translations = _deep_copy_json_value(getattr(it, 'description_translations', None))
            new_it.description = getattr(it, 'description', None)
            new_it.archived = getattr(it, 'archived', False)
            # Matrix/plugin configs are within config already
        db.session.add(new_it)
        item_pairs.append((it, new_it))
        items_cloned += 1
        # no need to flush per-iteration beyond session add

    # Flush once to obtain new IDs, then remap rule references to the new IDs.
    db.session.flush()
    item_id_map = {
        src_it.id: new_it.id
        for (src_it, new_it) in item_pairs
        if getattr(src_it, 'id', None) is not None and getattr(new_it, 'id', None) is not None
    }

    # Remap relevance/validation conditions and calculated list filter references
    current_app.logger.debug(f"VERSIONING_DEBUG: Remapping conditions using item_id_map with {len(item_id_map)} entries: {item_id_map}")
    remapped_count = 0
    for src_it, new_it in item_pairs:
        try:
            old_rel = getattr(src_it, 'relevance_condition', None)
            if old_rel:
                new_rel = _remap_rule_payload_to_string(old_rel, item_id_map)
                new_it.relevance_condition = new_rel
                if new_rel != old_rel:
                    remapped_count += 1
                    current_app.logger.debug(f"VERSIONING_DEBUG: Remapped relevance_condition for item {src_it.id} -> {new_it.id}: '{old_rel[:100]}...' -> '{new_rel[:100]}...'")
                else:
                    current_app.logger.debug(f"VERSIONING_DEBUG: No remapping needed for item {src_it.id} -> {new_it.id} relevance_condition")

            old_val = getattr(src_it, 'validation_condition', None)
            if old_val:
                new_val = _remap_rule_payload_to_string(old_val, item_id_map)
                new_it.validation_condition = new_val
                if new_val != old_val:
                    remapped_count += 1

            with suppress(Exception):
                lf = _deep_copy_json_value(getattr(src_it, 'list_filters_json', None))
                if lf is not None:
                    remapped_lf = _remap_ids_in_obj(lf, item_id_map)
                    new_it.list_filters_json = remapped_lf
        except Exception as e:
            current_app.logger.warning(f"VERSIONING_DEBUG: Error remapping conditions for item {src_it.id} -> {new_it.id}: {e}", exc_info=True)

    for src_s, new_s in section_pairs:
        try:
            old_rel = getattr(src_s, 'relevance_condition', None)
            if old_rel:
                new_rel = _remap_rule_payload_to_string(old_rel, item_id_map)
                new_s.relevance_condition = new_rel
                if new_rel != old_rel:
                    remapped_count += 1
                    current_app.logger.debug(f"VERSIONING_DEBUG: Remapped relevance_condition for section {src_s.id} -> {new_s.id}: '{old_rel[:100]}...' -> '{new_rel[:100]}...'")
        except Exception as e:
            current_app.logger.warning(f"VERSIONING_DEBUG: Error remapping section condition {src_s.id} -> {new_s.id}: {e}", exc_info=True)

    # Flush again to persist the remapped conditions
    db.session.flush()
    current_app.logger.info(f"VERSIONING_DEBUG: Remapped {remapped_count} relevance/validation conditions")

    current_app.logger.info(f"VERSIONING_DEBUG: _clone_template_structure - successfully cloned structure: {len(page_id_map)} pages, {len(section_id_map)} sections, {items_cloned} items from version {source_version_id} to {target_version_id}")

def _clone_template_structure_between_templates(*, source_template_id: int, source_version_id: int, target_template_id: int, target_version_id: int) -> None:
    """Clone pages, sections, and items from one template/version to another template/version.

    This mirrors _clone_template_structure but allows source and target template IDs to differ.
    """
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates called for source_template_id={source_template_id}, source_version_id={source_version_id}, target_template_id={target_template_id}, target_version_id={target_version_id}")
    page_id_map = {}
    section_id_map = {}

    # Clone pages from source -> target
    src_pages = (
        FormPage.query
        .filter_by(template_id=source_template_id, version_id=source_version_id)
        .order_by(FormPage.order)
        .all()
    )
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - cloning {len(src_pages)} pages")
    for p in src_pages:
        new_p = FormPage(
            template_id=target_template_id,
            version_id=target_version_id,
            name=p.name,
            order=p.order,
            name_translations=p.name_translations
        )
        db.session.add(new_p)
        db.session.flush()
        page_id_map[p.id] = new_p.id
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - cloned {len(page_id_map)} pages")

    # Clone sections (two-pass to preserve parents)
    src_sections = (
        FormSection.query
        .filter_by(template_id=source_template_id, version_id=source_version_id)
        .order_by(FormSection.order)
        .all()
    )
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - cloning {len(src_sections)} sections")
    section_pairs = []  # (src_section, new_section) for later rule-id remap
    for s in src_sections:
        # Deep copy config to avoid cross-version mutations
        _new_config = _deep_copy_json_value(s.config) if s.config is not None else None

        new_s = FormSection(
            template_id=target_template_id,
            version_id=target_version_id,
            name=s.name,
            order=s.order,
            parent_section_id=None,
            page_id=page_id_map.get(s.page_id) if s.page_id else None,
            section_type=s.section_type,
            max_dynamic_indicators=s.max_dynamic_indicators,
            allowed_sectors=s.allowed_sectors,
            indicator_filters=s.indicator_filters,
            allow_data_not_available=s.allow_data_not_available,
            allow_not_applicable=s.allow_not_applicable,
            allowed_disaggregation_options=s.allowed_disaggregation_options,
            data_entry_display_filters=s.data_entry_display_filters,
            add_indicator_note=s.add_indicator_note,
            name_translations=s.name_translations,
            relevance_condition=None,  # Will be set after remapping
            config=_new_config,
            archived=getattr(s, 'archived', False)
        )
        db.session.add(new_s)
        db.session.flush()
        section_id_map[s.id] = new_s.id
        section_pairs.append((s, new_s))

    # Second pass: wire parent relations
    parent_updates = 0
    for s in src_sections:
        if s.parent_section_id:
            new_id = section_id_map[s.id]
            new_parent_id = section_id_map.get(s.parent_section_id)
            if new_parent_id:
                FormSection.query.filter_by(id=new_id).update({'parent_section_id': new_parent_id})
                parent_updates += 1
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - cloned {len(section_id_map)} sections, updated {parent_updates} parent relationships")

    # Clone items
    src_items = (
        FormItem.query
        .join(FormSection, FormItem.section_id == FormSection.id)
        .filter(
            FormItem.template_id == source_template_id,
            FormItem.version_id == source_version_id
        )
        .order_by(FormItem.order)
        .all()
    )
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - cloning {len(src_items)} items")
    items_cloned = 0
    item_pairs = []  # (src_item, new_item) for later rule-id remap
    for it in src_items:
        # Deep copy config to avoid cross-template mutations
        _new_config2 = _deep_copy_json_value(it.config) if it.config is not None else None

        new_it = FormItem(
            template_id=target_template_id,
            version_id=target_version_id,
            section_id=section_id_map.get(it.section_id),
            item_type=it.item_type,
            label=it.label,
            order=it.order,
            relevance_condition=None,  # Will be set after remapping
            config=_new_config2,
            indicator_bank_id=it.indicator_bank_id,
            type=it.type,
            unit=it.unit,
            validation_condition=None,  # Will be set after remapping
            validation_message=it.validation_message,
            definition=it.definition,
            options_json=_deep_copy_json_value(it.options_json),
        )
        with suppress(Exception):
            new_it.lookup_list_id = getattr(it, 'lookup_list_id', None)
            new_it.list_display_column = getattr(it, 'list_display_column', None)
            new_it.list_filters_json = _deep_copy_json_value(getattr(it, 'list_filters_json', None))
            new_it.label_translations = _deep_copy_json_value(getattr(it, 'label_translations', None))
            new_it.definition_translations = _deep_copy_json_value(getattr(it, 'definition_translations', None))
            new_it.options_translations = _deep_copy_json_value(getattr(it, 'options_translations', None))
            new_it.description_translations = _deep_copy_json_value(getattr(it, 'description_translations', None))
            new_it.description = getattr(it, 'description', None)
            new_it.archived = getattr(it, 'archived', False)
        db.session.add(new_it)
        item_pairs.append((it, new_it))
        items_cloned += 1

    # Flush once to obtain new IDs, then remap rule references to the new IDs.
    db.session.flush()
    item_id_map = {
        src_it.id: new_it.id
        for (src_it, new_it) in item_pairs
        if getattr(src_it, 'id', None) is not None and getattr(new_it, 'id', None) is not None
    }

    # Remap relevance/validation conditions and calculated list filter references
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - Remapping conditions using item_id_map with {len(item_id_map)} entries: {item_id_map}")
    remapped_count = 0
    for src_it, new_it in item_pairs:
        try:
            old_rel = getattr(src_it, 'relevance_condition', None)
            if old_rel:
                new_rel = _remap_rule_payload_to_string(old_rel, item_id_map)
                new_it.relevance_condition = new_rel
                if new_rel != old_rel:
                    remapped_count += 1
                    current_app.logger.debug(f"VERSIONING_DEBUG: Remapped relevance_condition for item {src_it.id} -> {new_it.id}: '{old_rel[:100]}...' -> '{new_rel[:100]}...'")

            old_val = getattr(src_it, 'validation_condition', None)
            if old_val:
                new_val = _remap_rule_payload_to_string(old_val, item_id_map)
                new_it.validation_condition = new_val
                if new_val != old_val:
                    remapped_count += 1

            with suppress(Exception):
                lf = _deep_copy_json_value(getattr(src_it, 'list_filters_json', None))
                if lf is not None:
                    remapped_lf = _remap_ids_in_obj(lf, item_id_map)
                    new_it.list_filters_json = remapped_lf
        except Exception as e:
            current_app.logger.warning(f"VERSIONING_DEBUG: Error remapping conditions for item {src_it.id} -> {new_it.id}: {e}", exc_info=True)

    for src_s, new_s in section_pairs:
        try:
            old_rel = getattr(src_s, 'relevance_condition', None)
            if old_rel:
                new_rel = _remap_rule_payload_to_string(old_rel, item_id_map)
                new_s.relevance_condition = new_rel
                if new_rel != old_rel:
                    remapped_count += 1
                    current_app.logger.debug(f"VERSIONING_DEBUG: Remapped relevance_condition for section {src_s.id} -> {new_s.id}: '{old_rel[:100]}...' -> '{new_rel[:100]}...'")
        except Exception as e:
            current_app.logger.warning(f"VERSIONING_DEBUG: Error remapping section condition {src_s.id} -> {new_s.id}: {e}", exc_info=True)

    # Flush again to persist the remapped conditions
    db.session.flush()
    current_app.logger.info(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - successfully cloned structure: {len(page_id_map)} pages, {len(section_id_map)} sections, {items_cloned} items from template {source_template_id}/version {source_version_id} to template {target_template_id}/version {target_version_id}, remapped {remapped_count} conditions")

def _handle_template_pages(template, form_data, version_id: int):
    """Handle template pages data processing"""
    page_ids = form_data.getlist('page_ids')
    page_names = form_data.getlist('page_names')
    page_orders = form_data.getlist('page_orders')
    page_name_translations = form_data.getlist('page_name_translations')

    # Create a set of existing page IDs for tracking deletions
    existing_pages = FormPage.query.filter_by(template_id=template.id, version_id=version_id).all()
    existing_page_ids = {str(page.id) for page in existing_pages}
    processed_page_ids = set()

    current_app.logger.debug(
        f"VERSIONING_DEBUG: _handle_template_pages - start template_id={template.id}, version_id={version_id}, "
        f"existing_pages={len(existing_pages)}, incoming_names={len(page_names)}"
    )

    # Process each page from the form
    for i in range(len(page_names)):
        page_id = page_ids[i] if i < len(page_ids) and page_ids[i] else None
        name = page_names[i]
        try:
            order = int(page_orders[i])
        except (ValueError, TypeError):
            order = i + 1

        # Handle page translations (ISO codes only)
        name_translations = None
        if i < len(page_name_translations) and page_name_translations[i]:
            try:
                parsed_translations = json.loads(page_name_translations[i])
                supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
                filtered_translations = {}
                if isinstance(parsed_translations, dict):
                    for k, v in parsed_translations.items():
                        if not (isinstance(k, str) and isinstance(v, str) and v.strip()):
                            continue
                        code = k.strip().lower().split('_', 1)[0]
                        if code in supported_codes:
                            filtered_translations[code] = v.strip()
                name_translations = filtered_translations if filtered_translations else None
            except (json.JSONDecodeError, TypeError) as e:
                current_app.logger.error(f"Error parsing page name translations: {e}")
                name_translations = None

        if page_id and page_id in existing_page_ids:
            # Update existing page
            try:
                page_pk = int(page_id)
            except Exception as e:
                current_app.logger.debug("page_id int parse failed: %s", e)
                page_pk = page_id
            page = FormPage.query.get(page_pk)
            if page:
                page.name = name
                page.order = order
                page.name_translations = name_translations
                processed_page_ids.add(page_id)
                current_app.logger.debug(
                    f"VERSIONING_DEBUG: _handle_template_pages - updated page id={page_id} name='{name}' order={order}"
                )
        else:
            # Create new page
            new_page = FormPage(
                template_id=template.id,
                version_id=version_id,
                name=name,
                order=order,
                name_translations=name_translations
            )
            db.session.add(new_page)
            current_app.logger.debug(
                f"VERSIONING_DEBUG: _handle_template_pages - creating new page name='{name}' order={order}"
            )

    # Delete pages that were removed from the form
    pages_to_delete = existing_page_ids - processed_page_ids
    if pages_to_delete:
        current_app.logger.debug(
            f"VERSIONING_DEBUG: _handle_template_pages - pages_to_delete={sorted(list(pages_to_delete))}"
        )
    for page_id in pages_to_delete:
        try:
            page_pk = int(page_id)
        except Exception as e:
            current_app.logger.debug("page_id int parse failed for %r: %s", page_id, e)
            page_pk = page_id
        page = FormPage.query.get(page_pk)
        if page:
            db.session.delete(page)
            current_app.logger.debug(
                f"VERSIONING_DEBUG: _handle_template_pages - deleted page id={page_id}"
            )

def _build_template_data_for_js(template, version_id: int):
    """Build template data structures for JavaScript, scoped to a specific version."""
    sections_with_items_for_js = []
    all_template_items_for_js = []
    sections_with_items = []

    all_sections = FormSection.query.filter_by(template_id=template.id, version_id=version_id).order_by(FormSection.order).all()

    # Clean setup: migrate any legacy decimal subsection orders (e.g. 4.2) into the parent/child scheme.
    # After this runs, subsections should have parent_section_id set and order as an integer child order.
    try:
        changed = 0
        parent_by_order = {}
        for s in all_sections:
            if s.parent_section_id is None:
                try:
                    parent_by_order[int(float(s.order))] = s
                except Exception as e:
                    current_app.logger.debug("parent_by_order order parse failed: %s", e)
                    continue

        for s in all_sections:
            if s.parent_section_id is not None:
                continue
            try:
                raw = float(s.order)
            except Exception as e:
                current_app.logger.debug("order float parse failed: %s", e)
                continue
            parent_part = int(raw)
            frac = raw - parent_part
            if frac <= 0:
                continue
            child_part = int(round(frac * 10))
            if child_part <= 0:
                continue

            parent = parent_by_order.get(parent_part)
            if not parent or parent.id == s.id:
                continue

            # Avoid collisions with existing children: if used, append at end
            existing_child_orders = []
            for c in all_sections:
                if c.parent_section_id != parent.id or c.order is None:
                    continue
                try:
                    existing_child_orders.append(int(float(c.order)))
                except Exception as e:
                    current_app.logger.debug("child order parse failed: %s", e)
                    continue
            if child_part in existing_child_orders:
                child_part = (max(existing_child_orders) + 1) if existing_child_orders else child_part

            s.parent_section_id = parent.id
            s.order = int(child_part)
            changed += 1

        if changed:
            db.session.flush()
            current_app.logger.info(
                f"FormBuilder: migrated {changed} legacy subsection order(s) for template_id={template.id} version_id={version_id}"
            )
    except Exception as _e:
        # Don't block rendering if migration fails
        try:
            current_app.logger.warning(f"FormBuilder: legacy subsection order migration failed: {_e}")
        except Exception as e:
            current_app.logger.debug("Legacy subsection order migration exception: %s", e)

    all_template_sections_for_js = [[s.id, s.name] for s in all_sections]

    # Build indicator bank choices
    all_ib_objects = IndicatorBank.query.order_by(IndicatorBank.name).all()
    indicator_bank_choices_with_units_for_js = []
    for ib in all_ib_objects:
        if ib and hasattr(ib, 'id') and hasattr(ib, 'name') and hasattr(ib, 'type'):
            indicator_bank_choices_with_units_for_js.append({
                'value': ib.id,
                # `label` is used for the dropdown option text (keep it descriptive).
                'label': f"{ib.name} (Type: {ib.type}, Unit: {ib.unit or 'N/A'})",
                # Additional fields for UI hints (e.g. placeholders) when switching indicators.
                # These are safe to include for backwards compatibility (existing consumers ignore them).
                'name': ib.name,
                'definition': getattr(ib, 'definition', '') or '',
                'type': ib.type,
                'unit': ib.unit if ib.unit else ''
            })

    # Build question type choices
    question_type_choices_for_js = [
        (qt.value, 'Blank / Note' if qt.value == 'blank' else qt.value.replace('_', ' ').title())
        for qt in QuestionType
    ]

    # Build indicator fields configuration
    indicator_fields_config = _build_indicator_fields_config()

    # Get total indicator count
    total_indicator_count = db.session.query(IndicatorBank).count()

    # Process sections and items
    for section_obj in all_sections:
        section_data = _build_section_data_for_js(section_obj, all_sections)
        sections_with_items_for_js.append(section_data)

        # Build section items for template rendering
        section_items = _build_section_items_for_template(section_obj, all_sections, all_template_items_for_js)
        sections_with_items.append(section_items)

    # Sort all items by section order, then item order
    section_order_map = {s.id: s.order for s in all_sections}
    all_template_items_for_js.sort(key=lambda x: (
        section_order_map.get(x['section_id'], 9999),
        x.get('order', 9999)
    ))

    # Get regular lookup lists from database
    regular_lookup_lists = LookupList.query.order_by(LookupList.name).all()

    # Get plugin-provided lookup lists
    plugin_lookup_lists = []
    if current_app.form_integration:
        plugin_lookup_lists = current_app.form_integration.get_plugin_lookup_lists()

    # Convert plugin lookup lists to objects that match the database lookup list interface
    plugin_lookup_objects = []
    for lookup_list_data in plugin_lookup_lists:
        # Create a mock object that matches the LookupList interface
        # Include has_config_ui flag to indicate if this list has configuration UI
        has_config_ui = 'get_config_ui_handler' in lookup_list_data and callable(lookup_list_data.get('get_config_ui_handler'))
        config_js_handler = lookup_list_data.get('config_ui_js_handler', None)
        lookup_obj = type('PluginLookupList', (), {
            'id': lookup_list_data['id'],
            'name': lookup_list_data['name'],
            'columns_config': lookup_list_data.get('columns_config', []),
            'has_config_ui': has_config_ui,  # Flag to indicate config UI availability
            'config_js_handler': config_js_handler  # JavaScript handler function name for config UI
        })()
        plugin_lookup_objects.append(lookup_obj)

    # Add system lists (Country Map and Indicator Bank)
    system_lookup_objects = []

    # Helper function to get all columns from a SQLAlchemy model
    def get_model_columns_config(model_class, is_multilingual_name=False):
        """Get all column names from a SQLAlchemy model, excluding relationships and internal fields.

        Args:
            model_class: SQLAlchemy model class
            is_multilingual_name: If True, mark 'name' column as multilingual
        """
        inspector = inspect(model_class)
        columns_config = []

        # Get all columns from the model
        for column in inspector.columns:
            # Skip primary key 'id' column as it's usually not needed for display
            if column.name == 'id':
                continue

            # Skip name_translations field - we use 'name' with multilingual support instead
            if column.name == 'name_translations':
                continue

            # Determine column type
            col_type = "string"  # default
            if hasattr(column.type, 'python_type'):
                py_type = column.type.python_type
                if py_type == int or py_type == float:
                    col_type = "number"
                elif py_type == bool:
                    col_type = "boolean"
                elif py_type == datetime:
                    col_type = "date"

            col_config = {
                "name": column.name,
                "type": col_type
            }

            # Mark 'name' column as multilingual if specified
            if is_multilingual_name and column.name == 'name':
                col_config["multilingual"] = True

            columns_config.append(col_config)

        return columns_config

    # Country Map system list - dynamically get all columns, mark 'name' as multilingual
    country_columns = get_model_columns_config(Country, is_multilingual_name=True)
    country_map_obj = type('SystemLookupList', (), {
        'id': 'country_map',
        'name': 'Country Map',
        'columns_config': country_columns
    })()
    system_lookup_objects.append(country_map_obj)

    # Indicator Bank system list - dynamically get all columns
    indicator_columns = get_model_columns_config(IndicatorBank)
    indicator_bank_obj = type('SystemLookupList', (), {
        'id': 'indicator_bank',
        'name': 'Indicator Bank',
        'columns_config': indicator_columns
    })()
    system_lookup_objects.append(indicator_bank_obj)

    # National Society system list - dynamically get all columns, mark 'name' as multilingual
    ns_columns = get_model_columns_config(NationalSociety, is_multilingual_name=True)
    # Add region field from related Country table
    ns_columns.append({
        "name": "region",
        "type": "string",
        "relationship": "country.region"  # Indicates this comes from a related table
    })
    national_society_obj = type('SystemLookupList', (), {
        'id': 'national_society',
        'name': 'National Society',
        'columns_config': ns_columns
    })()
    system_lookup_objects.append(national_society_obj)

    # Combine regular lookup lists with plugin lookup lists and system lists
    all_lookup_lists = list(regular_lookup_lists) + plugin_lookup_objects + system_lookup_objects

    # Get template variables for the version
    template_version = FormTemplateVersion.query.get(version_id)
    template_variables = template_version.variables if template_version and template_version.variables else {}

    # Collect plugin label variables (for "[" suggestions in section/item labels)
    plugin_label_variables = []
    if getattr(current_app, 'plugin_manager', None):
        for field_type_name, field_type in current_app.plugin_manager.field_types.items():
            if hasattr(field_type, 'get_label_variables'):
                for v in (field_type.get_label_variables() or []):
                    if isinstance(v, dict) and v.get('key'):
                        plugin_label_variables.append({'key': str(v['key']), 'label': str(v.get('label', v['key']))})

    return {
        'sections_with_items': sections_with_items,
        'all_template_sections_for_js': all_template_sections_for_js,
        'indicator_bank_choices_with_units_for_js': indicator_bank_choices_with_units_for_js,
        'question_type_choices_for_js': question_type_choices_for_js,
        'all_template_items_for_js': all_template_items_for_js,
        'sections_with_items_for_js': sections_with_items_for_js,
        'indicator_fields_config': indicator_fields_config,
        'total_indicator_count': total_indicator_count,
        'lookup_lists_for_js': all_lookup_lists,
        'all_template_pages_for_js': [{'id': p.id, 'name': p.name, 'name_translations': p.name_translations}
                                      for p in FormPage.query.filter_by(template_id=template.id, version_id=version_id).order_by(FormPage.order).all()],
        'template_variables': template_variables,
        'plugin_label_variables': plugin_label_variables
    }

def _get_plugin_measures(plugin_type):
    """Fallback when a plugin does not implement get_relevance_measures(). Plugin-specific measures belong in the plugin."""
    return []

def _build_indicator_fields_config():
    """Build indicator fields configuration for dynamic filters"""
    config = {
        'type': {'label': 'Type', 'type': 'select', 'values': []},
        'unit': {'label': 'Unit', 'type': 'select', 'values': []},
        'sector': {'label': 'Sector', 'type': 'select', 'values': []},
        'subsector': {'label': 'Sub-Sector', 'type': 'select', 'values': []},
        'emergency': {'label': 'Emergency', 'type': 'boolean', 'values': [
            {'value': 'true', 'label': 'Yes'},
            {'value': 'false', 'label': 'No'}
        ]},
        'archived': {'label': 'Archived', 'type': 'boolean', 'values': [
            {'value': 'true', 'label': 'Yes'},
            {'value': 'false', 'label': 'No'}
        ]},
        'related_programs': {'label': 'Related Programs', 'type': 'select', 'values': []}
    }

    # Get distinct values from database
    types = db.session.query(IndicatorBank.type).distinct().filter(IndicatorBank.type.isnot(None)).all()
    config['type']['values'] = [{'value': t[0], 'label': t[0].title()} for t in types if t[0]]

    units = db.session.query(IndicatorBank.unit).distinct().filter(IndicatorBank.unit.isnot(None)).all()
    config['unit']['values'] = [{'value': u[0], 'label': u[0]} for u in units if u[0]]

    # Get distinct programs
    programs_raw = db.session.query(IndicatorBank.related_programs).distinct().filter(IndicatorBank.related_programs.isnot(None)).all()
    programs_set = set()
    for prog_row in programs_raw:
        if prog_row[0]:
            for prog in prog_row[0].split(','):
                prog_clean = prog.strip()
                if prog_clean:
                    programs_set.add(prog_clean)
    config['related_programs']['values'] = [{'value': p, 'label': p} for p in sorted(programs_set)]

    # Get distinct sectors and subsectors
    config['sector']['values'] = _get_sector_choices()
    config['subsector']['values'] = _get_subsector_choices()

    return config

def _get_sector_choices():
    """Get sector choices for filters"""
    # Cast JSON/JSONB to text to allow DISTINCT across backends
    sectors_raw = db.session.query(cast(IndicatorBank.sector, String)).distinct().filter(IndicatorBank.sector.isnot(None)).all()
    all_sectors_set = set()

    for sector_row in sectors_raw:
        sector_data = None
        try:
            sector_data = json.loads(sector_row[0]) if isinstance(sector_row[0], str) else sector_row[0]
        except Exception as e:
            current_app.logger.debug("sector_data parse failed: %s", e)
            sector_data = None
        if sector_data and isinstance(sector_data, dict):
            if sector_data.get('primary'):
                all_sectors_set.add(sector_data['primary'])
            if sector_data.get('secondary'):
                all_sectors_set.add(sector_data['secondary'])
            if sector_data.get('tertiary'):
                all_sectors_set.add(sector_data['tertiary'])

    sector_choices = []
    for sector_id in sorted(all_sectors_set):
        if isinstance(sector_id, int):
            sector = Sector.query.get(sector_id)
            if sector:
                sector_choices.append({'value': sector.name, 'label': sector.name})

    return sector_choices

def _get_subsector_choices():
    """Get subsector choices for filters"""
    subsectors_raw = db.session.query(cast(IndicatorBank.sub_sector, String)).distinct().filter(IndicatorBank.sub_sector.isnot(None)).all()
    all_subsectors_set = set()

    for subsector_row in subsectors_raw:
        subsector_data = None
        try:
            subsector_data = json.loads(subsector_row[0]) if isinstance(subsector_row[0], str) else subsector_row[0]
        except Exception as e:
            current_app.logger.debug("subsector_data parse failed: %s", e)
            subsector_data = None
        if subsector_data and isinstance(subsector_data, dict):
            if subsector_data.get('primary'):
                all_subsectors_set.add(subsector_data['primary'])
            if subsector_data.get('secondary'):
                all_subsectors_set.add(subsector_data['secondary'])
            if subsector_data.get('tertiary'):
                all_subsectors_set.add(subsector_data['tertiary'])

    subsector_choices = []
    for subsector_id in sorted(all_subsectors_set):
        if isinstance(subsector_id, int):
            subsector = SubSector.query.get(subsector_id)
            if subsector:
                subsector_choices.append({'value': subsector.name, 'label': subsector.name})

    return subsector_choices

def _build_section_data_for_js(section_obj, all_sections):
    """Build section data for JavaScript"""
    section_data = {
        'id': section_obj.id,
        'name': section_obj.name,
        'name_translations': section_obj.name_translations,
        'order': section_obj.order,
        'indicators': [],
        'questions': [],
        'document_fields': [],
        'form_items': []
    }

    # Load unified FormItems for this section (include archived items for form builder display)
    for form_item_obj in FormItem.query.filter_by(section_id=section_obj.id).order_by(FormItem.order).all():
        if form_item_obj is None:
            continue

        # Add to unified form_items
        section_data['form_items'].append({
            'item_id': form_item_obj.id,
            'item_type': form_item_obj.item_type,
            'label': form_item_obj.label,
            'type': form_item_obj.type,
            'unit': form_item_obj.unit,
            'order': form_item_obj.order,
            'is_required': form_item_obj.is_required,
            'privacy': getattr(form_item_obj, 'privacy', 'ifrc_network'),
            'archived': form_item_obj.archived,  # Include archived flag
            'allowed_disaggregation_options': form_item_obj.allowed_disaggregation_options if form_item_obj.is_indicator else None,
            'age_groups_config': form_item_obj.age_groups_config if form_item_obj.is_indicator else None,
            'default_value': (form_item_obj.config.get('default_value') if (form_item_obj.is_indicator and isinstance(form_item_obj.config, dict)) else None),
            'relevance_condition': form_item_obj.relevance_condition,
            'validation_condition': form_item_obj.validation_condition,
            'validation_message': form_item_obj.validation_message,
            'definition': getattr(form_item_obj, 'definition', None) or getattr(form_item_obj, 'description', None),
            'label_translations': getattr(form_item_obj, 'label_translations', None),
            'definition_translations': getattr(form_item_obj, 'definition_translations', None) or getattr(form_item_obj, 'description_translations', None),
            'item_model': 'form_item',
            'plugin_config': form_item_obj.config.get('plugin_config') if form_item_obj.item_type.startswith('plugin_') and form_item_obj.config else None
        })

        # Add to type-specific arrays for backward compatibility
        if form_item_obj.is_indicator:
            section_data['indicators'].append({
                'id': form_item_obj.id,
                'label': form_item_obj.label,
                'type': form_item_obj.type,
                'unit': form_item_obj.unit,
                'order': form_item_obj.order,
                'privacy': getattr(form_item_obj, 'privacy', 'ifrc_network'),
                'allowed_disaggregation_options': form_item_obj.allowed_disaggregation_options,
                'age_groups_config': form_item_obj.age_groups_config,
                'default_value': (form_item_obj.config.get('default_value') if (isinstance(form_item_obj.config, dict)) else None),
                'relevance_condition': form_item_obj.relevance_condition,
                'validation_condition': form_item_obj.validation_condition,
                'validation_message': form_item_obj.validation_message,
                'definition': form_item_obj.definition,
                'label_translations': form_item_obj.label_translations,
                'definition_translations': form_item_obj.definition_translations,
                'item_model': 'indicator'
            })
        elif form_item_obj.is_question:
            section_data['questions'].append({
                'id': form_item_obj.id,
                'label': form_item_obj.label,
                'question_type': form_item_obj.question_type.value,
                'order': form_item_obj.order,
                'privacy': getattr(form_item_obj, 'privacy', 'ifrc_network'),
                'options': form_item_obj.options,
                'options_translations': form_item_obj.options_translations,
                'label_translations': form_item_obj.label_translations,
                'definition_translations': form_item_obj.definition_translations,
                'relevance_condition': form_item_obj.relevance_condition,
                'validation_condition': form_item_obj.validation_condition,
                'validation_message': form_item_obj.validation_message,
                'item_model': 'question'
            })
        elif form_item_obj.is_document_field:
            section_data['document_fields'].append({
                'id': form_item_obj.id,
                'label': form_item_obj.label,
                'order': form_item_obj.order,
                'is_required': form_item_obj.is_required,
                'privacy': getattr(form_item_obj, 'privacy', 'ifrc_network'),
                'description': form_item_obj.description,
                'label_translations': form_item_obj.label_translations,
                'description_translations': form_item_obj.description_translations,
                'relevance_condition': form_item_obj.relevance_condition,
                'config': form_item_obj.config,  # Include full config for max_documents
                'item_model': 'document_field'
            })

    # Add existing indicator filters to the section data
    section_data['existing_filters'] = section_obj.indicator_filters_list

    return section_data

def _build_section_items_for_template(section_obj, all_sections, all_template_items_for_js):
    """Build section items for template rendering"""
    form_items_with_forms = []
    indicators_with_forms = []
    questions_with_forms = []
    document_fields_with_forms = []

    # Process all form items in section (include archived items for form builder display)
    form_items = FormItem.query.filter_by(section_id=section_obj.id).order_by(FormItem.order).all()

    for form_item_obj in form_items:
        if form_item_obj is None:
            continue

        # Create edit forms based on item type
        if form_item_obj.is_indicator:
            edit_form_instance = IndicatorForm(obj=form_item_obj, prefix=f"edit_item_{form_item_obj.id}")
            edit_form_instance.section_id.choices = [(s.id, s.name) for s in all_sections]
            edit_form_instance.section_id.data = section_obj.id
            if form_item_obj.allowed_disaggregation_options:
                edit_form_instance.allowed_disaggregation_options.data = form_item_obj.allowed_disaggregation_options
            else:
                edit_form_instance.allowed_disaggregation_options.data = ["total"]
            edit_form_instance.age_groups_config.data = form_item_obj.age_groups_config
            edit_form_instance.indicator_bank_id.data = form_item_obj.indicator_bank_id

            indicators_with_forms.append({
                'indicator': form_item_obj,
                'form': edit_form_instance
            })

        elif form_item_obj.is_question:
            edit_form_instance = QuestionForm(obj=form_item_obj, prefix=f"edit_item_{form_item_obj.id}")
            edit_form_instance.section_id.choices = [(s.id, s.name) for s in all_sections]
            edit_form_instance.section_id.data = section_obj.id
            edit_form_instance.options_json.data = json.dumps(form_item_obj.options) if form_item_obj.options else ""
            if hasattr(edit_form_instance, 'options_translations_json'):
                edit_form_instance.options_translations_json.data = json.dumps(form_item_obj.options_translations) if form_item_obj.options_translations else "[]"

            questions_with_forms.append({
                'question': form_item_obj,
                'form': edit_form_instance
            })

        elif form_item_obj.is_document_field:
            edit_form_instance = DocumentFieldForm(obj=form_item_obj, prefix=f"edit_item_{form_item_obj.id}")
            edit_form_instance.section_id.choices = [(s.id, s.name) for s in all_sections]
            edit_form_instance.section_id.data = section_obj.id

            document_fields_with_forms.append({
                'document_field': form_item_obj,
                'form': edit_form_instance
            })

        elif form_item_obj.is_plugin:
            # Plugin items don't need edit forms in the same way
            # They use the unified modal system
            pass

        # Add to unified form items
        form_items_with_forms.append({
            'form_item': form_item_obj,
            'form': edit_form_instance if 'edit_form_instance' in locals() else None
        })

        # Add to flat list for rule builder
        if form_item_obj.is_indicator:
            item_id = f'indicator_{form_item_obj.id}'
            item_label = f'Indicator: {form_item_obj.label}'
            item_model = 'indicator'
        elif form_item_obj.is_question:
            item_id = f'question_{form_item_obj.id}'
            item_label = f'Question: {form_item_obj.label[:50]}{"..." if len(form_item_obj.label) > 50 else ""}'
            item_model = 'question'
        elif form_item_obj.is_document_field:
            item_id = f'document_field_{form_item_obj.id}'
            item_label = f'Document Field: {form_item_obj.label}'
            item_model = 'document_field'
        elif form_item_obj.is_matrix:
            item_id = f'matrix_{form_item_obj.id}'
            item_label = f'Matrix: {form_item_obj.label}'
            item_model = 'matrix'
        elif form_item_obj.is_plugin:
            plugin_type = form_item_obj.item_type.replace('plugin_', '')
            item_id = f'plugin_{form_item_obj.id}'
            item_label = f'Plugin ({plugin_type.replace("_", " ").title()}): {form_item_obj.label}'
            item_model = 'plugin'
        else:
            item_id = f'form_item_{form_item_obj.id}'
            item_label = f'{form_item_obj.item_type.title()}: {form_item_obj.label}'
            item_model = 'form_item'

        # Add translation fields for the auto-translate modal
        item_data = {
            'id': item_id,
            'label': form_item_obj.label,  # Use actual label, not formatted label
            'description': form_item_obj.definition or form_item_obj.description or '',
            'type': form_item_obj.type,
            'item_model': item_model,
            'section_id': section_obj.id,
            'order': form_item_obj.order,
            'options': form_item_obj.options if form_item_obj.is_question else [],
            'item_id_raw': form_item_obj.id,  # For saving translations back
            'item_type_raw': form_item_obj.item_type,  # For saving translations back
            'config': form_item_obj.config or {}  # Include config for frontend
        }

        # Add plugin-specific data (measures from plugin field type when available)
        if form_item_obj.is_plugin:
            plugin_type = form_item_obj.item_type.replace('plugin_', '')
            item_data['plugin_type'] = plugin_type
            field_type = current_app.plugin_manager.get_field_type(plugin_type) if getattr(current_app, 'plugin_manager', None) else None
            if field_type and hasattr(field_type, 'get_relevance_measures'):
                item_data['plugin_measures'] = field_type.get_relevance_measures() or []
            else:
                item_data['plugin_measures'] = _get_plugin_measures(plugin_type)

        # Add translation payloads (JSON dicts keyed by ISO code; no hardcoded languages)
        label_translations = getattr(form_item_obj, 'label_translations', None)
        item_data['label_translations'] = label_translations if isinstance(label_translations, dict) else {}

        # Add description/definition translations
        description_translations = None
        if hasattr(form_item_obj, 'definition_translations') and form_item_obj.definition_translations:
            description_translations = form_item_obj.definition_translations
        elif hasattr(form_item_obj, 'description_translations') and form_item_obj.description_translations:
            description_translations = form_item_obj.description_translations

        item_data['description_translations'] = description_translations if isinstance(description_translations, dict) else {}

        all_template_items_for_js.append(item_data)

    # Set display configuration attributes
    section_obj.data_entry_display_filters_config = section_obj.data_entry_display_filters_list
    section_obj.allowed_disaggregation_options_config = section_obj.allowed_disaggregation_options_list

    # Build a combined, sorted list for simplified template rendering
    combined = []
    for x in indicators_with_forms:
        combined.append({'type': 'indicator', 'item': x['indicator'], 'form': x['form']})
    for x in questions_with_forms:
        combined.append({'type': 'question', 'item': x['question'], 'form': x['form']})
    for x in document_fields_with_forms:
        combined.append({'type': 'document', 'item': x['document_field'], 'form': x['form']})
    # Include plugin and matrix items in combined list
    for x in form_items_with_forms:
        if x['form_item'].item_type.startswith('plugin_'):
            combined.append({'type': 'plugin', 'item': x['form_item'], 'form': x['form']})
        elif x['form_item'].item_type == 'matrix':
            combined.append({'type': 'matrix', 'item': x['form_item'], 'form': x['form']})

    combined_sorted = sorted(combined, key=lambda y: getattr(y['item'], 'order', 0))

    return {
        'section': section_obj,
        'indicators_with_forms': indicators_with_forms,
        'document_fields_with_forms': document_fields_with_forms,
        'questions_with_forms': questions_with_forms,
        'form_items_with_forms': form_items_with_forms,
        'combined_sorted_items': combined_sorted
    }

def _create_indicator_form_item(template, section, form_data, default_order):
    """Create a new indicator form item"""
    # Use the provided default order
    order = default_order

    # Helper function to get field value with or without prefix
    def get_field_value(field_name, prefix='add_ind_modal-'):
        # Try with prefix first, then without
        prefixed_name = f"{prefix}{field_name}"
        return form_data.get(prefixed_name) or form_data.get(field_name)

    # Get indicator bank
    indicator_bank_id_raw = get_field_value('indicator_bank_id')
    indicator_bank_id_int = None
    try:
        if indicator_bank_id_raw:
            indicator_bank_id_int = int(indicator_bank_id_raw)
    except (ValueError, TypeError):
        indicator_bank_id_int = None

    indicator_bank = IndicatorBank.query.get(indicator_bank_id_int) if indicator_bank_id_int else None

    # Handle order field - use form value if valid, otherwise use calculated default
    order_value = get_field_value('order', '')
    if order_value and str(order_value).strip():
        with suppress(ValueError, TypeError):
            order = float(order_value)

    # Determine custom definition (store only if provided; otherwise rely on bank fallback at render time)
    _custom_def_val = None
    try:
        _def_raw = get_field_value('definition', '')
        if _def_raw and str(_def_raw).strip():
            _custom_def_val = str(_def_raw).strip()
    except Exception as e:
        current_app.logger.debug("_custom_def_val parse failed: %s", e)
        _custom_def_val = None

    # Create FormItem
    form_item = FormItem(
        item_type='indicator',
        section_id=section.id,
        template_id=template.id,  # Add template_id
        version_id=section.version_id,
        label=(get_field_value('label', '') or (indicator_bank.name if indicator_bank else 'Indicator')),
        type=indicator_bank.type if indicator_bank else 'number', # Use indicator bank type
        unit=indicator_bank.unit if indicator_bank else '', # Use indicator bank unit
        order=order,
        definition=_custom_def_val,
        indicator_bank_id=indicator_bank_id_int if indicator_bank_id_int else None
    )

    # Initialize config with default values
    config = {
        'is_required': bool(get_field_value('is_required', '')),
        'layout_column_width': int(get_field_value('layout_column_width', '12')),
        'layout_break_after': bool(get_field_value('layout_break_after', '')),
        'allowed_disaggregation_options': ["total"],
        'age_groups_config': None,
        'allow_data_not_available': bool(get_field_value('allow_data_not_available', '')),
        'allow_not_applicable': bool(get_field_value('allow_not_applicable', '')),
        'indirect_reach': bool(get_field_value('indirect_reach', '')),
        'default_value': None,
        'privacy': (get_field_value('privacy', '') or 'ifrc_network'),
        'allow_over_100': False  # Default to False
    }

    # Default value (optional): literal or template variable like [var_name]
    try:
        dv_raw = get_field_value('default_value', '')
        dv_raw = str(dv_raw).strip() if dv_raw is not None else ''
        if dv_raw:
            config['default_value'] = dv_raw
    except Exception as e:
        current_app.logger.debug("default_value config update failed: %s", e)

    # Handle allow_over_100 - check direct field first, then config JSON
    allow_over_100_val = get_field_value('allow_over_100', '')
    if allow_over_100_val in ['true', 'on', '1']:
        config['allow_over_100'] = True
    else:
        # Fall back to config field if present
        config_field = form_data.get('config')
        if config_field:
            try:
                config_json = json.loads(config_field)
                if 'allow_over_100' in config_json:
                    config['allow_over_100'] = bool(config_json['allow_over_100'])
            except (json.JSONDecodeError, TypeError):
                pass

    # Handle disaggregation options
    current_app.logger.debug("DISAGG_DEBUG: Processing disaggregation options")
    current_app.logger.debug(f"DISAGG_DEBUG: Form data keys: {list(form_data.keys())}")

    # Try both unprefixed and prefixed versions
    disagg_options = form_data.getlist('allowed_disaggregation_options')
    current_app.logger.debug(f"DISAGG_DEBUG: Unprefixed options: {disagg_options}")

    if not disagg_options:
        # Try with prefix
        disagg_options = form_data.getlist('add_ind_modal-allowed_disaggregation_options')
        current_app.logger.debug(f"DISAGG_DEBUG: Prefixed options: {disagg_options}")

    if disagg_options:
        current_app.logger.debug(f"DISAGG_DEBUG: Setting options in config: {disagg_options}")
        config['allowed_disaggregation_options'] = disagg_options
    else:
        current_app.logger.warning("DISAGG_DEBUG: No disaggregation options found in form data")

    # Handle age groups config
    age_groups_json = get_field_value('age_groups_config')
    if age_groups_json:
        try:
            config['age_groups_config'] = json.loads(age_groups_json)
        except json.JSONDecodeError:
            config['age_groups_config'] = age_groups_json  # Store as string if JSON parsing fails

    # Set the consolidated config
    form_item.config = config

    # Handle conditions (save only if meaningful)
    _rel = get_field_value('relevance_condition', '') or ''
    _val = get_field_value('validation_condition', '') or ''
    _msg = get_field_value('validation_message', '') or ''
    form_item.relevance_condition = _rel if is_conditions_meaningful(_rel) else None
    form_item.validation_condition = _val if is_conditions_meaningful(_val) else None
    form_item.validation_message = _msg if _msg else None

    # Save translations if provided
    with suppress(Exception):
        label_translations_raw = get_field_value('label_translations', '')
        if label_translations_raw:
            import json as _json
            lt = _json.loads(label_translations_raw)
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            filtered_translations = {}
            if isinstance(lt, dict):
                for k, v in lt.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        filtered_translations[code] = str(v).strip()
            form_item.label_translations = filtered_translations or None
    with suppress(Exception):
        definition_translations_raw = get_field_value('definition_translations', '')
        if definition_translations_raw:
            import json as _json
            dt = _json.loads(definition_translations_raw)
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            filtered_translations = {}
            if isinstance(dt, dict):
                for k, v in dt.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        filtered_translations[code] = str(v).strip()
            form_item.definition_translations = filtered_translations or None

    db.session.add(form_item)
    db.session.flush()

    return form_item

def _create_question_form_item(template, section, form_data, default_order):
    """Create a new question form item"""
    # Use the provided default order
    order = default_order

    # Helper function to get field value with or without prefix
    def get_field_value(field_name, prefix='add_q_modal-'):
        # Try with prefix first, then without
        prefixed_name = f"{prefix}{field_name}"
        return form_data.get(prefixed_name) or form_data.get(field_name)

    # Get question type
    question_type_str = get_field_value('question_type')
    if not question_type_str:
        flash("Question type is required", "danger")
        return None

    try:
        question_type = QuestionType(question_type_str)
    except ValueError:
        flash(f"Invalid question type: {question_type_str}", "danger")
        return None

    # Handle order field - use form value if valid, otherwise use calculated default
    order_value = get_field_value('order', '')
    if order_value and str(order_value).strip():
        with suppress(ValueError, TypeError):
            order = float(order_value)

    # Create FormItem
    # For blank/note questions, allow empty label; for others, provide default
    question_label = get_field_value('label', '')
    if not question_label and question_type.value != 'blank':
        question_label = 'Question'  # Only provide default for non-blank questions

    form_item = FormItem(
        item_type='question',
        section_id=section.id,
        template_id=template.id,  # Add template_id
        version_id=section.version_id,
        label=question_label or '',  # Allow empty label for blank questions
        type=question_type.value,  # Use 'type' field instead of 'question_type' property
        order=order,
        definition=get_field_value('definition', '') or ''
    )

    # Initialize config with default values
    config = {
        'is_required': bool(get_field_value('is_required', '')),
        'layout_column_width': int(get_field_value('layout_column_width', '12')),
        'layout_break_after': bool(get_field_value('layout_break_after', '')),
        'allowed_disaggregation_options': ["total"],  # Not used for questions but kept for consistency
        'age_groups_config': None,  # Not used for questions but kept for consistency
        'allow_data_not_available': bool(get_field_value('allow_data_not_available', '')),
        'allow_not_applicable': bool(get_field_value('allow_not_applicable', '')),
        'indirect_reach': bool(get_field_value('indirect_reach', '')),
        'privacy': (get_field_value('privacy', '') or 'ifrc_network'),
        'allow_over_100': False  # Default to False
    }

    # Handle allow_over_100 - check direct field first, then config JSON
    allow_over_100_val = get_field_value('allow_over_100', '')
    if allow_over_100_val in ['true', 'on', '1']:
        config['allow_over_100'] = True
    else:
        # Fall back to config field if present
        config_field = form_data.get('config')
        if config_field:
            try:
                config_json = json.loads(config_field)
                if 'allow_over_100' in config_json:
                    config['allow_over_100'] = bool(config_json['allow_over_100'])
            except (json.JSONDecodeError, TypeError):
                pass

    # Set the consolidated config
    form_item.config = config

    # Handle options vs calculated lists
    options_source = get_field_value('options_source') or 'manual'
    is_choice_type = question_type.value in ['single_choice', 'multiple_choice']

    if is_choice_type and options_source == 'calculated':
        # Calculated list fields
        lookup_list_id_raw = get_field_value('lookup_list_id')

        # Handle plugin lookup lists (including emergency_operations)
        if lookup_list_id_raw and not lookup_list_id_raw.isdigit():
            # This is a plugin lookup list (non-numeric ID)
            form_item.lookup_list_id = lookup_list_id_raw
            # Display column: provided or default to 'name'
            display_column = get_field_value('list_display_column')
            if not display_column:
                # Prefer sensible defaults for known system/plugin lists
                if lookup_list_id_raw == 'reporting_currency':
                    display_column = 'code'
                else:
                    display_column = 'name'  # Generic default
            form_item.list_display_column = display_column
        else:
            # Regular lookup list from database
            lookup_list_id_int = None
            try:
                if lookup_list_id_raw:
                    lookup_list_id_int = int(lookup_list_id_raw)
            except (ValueError, TypeError):
                lookup_list_id_int = None

            lookup_obj = LookupList.query.get(lookup_list_id_int) if lookup_list_id_int else None
            form_item.lookup_list_id = lookup_list_id_int if lookup_obj else None

            display_column = get_field_value('list_display_column')
            if not display_column and lookup_obj and getattr(lookup_obj, 'columns_config', None):
                try:
                    display_column = lookup_obj.columns_config[0]['name'] if lookup_obj.columns_config else None
                except Exception as e:
                    current_app.logger.debug("columns_config display_column (edit) failed: %s", e)
                    display_column = None
            form_item.list_display_column = display_column

        filters_json_raw = get_field_value('list_filters_json')
        try:
            form_item.list_filters_json = json.loads(filters_json_raw) if filters_json_raw else None
        except (json.JSONDecodeError, TypeError):
            form_item.list_filters_json = None

        # Ensure manual options cleared
        form_item.options_json = None
    else:
        # Manual options (or non-choice type): persist options_json, clear list references
        options_json_str = get_field_value('options_json')
        if options_json_str:
            try:
                parsed_options = json.loads(options_json_str)
            except json.JSONDecodeError:
                parsed_options = None
            form_item.options_json = parsed_options if isinstance(parsed_options, list) else None
        else:
            form_item.options_json = None

        form_item.lookup_list_id = None
        form_item.list_display_column = None
        form_item.list_filters_json = None

    # Handle conditions (save only if meaningful)
    _rel = get_field_value('relevance_condition', '') or ''
    _val = get_field_value('validation_condition', '') or ''
    _msg = get_field_value('validation_message', '') or ''
    form_item.relevance_condition = _rel if is_conditions_meaningful(_rel) else None
    form_item.validation_condition = _val if is_conditions_meaningful(_val) else None
    form_item.validation_message = _msg if _msg else None

    db.session.add(form_item)
    db.session.flush()

    return form_item

def _create_document_field_form_item(template, section, form_data, default_order):
    """Create a new document field form item"""
    # Use the provided default order
    order = default_order

    # Helper function to get field value with or without prefix
    def get_field_value(field_name, prefix='doc_field-'):
        # Try with prefix first, then without
        prefixed_name = f"{prefix}{field_name}"
        return form_data.get(prefixed_name) or form_data.get(field_name)

    # Use section_id from form if provided, otherwise use the section parameter
    form_section_id = get_field_value('section_id')
    target_section_id = int(form_section_id) if form_section_id else section.id
    target_section = FormSection.query.get(target_section_id)

    # Handle order field - use form value if valid, otherwise use calculated default
    order_value = get_field_value('order', '')
    if order_value and str(order_value).strip():
        with suppress(ValueError, TypeError):
            order = float(order_value)

    # Create FormItem
    form_item = FormItem(
        item_type='document_field',
        section_id=target_section_id,
        template_id=template.id,  # Add template_id
        version_id=target_section.version_id if target_section else section.version_id,
        label=get_field_value('label', '') or 'Document Field',  # Provide default label
        order=order,
        description=get_field_value('description', '') or ''
    )

    # Get max_documents value
    max_docs_value = None
    max_docs_raw = get_field_value('max_documents', '')
    if max_docs_raw and str(max_docs_raw).strip():
        try:
            max_docs_value = int(max_docs_raw)
        except (ValueError, TypeError):
            max_docs_value = None

    # Optional document type
    document_type = get_field_value('document_type', '')
    if document_type is not None:
        document_type = str(document_type).strip() or None

    # Initialize config with default values
    config = {
        'is_required': bool(get_field_value('is_required', '')),
        'layout_column_width': int(get_field_value('layout_column_width', '12')),
        'layout_break_after': bool(get_field_value('layout_break_after', '')),
        'max_documents': max_docs_value,  # Add max_documents configuration
        'document_type': document_type,   # Optional: document type from system list
        'show_language': get_field_value('show_language', '') in ['true', 'on', '1', True],
        'show_document_type': get_field_value('show_document_type', '') in ['true', 'on', '1', True],
        'show_year': get_field_value('show_year', '') in ['true', 'on', '1', True],
        'show_public_checkbox': get_field_value('show_public_checkbox', '') in ['true', 'on', '1', True],
        'allow_single_year': get_field_value('allow_single_year', '') in ['true', 'on', '1', True],
        'allow_year_range': get_field_value('allow_year_range', '') in ['true', 'on', '1', True],
        'allow_month_range': get_field_value('allow_month_range', '') in ['true', 'on', '1', True],
        'allowed_disaggregation_options': ["total"],  # Not used for documents but kept for consistency
        'age_groups_config': None,  # Not used for documents but kept for consistency
        'allow_data_not_available': False,  # Not used for documents but kept for consistency
        'allow_not_applicable': False,  # Not used for documents but kept for consistency
        'indirect_reach': False,  # Not used for documents but kept for consistency
        'privacy': (get_field_value('privacy', '') or 'ifrc_network')
    }

    # Set the consolidated config
    form_item.config = config

    # Handle conditions (save only if meaningful)
    _rel = get_field_value('relevance_condition', '') or ''
    form_item.relevance_condition = _rel if is_conditions_meaningful(_rel) else None

    db.session.add(form_item)
    db.session.flush()

    return form_item

def _create_matrix_form_item(template, section, form_data, default_order):
    """Create a new matrix form item"""
    # Use the provided default order
    order = default_order

    # Helper function to get field value with or without prefix
    def get_field_value(field_name, prefix=''):
        # For matrix creation, we don't use prefix since the form submits field names directly
        # Try with prefix first (for backward compatibility), then without
        if prefix:
            prefixed_name = f"{prefix}{field_name}"
            value = form_data.get(prefixed_name)
            if value:
                return value
        return form_data.get(field_name)

    # Use section_id from form if provided, otherwise use the section parameter
    form_section_id = get_field_value('section_id')
    target_section_id = int(form_section_id) if form_section_id else section.id
    target_section = FormSection.query.get(target_section_id)

    # Handle order field - use form value if valid, otherwise use calculated default
    order_value = get_field_value('order')
    if order_value and str(order_value).strip():
        with suppress(ValueError, TypeError):
            order = float(order_value)

    # Create FormItem
    form_item = FormItem(
        item_type='matrix',
        section_id=target_section_id,
        template_id=template.id,
        version_id=target_section.version_id if target_section else section.version_id,
        label=get_field_value('label') or 'Matrix Table',
        order=order,
        description=get_field_value('description') or ''
    )

    # Initialize config with default values including matrix configuration
    matrix_config_raw = get_field_value('matrix_config') or get_field_value('config')
    matrix_config = {}

    # Parse matrix configuration if provided
    if matrix_config_raw:
        try:
            import json
            matrix_config = json.loads(matrix_config_raw)
        except (json.JSONDecodeError, TypeError):
            # If parsing fails, use default empty config
            matrix_config = {
                'type': 'matrix',
                'rows': [],
                'columns': []
            }
    else:
        matrix_config = {
            'type': 'matrix',
            'rows': [],
            'columns': []
        }

    config = {
        'is_required': bool(get_field_value('is_required')),
        'layout_column_width': int(get_field_value('layout_column_width') or '12'),
        'layout_break_after': bool(get_field_value('layout_break_after')),
        'matrix_config': matrix_config,
        'allowed_disaggregation_options': ["total"],  # Not used for matrix but kept for consistency
        'age_groups_config': None,  # Not used for matrix but kept for consistency
        'allow_data_not_available': False,  # Not used for matrix but kept for consistency
        'allow_not_applicable': False,  # Not used for matrix but kept for consistency
        'indirect_reach': False,  # Not used for matrix but kept for consistency
        'privacy': (get_field_value('privacy') or 'ifrc_network')
    }

    # Set the consolidated config
    form_item.config = config

    # Handle list library configuration for advanced matrix mode
    if matrix_config.get('row_mode') == 'list_library':
        if 'lookup_list_id' in matrix_config:
            form_item.lookup_list_id = matrix_config['lookup_list_id']
        if 'list_display_column' in matrix_config:
            form_item.list_display_column = matrix_config['list_display_column']
        if 'list_filters' in matrix_config:
            form_item.list_filters_json = json.dumps(matrix_config['list_filters'])

    # Handle conditions (save only if meaningful)
    _rel = get_field_value('relevance_condition') or ''
    form_item.relevance_condition = _rel if is_conditions_meaningful(_rel) else None

    db.session.add(form_item)
    db.session.flush()

    return form_item

def _create_plugin_form_item(template, section, form_data, item_type, default_order):
    """Create a new plugin form item"""
    try:
        # Extract the plugin type from the item_type (e.g., 'plugin_interactive_map' -> 'interactive_map')
        plugin_type = item_type.replace('plugin_', '')

        # Use the provided default order
        order = default_order

        # Handle order field - use form value if valid, otherwise use calculated default
        order_value = form_data.get('order', '')
        if order_value and str(order_value).strip():
            with suppress(ValueError, TypeError):
                order = float(order_value)

        # Get plugin configuration from form data
        plugin_config = {}
        plugin_config_raw = form_data.get('plugin_config')
        if plugin_config_raw:
            try:
                plugin_config = json.loads(plugin_config_raw) if isinstance(plugin_config_raw, str) else plugin_config_raw
            except (json.JSONDecodeError, TypeError):
                current_app.logger.warning(f"Invalid plugin config JSON for {item_type}: {plugin_config_raw}")
                plugin_config = {}

        # Get label - check if it's meaningful (not empty/whitespace)
        label_value = form_data.get('label', '').strip() if form_data.get('label') else ''
        if not label_value:
            label_value = f'{plugin_type.title()} Field'

        # Get description
        description_value = form_data.get('description', '').strip() if form_data.get('description') else ''

        # Create a new FormItem with the plugin type
        form_item = FormItem(
            template_id=template.id,
            section_id=section.id,
            version_id=section.version_id,
            item_type=item_type,
            label=label_value,
            description=description_value,
            order=order,
            config={
                'is_required': form_data.get('is_required', False),
                'layout_column_width': int(form_data.get('layout_column_width', 12)),
                'layout_break_after': form_data.get('layout_break_after', False),
                'allow_data_not_available': form_data.get('allow_data_not_available', False),
                'allow_not_applicable': form_data.get('allow_not_applicable', False),
                'indirect_reach': form_data.get('indirect_reach', False),
                'privacy': (form_data.get('privacy') or 'ifrc_network'),
                'plugin_type': plugin_type,
                'plugin_config': plugin_config,
                'allow_over_100': False  # Default to False
            }
        )

        # Handle allow_over_100 - check direct field first, then config JSON
        allow_over_100_val = form_data.get('allow_over_100', '')
        if allow_over_100_val in ['true', 'on', '1']:
            form_item.config['allow_over_100'] = True
        else:
            # Fall back to config field if present
            config_field = form_data.get('config')
            if config_field:
                try:
                    config_json = json.loads(config_field)
                    if 'allow_over_100' in config_json:
                        form_item.config['allow_over_100'] = bool(config_json['allow_over_100'])
                except (json.JSONDecodeError, TypeError):
                    pass

        # Handle conditions (save only if meaningful)
        with suppress(Exception):
            _rel = form_data.get('relevance_condition') or ''
            _val = form_data.get('validation_condition') or ''
            _msg = form_data.get('validation_message') or ''
            form_item.relevance_condition = _rel if is_conditions_meaningful(_rel) else None
            form_item.validation_condition = _val if is_conditions_meaningful(_val) else None
            form_item.validation_message = _msg if _msg else None

        # Add to database
        db.session.add(form_item)
        db.session.flush()

        current_app.logger.info(f"Created plugin form item: {item_type} with ID {form_item.id}")
        return form_item

    except Exception as e:
        current_app.logger.error(f"Error creating plugin form item {item_type}: {e}", exc_info=True)
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        return None


def _handle_template_sharing(template, shared_admin_ids, shared_by_user_id, template_name=None):
    """
    Handle template sharing by creating/updating TemplateShare records.

    Args:
        template: The FormTemplate object
        shared_admin_ids: List of user IDs to share the template with
        shared_by_user_id: ID of the user who is sharing the template
        template_name: Optional template name to avoid accessing template.name property
                       (useful during template creation when versions might not be fully persisted)
    """
    current_app.logger.debug(f"_handle_template_sharing called with template_id={template.id}, shared_admin_ids={shared_admin_ids}, shared_by_user_id={shared_by_user_id}")

    if not shared_admin_ids:
        shared_admin_ids = []

    # Get current sharing records for this template
    current_shares = TemplateShare.query.filter_by(template_id=template.id).all()
    current_shared_user_ids = {share.shared_with_user_id for share in current_shares}

    # Convert to set for easier comparison
    new_shared_user_ids = set(shared_admin_ids)

    # Remove shares that are no longer needed
    shares_to_remove = current_shared_user_ids - new_shared_user_ids
    for user_id in shares_to_remove:
        TemplateShare.query.filter_by(
            template_id=template.id,
            shared_with_user_id=user_id
        ).delete()

    # Add new shares
    shares_to_add = new_shared_user_ids - current_shared_user_ids
    for user_id in shares_to_add:
        # Don't share with the owner
        if user_id != template.owned_by:
            share = TemplateShare(
                template_id=template.id,
                shared_with_user_id=user_id,
                shared_by_user_id=shared_by_user_id
            )
            db.session.add(share)

    current_app.logger.info(f"Updated template sharing for template {template.id}: "
                          f"removed {len(shares_to_remove)}, added {len(shares_to_add)}")

    # Log admin action for audit trail if there were changes
    if shares_to_add or shares_to_remove:
        try:
            # Get user names for better audit trail description
            added_users = []
            removed_users = []
            if shares_to_add:
                added_users = User.query.filter(User.id.in_(shares_to_add)).all()
            if shares_to_remove:
                removed_users = User.query.filter(User.id.in_(shares_to_remove)).all()

            description_parts = []
            if added_users:
                added_names = [u.name or u.email for u in added_users]
                description_parts.append(f"Shared with: {', '.join(added_names)}")
            if removed_users:
                removed_names = [u.name or u.email for u in removed_users]
                description_parts.append(f"Removed access: {', '.join(removed_names)}")

            # Use provided template_name or fall back to template.name property
            # During template creation, template_name should be provided to avoid
            # accessing template.name which queries versions relationship
            name_to_use = template_name if template_name is not None else template.name

            log_admin_action(
                action_type='template_sharing_update',
                description=f"Updated sharing for template '{name_to_use}'. " + "; ".join(description_parts),
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, Added: {len(shares_to_add)}, Removed: {len(shares_to_remove)}",
                risk_level='medium'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging template sharing update: {log_error}")


def _populate_template_sharing(form, template):
    """
    Populate the owned_by and shared_with_admins fields with current sharing data.

    Args:
        form: The FormTemplateForm instance
        template: The FormTemplate object
    """
    # Populate the owner field
    form.owned_by.data = template.owned_by

    # Populate the shared users
    current_shares = TemplateShare.query.filter_by(template_id=template.id).all()
    shared_user_ids = [share.shared_with_user_id for share in current_shares]
    form.shared_with_admins.data = shared_user_ids


def _ensure_template_access_or_redirect(template_id, version_id=None):
    """Return redirect response if user lacks template access, otherwise None."""
    if check_template_access(template_id, current_user.id):
        return None

    flash("Access denied. You don't have permission to modify this template.", "warning")
    redirect_kwargs = {"template_id": template_id}
    if version_id:
        redirect_kwargs["version_id"] = version_id
    return redirect(url_for("form_builder.edit_template", **redirect_kwargs))
