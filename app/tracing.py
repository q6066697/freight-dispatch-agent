"""Optional Langfuse tracing. No-op unless LANGFUSE_ENABLED and keys are set.

Usage:
    from app.tracing import trace_step
    with trace_step("extractor", input=text) as span:
        ...
        span.update(output=result)

When disabled (the default), `trace_step` yields a dummy span and does nothing,
so nothing in the graph depends on Langfuse being installed or reachable.
"""

from __future__ import annotations

from contextlib import contextmanager

from app.config import get_settings


class _NoopSpan:
    def update(self, **_kwargs) -> None:
        pass


class _Tracer:
    def __init__(self) -> None:
        self._client = None
        settings = get_settings()
        if not (settings.langfuse_enabled and settings.langfuse_secret_key):
            return
        try:  # pragma: no cover - only runs when explicitly enabled
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
        except Exception:
            self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None


_tracer: _Tracer | None = None


def get_tracer() -> _Tracer:
    global _tracer
    if _tracer is None:
        _tracer = _Tracer()
    return _tracer


@contextmanager
def trace_step(name: str, **data):
    """Context manager yielding a span. No-op when tracing is disabled."""
    tracer = get_tracer()
    if not tracer.enabled:  # fast path, the default
        yield _NoopSpan()
        return
    # pragma: no cover - exercised only with real Langfuse configured
    span = tracer._client.span(name=name, input=data or None)
    try:
        yield span
    finally:
        span.end()
