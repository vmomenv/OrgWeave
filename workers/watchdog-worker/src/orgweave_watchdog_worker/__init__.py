"""Watchdog Worker skeleton.

Phase 0 monitors worker heartbeat freshness deterministically. Agent session
loop detection, budget enforcement and takeover triggers are Phase 7; they will
reuse this alert channel rather than scrape logs.
"""

__version__ = "0.1.0"
