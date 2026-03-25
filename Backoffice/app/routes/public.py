# ========== File: app/routes/public.py ==========
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, abort, jsonify, send_from_directory, Response
from app.models import db, Resource
from sqlalchemy import inspect, text
import traceback
from urllib.parse import urlparse, urlunparse
import os
from datetime import datetime
from flask_migrate import upgrade as alembic_upgrade
from app.utils.datetime_helpers import utcnow
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_error
from app.utils.file_paths import (
    get_resource_upload_path,
    resolve_resource_file,
    resolve_resource_thumbnail,
    resolve_admin_document,
    resolve_admin_document_thumbnail,
    get_admin_documents_upload_path,
)
from contextlib import suppress

from app.utils.form_processing import slugify_age_group

bp = Blueprint("public", __name__)

THUMBNAIL_SUBFOLDER_NAME = 'thumbnails'

# =================== RESOURCE DOWNLOAD ROUTES ===================
# These routes allow public access to resources without API key

@bp.route("/resources/download/<int:resource_id>/<language>", methods=["GET"])
def download_resource_file(resource_id, language):
    """Download a resource file in a specific language."""
    resource = Resource.query.get_or_404(resource_id)
    translation = resource.get_translation(language)

    if not translation or not translation.file_relative_path:
        current_app.logger.error(f"Public download (doc): No file path for resource ID {resource_id} in language {language}")
        abort(404, description="Document file not found for this resource.")

    try:
        full_path_to_file = resolve_resource_file(translation.file_relative_path)
        upload_base_path = get_resource_upload_path()
    except PermissionError:
        current_app.logger.error("Public download (doc): path escapes base directory")
        abort(403)

    if not os.path.exists(full_path_to_file):
        current_app.logger.error(f"Public download (doc): File not found for ID {resource_id} at {full_path_to_file}")
        abort(404)

    directory_of_file = os.path.dirname(full_path_to_file)
    filename_on_disk = os.path.basename(full_path_to_file)

    # Security check: Ensure the file is within the designated upload folder
    if not directory_of_file.startswith(upload_base_path):
         current_app.logger.error(f"Public download (doc): Attempt to serve file from outside designated folder: {full_path_to_file}")
         abort(403)

    response = send_from_directory(
        directory_of_file,
        filename_on_disk,
        as_attachment=False,  # Allow inline viewing
        download_name=translation.filename
    )

    # Add headers for PDF viewing if it's a PDF
    if translation.filename.lower().endswith('.pdf'):
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Range'
        response.headers['Access-Control-Expose-Headers'] = 'Accept-Ranges, Content-Encoding, Content-Length, Content-Range'

    return response

@bp.route("/resources/thumbnail/<int:resource_id>/<language>", methods=["GET"])
def download_resource_thumbnail(resource_id, language):
    """Download a resource thumbnail in a specific language with fallback to English."""
    resource = Resource.query.get_or_404(resource_id)
    translation = resource.get_translation(language)

    # If requested language doesn't have thumbnail, try English fallback
    if (not translation or not translation.thumbnail_relative_path) and language != 'en':
        current_app.logger.info(f"Public download (thumb): No thumbnail for resource ID {resource_id} in {language}, trying English fallback")
        translation = resource.get_translation('en')

    if not translation or not translation.thumbnail_relative_path:
        current_app.logger.warning(f"Public download (thumb): No thumbnail path for resource ID {resource_id} in language {language} or English fallback")
        abort(404, description="Thumbnail not found for this resource.")

    try:
        full_path_to_thumbnail = resolve_resource_thumbnail(translation.thumbnail_relative_path)
        upload_base_path = get_resource_upload_path()
    except PermissionError:
        current_app.logger.error("Public download (thumb): path escapes base directory")
        abort(403)

    if not os.path.exists(full_path_to_thumbnail):
        current_app.logger.error(f"Public download (thumb): Thumbnail file not found for ID {resource_id} at {full_path_to_thumbnail}")
        abort(404)

    directory_of_thumbnail = os.path.dirname(full_path_to_thumbnail)
    thumbnail_filename_on_disk = os.path.basename(full_path_to_thumbnail)

    # Security check: Ensure the file is within the designated upload folder
    if not directory_of_thumbnail.startswith(upload_base_path):
         current_app.logger.error(f"Public download (thumb): Attempt to serve file from outside designated folder: {full_path_to_thumbnail}")
         abort(403)

    # Serve the image directly, not as an attachment
    return send_from_directory(directory_of_thumbnail, thumbnail_filename_on_disk, as_attachment=False)

