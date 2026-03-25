# Backoffice/app/routes/api/documents.py
"""
Document and Upload API endpoints.
Part of the /api/v1 blueprint.
"""

from flask import request, current_app, send_from_directory, abort, url_for
import os

# Import the API blueprint from parent
from app.routes.api import api_bp

# Import models
from app.models.documents import SubmittedDocument
from app.utils.auth import require_api_key

# Import utility functions
from app.utils.api_helpers import json_response, api_error
from app.utils.file_paths import (
    resolve_admin_document,
    resolve_admin_document_thumbnail,
    get_sector_logo_path,
    get_subsector_logo_path
)


@api_bp.route('/submitted-documents', methods=['GET'])
@require_api_key
def get_submitted_documents():
    """
    API endpoint to retrieve submitted documents by country.
    Authentication: API key in Authorization header (Bearer token).
    Query Parameters:
        - country_id: Filter by country ID (optional)
        - document_type: Filter by document type (optional)
        - language: Language code for filtering (optional)
        - is_public: Filter by public status (true/false, optional)
        - status: Filter by approval status ('approved', 'pending', 'rejected', optional)
        - page: Page number (default: 1)
        - per_page: Items per page (default: 20)
    Returns:
        JSON object containing:
        - documents: List of submitted document objects
        - total_items: Total number of documents
        - total_pages: Total number of pages
        - current_page: Current page number
        - per_page: Items per page
    """
    try:
        current_app.logger.debug("Entering submitted documents API endpoint")

        # Get filter parameters
        country_id = request.args.get('country_id', type=int)
        document_type = request.args.get('document_type', default='', type=str).strip()
        language = request.args.get('language', default='', type=str).strip()
        is_public = request.args.get('is_public')
        status = request.args.get('status', default='', type=str).strip()
        from app.utils.api_pagination import validate_pagination_params
        page, per_page = validate_pagination_params(request.args, default_per_page=20)

        # Build base query
        query = SubmittedDocument.query

        # Apply filters
        if country_id:
            query = query.filter(SubmittedDocument.country_id == country_id)

        if document_type:
            query = query.filter(SubmittedDocument.document_type == document_type)

        if language:
            query = query.filter(SubmittedDocument.language == language)

        if is_public is not None:
            if is_public.lower() == 'true':
                query = query.filter(SubmittedDocument.is_public == True)
            elif is_public.lower() == 'false':
                query = query.filter(SubmittedDocument.is_public == False)

        if status:
            query = query.filter(SubmittedDocument.status == status)

        # Only show approved documents by default, unless status filter is specified
        if not status:
            query = query.filter(SubmittedDocument.status == 'approved')

        # Order by upload date (newest first) and paginate
        paginated_docs = query.order_by(SubmittedDocument.uploaded_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

        # Serialize document data
        documents_data = []
        for doc in paginated_docs.items:
            # Get download URL and display URL
            download_url = None
            display_url = None
            try:
                abs_path = resolve_admin_document(doc.storage_path)
            except Exception as e:
                current_app.logger.debug("resolve_admin_document: %s", e)
                abs_path = None
            if abs_path and os.path.exists(abs_path):
                download_url = url_for('content_management.download_document', doc_id=doc.id, _external=True)
                # For cover images, also provide a display URL that doesn't force download
                if doc.document_type == 'Cover Image':
                    display_url = url_for('public.display_document_file_public', doc_id=doc.id, _external=True)

            # Get country information
            country_info = None
            if doc.country:
                ns = getattr(doc.country, 'primary_national_society', None)
                country_info = {
                    'id': doc.country.id,
                    'name': doc.country.name,
                    'iso3': doc.country.iso3,
                    'national_society_name': (ns.name if ns else None),
                    'region': doc.country.region
                }

            # Get thumbnail URL if available
            thumbnail_url = None
            if doc.thumbnail_relative_path:
                try:
                    thumb_abs = resolve_admin_document_thumbnail(doc.thumbnail_relative_path)
                except Exception as e:
                    current_app.logger.debug("resolve_admin_document_thumbnail: %s", e)
                    thumb_abs = None
                if thumb_abs and os.path.exists(thumb_abs):
                    # Use public route so frontend can load without admin permissions
                    thumbnail_url = url_for('public.download_document_thumbnail_public', doc_id=doc.id, _external=True)

            documents_data.append({
                'id': doc.id,
                'filename': doc.filename,
                'document_type': doc.document_type,
                'language': doc.language,
                # Legacy field: `year` is not always present on the model; keep it nullable.
                'year': getattr(doc, 'year', None),
                'period': getattr(doc, 'period', None),
                'is_public': doc.is_public,
                'status': doc.status,
                'uploaded_at': doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                'download_url': download_url,
                'display_url': display_url,
                'thumbnail_url': thumbnail_url,
                'has_thumbnail': bool(thumbnail_url),
                'country_info': country_info,
                'has_file': bool(abs_path and os.path.exists(abs_path))
            })

        current_app.logger.debug(f"Submitted documents API returning {len(documents_data)} items")

        return json_response({
            'documents': documents_data,
            'total_items': paginated_docs.total,
            'total_pages': paginated_docs.pages,
            'current_page': paginated_docs.page,
            'per_page': paginated_docs.per_page,
            'country_id_filter': country_id,
            'document_type_filter': document_type,
            'language_filter': language,
            'is_public_filter': is_public,
            'status_filter': status
        })

    except Exception as e:
        current_app.logger.error(f"API Error fetching submitted documents: {e}", exc_info=True)
        return api_error("Could not fetch submitted documents", 500)


@api_bp.route('/uploads/sectors/<path:filename>', methods=['GET'])
def serve_sector_logo(filename):
    """Serve sector logo files."""
    try:
        # SECURITY: Validate filename to prevent path traversal attacks
        from app.utils.file_paths import resolve_under
        upload_folder = get_sector_logo_path()

        # Validate the file stays within the upload folder
        try:
            resolved_path = resolve_under(upload_folder, filename)
        except PermissionError:
            current_app.logger.warning(f"Path traversal attempt blocked for sector logo: {filename}")
            abort(404)

        # Extract just the filename after validation
        import os
        safe_filename = os.path.relpath(resolved_path, upload_folder)
        return send_from_directory(upload_folder, safe_filename, as_attachment=False)
    except Exception as e:
        current_app.logger.error(f"Error serving sector logo {filename}: {str(e)}")
        abort(404)


@api_bp.route('/uploads/subsectors/<path:filename>', methods=['GET'])
def serve_subsector_logo(filename):
    """Serve subsector logo files."""
    try:
        # SECURITY: Validate filename to prevent path traversal attacks
        from app.utils.file_paths import resolve_under
        upload_folder = get_subsector_logo_path()

        # Validate the file stays within the upload folder
        try:
            resolved_path = resolve_under(upload_folder, filename)
        except PermissionError:
            current_app.logger.warning(f"Path traversal attempt blocked for subsector logo: {filename}")
            abort(404)

        # Extract just the filename after validation
        import os
        safe_filename = os.path.relpath(resolved_path, upload_folder)
        return send_from_directory(upload_folder, safe_filename, as_attachment=False)
    except Exception as e:
        current_app.logger.error(f"Error serving subsector logo {filename}: {str(e)}")
        abort(404)
