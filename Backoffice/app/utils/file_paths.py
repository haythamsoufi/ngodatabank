import os
import re
from flask import current_app


def _abs(path: str) -> str:
    return os.path.abspath(path or '')


def get_upload_base_path() -> str:
    """Return absolute uploads base directory from config."""
    base = current_app.config.get('UPLOAD_FOLDER', 'uploads')
    return _abs(base)


def get_resource_upload_path() -> str:
    """Return absolute resources root under uploads."""
    return _abs(os.path.join(get_upload_base_path(), 'resources'))


def get_admin_documents_upload_path() -> str:
    """Return absolute admin documents root under uploads."""
    return _abs(os.path.join(get_upload_base_path(), 'admin_documents'))


def get_submissions_upload_path() -> str:
    """Return absolute submissions root under uploads."""
    return _abs(os.path.join(get_upload_base_path(), 'submissions'))


def get_submission_assignment_path(assignment_id: int, form_item_id: int) -> str:
    """Return absolute path for assignment submission document.

    Args:
        assignment_id: The assignment entity status ID
        form_item_id: The form item ID

    Returns:
        Absolute path to the assignment submission directory
    """
    base = get_submissions_upload_path()
    rel_path = f"assignments/{assignment_id}/{form_item_id}"
    return _abs(os.path.join(base, rel_path))


def get_submission_public_path(form_id: int, submission_id: int, form_item_id: int) -> str:
    """Return absolute path for public submission document.

    Args:
        form_id: The assigned form ID
        submission_id: The public submission ID
        form_item_id: The form item ID

    Returns:
        Absolute path to the public submission directory
    """
    base = get_submissions_upload_path()
    rel_path = f"public/{form_id}/{submission_id}/{form_item_id}"
    return _abs(os.path.join(base, rel_path))


def get_system_upload_path() -> str:
    """Return absolute system files root under uploads."""
    return _abs(os.path.join(get_upload_base_path(), 'system'))


def get_sector_logo_path() -> str:
    """Return absolute path for sector logos."""
    return _abs(os.path.join(get_system_upload_path(), 'sectors'))


def get_subsector_logo_path() -> str:
    """Return absolute path for subsector logos."""
    return _abs(os.path.join(get_system_upload_path(), 'subsectors'))


def get_temp_upload_path() -> str:
    """Return absolute path for temporary files."""
    return _abs(os.path.join(get_upload_base_path(), 'temp'))


def get_plugin_upload_path(plugin_name: str) -> str:
    """Return absolute path for plugin-specific uploads.

    Args:
        plugin_name: The name of the plugin

    Returns:
        Absolute path to the plugin's upload directory
    """
    base = _abs(os.path.join(get_upload_base_path(), 'plugins'))
    return _abs(os.path.join(base, plugin_name))


_WINDOWS_DRIVE_PREFIX = re.compile(r'^[A-Za-z]:[\\/]')


def normalize_stored_relative_path(value: str, root_folder: str | None = None) -> str:
    """Normalize a stored relative path to a consistent forward-slash form.
    - Strips Windows drive prefixes
    - Converts backslashes to forward slashes
    - Trims leading slashes
    - If root_folder is provided, strips any leading '<root_folder>/' prefix
    """
    rel = (value or '').strip()
    if _WINDOWS_DRIVE_PREFIX.match(rel):
        rel = os.path.basename(rel)
    rel = rel.replace('\\', '/').strip('/')
    if root_folder:
        prefix = f"{root_folder.strip('/')}/"
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
    return rel


def resolve_under(base_dir: str, rel_path: str) -> str:
    """Resolve a relative path under a base dir and ensure it stays under base.
    Returns the absolute resolved path. Does not check file existence.
    """
    safe_rel = normalize_stored_relative_path(rel_path)
    candidate = _abs(os.path.join(base_dir, *([p for p in safe_rel.split('/') if p])))
    base_real = os.path.realpath(base_dir)
    cand_real = os.path.realpath(candidate)
    if not cand_real.startswith(base_real + os.sep) and cand_real != base_real:
        raise PermissionError('Resolved path escapes base directory')
    return cand_real


# Convenience resolvers for resources
def resolve_resource_file(rel_path: str) -> str:
    return resolve_under(get_resource_upload_path(), normalize_stored_relative_path(rel_path))


def resolve_resource_thumbnail(rel_path: str) -> str:
    rel = normalize_stored_relative_path(rel_path)
    # Thumbnails live anywhere under resources root; caller controls subfolder
    return resolve_under(get_resource_upload_path(), rel)


# Convenience resolvers for admin documents
def resolve_admin_document(rel_path: str) -> str:
    return resolve_under(get_admin_documents_upload_path(), normalize_stored_relative_path(rel_path))


def resolve_admin_document_thumbnail(rel_path: str) -> str:
    rel = normalize_stored_relative_path(rel_path)
    return resolve_under(get_admin_documents_upload_path(), rel)