# =================== BACKWARD COMPATIBILITY REDIRECTS ===================
# These routes redirect old public routes to the new unified forms system

@bp.route("/form/<uuid:public_token>", methods=["GET", "POST"])
def fill_public_form_redirect(public_token):
    """DEPRECATED: Redirect to unified forms system."""
    return redirect(url_for('forms.fill_public_form', public_token=public_token))

@bp.route("/public_submission_success/<int:submission_id>", methods=["GET"])
def public_submission_success_redirect(submission_id):
    """DEPRECATED: Redirect to unified forms system."""
    return redirect(url_for('forms.public_submission_success', submission_id=submission_id))

@bp.route("/public_documents/download/<int:submitted_document_id>", methods=["GET"])
def download_public_document_redirect(submitted_document_id):
    """DEPRECATED: Redirect to unified forms system."""
    return redirect(url_for('forms.download_public_document_public', document_id=submitted_document_id))

# =================== PUBLIC DOCUMENT THUMBNAILS ===================
# Serve document thumbnails publicly for approved public documents

@bp.route("/documents/thumbnail/<int:doc_id>", methods=["GET"])
def download_document_thumbnail_public(doc_id):
    """Serve a public thumbnail for a submitted document."""
    from app.models import SubmittedDocument
    document = SubmittedDocument.query.get_or_404(doc_id)

    # Only allow public, approved documents
    if not document.is_public or (document.status and document.status.strip().lower() != 'approved'):
        abort(404)

    if not document.thumbnail_relative_path:
        abort(404)

    try:
        thumbnail_path = resolve_admin_document_thumbnail(document.thumbnail_relative_path)
        upload_dir = get_admin_documents_upload_path()
    except PermissionError:
        current_app.logger.error("Public document thumb outside folder resolution")
        abort(403)

    if not os.path.exists(thumbnail_path):
        abort(404)

    directory_of_thumbnail = os.path.dirname(thumbnail_path)
    thumbnail_filename_on_disk = os.path.basename(thumbnail_path)

    # Security check: Ensure the file is within the designated upload folder
    if not directory_of_thumbnail.startswith(upload_dir):
         current_app.logger.error(f"Public document thumb outside folder: {thumbnail_path}")
         abort(403)

    return send_from_directory(directory_of_thumbnail, thumbnail_filename_on_disk, as_attachment=False)

# =================== PUBLIC DOCUMENT DISPLAY (IMAGES ONLY) ===================

@bp.route("/documents/display/<int:doc_id>", methods=["GET"])
def display_document_file_public(doc_id):
    """Serve a public document file inline when it's an image (for cover images)."""
    from app.models import SubmittedDocument
    document = SubmittedDocument.query.get_or_404(doc_id)

    # Only allow public, approved documents
    if not document.is_public or (document.status and document.status.strip().lower() != 'approved'):
        abort(404)

    # Build absolute path from stored relative path
    try:
        file_path = resolve_admin_document(document.storage_path)
    except PermissionError:
        abort(403)

    if not (file_path and os.path.exists(file_path)):
        abort(404)

    # Only serve inline if it's an image
    lower = (document.filename or '').lower()
    if not lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
        abort(404)

    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)

    # Security check: Ensure the file is within uploads
    from app.utils.file_paths import get_upload_base_path
    upload_base = get_upload_base_path()
    if not directory.startswith(upload_base):
        abort(403)

    return send_from_directory(directory, filename, as_attachment=False)

