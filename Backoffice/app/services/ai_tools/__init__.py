"""
ai_tools – Sub-package for AI agent tool definitions and execution.

Public API (import either from this package or the legacy flat module):

    from app.services.ai_tools import AIToolsRegistry, ToolExecutionError
    # or (legacy / backward-compat):
    from app.services.ai_tools_registry import AIToolsRegistry, ToolExecutionError

Module layout
─────────────
_cache.py       – In-memory TTL/LRU tool-result cache.
_utils.py       – JSON helpers, tool-usage logger, ToolExecutionError, tool_wrapper.
_query_utils.py – Query rewriting and heuristic helpers (country inference, UPR detection).
registry.py     – AIToolsRegistry class (all tool implementations).

To avoid breaking existing code the original flat file
(app/services/ai_tools_registry.py) is kept as a thin shim that imports
from this package.  New code should prefer this package path.
"""

# Re-export the full public surface from the implementation module
# (registry.py lives here; the flat shim delegates back for legacy imports).
from app.services.ai_tools._cache import (
    _TOOL_CACHE,
    _TOOL_CACHE_LOCK,
    tool_cache_get,
    tool_cache_set,
)
from app.services.ai_tools._utils import (
    ToolExecutionError,
    tool_wrapper,
    json_sanitize,
    truncate_json_value,
    log_tool_usage,
    resolve_ai_user_context,
    resolve_source_config,
    apply_document_source_filters,
)
from app.services.ai_tools._query_utils import (
    infer_country_identifier_from_query,
    rewrite_document_search_query,
    resolve_country_search_filters,
)
from app.services.upr.query_detection import query_prefers_upr_documents
from app.services.ai_tools.registry import AIToolsRegistry

__all__ = [
    "AIToolsRegistry",
    "ToolExecutionError",
    "tool_wrapper",
    "json_sanitize",
    "truncate_json_value",
    "log_tool_usage",
    "resolve_ai_user_context",
    "resolve_source_config",
    "apply_document_source_filters",
    "tool_cache_get",
    "tool_cache_set",
    "infer_country_identifier_from_query",
    "query_prefers_upr_documents",
    "rewrite_document_search_query",
    "resolve_country_search_filters",
]
