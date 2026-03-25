from app.utils.transactions import request_transaction_rollback
from contextlib import suppress
# File: Backoffice/app/routes/admin/content_management.py
from app.utils.datetime_helpers import utcnow
from app.utils.sql_utils import safe_ilike_pattern
"""
Content Management Module - Resources, Publications, and Document Management
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, send_file, send_from_directory, abort
from flask_login import current_user
from app import db
from app.models import (
    Resource, ResourceTranslation, SubmittedDocument,
    PublicSubmission
)
from app.models.assignments import AssignmentEntityStatus
from sqlalchemy import and_, literal
from app.forms.content import ResourceForm
from app.forms.shared import DeleteForm
from app.routes.admin.shared import admin_required, permission_required, permission_required_any, user_has_permission, rbac_guard_audit_exempt
from app.utils.request_utils import is_json_request
from werkzeug.utils import secure_filename
import os
import uuid
import io
from datetime import datetime
from app.utils.redirect_utils import safe_redirect
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_bad_request, json_not_found, json_ok, json_server_error
from app.utils.file_paths import (
    get_resource_upload_path,
    get_admin_documents_upload_path,
    resolve_resource_file,
    resolve_resource_thumbnail,
    resolve_admin_document,
    resolve_admin_document_thumbnail,
    save_stream_to,
    secure_join_filename,
)
from app.utils.error_handling import handle_view_exception
from app.utils.advanced_validation import AdvancedValidator

# Allowed file extensions for uploads
ALLOWED_DOCUMENT_EXTENSIONS = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']
ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp']

bp = Blueprint("content_management", __name__, url_prefix="/admin")

# === Resource Management Routes ===
@bp.route("/resources", methods=["GET"])
@permission_required('admin.resources.manage')
def manage_resources():
    from app.utils.api_pagination import validate_pagination_params
    page, per_page = validate_pagination_params(request.args, default_per_page=10, max_per_page=100)
    search_query = request.args.get('search', '').strip()
    query = Resource.query.order_by(Resource.publication_date.desc(), Resource.created_at.desc())
    if search_query:
        query = query.filter(Resource.default_title.ilike(safe_ilike_pattern(search_query)))
    resources = query.paginate(page=page, per_page=per_page, error_out=False)

    # Return JSON for API requests (mobile app)
    if is_json_request():
        resources_data = []
        for resource in resources.items:
            resources_data.append({
                'id': resource.id,
                'default_title': resource.default_title if hasattr(resource, 'default_title') else None,
                'publication_date': resource.publication_date.isoformat() if hasattr(resource, 'publication_date') and resource.publication_date else None,
                'created_at': resource.created_at.isoformat() if hasattr(resource, 'created_at') and resource.created_at else None,
                'updated_at': resource.updated_at.isoformat() if hasattr(resource, 'updated_at') and resource.updated_at else None,
            })
        return json_ok(
            resources=resources_data,
            count=len(resources_data),
            total=resources.total,
            page=resources.page,
            pages=resources.pages,
        )

    delete_form = DeleteForm()
    return render_template(
        "admin/resources/manage_resources.html",
        title="Manage Resources",
        resources=resources,
        delete_form=delete_form,
        search_query=search_query
    )

@bp.route("/resources/new", methods=["GET", "POST"])
@permission_required('admin.resources.manage')
def new_resource():
    form = ResourceForm()

    if form.validate_on_submit():
        try:
            # Generate unique folder name for this resource
            unique_folder_name = str(uuid.uuid4())
            upload_base_path = get_resource_upload_path()

            # Create new resource
            new_resource = Resource(
                resource_type=form.resource_type.data,
                default_title=form.default_title.data,
                default_description=form.default_description.data,
                publication_date=form.publication_date.data
            )

            db.session.add(new_resource)
            db.session.flush()  # Get the ID

            # Handle multilingual file uploads
            _handle_multilingual_uploads(form, new_resource, upload_base_path, unique_folder_name)

            db.session.flush()
            flash(f"Resource '{new_resource.default_title}' created successfully.", "success")
            return redirect(url_for("content_management.manage_resources"))

        except Exception as e:
            handle_view_exception(
                e,
                GENERIC_ERROR_MESSAGE,
                log_message=f"Error creating resource: {e}"
            )

    return render_template("admin/resources/edit_resource.html",
                         form=form,
                         title="Create New Resource")

@bp.route("/resources/edit/<int:resource_id>", methods=["GET", "POST"])
@permission_required('admin.resources.manage')
def edit_resource(resource_id):
    resource = Resource.query.get_or_404(resource_id)
    form = ResourceForm(obj=resource)

    if form.validate_on_submit():
        try:
            if current_app.config.get('VERBOSE_FORM_DEBUG', False):
                current_app.logger.debug("Form validation passed, processing resource update")

            # Update basic fields
            resource.resource_type = form.resource_type.data
            resource.default_title = form.default_title.data
            resource.default_description = form.default_description.data
            resource.publication_date = form.publication_date.data

            # Handle file updates if new files are uploaded
            upload_base_path = get_resource_upload_path()

            # Extract existing folder name from file paths or generate new one
            unique_folder_name = None
            for translation in resource.translations:
                if translation.file_relative_path:
                    # Extract folder name from existing file path
                    # Expected format: <uuid_folder>/<language>/<filename> or <uuid_folder>\<language>\<filename>
                    # Handle both forward and backward slashes
                    path_parts = translation.file_relative_path.replace('\\', '/').split('/')
                    if len(path_parts) >= 1:
                        unique_folder_name = path_parts[0]
                        current_app.logger.info(f"Extracted folder name from {translation.file_relative_path}: {unique_folder_name}")
                        break

            # If no existing folder found, generate a new one
            if not unique_folder_name:
                unique_folder_name = str(uuid.uuid4())

            _handle_multilingual_uploads(form, resource, upload_base_path, unique_folder_name)

            db.session.flush()
            flash(f"Resource '{resource.default_title}' updated successfully.", "success")
            return redirect(url_for("content_management.manage_resources"))

        except Exception as e:
            handle_view_exception(
                e,
                GENERIC_ERROR_MESSAGE,
                log_message=f"Error updating resource {resource_id}: {e}"
            )
    else:
        if request.method == 'POST':
            current_app.logger.warning("Form validation failed: %s", form.errors)

    # Pre-populate form for GET requests
    if request.method == 'GET':
        form.default_title.data = resource.default_title
        form.default_description.data = resource.default_description
        # Pre-populate per-language fields from ResourceTranslation
        # Use the same language source as the form to ensure dynamically added languages are included
        from app.forms.base import _get_supported_language_codes
        for lang_code in _get_supported_language_codes():
            translation = resource.get_translation(lang_code)
            if translation:
                title_attr = f'title_{lang_code}'
                desc_attr = f'description_{lang_code}'
                if hasattr(form, title_attr):
                    getattr(form, title_attr).data = translation.title or ''
                if hasattr(form, desc_attr):
                    getattr(form, desc_attr).data = translation.description or ''
            else:
                # If no translation exists, pre-populate with default values for English
                if lang_code == 'en':
                    title_attr = f'title_{lang_code}'
                    desc_attr = f'description_{lang_code}'
                    if hasattr(form, title_attr):
                        getattr(form, title_attr).data = resource.default_title or ''
                    if hasattr(form, desc_attr):
                        getattr(form, desc_attr).data = resource.default_description or ''

    return render_template("admin/resources/edit_resource.html",
                         title=f"Edit Resource: {resource.default_title}",
                         form=form,
                         resource=resource)

@bp.route("/resources/delete/<int:resource_id>", methods=["POST"])
@permission_required('admin.resources.manage')
def delete_resource(resource_id):
    resource = Resource.query.get_or_404(resource_id)

    try:
        # Delete associated files and translations
        for translation in resource.translations:
            if translation.file_relative_path:
                _delete_file_and_folder(get_resource_upload_path(), translation.file_relative_path)
            if translation.thumbnail_relative_path:
                _delete_file_and_folder(get_resource_upload_path(), translation.thumbnail_relative_path)

        # Delete database records
        ResourceTranslation.query.filter_by(resource_id=resource_id).delete()
        db.session.delete(resource)
        db.session.flush()

        flash(f"Resource '{resource.default_title}' deleted successfully.", "success")

    except Exception as e:
        handle_view_exception(
            e,
            GENERIC_ERROR_MESSAGE,
            log_message=f"Error deleting resource {resource_id}: {e}"
        )

    return redirect(url_for("content_management.manage_resources"))

@bp.route("/resources/admin_download/<int:resource_id>/<language>", methods=["GET"])
@permission_required('admin.resources.manage')
def download_resource_file_admin(resource_id, language):
    """Admin route to download resource files"""
    resource = Resource.query.get_or_404(resource_id)
    translation = ResourceTranslation.query.filter_by(
        resource_id=resource_id,
        language_code=language
    ).first()

    if not translation or not translation.file_relative_path:
        flash(f"No file found for {language} version of this resource.", "warning")
        return redirect(url_for("content_management.manage_resources"))

    try:
        file_path = resolve_resource_file(translation.file_relative_path)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True,
                           download_name=translation.filename or f"resource_{resource_id}_{language}")
        else:
            flash("File not found on server.", "danger")
            return redirect(url_for("content_management.manage_resources"))

    except Exception as e:
        current_app.logger.error(f"Error downloading resource file: {e}", exc_info=True)
        flash("Error downloading file.", "danger")
        return redirect(url_for("content_management.manage_resources"))

@bp.route("/resources/<int:resource_id>/admin_download_thumbnail/<language>", methods=["GET"])
@permission_required('admin.resources.manage')
def download_resource_thumbnail_admin(resource_id, language):
    """Admin route to download resource thumbnails"""
    current_app.logger.info(f"Download thumbnail route called for resource {resource_id}, language {language}")
    current_app.logger.info(f"Request URL: {request.url}")
    current_app.logger.info(f"Request method: {request.method}")

    resource = Resource.query.get_or_404(resource_id)
    current_app.logger.info(f"Found resource: {resource.default_title}")

    translation = ResourceTranslation.query.filter_by(
        resource_id=resource_id,
        language_code=language
    ).first()

    if not translation:
        current_app.logger.warning(f"No translation found for resource {resource_id}, language {language}")
        flash(f"No thumbnail found for {language} version.", "warning")
        return redirect(url_for("content_management.manage_resources"))

    if not translation.thumbnail_relative_path:
        current_app.logger.warning(f"No thumbnail path found for translation {translation.id}")
        flash(f"No thumbnail found for {language} version.", "warning")
        return redirect(url_for("content_management.manage_resources"))

    current_app.logger.info(f"Translation found with thumbnail path: {translation.thumbnail_relative_path}")

    try:
        upload_base_path = get_resource_upload_path()
        current_app.logger.info(f"Upload base path: {upload_base_path}")

        # Resolve thumbnail absolute path safely
        full_thumbnail_path = resolve_resource_thumbnail(translation.thumbnail_relative_path)

        current_app.logger.info(f"Full thumbnail path: {full_thumbnail_path}")
        current_app.logger.info(f"Thumbnail exists: {os.path.exists(full_thumbnail_path)}")

        if os.path.exists(full_thumbnail_path):
            current_app.logger.info(f"Serving thumbnail file: {full_thumbnail_path}")

            # Set proper headers for image serving
            response = send_file(
                full_thumbnail_path,
                mimetype='image/png',
                as_attachment=False,  # Don't force download, display in browser
                download_name=f"thumbnail_{resource_id}_{language}.png"
            )

            # Add cache control headers
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'

            current_app.logger.info(f"Response headers: {dict(response.headers)}")
            current_app.logger.info(f"Response status: {response.status_code}")

            return response
        else:
            current_app.logger.error(f"Thumbnail file not found at: {full_thumbnail_path}")
            flash("Thumbnail file not found on server.", "danger")
            return redirect(url_for("content_management.manage_resources"))

    except Exception as e:
        current_app.logger.error(f"Error downloading thumbnail: {e}", exc_info=True)
        flash("Error downloading thumbnail.", "danger")
        return redirect(url_for("content_management.manage_resources"))

@bp.route("/resources/<int:resource_id>/generate-thumbnail/<language_code>", methods=["POST"])
@permission_required('admin.resources.manage')
def generate_resource_thumbnail(resource_id, language_code):
    """Generate thumbnail for a specific resource language version"""

    # Check PDF processing capability first
    if not _check_pdf_processing_capability():
        current_app.logger.error("PDF processing libraries not available")
        if is_json_request():
            return json_server_error('PDF processing libraries not available on server.')
        else:
            flash("PDF processing libraries not available on server.", "danger")
            return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

    try:
        resource = Resource.query.get_or_404(resource_id)
        current_app.logger.info(f"Found resource: {resource.default_title}")

        translation = ResourceTranslation.query.filter_by(
            resource_id=resource_id,
            language_code=language_code
        ).first()

        if not translation:
            current_app.logger.warning(f"No translation found for resource {resource_id}, language {language_code}")
            if is_json_request():
                return json_bad_request(f'No file found for {language_code} version.')
            else:
                flash(f"No file found for {language_code} version.", "warning")
                return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

        if not translation.file_relative_path:
            current_app.logger.warning(f"No file path found for translation {translation.id}")
            if is_json_request():
                return json_bad_request(f'No file found for {language_code} version.')
            else:
                flash(f"No file found for {language_code} version.", "warning")
                return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

        current_app.logger.info(f"Processing file: {translation.file_relative_path}")

        upload_base_path = get_resource_upload_path()
        file_path = resolve_resource_file(translation.file_relative_path)

        current_app.logger.info(f"Full file path: {file_path}")
        current_app.logger.info(f"File exists: {os.path.exists(file_path)}")

        if not os.path.exists(file_path):
            current_app.logger.error(f"File not found at path: {file_path}")
            if is_json_request():
                return json_not_found('File not found on server.')
            else:
                flash("File not found on server.", "danger")
                return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

        if file_path.lower().endswith('.pdf'):
            # Extract folder name from existing file path
            # Expected format: <uuid_folder>/<language>/<filename> or <uuid_folder>\<language>\<filename>
            # Handle both forward and backward slashes
            path_parts = translation.file_relative_path.replace('\\', '/').split('/')
            current_app.logger.info(f"Path parts after normalization: {path_parts}")

            if len(path_parts) >= 1:
                unique_folder_name = path_parts[0]
                current_app.logger.info(f"Extracted folder name: {unique_folder_name}")

                # Check if the path has the expected language subfolder structure
                if len(path_parts) >= 2 and path_parts[1] == language_code:
                    current_app.logger.info(f"Path has correct language subfolder structure")
                else:
                    current_app.logger.warning(f"Path does not have expected language subfolder structure. Expected: {unique_folder_name}/{language_code}/filename, Got: {translation.file_relative_path}")
                    # For existing files without proper structure, we'll still try to generate thumbnail
                    # but log a warning
            else:
                current_app.logger.error(f"Invalid file path structure: {translation.file_relative_path}")
                if is_json_request():
                    return json_bad_request('Invalid file path structure.')
                else:
                    flash("Invalid file path structure.", "danger")
                    return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

            current_app.logger.info(f"Generating thumbnail for PDF: {file_path}")
            thumbnail_path = _generate_pdf_thumbnail(
                file_path,
                unique_folder_name,
                upload_base_path,
                language_code
            )

            if thumbnail_path:
                current_app.logger.info(f"Thumbnail generated successfully: {thumbnail_path}")
                translation.thumbnail_relative_path = thumbnail_path
                db.session.flush()

                if is_json_request():
                    return json_ok(
                        message=f'Thumbnail generated successfully for {language_code} version.',
                        thumbnail_path=thumbnail_path,
                    )
                else:
                    flash(f"Thumbnail generated successfully for {language_code} version.", "success")
            else:
                current_app.logger.error("Thumbnail generation failed")
                if is_json_request():
                    return json_server_error('Error generating thumbnail.')
                else:
                    flash("Error generating thumbnail.", "danger")
        else:
            current_app.logger.warning(f"File is not a PDF: {file_path}")
            if is_json_request():
                return json_bad_request('Thumbnail generation is only supported for PDF files.')
            else:
                flash("Thumbnail generation is only supported for PDF files.", "warning")

    except Exception as e:
        current_app.logger.error(f"Error generating thumbnail: {e}", exc_info=True)
        request_transaction_rollback()

        if is_json_request():
            return json_server_error(GENERIC_ERROR_MESSAGE)
        else:
            flash("Error generating thumbnail.", "danger")

    # For non-AJAX requests, redirect back to edit page
    if not is_json_request():
        return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

    # For AJAX requests, return a default response if we reach here
    return json_server_error('Unexpected error occurred.')

@bp.route("/resources/<int:resource_id>/delete-thumbnail/<language_code>", methods=["POST"])
@permission_required('admin.resources.manage')
def delete_resource_thumbnail(resource_id, language_code):
    """Delete thumbnail for a specific resource language version"""
    current_app.logger.info(f"Thumbnail deletion requested for resource {resource_id}, language {language_code}")

    try:
        resource = Resource.query.get_or_404(resource_id)
        current_app.logger.info(f"Found resource: {resource.default_title}")

        translation = ResourceTranslation.query.filter_by(
            resource_id=resource_id,
            language_code=language_code
        ).first()

        if not translation:
            current_app.logger.warning(f"No translation found for resource {resource_id}, language {language_code}")
            if is_json_request():
                return json_bad_request(f'No translation found for {language_code} version.')
            else:
                flash(f"No translation found for {language_code} version.", "warning")
                return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

        if not translation.thumbnail_relative_path:
            current_app.logger.warning(f"No thumbnail found for translation {translation.id}")
            if is_json_request():
                return json_bad_request(f'No thumbnail found for {language_code} version.')
            else:
                flash(f"No thumbnail found for {language_code} version.", "warning")
                return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

        current_app.logger.info(f"Deleting thumbnail: {translation.thumbnail_relative_path}")

        # Delete thumbnail file from filesystem
        thumbnail_path = resolve_resource_thumbnail(translation.thumbnail_relative_path)

        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
            current_app.logger.info(f"Deleted thumbnail file: {thumbnail_path}")
        else:
            current_app.logger.warning(f"Thumbnail file not found: {thumbnail_path}")

        # Clear thumbnail fields in database
        translation.thumbnail_relative_path = None
        translation.thumbnail_filename = None
        db.session.flush()

        current_app.logger.info(f"Thumbnail deleted successfully for resource {resource_id}, language {language_code}")

        if is_json_request():
            return json_ok(message=f'Thumbnail deleted successfully for {language_code} version.')
        else:
            flash(f"Thumbnail deleted successfully for {language_code} version.", "success")
            return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

    except Exception as e:
        current_app.logger.error(f"Error deleting thumbnail: {e}", exc_info=True)
        request_transaction_rollback()

        if is_json_request():
            return json_server_error(GENERIC_ERROR_MESSAGE)
        else:
            flash("Error deleting thumbnail.", "danger")
            return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

# === Publication Management Routes ===
@bp.route("/publications", methods=["GET"])
@permission_required('admin.publications.manage')
def manage_publications():
    publications = Resource.query.filter_by(resource_type='publication').order_by(Resource.created_at.desc()).all()
    delete_form = DeleteForm()
    return render_template("admin/publications/manage_publications.html",
                         publications=publications,
                         delete_form=delete_form,
                         title="Manage Publications")

@bp.route("/publications/new", methods=["GET", "POST"])
@permission_required('admin.publications.manage')
def new_publication():
    form = ResourceForm()

    if form.validate_on_submit():
        try:
            # Generate unique folder name for this publication
            unique_folder_name = str(uuid.uuid4())

            # Create new publication
            new_publication = Resource(
                resource_type=form.resource_type.data,
                default_title=form.default_title.data,
                default_description=form.default_description.data,
                publication_date=form.publication_date.data
            )

            db.session.add(new_publication)
            db.session.flush()  # Get the ID

            # Handle multilingual file uploads using ResourceForm's language-specific fields
            upload_base_path = get_resource_upload_path()
            unique_folder_name = str(uuid.uuid4())
            _handle_multilingual_uploads(form, new_publication, upload_base_path, unique_folder_name)

            db.session.flush()

            flash(f"Publication '{new_publication.default_title}' created successfully.", "success")
            return redirect(url_for("content_management.manage_publications"))

        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")
            current_app.logger.error(f"Error creating publication: {e}", exc_info=True)

    return render_template("admin/publications/edit_publication.html",
                         form=form,
                         title="Create New Publication")

@bp.route("/publications/edit/<int:publication_id>", methods=["GET", "POST"])
@permission_required('admin.publications.manage')
def edit_publication(publication_id):
    publication = Resource.query.get_or_404(publication_id)
    form = ResourceForm(obj=publication)

    if form.validate_on_submit():
        try:
            # Update basic fields
            publication.resource_type = form.resource_type.data
            publication.default_title = form.default_title.data
            publication.default_description = form.default_description.data
            publication.publication_date = form.publication_date.data

            # Handle multilingual file uploads using ResourceForm's language-specific fields
            upload_base_path = get_resource_upload_path()

            # Extract existing folder name from file paths or generate new one
            unique_folder_name = None
            for translation in publication.translations:
                if translation.file_relative_path:
                    # Extract folder name from existing file path
                    path_parts = translation.file_relative_path.replace('\\', '/').split('/')
                    if len(path_parts) >= 1:
                        unique_folder_name = path_parts[0]
                        break

            # If no existing folder found, generate a new one
            if not unique_folder_name:
                unique_folder_name = str(uuid.uuid4())

            _handle_multilingual_uploads(form, publication, upload_base_path, unique_folder_name)

            db.session.flush()
            flash(f"Publication '{publication.default_title}' updated successfully.", "success")
            return redirect(url_for("content_management.manage_publications"))

        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")
            current_app.logger.error(f"Error updating publication {publication_id}: {e}", exc_info=True)

    return render_template("admin/publications/edit_publication.html",
                         title=f"Edit Publication: {publication.default_title}",
                         form=form,
                         publication=publication)

@bp.route("/publications/delete/<int:publication_id>", methods=["POST"])
@permission_required('admin.publications.manage')
def delete_publication(publication_id):
    publication = Resource.query.get_or_404(publication_id)

    try:
        # Delete database record (file handling is now done through ResourceTranslation model)
        db.session.delete(publication)
        db.session.flush()

        flash(f"Publication '{publication.default_title}' deleted successfully.", "success")

    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error deleting publication {publication_id}: {e}", exc_info=True)

    return redirect(url_for("content_management.manage_publications"))

@bp.route("/publications/admin_download/<int:publication_id>", methods=["GET"])
@permission_required('admin.publications.manage')
def download_publication_file_admin(publication_id):
    """Admin route to download publication files (supports per-language files)."""
    publication = Resource.query.get_or_404(publication_id)
    requested_language = request.args.get("language") or request.args.get("lang")

    translations_with_files = (
        publication.translations
        .filter(ResourceTranslation.file_relative_path.isnot(None))  # type: ignore[attr-defined]
        .all()
    )

    translation = None
    if requested_language:
        translation = next(
            (tr for tr in translations_with_files if tr.language_code == requested_language),
            None
        )
        if not translation:
            flash(f"No {requested_language.upper()} version found for this publication.", "warning")
            return redirect(url_for("content_management.manage_publications"))
    else:
        available_codes = [tr.language_code for tr in translations_with_files]
        best_match = request.accept_languages.best_match(available_codes) if available_codes else None
        preferred_order = []
        if best_match:
            preferred_order.append(best_match)
        preferred_order.append('en')

        for code in preferred_order:
            translation = next((tr for tr in translations_with_files if tr.language_code == code), None)
            if translation:
                break

        if not translation and translations_with_files:
            translation = translations_with_files[0]

    if not translation or not translation.file_relative_path:
        flash("No file available to download for this publication.", "warning")
        return redirect(url_for("content_management.manage_publications"))

    try:
        file_path = resolve_resource_file(translation.file_relative_path)
    except Exception as exc:
        current_app.logger.error(f"Failed to resolve publication file path: {exc}", exc_info=True)
        flash("Unable to locate the requested file on the server.", "danger")
        return redirect(url_for("content_management.manage_publications"))

    if not os.path.exists(file_path):
        flash("File not found on the server. It may have been removed.", "danger")
        return redirect(url_for("content_management.manage_publications"))

    download_name = translation.filename or os.path.basename(file_path)
    return send_file(
        file_path,
        as_attachment=True,
        download_name=download_name
    )

# === Document Management Routes ===
@bp.route("/documents", methods=["GET"])
@permission_required("admin.documents.manage")
def manage_documents():
    """Manage submitted documents (both regular and public)"""
    from app.models import Country, User, AssignedForm
    from app.utils.app_settings import get_document_types
    from config import Config

    # Load document types from database and update config for template access
    document_types = get_document_types(default=Config.DOCUMENT_TYPES)
    current_app.config['DOCUMENT_TYPES'] = document_types
    # Also update jinja globals to ensure template has access to latest values
    with suppress(Exception):
        current_app.jinja_env.globals['DOCUMENT_TYPES'] = document_types

    # Permission is enforced by decorator: @permission_required("admin.documents.manage")

    # Get regular submitted documents with related data (both standalone and assignment-linked)
    # Query standalone documents (with direct country_id)
    standalone_docs_query = db.session.query(
        SubmittedDocument,
        SubmittedDocument.status.label('status'),
        Country,
        User,
        SubmittedDocument.uploaded_at.label('uploaded_at'),
        db.literal(None).label('assignment_period')
    ).join(User, SubmittedDocument.uploaded_by_user_id == User.id)\
     .join(Country, SubmittedDocument.country_id == Country.id)\
     .filter(SubmittedDocument.country_id.isnot(None))\
     .order_by(SubmittedDocument.uploaded_at.desc())

    # Query assignment-linked documents (with assignment_entity_status_id)
    assignment_docs_query = db.session.query(
        SubmittedDocument,
        SubmittedDocument.status.label('status'),
        Country,
        User,
        SubmittedDocument.uploaded_at.label('uploaded_at'),
        AssignedForm.period_name.label('assignment_period')
    ).join(User, SubmittedDocument.uploaded_by_user_id == User.id)\
     .join(AssignmentEntityStatus, SubmittedDocument.assignment_entity_status_id == AssignmentEntityStatus.id)\
     .join(Country, and_(AssignmentEntityStatus.entity_id == Country.id, AssignmentEntityStatus.entity_type == 'country'))\
     .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)\
     .filter(SubmittedDocument.assignment_entity_status_id.isnot(None))\
     .order_by(SubmittedDocument.uploaded_at.desc())

    show_country_column = True

    # Combine both queries after applying any filters
    standalone_docs = standalone_docs_query.all()
    assignment_docs = assignment_docs_query.all()
    regular_docs = standalone_docs + assignment_docs

    # Get public submitted documents with related data
    # Note: SubmittedDocument now handles both internal and public submissions
    # These come from the parent PublicSubmission
    # PublicSubmission doesn't have a submitted_by field, it has submitter_name and submitter_email
    public_docs_query = db.session.query(
        SubmittedDocument,
        PublicSubmission.status.label('status'),
        Country,
        PublicSubmission.submitter_name.label('user_name'),
        PublicSubmission.submitted_at.label('uploaded_at'),
        db.literal(None).label('assignment_period')
    ).join(
        PublicSubmission,
        SubmittedDocument.public_submission_id == PublicSubmission.id
    ).join(
        Country,
        PublicSubmission.country_id == Country.id
    ).order_by(PublicSubmission.submitted_at.desc())

    public_docs = public_docs_query.all()

    # Combine both types of documents
    documents = regular_docs + public_docs

    # Return JSON for API requests (mobile app)
    if is_json_request():
        documents_data = []
        for doc_row in documents:
            # Handle Row/tuple results from queries - SQLAlchemy returns Row objects
            # Try accessing by class name first (SQLAlchemy Row supports this)
            try:
                doc = getattr(doc_row, 'SubmittedDocument', None)
                if doc is None:
                    # Fallback to index access
                    doc = doc_row[0] if hasattr(doc_row, '__getitem__') else doc_row
            except (AttributeError, IndexError, TypeError):
                # If that fails, try index access
                try:
                    doc = doc_row[0] if hasattr(doc_row, '__getitem__') else doc_row
                except (IndexError, TypeError):
                    doc = doc_row

            # Extract other fields from the row
            try:
                status = getattr(doc_row, 'status', None)
                if status is None and hasattr(doc_row, '__getitem__'):
                    try:
                        status = doc_row[1]
                    except (IndexError, TypeError):
                        status = getattr(doc, 'status', None)
            except (AttributeError, IndexError):
                status = getattr(doc, 'status', None)

            try:
                country = getattr(doc_row, 'Country', None)
                if country is None and hasattr(doc_row, '__getitem__'):
                    try:
                        country = doc_row[2]
                    except (IndexError, TypeError):
                        country = None
            except (AttributeError, IndexError):
                country = None

            try:
                user = getattr(doc_row, 'User', None)
                if user is None and hasattr(doc_row, '__getitem__'):
                    try:
                        user = doc_row[3]
                    except (IndexError, TypeError):
                        user = None
            except (AttributeError, IndexError):
                user = None

            try:
                uploaded_at = getattr(doc_row, 'uploaded_at', None)
                if uploaded_at is None and hasattr(doc_row, '__getitem__'):
                    try:
                        uploaded_at = doc_row[4]
                    except (IndexError, TypeError):
                        uploaded_at = getattr(doc, 'uploaded_at', None)
            except (AttributeError, IndexError):
                uploaded_at = getattr(doc, 'uploaded_at', None)

            try:
                assignment_period = getattr(doc_row, 'assignment_period', None)
                if assignment_period is None and hasattr(doc_row, '__getitem__'):
                    try:
                        assignment_period = doc_row[5]
                    except (IndexError, TypeError):
                        assignment_period = None
            except (AttributeError, IndexError):
                assignment_period = None

            # Get user name - try from row first (for public submissions)
            uploaded_by_name = None
            try:
                uploaded_by_name = getattr(doc_row, 'user_name', None)
            except AttributeError:
                pass
            if not uploaded_by_name and user and hasattr(user, 'name'):
                uploaded_by_name = user.name

            # Determine if public
            is_public = getattr(doc, 'public_submission_id', None) is not None

            documents_data.append({
                'id': getattr(doc, 'id', None),
                'file_name': getattr(doc, 'filename', None),
                'document_type': getattr(doc, 'document_type', None),
                'language': getattr(doc, 'language', None),
                'period': getattr(doc, 'period', None),
                'status': str(status) if status else None,
                'country_name': getattr(country, 'name', None) if country else None,
                'uploaded_by_name': uploaded_by_name,
                'uploaded_at': uploaded_at.isoformat() if uploaded_at else None,
                'assignment_period': assignment_period,
                'is_public': is_public,
            })
        return json_ok(documents=documents_data, count=len(documents_data))

    # Countries for upload modal select: admin documents page shows all countries
    countries = Country.query.all()

    return render_template("admin/documents/documents.html",
                         documents=documents,
                         countries=countries,
                          show_country_column=show_country_column,
                         title="Manage Documents")

@bp.route("/documents/serve/<int:doc_id>", methods=["GET"])
@rbac_guard_audit_exempt("Intentionally public for rendering approved public cover images.")
def serve_document_file(doc_id):
    """Serve a document file for display (not download) - used for cover images"""
    document = SubmittedDocument.query.get_or_404(doc_id)

    # For cover images, we can serve them publicly since they're meant to be displayed
    if document.document_type != 'Cover Image' or not document.is_public:
        abort(404)

    try:
        file_path = resolve_admin_document(document.storage_path)

        if file_path and os.path.exists(file_path):
            # Check if it's an image file
            if document.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                return send_file(file_path, mimetype='image/jpeg')
            else:
                # For non-image files, redirect to download
                return redirect(url_for('content_management.download_document', doc_id=doc_id))
        else:
            abort(404)

    except Exception as e:
        current_app.logger.error(f"Error serving document file: {e}", exc_info=True)
        abort(404)

@bp.route("/documents/download/<int:doc_id>", methods=["GET"])
@permission_required_any('admin.documents.manage', 'assignment.documents.upload')
def download_document(doc_id):
    """Download a submitted document"""
    # Try regular documents first
    document = SubmittedDocument.query.get(doc_id)
    doc_country_id = None
    if not document:
        # Document not found in regular documents
        # All documents are now in SubmittedDocument table
        pass
    else:
        # Determine country id for authorization
        if getattr(document, 'country_id', None):
            doc_country_id = document.country_id
        elif getattr(document, 'assignment_entity_status_id', None):
            aes = AssignmentEntityStatus.query.get(document.assignment_entity_status_id)
            doc_country_id = aes.entity_id if aes and aes.entity_type == 'country' else None

    if not document:
        flash("Document not found.", "danger")
        return redirect(url_for("content_management.manage_documents"))

    # Authorization: system managers (full access), admins with permission, or focal points with matching country
    from app.services.authorization_service import AuthorizationService
    is_admin_with_perm = AuthorizationService.has_rbac_permission(current_user, 'admin.documents.manage')
    is_system_manager = AuthorizationService.is_system_manager(current_user)
    if not (is_admin_with_perm or is_system_manager):
        user_country_ids = [c.id for c in current_user.countries]
        if not doc_country_id or doc_country_id not in user_country_ids:
            flash("Access denied. Document access permission required.", "warning")
            return redirect(url_for("main.dashboard"))

    try:
        file_path = resolve_admin_document(document.storage_path)
        if file_path and os.path.exists(file_path):
            return send_file(file_path, as_attachment=True,
                           download_name=document.filename)
        else:
            flash("File not found on server.", "danger")
            return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

    except Exception as e:
        current_app.logger.error(f"Error downloading document: {e}", exc_info=True)
        flash("Error downloading file.", "danger")
        return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

@bp.route("/documents/delete/<int:doc_id>", methods=["POST"])
@permission_required_any('admin.documents.manage', 'assignment.documents.upload')
def delete_document(doc_id):
    """Delete a submitted document"""
    # Try regular documents first
    document = SubmittedDocument.query.get(doc_id)
    doc_type = "regular"

    if not document:
        # Document not found - all documents are now in SubmittedDocument table
        pass

    if not document:
        flash("Document not found.", "danger")
        return redirect(url_for("content_management.manage_documents"))

    # Authorization: system managers (full access), admins with permission, or focal points with matching country
    from app.services.authorization_service import AuthorizationService
    is_admin_with_perm = AuthorizationService.has_rbac_permission(current_user, 'admin.documents.manage')
    is_system_manager = AuthorizationService.is_system_manager(current_user)
    if not (is_admin_with_perm or is_system_manager):
        # Non-admins need the Assignment "Documents (Upload)" capability to manage docs here
        if not AuthorizationService.has_rbac_permission(current_user, 'assignment.documents.upload'):
            flash("Access denied. Document access permission required.", "warning")
            return redirect(url_for("main.dashboard"))
        # Determine country id for authorization
        doc_country_id = None
        # All documents are now in SubmittedDocument table
        if getattr(document, 'country_id', None):
            doc_country_id = document.country_id
        elif getattr(document, 'assignment_entity_status_id', None):
            aes = AssignmentEntityStatus.query.get(document.assignment_entity_status_id)
            doc_country_id = aes.entity_id if aes and aes.entity_type == 'country' else None
        elif getattr(document, 'document_country_id', None):
            doc_country_id = document.document_country_id

        user_country_ids = [c.id for c in current_user.countries]
        if not doc_country_id or doc_country_id not in user_country_ids:
            flash("Access denied. Document access permission required.", "warning")
            return redirect(url_for("main.dashboard"))
        # Focal points can only delete documents they uploaded
        if getattr(document, "uploaded_by_user_id", None) != getattr(current_user, "id", None):
            flash("Access denied. You can only delete documents you uploaded.", "warning")
            return redirect(url_for("main.dashboard"))

    try:
        # Delete file from filesystem
        # `storage_path` is stored as a relative path under the admin documents upload dir.
        # Always resolve via helper to avoid orphan files (and to ensure path safety).
        resolved_path = resolve_admin_document(getattr(document, 'storage_path', None))
        if resolved_path and os.path.exists(resolved_path):
            os.remove(resolved_path)

        # Delete database record
        db.session.delete(document)
        db.session.flush()

        flash(f"Document '{document.filename}' deleted successfully.", "success")

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error deleting document {doc_id}: {e}", exc_info=True)
        flash("Error deleting document.", "danger")

    return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

@bp.route("/documents/upload", methods=["GET", "POST"])
@permission_required_any('admin.documents.manage', 'assignment.documents.upload')
def upload_document():
    """Upload a new document"""
    if request.method == 'POST':
        try:
            # UI policy: uploading on this screen requires the Assignment "Documents (Upload)" capability (or admin/system).
            # Admins/System Managers: allowed via admin.documents.manage or role.
            # Non-admins: require assignment.documents.upload.
            from app.services.authorization_service import AuthorizationService
            is_admin_with_perm = AuthorizationService.has_rbac_permission(current_user, 'admin.documents.manage')
            is_system_manager = AuthorizationService.is_system_manager(current_user)
            if not (is_admin_with_perm or is_system_manager):
                if not AuthorizationService.has_rbac_permission(current_user, 'assignment.documents.upload'):
                    flash("Access denied. Document upload permission required.", "warning")
                    return safe_redirect(request.args.get("next"), default_route="main.dashboard")

            if 'document' not in request.files:
                flash("No file selected.", "danger")
                # SECURITY: Use request.path instead of request.url to prevent query param injection
                return redirect(request.path)

            file = request.files['document']
            if file.filename == '':
                flash("No file selected.", "danger")
                # SECURITY: Use request.path instead of request.url to prevent query param injection
                return redirect(request.path)

            if file:
                filename = secure_filename(file.filename)

                # SECURITY: Validate file upload before saving
                # Define allowed document extensions
                ALLOWED_DOC_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv'}
                ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
                MAX_FILE_SIZE_MB = 50  # 50MB max for documents

                # Check file extension
                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext not in ALLOWED_DOC_EXTENSIONS and file_ext not in ALLOWED_IMAGE_EXTENSIONS:
                    flash(f"File type '{file_ext}' is not allowed. Allowed types: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, CSV, and images.", "danger")
                    # SECURITY: Use request.path instead of request.url to prevent query param injection
                    return redirect(request.path)

                # Check file size
                file.seek(0, 2)  # Seek to end
                file_size = file.tell()
                file.seek(0)  # Reset to beginning
                max_size_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
                if file_size > max_size_bytes:
                    flash(f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB.", "danger")
                    # SECURITY: Use request.path instead of request.url to prevent query param injection
                    return redirect(request.path)

                # Validate MIME type to prevent spoofing
                try:
                    from app.utils.advanced_validation import AdvancedValidator
                    is_valid_mime, detected_mime = AdvancedValidator.validate_mime_type(file, [file_ext])
                    if not is_valid_mime and detected_mime:
                        current_app.logger.warning(f"Document upload MIME mismatch: claimed {file_ext}, detected {detected_mime}")
                        flash("File content does not match its extension. Please upload a valid file.", "danger")
                        # SECURITY: Use request.path instead of request.url to prevent query param injection
                        return redirect(request.path)
                except Exception as e:
                    current_app.logger.warning(f"MIME validation error (allowing upload): {e}")

                # Save file under admin_documents as relative path
                upload_dir = get_admin_documents_upload_path()
                rel_path = save_stream_to(upload_dir, secure_join_filename(None, filename), file)

                # Parse form fields
                country_id = request.form.get('country_id', type=int)
                document_type = request.form.get('document_type', type=str)
                language = request.form.get('language', type=str)
                period = request.form.get('year', type=str)  # Form field is still named 'year' but contains period string
                is_public = request.form.get('is_public') == 'on'
                status = request.form.get('status', default='Pending')

                # Handle thumbnail upload
                thumbnail_file = request.files.get('thumbnail')
                thumbnail_filename = None
                thumbnail_relative_path = None

                if thumbnail_file and thumbnail_file.filename:
                    thumbnail_filename = secure_filename(thumbnail_file.filename)

                    # SECURITY: Validate thumbnail is an image
                    thumb_ext = os.path.splitext(thumbnail_filename)[1].lower()
                    if thumb_ext not in ALLOWED_IMAGE_EXTENSIONS:
                        flash(f"Thumbnail must be an image. Allowed types: JPG, PNG, GIF, WEBP.", "warning")
                        # Continue without thumbnail rather than blocking the upload
                        thumbnail_filename = None
                    else:
                        # Check thumbnail size (max 5MB)
                        thumbnail_file.seek(0, 2)
                        thumb_size = thumbnail_file.tell()
                        thumbnail_file.seek(0)
                        if thumb_size > 5 * 1024 * 1024:
                            flash("Thumbnail too large. Maximum size is 5MB.", "warning")
                            thumbnail_filename = None
                        else:
                            thumb_rel = f"thumbnails/thumb_{filename}_{thumbnail_filename}"
                            thumbnail_relative_path = save_stream_to(upload_dir, thumb_rel, thumbnail_file)

                # Handle Cover Image document type specially
                if document_type == 'Cover Image':
                    language = None  # Cover images don't have language
                    period = None      # Cover images don't have period
                    is_public = True # Cover images are always public

                # Authorization for non-admins: must be uploading for their own country
                if not (is_admin_with_perm or is_system_manager):
                    user_country_ids = [c.id for c in current_user.countries]
                    if not country_id or country_id not in user_country_ids:
                        flash("Access denied. You can only upload documents for your assigned countries.", "warning")
                        return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

                # Create database record
                document = SubmittedDocument(
                    filename=filename,
                    storage_path=rel_path,
                    uploaded_by_user_id=current_user.id,
                    uploaded_at=utcnow(),
                    country_id=country_id,
                    document_type=document_type,
                    language=language,
                    is_public=is_public,
                    period=period,
                    status=status if (is_admin_with_perm or is_system_manager) else 'Pending',
                    thumbnail_filename=thumbnail_filename,
                    thumbnail_relative_path=thumbnail_relative_path
                )

                db.session.add(document)
                db.session.flush()  # Flush to get document.id

                current_app.logger.info(
                    f"[DOCUMENT_UPLOAD] Document uploaded successfully. ID: {document.id}, "
                    f"filename: '{document.filename}', status: '{document.status}', "
                    f"country_id: {country_id}, uploaded_by: {current_user.id} ({current_user.email})"
                )

                # Send notifications for standalone document uploads
                try:
                    from app.utils.notifications import notify_standalone_document_uploaded
                    current_app.logger.info(
                        f"[DOCUMENT_UPLOAD] Triggering notification function for document {document.id}"
                    )
                    notification_results = notify_standalone_document_uploaded(document, country_id)
                    current_app.logger.info(
                        f"[DOCUMENT_UPLOAD] Notification function returned {len(notification_results) if notification_results else 0} notifications"
                    )
                except Exception as e:
                    current_app.logger.error(
                        f"[DOCUMENT_UPLOAD] Error sending document upload notifications: {str(e)}",
                        exc_info=True
                    )
                    # Don't fail the upload if notifications fail

                db.session.flush()

                flash(f"Document '{filename}' uploaded successfully.", "success")
                return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error(f"Error uploading document: {e}", exc_info=True)
            flash("Error uploading document.", "danger")

    # Redirect to documents page instead of rendering non-existent template
    return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

@bp.route("/documents/edit/<int:doc_id>", methods=["GET", "POST"])
@permission_required_any('admin.documents.manage', 'assignment.documents.upload')
def edit_document(doc_id):
    """Edit document metadata"""
    # Try regular documents first
    document = SubmittedDocument.query.get(doc_id)
    if not document:
        # Document not found - all documents are now in SubmittedDocument table
        pass

    if not document:
        flash("Document not found.", "danger")
        return redirect(url_for("content_management.manage_documents"))

    # Authorization: system managers (full access), admins with permission, or focal points with matching country
    from app.services.authorization_service import AuthorizationService
    is_admin_with_perm = AuthorizationService.has_rbac_permission(current_user, 'admin.documents.manage')
    is_system_manager = AuthorizationService.is_system_manager(current_user)
    if not (is_admin_with_perm or is_system_manager):
        # Non-admins need the Assignment "Documents (Upload)" capability to manage docs here
        if not AuthorizationService.has_rbac_permission(current_user, 'assignment.documents.upload'):
            flash("Access denied. Document edit permission required.", "warning")
            return redirect(url_for("main.dashboard"))
        doc_country_id = None
        if getattr(document, 'country_id', None):
            doc_country_id = document.country_id
        elif getattr(document, 'assignment_entity_status_id', None):
            aes = AssignmentEntityStatus.query.get(document.assignment_entity_status_id)
            doc_country_id = aes.entity_id if aes and aes.entity_type == 'country' else None
        user_country_ids = [c.id for c in current_user.countries]
        if not doc_country_id or doc_country_id not in user_country_ids:
            flash("Access denied. Document access permission required.", "warning")
            return redirect(url_for("main.dashboard"))
        # Focal points can only edit documents they uploaded
        if getattr(document, "uploaded_by_user_id", None) != getattr(current_user, "id", None):
            flash("Access denied. You can only edit documents you uploaded.", "warning")
            return redirect(url_for("main.dashboard"))

    if request.method == 'POST':
        try:
            # Update document metadata
            new_filename = request.form.get('filename', '').strip()
            if new_filename and new_filename != document.filename:
                document.filename = new_filename

            # Update basic fields
            document.document_type = request.form.get('document_type', document.document_type)

            # Handle Cover Image document type specially
            if document.document_type == 'Cover Image':
                document.language = None  # Cover images don't have language
                document.period = None      # Cover images don't have period
                document.is_public = True # Cover images are always public
            else:
                document.language = request.form.get('language', document.language)
                period_val = request.form.get('year')  # Form field is still named 'year' but contains period string
                if period_val:
                    document.period = period_val
                else:
                    document.period = None
                document.is_public = True if request.form.get('is_public') == 'on' else False
            # Only admins with permission or system managers can change status
            if is_admin_with_perm or is_system_manager:
                status_val = request.form.get('status')
                if status_val:
                    document.status = status_val

            # Handle thumbnail upload
            thumbnail_file = request.files.get('thumbnail')
            if thumbnail_file and thumbnail_file.filename:
                try:
                    # SECURITY: Validate thumbnail is a valid image file
                    validation_result = AdvancedValidator.validate_file_upload(
                        thumbnail_file,
                        allowed_extensions=ALLOWED_IMAGE_EXTENSIONS
                    )
                    if not validation_result['valid']:
                        error_msg = '; '.join(validation_result['errors'])
                        current_app.logger.warning(f"Invalid thumbnail upload: {error_msg}")
                        flash(f"Invalid thumbnail: {error_msg}", "warning")
                    else:
                        # Save new thumbnail under admin_documents/thumbnails
                        upload_dir = get_admin_documents_upload_path()
                        thumbnail_filename = validation_result['sanitized_filename']
                        thumb_rel = f"thumbnails/thumb_{document.id}_{thumbnail_filename}"
                        thumbnail_relative_path = save_stream_to(upload_dir, thumb_rel, thumbnail_file)

                        # Update document with new thumbnail
                        document.thumbnail_filename = thumbnail_filename
                        document.thumbnail_relative_path = thumbnail_relative_path

                except Exception as e:
                    current_app.logger.error(f"Error uploading thumbnail: {e}", exc_info=True)
                    flash("Error uploading thumbnail.", "warning")

            db.session.flush()
            flash("Document updated successfully.", "success")
            return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error(f"Error updating document {doc_id}: {e}", exc_info=True)
            flash("Error updating document.", "danger")

    return render_template("admin/documents/edit_document.html",
                         document=document,
                         title=f"Edit Document: {document.filename}")

@bp.route("/documents/<int:doc_id>/generate-thumbnail/<language_code>", methods=["POST"])
@bp.route("/documents/<int:doc_id>/generate-thumbnail", methods=["POST"])
@permission_required('admin.documents.manage')
def generate_document_thumbnail(doc_id, language_code=None):
    """Generate thumbnail for a document"""
    current_app.logger.info(f"Document thumbnail generation requested for document {doc_id}, language: {language_code}")

    # Check PDF processing capability first
    if not _check_pdf_processing_capability():
        current_app.logger.error("PDF processing libraries not available")
        if is_json_request():
            return json_server_error('PDF processing libraries not available on server.')
        else:
            flash("PDF processing libraries not available on server.", "danger")
            return redirect(url_for("content_management.manage_documents"))

    try:
        document = SubmittedDocument.query.get_or_404(doc_id)
        current_app.logger.info(f"Found document: {document.filename}")

        if not document.storage_path:
            current_app.logger.warning(f"No file path found for document {document.id}")
            if is_json_request():
                return json_bad_request('No file found for this document.')
            else:
                flash("No file found for this document.", "warning")
                return redirect(url_for("content_management.manage_documents"))

        current_app.logger.info(f"Processing file: {document.storage_path}")

        # Check if file is PDF
        if not document.filename.lower().endswith('.pdf'):
            if is_json_request():
                return json_bad_request('Thumbnail generation is only available for PDF files.')
            else:
                flash("Thumbnail generation is only available for PDF files.", "warning")
                return redirect(url_for("content_management.manage_documents"))

        # Get the full file path
        file_path = resolve_admin_document(document.storage_path)

        current_app.logger.info(f"Full file path: {file_path}")
        current_app.logger.info(f"File exists: {os.path.exists(file_path)}")

        if not os.path.exists(file_path):
            current_app.logger.error(f"File not found: {file_path}")
            if is_json_request():
                return json_not_found('File not found on server.')
            else:
                flash("File not found on server.", "danger")
                return redirect(url_for("content_management.manage_documents"))

        # Generate thumbnail under admin_documents
        upload_dir = get_admin_documents_upload_path()
        # Use provided language_code or default to 'en' for documents
        lang_code = language_code or 'en'
        thumbnail_path = _generate_pdf_thumbnail(file_path, str(document.id), upload_dir, lang_code)

        if thumbnail_path:
            # The thumbnail_path returned by _generate_pdf_thumbnail is already relative to upload_dir
            # So we can use it directly without calculating relpath
            document.thumbnail_relative_path = thumbnail_path
            document.thumbnail_filename = os.path.basename(thumbnail_path)
            db.session.flush()

            current_app.logger.info(f"Thumbnail generated successfully: {thumbnail_path}")

            if is_json_request():
                return json_ok(
                    message='Thumbnail generated successfully.',
                    thumbnail_url=url_for('content_management.download_document_thumbnail', doc_id=document.id),
                )
            else:
                flash("Thumbnail generated successfully.", "success")
                return redirect(url_for("content_management.manage_documents"))
        else:
            current_app.logger.error("Failed to generate thumbnail")
            if is_json_request():
                return json_server_error('Failed to generate thumbnail.')
            else:
                flash("Failed to generate thumbnail.", "danger")
                return redirect(url_for("content_management.manage_documents"))

    except Exception as e:
        current_app.logger.error(f"Error generating document thumbnail: {e}", exc_info=True)
        request_transaction_rollback()

        if is_json_request():
            return json_server_error(GENERIC_ERROR_MESSAGE)
        else:
            flash("Error generating thumbnail.", "danger")
            return redirect(url_for("content_management.manage_documents"))

@bp.route("/documents/<int:doc_id>/delete-thumbnail/<language_code>", methods=["POST"])
@bp.route("/documents/<int:doc_id>/delete-thumbnail", methods=["POST"])
@permission_required('admin.documents.manage')
def delete_document_thumbnail(doc_id, language_code=None):
    """Delete thumbnail for a document"""
    current_app.logger.info(f"Document thumbnail deletion requested for document {doc_id}, language: {language_code}")

    try:
        document = SubmittedDocument.query.get_or_404(doc_id)
        current_app.logger.info(f"Found document: {document.filename}")

        if not document.thumbnail_relative_path:
            current_app.logger.warning(f"No thumbnail found for document {document.id}")
            if is_json_request():
                return json_bad_request('No thumbnail found for this document.')
            else:
                flash("No thumbnail found for this document.", "warning")
                return redirect(url_for("content_management.manage_documents"))

        current_app.logger.info(f"Deleting thumbnail: {document.thumbnail_relative_path}")

        # Delete thumbnail file from filesystem
        thumbnail_path = resolve_admin_document_thumbnail(document.thumbnail_relative_path)

        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
            current_app.logger.info(f"Deleted thumbnail file: {thumbnail_path}")
        else:
            current_app.logger.warning(f"Thumbnail file not found: {thumbnail_path}")

        # Clear thumbnail fields in database
        document.thumbnail_relative_path = None
        document.thumbnail_filename = None
        db.session.flush()

        current_app.logger.info(f"Thumbnail deleted successfully for document {doc_id}")

        if is_json_request():
            return json_ok(message='Thumbnail deleted successfully.')
        else:
            flash("Thumbnail deleted successfully.", "success")
            return redirect(url_for("content_management.manage_documents"))

    except Exception as e:
        current_app.logger.error(f"Error deleting document thumbnail: {e}", exc_info=True)
        request_transaction_rollback()

        if is_json_request():
            return json_server_error(GENERIC_ERROR_MESSAGE)
        else:
            flash("Error deleting thumbnail.", "danger")
            return redirect(url_for("content_management.manage_documents"))

@bp.route("/documents/<int:doc_id>/thumbnail", methods=["GET"])
@permission_required('admin.documents.manage')
def download_document_thumbnail(doc_id):
    """Download document thumbnail"""
    document = SubmittedDocument.query.get_or_404(doc_id)

    if not document.thumbnail_relative_path:
        flash("No thumbnail found for this document.", "warning")
        return redirect(url_for("content_management.manage_documents"))

    try:
        thumbnail_path = resolve_admin_document_thumbnail(document.thumbnail_relative_path)

        # Debug logging
        current_app.logger.debug(f"Document {doc_id} thumbnail download:")
        current_app.logger.debug(f"  thumbnail_relative_path: {document.thumbnail_relative_path}")
        current_app.logger.debug(f"  constructed thumbnail_path: {thumbnail_path}")
        current_app.logger.debug(f"  file exists: {os.path.exists(thumbnail_path)}")

        if not os.path.exists(thumbnail_path):
            current_app.logger.warning(f"Thumbnail file not found at: {thumbnail_path}")
            flash("Thumbnail file not found.", "warning")
            return redirect(url_for("content_management.manage_documents"))

        return send_file(thumbnail_path, as_attachment=False)

    except Exception as e:
        current_app.logger.error(f"Error serving document thumbnail: {e}", exc_info=True)
        flash("Error serving thumbnail.", "danger")
        return redirect(url_for("content_management.manage_documents"))

@bp.route("/documents/approve/<int:doc_id>", methods=["POST"])
@permission_required('admin.documents.manage')
def approve_document(doc_id):
    """Approve a document (if status tracking is implemented)"""
    document = SubmittedDocument.query.get_or_404(doc_id)

    try:
        # Update approval status if field exists
        if hasattr(document, 'status'):
            document.status = 'approved'
        if hasattr(document, 'approved_by'):
            document.approved_by = current_user.id
        if hasattr(document, 'approved_at'):
            document.approved_at = utcnow()

        db.session.flush()
        flash(f"Document '{document.filename}' approved.", "success")

        # Return JSON response for AJAX requests
        if is_json_request():
            return json_ok(message=f"Document '{document.filename}' approved successfully.")

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error approving document {doc_id}: {e}", exc_info=True)
        flash("Error approving document.", "danger")

        # Return JSON response for AJAX requests
        if is_json_request():
            return json_server_error(GENERIC_ERROR_MESSAGE)

    return redirect(url_for("content_management.manage_documents"))

@bp.route("/documents/decline/<int:doc_id>", methods=["POST"])
@permission_required('admin.documents.manage')
def decline_document(doc_id):
    """Decline a document (if status tracking is implemented)"""
    document = SubmittedDocument.query.get_or_404(doc_id)

    try:
        # Update decline status if field exists
        if hasattr(document, 'status'):
            document.status = 'rejected'
        if hasattr(document, 'reviewed_by'):
            document.reviewed_by = current_user.id
        if hasattr(document, 'reviewed_at'):
            document.reviewed_at = utcnow()

        db.session.flush()
        flash(f"Document '{document.filename}' declined.", "success")

        # Return JSON response for AJAX requests
        if is_json_request():
            return json_ok(message=f"Document '{document.filename}' declined successfully.")

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error declining document {doc_id}: {e}", exc_info=True)
        flash("Error declining document.", "danger")

        # Return JSON response for AJAX requests
        if is_json_request():
            return json_server_error(GENERIC_ERROR_MESSAGE)

    return redirect(url_for("content_management.manage_documents"))

# === Helper Functions ===

def _handle_multilingual_uploads(form, resource, upload_base_path, unique_id_folder):
    """Handle multilingual file uploads and text fields for resources"""
    # Use the same language source as the form to ensure dynamically added languages are included
    # This matches what the form uses: _get_supported_language_codes()
    from app.forms.base import _get_supported_language_codes
    languages = _get_supported_language_codes()  # Dynamic list from runtime config

    current_app.logger.info(f"Processing multilingual uploads for resource {resource.id}")

    # Debug: Log all form fields and their values
    current_app.logger.info("Form fields available:")
    for field_name in dir(form):
        if not field_name.startswith('_') and hasattr(getattr(form, field_name), 'data'):
            field = getattr(form, field_name)
            current_app.logger.info(f"  {field_name}: {field.data} (type: {type(field.data)})")

    current_app.logger.info(f"Form data: {form.data}")

    for lang in languages:
        current_app.logger.info(f"Processing language: {lang}")

        # Handle text fields (title and description)
        title_field = getattr(form, f'title_{lang}', None)
        desc_field = getattr(form, f'description_{lang}', None)

        # Get or create translation record
        translation = ResourceTranslation.query.filter_by(
            resource_id=resource.id,
            language_code=lang
        ).first()

        if not translation:
            translation = ResourceTranslation(
                resource_id=resource.id,
                language_code=lang
            )
            db.session.add(translation)
            current_app.logger.info(f"Created new translation record for {lang}")

        # Update text fields if they exist in the form and have valid data
        if title_field and hasattr(title_field, 'data'):
            title_value = title_field.data
            current_app.logger.info(f"Title field for {lang}: {title_value} (type: {type(title_value)})")

            if title_value and str(title_value).strip():
                # Only update if the field has actual data (not None or empty string)
                translation.title = str(title_value).strip()
                current_app.logger.info(f"Updated title for {lang}: {translation.title}")
            elif lang == 'en' and not translation.title:
                # For English, use default title if no translation title exists
                translation.title = resource.default_title or "Untitled"
                current_app.logger.info(f"Set default title for {lang}: {translation.title}")
        elif lang == 'en' and not translation.title:
            # For English, use default title if no translation title exists
            translation.title = resource.default_title or "Untitled"
            current_app.logger.info(f"Set default title for {lang}: {translation.title}")

        if desc_field and hasattr(desc_field, 'data'):
            desc_value = desc_field.data
            current_app.logger.info(f"Description field for {lang}: {desc_value} (type: {type(desc_value)})")

            if desc_value and str(desc_value).strip():
                # Only update if the field has actual data (not None or empty string)
                translation.description = str(desc_value).strip()
                current_app.logger.info(f"Updated description for {lang}: {translation.description}")
            elif lang == 'en' and not translation.description:
                # For English, use default description if no translation description exists
                translation.description = resource.default_description or ""
                current_app.logger.info(f"Set default description for {lang}: {translation.description}")
        elif lang == 'en' and not translation.description:
            # For English, use default description if no translation description exists
            translation.description = resource.default_description or ""
            current_app.logger.info(f"Set default description for {lang}: {translation.description}")

        # Ensure required fields are never None
        if not translation.title:
            if lang == 'en':
                translation.title = resource.default_title or "Untitled"
                current_app.logger.info(f"Ensured title for {lang}: {translation.title}")
            else:
                # For non-English languages, skip creating/updating if no title provided
                current_app.logger.warning(f"Skipping {lang} - no title provided and not English")
                continue

        # Log the final state before proceeding
        current_app.logger.info(f"Final translation state for {lang}: title='{translation.title}', description='{translation.description}'")

        # Handle file uploads
        file_field = getattr(form, f'document_{lang}', None)
        if file_field and file_field.data:
            try:
                # SECURITY: Validate file upload (type, size, MIME)
                validation_result = AdvancedValidator.validate_file_upload(
                    file_field.data,
                    allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS
                )
                if not validation_result['valid']:
                    error_msg = '; '.join(validation_result['errors'])
                    current_app.logger.warning(f"File validation failed for {lang}: {error_msg}")
                    flash(f"Invalid file for {lang}: {error_msg}", "warning")
                    continue

                original_filename = validation_result['sanitized_filename']
                name, ext = os.path.splitext(original_filename)
                filename_with_lang = f"{name}_{lang}{ext}"
                sub_rel = f"{unique_id_folder}/{lang}/{filename_with_lang}"
                saved_rel = save_stream_to(upload_base_path, sub_rel, file_field.data)
                if saved_rel:
                    translation.file_relative_path = saved_rel
                    translation.filename = original_filename
                    current_app.logger.info(f"Updated file for {lang}: {saved_rel}")

            except Exception as e:
                current_app.logger.error(f"Error handling {lang} file upload: {e}", exc_info=True)
                flash("An error occurred uploading the file. Please try again.", "warning")

        # Handle thumbnail uploads
        thumbnail_field = getattr(form, f'thumbnail_{lang}', None)
        if thumbnail_field and thumbnail_field.data:
            try:
                # SECURITY: Validate thumbnail upload (must be image type)
                validation_result = AdvancedValidator.validate_file_upload(
                    thumbnail_field.data,
                    allowed_extensions=ALLOWED_IMAGE_EXTENSIONS
                )
                if not validation_result['valid']:
                    error_msg = '; '.join(validation_result['errors'])
                    current_app.logger.warning(f"Thumbnail validation failed for {lang}: {error_msg}")
                    flash(f"Invalid thumbnail for {lang}: {error_msg}", "warning")
                    continue

                thumb_filename = validation_result['sanitized_filename']
                sub_rel = f"{unique_id_folder}/{lang}/thumbnails/{thumb_filename}"
                saved_rel = save_stream_to(upload_base_path, sub_rel, thumbnail_field.data)
                if saved_rel:
                    translation.thumbnail_relative_path = saved_rel
                    translation.thumbnail_filename = thumb_filename
                    current_app.logger.info(f"Updated thumbnail for {lang}: {saved_rel}")

            except Exception as e:
                current_app.logger.error(f"Error handling {lang} thumbnail upload: {e}", exc_info=True)
                flash("An error occurred uploading the thumbnail. Please try again.", "warning")

    # Final validation - ensure no translation records have null titles
    current_app.logger.info("Performing final validation...")
    for translation in resource.translations:
        if not translation.title:
            current_app.logger.error(f"Found translation with null title: {translation.id}, language: {translation.language_code}")
            if translation.language_code == 'en':
                translation.title = resource.default_title or "Untitled"
                current_app.logger.info(f"Fixed null title for English: {translation.title}")
            else:
                current_app.logger.error(f"Non-English translation with null title - this should not happen")
                # Remove invalid translation records
                db.session.delete(translation)
                current_app.logger.info(f"Removed invalid translation for {translation.language_code}")

    current_app.logger.info("Multilingual upload processing completed")

def _delete_file_and_folder(base_path, relative_file_path):
    """Delete a file and its containing folder if empty"""
    try:
        full_path = os.path.join(base_path, relative_file_path)
        if os.path.exists(full_path):
            os.remove(full_path)

            # Try to remove parent directory if empty
            parent_dir = os.path.dirname(full_path)
            with suppress(OSError):  # Directory not empty
                os.rmdir(parent_dir)

    except Exception as e:
        current_app.logger.error(f"Error deleting file: {e}", exc_info=True)

def _generate_pdf_thumbnail(pdf_full_path, unique_folder_name, base_path, language_code=None):
    """Generate thumbnail for PDF file"""
    try:
        if not _check_pdf_processing_capability():
            return None

        # Open PDF
        import fitz
        from PIL import Image
        pdf_document = fitz.open(pdf_full_path)
        page = pdf_document[0]  # Get first page

        # Render page to image
        mat = fitz.Matrix(1.5, 1.5)  # Scaling factor for better quality
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")

        # Convert to PIL Image and resize
        img = Image.open(io.BytesIO(img_data))
        img.thumbnail((300, 400), Image.Resampling.LANCZOS)

        # Save thumbnail
        if language_code:
            thumbnail_filename = f"thumbnail_{language_code}.png"
        else:
            thumbnail_filename = "thumbnail.png"

        thumbnail_dir = os.path.join(base_path, unique_folder_name, "thumbnails")
        os.makedirs(thumbnail_dir, exist_ok=True)

        thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)
        img.save(thumbnail_path, "PNG")

        pdf_document.close()

        # Return relative path
        return os.path.join(unique_folder_name, "thumbnails", thumbnail_filename)

    except Exception as e:
        current_app.logger.error(f"Error generating PDF thumbnail: {e}", exc_info=True)
        return None

def _check_pdf_processing_capability():
    """Check if PDF processing libraries are available"""
    try:
        import fitz
        from PIL import Image
        return True
    except ImportError:
        current_app.logger.warning("PDF processing libraries not available")
        return False
