"""
AI Tools Registry (legacy shim).

The implementation lives in app.services.ai_tools.registry. This module
keeps backward compatibility for ``from app.services.ai_tools_registry import …``.
"""

from app.services.ai_tools.registry import AIToolsRegistry, ToolExecutionError

__all__ = ["AIToolsRegistry", "ToolExecutionError"]