@bp.route("/landing", methods=["GET"])
def landing_page():
    """Public landing page introducing the platform and its features."""
    return render_template("public/landing.html", current_year=utcnow().year)


@bp.route("/health", methods=["GET"])
def health_check():
    """Simple health check endpoint for Fly.io and load balancers.

    Returns 200 OK if the application is healthy.
    This is a lightweight endpoint that should respond quickly.
    Optionally checks database connectivity if DB_CHECK=true.
    """
    try:
        # Basic health check - just return OK immediately
        # This ensures the health check responds quickly even under load
        health_status = {
            "status": "healthy",
            "timestamp": utcnow().isoformat(),
            "service": "backoffice-databank"
        }

        # Optional: Check database connectivity (can be enabled via env var)
        # By default, this is disabled to keep health checks fast
        db_check_enabled = str(os.environ.get('HEALTH_CHECK_DB', 'false')).strip().lower() == 'true'
        if db_check_enabled:
            try:
                # Simple database connectivity check with timeout
                # Use a very simple query that should complete quickly
                db.session.execute(text('SELECT 1'))
                db.session.flush()  # Ensure transaction is committed
                health_status["database"] = "connected"
            except Exception as db_error:
                # Log but don't fail the health check unless critical
                current_app.logger.warning(f"Health check: Database connectivity issue: {db_error}")
                health_status["database"] = "error"
                # Only mark as degraded, not unhealthy, to avoid cascading failures
                health_status["status"] = "degraded"

        status_code = 200 if health_status["status"] in ["healthy", "degraded"] else 503
        return jsonify(health_status), status_code

    except Exception as e:
        # Log the error but still return a response
        current_app.logger.error(f"Health check failed: {e}", exc_info=True)
        return json_error(GENERIC_ERROR_MESSAGE, 503, status="unhealthy", timestamp=utcnow().isoformat())


# =================== TEMPORARY DB DIAGNOSTICS ===================
def _check_dbinfo_access():
    """Check if /dbinfo endpoint access is allowed.

    Returns tuple (allowed: bool, error_code: int or None)
    - (True, None) if access is allowed
    - (False, 404) if endpoint is disabled or user not authenticated (hide existence)
    - (False, 403) if authenticated but not authorized
    """
    from flask_login import current_user
    from app.services.authorization_service import AuthorizationService

    # Check if endpoint is enabled (defaults to True for any environment)
    enabled = current_app.config.get("ENABLE_DBINFO", True)

    # SECURITY: If endpoint is disabled, return 404 to hide endpoint existence
    if not enabled:
        return (False, 404)

    # SECURITY: Return 404 (not 403) for unauthenticated users to hide endpoint existence
    if not current_user.is_authenticated:
        return (False, 404)

    # Check authorization - require system manager (highest privilege level)
    if not AuthorizationService.is_system_manager(current_user):
        return (False, 403)

    # In production, restrict to localhost only
    if current_app.config.get("FLASK_CONFIG") == "production":
        if request.remote_addr not in ['127.0.0.1', '::1', 'localhost']:
            # Check X-Forwarded-For header if behind proxy
            forwarded_for = request.headers.get('X-Forwarded-For', '')
            if forwarded_for:
                client_ip = forwarded_for.split(',')[0].strip()
            else:
                client_ip = request.remote_addr

            if client_ip not in ['127.0.0.1', '::1', 'localhost']:
                current_app.logger.warning(
                    f"SECURITY: /dbinfo endpoint accessed from non-localhost IP: {client_ip} by user {current_user.id}"
                )
                return (False, 403)

    return (True, None)


