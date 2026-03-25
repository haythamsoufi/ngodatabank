"""
ai_agent – Sub-package for the AI agent execution pipeline.

Public API (import either from this package or the legacy flat module):

    from app.services.ai_agent import AIAgentExecutor
    # or (legacy / backward-compat):
    from app.services.ai_agent_executor import AIAgentExecutor

Module layout
─────────────
_circuit_breaker.py  – Per-run circuit-breaker state for tool failure isolation.
_loop.py             – Core ReAct iteration helpers (tool-call dispatch, result
                       parsing, convergence detection).
executor.py          – AIAgentExecutor class (assembles the above into a full
                       agent run).

To avoid breaking existing code the original flat file
(app/services/ai_agent_executor.py) is kept as a thin shim that imports
from this package.  New code should prefer this package path.
"""

from app.services.ai_agent._circuit_breaker import CircuitBreaker, CircuitBreakerState
from app.services.ai_agent.executor import AIAgentExecutor, AgentExecutionError

__all__ = [
    "AIAgentExecutor",
    "AgentExecutionError",
    "CircuitBreaker",
    "CircuitBreakerState",
]
