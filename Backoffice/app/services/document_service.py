from typing import Tuple
from contextlib import suppress
from flask import current_app
from app.models import db, SubmittedDocument
from app.utils.file_paths import resolve_submission_file, get_submissions_upload_path
import os


class DocumentService:
    """Service for document operations (download/delete) with security checks."""

    @classmethod
    def _resolve_storage_path(cls, storage_path: str) -> str:
        """Resolve storage_path to absolute path, handling both relative and absolute paths.

        Args:
            storage_path: Either a relative path from submissions root or an absolute path (legacy)

        Returns:
            Absolute path to the file
        """
        # Check if it's already an absolute path (legacy format)
        if os.path.isabs(storage_path):
            return storage_path

        # Check if it's a relative path from submissions root (new format)
        if storage_path.startswith(('assignments/', 'public/')):
            return resolve_submission_file(storage_path)

        # Fallback: try to resolve as relative path from submissions root
        try:
            return resolve_submission_file(storage_path)
        except Exception as e:
            from flask import current_app
            current_app.logger.debug("_resolve_storage_path fallback to legacy path: %s", e)
            # If that fails, assume it's a legacy absolute path
            return storage_path

    @classmethod
    def get_assignment_download_paths(cls, submitted_document_id: int, current_user) -> Tuple[str, str, str]:
        """Validate access and return (directory, filename_on_disk, download_name) for assignment document download."""
        submitted_document = SubmittedDocument.query.get_or_404(submitted_document_id)
        aes = submitted_document.assignment_entity_status
        if not aes:
            raise FileNotFoundError("Document not associated with an assignment")

        # Permission: must belong to user's countries unless admin/system_manager
        user_country_ids = [country.id for country in current_user.countries.all()]
        from app.services.authorization_service import AuthorizationService
        if aes.country_id not in user_country_ids and not AuthorizationService.is_admin(current_user):
            raise PermissionError("Not authorized to download this document")

        # Resolve storage path (handles both relative and absolute paths)
        abs_path = cls._resolve_storage_path(submitted_document.storage_path)
        directory = os.path.dirname(abs_path)
        filename = os.path.basename(abs_path)
        download_name = submitted_document.filename or filename

        # Security: ensure within UPLOAD_FOLDER using realpath to prevent symlink attacks
        upload_base = os.path.realpath(current_app.config['UPLOAD_FOLDER'])
        directory_real = os.path.realpath(directory)
        if not (directory_real.startswith(upload_base + os.sep) or directory_real == upload_base):
            raise PermissionError("Attempt to access file outside upload folder")

        return directory, filename, download_name

    @classmethod
    def delete_assignment_document(cls, submitted_document_id: int, current_user) -> str:
        """Delete an assignment document after permission checks. Returns deleted filename."""
        submitted_document = SubmittedDocument.query.get_or_404(submitted_document_id)
        aes = submitted_document.assignment_entity_status
        if not aes:
            raise FileNotFoundError("Document not associated with an assignment")

        # Permission checks
        user_country_ids = [country.id for country in current_user.countries.all()]
        is_valid_user_for_country_status = aes.country_id in user_country_ids
        from app.services.authorization_service import AuthorizationService
        can_edit = aes.status not in ["Submitted", "Approved"] or AuthorizationService.is_admin(current_user)

        if not is_valid_user_for_country_status and not AuthorizationService.is_admin(current_user):
            raise PermissionError("Not authorized to delete this document")
        if not can_edit:
            raise PermissionError("Assignment status prevents document deletion")

        # Delete file if present
        doc_filename = submitted_document.filename
        try:
            abs_path = cls._resolve_storage_path(submitted_document.storage_path)
            if os.path.exists(abs_path):
                os.remove(abs_path)
        except Exception as e:
            # Deleting DB row should still proceed, but leaving orphaned files should be observable.
            current_app.logger.warning(
                "Failed to delete document file from disk (will still delete DB row): doc_id=%s storage_path=%s error=%s",
                submitted_document_id,
                getattr(submitted_document, "storage_path", None),
                e,
                exc_info=True,
            )

        db.session.delete(submitted_document)
        db.session.commit()
        return doc_filename

    @classmethod
    def get_public_download_paths(cls, document_id: int) -> Tuple[str, str, str]:
        """Validate and return (directory, filename_on_disk, download_name) for public document download."""
        document = SubmittedDocument.query.get_or_404(document_id)
        if not document.public_submission_id:
            raise PermissionError("Not a public document")

        # Resolve storage path (handles both relative and absolute paths)
        abs_path = cls._resolve_storage_path(document.storage_path)
        directory = os.path.dirname(abs_path)
        filename = os.path.basename(abs_path)

        # Security: ensure within UPLOAD_FOLDER using realpath to prevent symlink attacks
        upload_base = os.path.realpath(current_app.config['UPLOAD_FOLDER'])
        directory_real = os.path.realpath(directory)
        if not (directory_real.startswith(upload_base + os.sep) or directory_real == upload_base):
            raise PermissionError("Attempt to access file outside upload folder")

        return directory, filename, (document.filename or filename)
