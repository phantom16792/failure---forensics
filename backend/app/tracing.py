"""Phase 2: tracing layer. Instrumenting a step is one decorator line: @traced("name")."""
from __future__ import annotations
import contextvars, time, uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from .models import Span, Trace

_trace: contextvars.ContextVar = contextvars.ContextVar("ff_trace", default=None)
_span: contextvars.ContextVar = contextvars.ContextVar("ff_span", default=None)
_hook: contextvars.ContextVar = contextvars.ContextVar("ff_hook", default=None)  # (emit, pace) for live streaming


def emit_event(ev: dict) -> None:
    h = _hook.get()
    if h and h[0]:
        h[0](ev)


def pace() -> float:
    h = _hook.get()
    return h[1] if h else 0.0


def current_trace():
    return _trace.get()


@contextmanager
def trace_context(doc_id: str, meta: dict | None = None, emit=None, pace: float = 0.0):
    t = Trace(trace_id=uuid.uuid4().hex[:12], doc_id=doc_id,
              ts=datetime.now(timezone.utc).isoformat(), meta=meta or {})
    token, htoken = _trace.set(t), _hook.set((emit, pace))
    try:
        yield t
    finally:
        _trace.reset(token)
        _hook.reset(htoken)


def record_llm(prompt: str, raw: str, tokens: int) -> None:
    """Called by the LLM wrapper so the active span captures prompt, raw response and tokens."""
    s = _span.get()
    if s:
        s.prompt, s.raw_response = prompt, raw
        s.tokens += tokens


def traced(step: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(inp):
            trace = _trace.get()
            span = Span(span_id=uuid.uuid4().hex[:8], step=step, input=inp.model_dump(mode="json"))
            token = _span.set(span)
            emit_event({"type": "start", "step": step, "span_id": span.span_id, "input": span.input})
            if pace():
                time.sleep(pace())
            t0 = time.perf_counter()
            try:
                out = fn(inp)
                span.output = out.model_dump(mode="json")
                span.confidence = getattr(out, "confidence", None)
                return out
            except Exception as e:  # captured, then re-raised so the pipeline stops
                span.status, span.error = "error", f"{type(e).__name__}: {e}"
                raise
            finally:
                span.latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                _span.reset(token)
                if trace is not None:
                    trace.spans.append(span)
                emit_event({"type": "end", "span": span.model_dump(mode="json")})
        return wrapper
    return deco
