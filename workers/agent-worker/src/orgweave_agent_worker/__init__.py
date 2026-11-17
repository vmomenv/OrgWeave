"""Agent Worker: Redis-backed job consumer skeleton.

Phase 0 intentionally implements only ``system.ping``. Unsupported jobs are
dead-lettered rather than silently dropped. Agent Runtime execution (sessions,
runs, tools, memory) is Phase 3.
"""

__version__ = "0.1.0"