@bp.route("/dbinfo", methods=["GET"])
def db_info():
    """Return plain-text DB connection diagnostics and table list.

    This route is intended for temporary/local debugging. It returns:
    - SQLALCHEMY_DATABASE_URI (password redacted)
    - Engine/dialect information
    - Connection test result
    - Available table names

    SECURITY: This endpoint requires system manager authentication and is restricted to localhost in production.
    Access is controlled by:
    - ENABLE_DBINFO config (default: true; set ENABLE_DBINFO=false to disable)
    - System manager role (highest privilege level)
    - Localhost-only access in production
    """
    # Centralized access check
    allowed, error_code = _check_dbinfo_access()
    if not allowed:
        abort(error_code)

    lines = []
    # Redact password in URI
    raw_uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "<not set>")
    try:
        parsed = urlparse(raw_uri)
        if parsed.password:
            netloc = parsed.hostname or ""
            if parsed.username:
                netloc = f"{parsed.username}:***@{netloc}"
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            redacted = urlunparse((parsed.scheme, netloc, parsed.path or '', parsed.params or '', parsed.query or '', parsed.fragment or ''))
        else:
            redacted = raw_uri
    except Exception as e:
        current_app.logger.debug("URI redaction failed: %s", e)
        redacted = raw_uri

    lines.append(f"SQLALCHEMY_DATABASE_URI: {redacted}")

    # Engine/dialect info
    try:
        engine = db.engine
        lines.append(f"Engine dialect: {engine.dialect.name}")
        lines.append(f"Driver: {engine.dialect.driver}")
        pool = getattr(engine, 'pool', None)
        if pool is not None:
            pool_cls = pool.__class__.__name__
            lines.append(f"Pool: {pool_cls}")
    except Exception as e:
        lines.append(f"Engine access error: {e}")

    # Connection test and server version (best-effort)
    # SECURITY: All SQL queries here use hardcoded strings, no user input - safe from injection
    try:
        with db.engine.connect() as conn:
            # Simple connectivity check - hardcoded query, no user input
            conn.execute(db.text("SELECT 1"))
            lines.append("Connection test: OK (SELECT 1)")
            # Try to get server version if supported
            try:
                if engine.dialect.name == 'postgresql':
                    ver = conn.execute(db.text("SHOW server_version")).scalar()
                    lines.append(f"PostgreSQL server_version: {ver}")
                elif engine.dialect.name == 'mysql':
                    ver = conn.execute(db.text("SELECT VERSION()")).scalar()
                    lines.append(f"MySQL version: {ver}")
            except Exception as e_ver:
                lines.append(f"Version check error: {e_ver}")

            # Postgres-specific context info - all hardcoded queries, no user input
            try:
                if engine.dialect.name == 'postgresql':
                    dbname = conn.execute(db.text("SELECT current_database()")).scalar()
                    user = conn.execute(db.text("SELECT current_user")).scalar()
                    schema = conn.execute(db.text("SELECT current_schema()")).scalar()
                    search_path = conn.execute(db.text("SHOW search_path")).scalar()
                    lines.append(f"Current database: {dbname}")
                    lines.append(f"Current user: {user}")
                    lines.append(f"Current schema: {schema}")
                    lines.append(f"search_path: {search_path}")
            except Exception as e_ctx:
                lines.append(f"Context info error: {e_ctx}")
    except Exception as e:
        lines.append("Connection test: FAILED")
        lines.append(f"Error: {e.__class__.__name__}: {e}")
        tb = traceback.format_exc(limit=2)
        lines.append(tb.strip())

    # Table names across schemas
    try:
        insp = inspect(db.engine)
        schemas = []
        with suppress(Exception):  # Table may not exist yet
            schemas = [s for s in insp.get_schema_names() if s not in ('information_schema', 'pg_catalog')]

        if schemas:
            lines.append("Schemas:")
            for s in sorted(schemas):
                lines.append(f"- {s}")

        aggregated = []
        # Prefer current schema first if available
        # SECURITY: Hardcoded query, no user input - safe from injection
        current_schema = None
        try:
            with db.engine.connect() as conn:
                if engine.dialect.name == 'postgresql':
                    current_schema = conn.execute(db.text("SELECT current_schema()")).scalar()
        except Exception as e:
            current_app.logger.debug("Current schema lookup failed: %s", e)
            current_schema = None

        def list_schema_tables(schema_name):
            try:
                return insp.get_table_names(schema=schema_name)
            except Exception as e:
                current_app.logger.debug("list_schema_tables failed for %r: %s", schema_name, e)
                return []

        # Determine order of schemas to show
        ordered_schemas = []
        if current_schema:
            ordered_schemas.append(current_schema)
        for s in schemas:
            if s not in ordered_schemas:
                ordered_schemas.append(s)
        if not ordered_schemas:
            ordered_schemas = [None]  # default behavior

        any_tables = False
        for s in ordered_schemas:
            tables = list_schema_tables(s) if s else insp.get_table_names()
            header = f"Tables (schema={s}):" if s else "Tables:"
            if tables:
                any_tables = True
                lines.append(header)
                for t in sorted(tables):
                    lines.append(f"- {t}")

        if not any_tables:
            lines.append("Tables: <none>")

        # Alembic version info if present
        with suppress(Exception):
            with db.engine.connect() as conn:
                ver = conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
                lines.append(f"alembic_version: {ver}")
    except Exception as e:
        lines.append(f"Table inspection error: {e}")

    return Response("\n".join(lines) + "\n", mimetype="text/plain; charset=utf-8")