# Convenience resolvers for submissions
def resolve_submission_file(rel_path: str) -> str:
    """Resolve a relative path to a submission file.

    Args:
        rel_path: Relative path from submissions root (e.g., 'assignments/123/456/file.pdf')

    Returns:
        Absolute path to the file
    """
    return resolve_under(get_submissions_upload_path(), normalize_stored_relative_path(rel_path))


# Convenience resolvers for system files
def resolve_sector_logo(filename: str) -> str:
    """Resolve a sector logo filename to absolute path."""
    return resolve_under(get_sector_logo_path(), normalize_stored_relative_path(filename))


def resolve_subsector_logo(filename: str) -> str:
    """Resolve a subsector logo filename to absolute path."""
    return resolve_under(get_subsector_logo_path(), normalize_stored_relative_path(filename))


def resolve_temp_file(rel_path: str) -> str:
    """Resolve a relative path to a temporary file."""
    return resolve_under(get_temp_upload_path(), normalize_stored_relative_path(rel_path))


def resolve_plugin_file(plugin_name: str, rel_path: str) -> str:
    """Resolve a relative path to a plugin file."""
    base = get_plugin_upload_path(plugin_name)
    return resolve_under(base, normalize_stored_relative_path(rel_path))


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def save_stream_to(base_dir: str, sub_rel_path: str, file_storage) -> str:
    """Save an uploaded file_storage under base_dir/sub_rel_path (relative), creating dirs.
    Returns the normalized relative path (forward-slash).
    """
    # Normalize the provided relative path and rebuild OS-specific path
    safe_rel = normalize_stored_relative_path(sub_rel_path)
    abs_path = resolve_under(base_dir, safe_rel)
    ensure_dir(os.path.dirname(abs_path))
    file_storage.save(abs_path)
    # Return normalized forward-slash path relative to base_dir
    return normalize_stored_relative_path(os.path.relpath(abs_path, base_dir))


def secure_join_filename(folder_rel: str | None, filename: str) -> str:
    """Join a folder (relative) and filename safely (no traversal), return forward-slash rel."""
    name = os.path.basename(filename)
    rel_folder = normalize_stored_relative_path(folder_rel or '')
    if rel_folder:
        return f"{rel_folder}/{name}"
    return name


def save_submission_document(file_storage, assignment_id: int, form_item_id: int, filename: str, is_public: bool = False, form_id: int = None, submission_id: int = None) -> str:
    """Save a submission document and return relative path from submissions root.

    Args:
        file_storage: The file storage object from Flask request
        assignment_id: The assignment entity status ID (for regular submissions)
        form_item_id: The form item ID
        filename: The secured filename
        is_public: Whether this is a public submission
        form_id: The assigned form ID (required if is_public=True)
        submission_id: The public submission ID (required if is_public=True)

    Returns:
        Relative path from submissions root (e.g., 'assignments/123/456/file.pdf' or 'public/789/101/456/file.pdf')
    """
    if is_public:
        if form_id is None or submission_id is None:
            raise ValueError("form_id and submission_id are required for public submissions")
        base_dir = get_submission_public_path(form_id, submission_id, form_item_id)
        rel_prefix = f"public/{form_id}/{submission_id}/{form_item_id}"
    else:
        base_dir = get_submission_assignment_path(assignment_id, form_item_id)
        rel_prefix = f"assignments/{assignment_id}/{form_item_id}"

    # Ensure on-disk filename is unique to prevent overwrites when users upload
    # multiple documents with the same original name (common across folders).
    # Keep `SubmittedDocument.filename` as the display/download name; `storage_path`
    # uses this unique name on disk.
    import uuid
    name, ext = os.path.splitext(os.path.basename(filename))
    unique_filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"

    rel_path = secure_join_filename(None, unique_filename)
    saved_rel = save_stream_to(base_dir, rel_path, file_storage)
    # Return full relative path from submissions root
    return f"{rel_prefix}/{saved_rel}"


def save_system_logo(file_storage, item_name: str, item_type: str, is_sector: bool = True) -> str:
    """Save a system logo (sector or subsector) and return the filename.

    Args:
        file_storage: The file storage object from Flask request
        item_name: The name of the item (for filename generation)
        item_type: The type of item (e.g., 'sector', 'subsector')
        is_sector: True for sector, False for subsector

    Returns:
        The saved filename (relative to the logo directory)
    """
    import uuid
    from werkzeug.utils import secure_filename

    if not file_storage or not file_storage.filename:
        return None

    filename = secure_filename(file_storage.filename)
    name, ext = os.path.splitext(filename)

    # Create unique filename
    unique_filename = f"{secure_filename(item_name)}_{item_type}_{uuid.uuid4().hex[:8]}{ext}"

    if is_sector:
        base_dir = get_sector_logo_path()
    else:
        base_dir = get_subsector_logo_path()

    # Save file
    save_stream_to(base_dir, unique_filename, file_storage)
    return unique_filename
