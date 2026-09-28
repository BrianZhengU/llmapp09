"""Langfuse tracing.

Enabled only when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set (LANGFUSE_HOST
selects the region / self-hosted server). Without keys, every helper here is a no-op,
so the app runs the same with or without Langfuse.
"""
import logging
import os

from app import config  # noqa: F401  (loads .env before we read the Langfuse keys)

logger = logging.getLogger("tracing")

LANGFUSE_ENABLED = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))

if LANGFUSE_ENABLED:
    from langfuse import get_client, observe

    langfuse = get_client()
else:
    langfuse = None

    def observe(func=None, **_kwargs):
        """No-op stand-in for langfuse.observe (supports @observe and @observe(...))."""
        return func if func is not None else (lambda f: f)


def update_generation(**kwargs) -> None:
    """Attach model, input/output, token usage... to the current generation."""
    if langfuse:
        langfuse.update_current_generation(**kwargs)


def update_trace(**kwargs) -> None:
    """Attach user_id, session_id, tags, metadata... to the current trace."""
    if langfuse:
        langfuse.update_current_trace(**kwargs)


def check_connection() -> None:
    """Log whether Langfuse is reachable. Never raises: tracing must not take the API down."""
    if not langfuse:
        logger.info("langfuse_disabled", extra={"reason": "LANGFUSE_PUBLIC_KEY/SECRET_KEY not set"})
        return
    host = os.getenv("LANGFUSE_HOST")
    try:
        ok = langfuse.auth_check()
    except Exception as exc:  # network errors, bad host, ...
        logger.warning("langfuse_unreachable", extra={"host": host, "error": str(exc)})
        return
    if ok:
        logger.info("langfuse_connected", extra={"host": host})
    else:
        logger.warning("langfuse_auth_failed", extra={"host": host})


def flush() -> None:
    """Send buffered events before the process exits."""
    if langfuse:
        langfuse.flush()