# =================== TEMPORARY DB MIGRATION TRIGGER ===================
def _check_migrate_access():
    """Check if /migrate endpoint access is allowed.

    SECURITY: This endpoint can run database migrations which is a critical operation.
    Access requires EITHER:
    1. Authenticated system manager, OR
    2. Valid MIGRATE_TOKEN (for automated deployments)

    Returns tuple (allowed: bool, error_response: Response or None)
    """
    from flask_login import current_user
    from app.services.authorization_service import AuthorizationService

    # Check if endpoint is enabled at all (defaults to True for any environment)
    enabled = current_app.config.get("ENABLE_MIGRATE", True)
    if not enabled:
        # Return 404 to hide endpoint existence when disabled
        return (False, Response(
            "Not found",
            status=404,
            mimetype="text/plain; charset=utf-8",
        ))

    # Check for token-based access (for automated deployments/CI)
    token_env = os.environ.get("MIGRATE_TOKEN")
    token_req = request.args.get("token")

    # SECURITY: Token must be at least 32 characters to be considered secure
    if token_env and len(token_env) >= 32:
        if token_req == token_env:
            # Valid token - allow access (for automated deployments)
            current_app.logger.info(
                f"SECURITY: /migrate endpoint accessed via token from IP: {request.remote_addr}"
            )
            return (True, None)
        elif token_req:
            # Token provided but invalid
            current_app.logger.warning(
                f"SECURITY: /migrate endpoint - invalid token attempt from IP: {request.remote_addr}"
            )
            return (False, Response(
                "Unauthorized: invalid token",
                status=401,
                mimetype="text/plain; charset=utf-8"
            ))

    # No valid token - require system manager authentication
    if not current_user.is_authenticated:
        # Return 404 to hide endpoint existence for unauthenticated users
        return (False, Response(
            "Not found",
            status=404,
            mimetype="text/plain; charset=utf-8",
        ))

    # Require system manager role (highest privilege level)
    if not AuthorizationService.is_system_manager(current_user):
        current_app.logger.warning(
            f"SECURITY: /migrate endpoint - access denied for user {current_user.id} (not system manager)"
        )
        return (False, Response(
            "Forbidden: system manager privileges required",
            status=403,
            mimetype="text/plain; charset=utf-8",
        ))

    # System manager - allow access
    current_app.logger.info(
        f"SECURITY: /migrate endpoint accessed by system manager user {current_user.id}"
    )
    return (True, None)


