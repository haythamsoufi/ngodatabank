"""
AI Agent Executor (legacy shim).

The implementation lives in app.services.ai_agent.executor. This module
keeps backward compatibility for ``from app.services.ai_agent_executor import …``.
"""

from app.services.ai_agent import AIAgentExecutor, AgentExecutionError

__all__ = ["AIAgentExecutor", "AgentExecutionError"]