@bp.route("/migrate", methods=["GET", "POST"])
def run_db_migrations():
    """Run Alembic upgrade to head and report before/after version.

    SECURITY: This endpoint performs database migrations - a critical operation.

    Access requires EITHER:
    1. Authenticated system manager (highest privilege level), OR
    2. Valid MIGRATE_TOKEN (must be 32+ chars) for automated deployments

    Guards:
    - Enabled by default (set ENABLE_MIGRATE=false to disable)
    - Requires system manager auth OR valid MIGRATE_TOKEN
    - All access is logged for audit trail
    """
    # Centralized access check
    allowed, error_response = _check_migrate_access()
    if not allowed:
        return error_response

    started_at = datetime.utcnow()
    lines = [
        "=== Database migration ===",
        f"Started: {started_at.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "",
    ]

    # Read current version (if table exists)
    # SECURITY: Hardcoded query, no user input - safe from injection
    before_ver = None
    try:
        with db.engine.connect() as conn:
            before_ver = conn.execute(db.text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as e:
        current_app.logger.debug("Alembic before-version read failed: %s", e)
        before_ver = None

    # Execute upgrade
    try:
        alembic_upgrade()
    except Exception as e:
        # SECURITY: Only expose stack traces in DEBUG mode to prevent information leakage
        if current_app.config.get('DEBUG', False):
            tb = traceback.format_exc(limit=3)
            return Response(
                "\n".join(lines) + f"\n\nMigration: FAILED\nError: {e.__class__.__name__}: {e}\n{tb}",
                status=500,
                mimetype="text/plain; charset=utf-8",
            )
        else:
            # Log full error for debugging but return generic message to user
            current_app.logger.error(f"Migration error: {e}", exc_info=True)
            return Response(
                "\n".join(lines) + "\n\nMigration: FAILED\nError: An internal error occurred. Check server logs.",
                status=500,
                mimetype="text/plain; charset=utf-8",
            )

    upgrade_duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)

    # Read after version
    # SECURITY: Hardcoded query, no user input - safe from injection
    after_ver = None
    try:
        with db.engine.connect() as conn:
            after_ver = conn.execute(db.text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as e:
        current_app.logger.debug("Alembic after-version read failed: %s", e)
        after_ver = None

    migrated = before_ver != after_ver
    lines.extend([
        "Alembic:",
        f"  Revision before: {before_ver or '(none)'}",
        f"  Revision after:  {after_ver or '(none)'}",
        f"  Status: {'migrated (upgrade applied)' if migrated else 'already at head (no changes)'}",
        f"  Duration: {upgrade_duration_ms} ms",
        "",
    ])

    # Check and fix sequences (PostgreSQL only). Reset any that are behind MAX(id).
    if db.engine.dialect.name != "postgresql":
        lines.append("Sequences: skipped (not PostgreSQL)")
    else:
        try:
            from app.utils.sequence_utils import scan_sequences_status, reset_table_sequence

            seq_results = scan_sequences_status(schema="public")
            need_reset = [(t, d) for t, status, d in seq_results if status == "needs_reset"]
            if need_reset:
                lines.append("Sequences: fixing tables that need reset")
                reset_ok = []
                reset_fail = []
                for table_name, _detail in need_reset:
                    ok, reason = reset_table_sequence(table_name, schema="public")
                    if ok:
                        reset_ok.append(table_name)
                        lines.append(f"  - {table_name}: reset")
                    else:
                        reset_fail.append((table_name, reason))
                        lines.append(f"  - {table_name}: failed ({reason})")
                if reset_fail:
                    lines.append(f"Sequences: {len(reset_ok)} reset, {len(reset_fail)} failed")
                else:
                    lines.append(f"Sequences: OK (reset {len(reset_ok)} table(s))")
            else:
                lines.append("Sequences: OK (no resets needed)")
        except Exception as e:
            current_app.logger.warning(f"Sequence scan/reset failed: {e}", exc_info=True)
            lines.append(f"Sequences: error ({e!s})")

    lines.extend(["", "=== Done ==="])
    return Response("\n".join(lines) + "\n", mimetype="text/plain; charset=utf-8")
