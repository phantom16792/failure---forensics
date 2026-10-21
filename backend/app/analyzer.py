"""Phase 3: backward trace analyzer. Judge every span, walk backward, the EARLIEST step with a
quality drop is the root cause; later failing steps are marked as propagation."""
from __future__ import annotations
import time
from . import heuristics as H, llm

STEPS = ["intake", "extraction", "classification", "summarization"]
TAXONOMY = ["extraction_hallucination", "misclassification", "propagation_error",
            "prompt_failure", "context_loss", "no_defect_found"]
THRESHOLD = 0.6


def _norm(s: str) -> str:
    return "".join(s.lower().split())


def _grounded(value: str, text: str) -> bool:
    return _norm(value) in _norm(text)


def _span(trace, step):
    return next((s for s in trace.spans if s.step == step), None)


def _judge(trace, span, text) -> dict:
    """Returns {score, category, note, data}. Deterministic grounding checks, optionally min()'d with an LLM judge."""
    r = {"score": 1.0, "category": None, "note": "ok", "data": {}}
    if span.status == "error":
        return {"score": 0.0, "category": "prompt_failure", "note": span.error, "data": {}}
    out = span.output or {}
    if span.step == "extraction":
        bad = [e["value"] for e in out["entities"] if not _grounded(e["value"], text)]
        if bad:
            r = {"score": 0.2, "category": "extraction_hallucination",
                 "note": f"{len(bad)} ungrounded entit{'y' if len(bad)==1 else 'ies'}", "data": {"ungrounded": bad}}
    elif span.step == "classification":
        golden = trace.meta.get("golden_type")
        expected = golden or H.top_type(text)[0]
        if out["doc_type"] != expected:
            r = {"score": 0.2, "category": "misclassification",
                 "note": f"predicted {out['doc_type']}, expected {expected}", "data": {"expected": expected}}
    elif span.step == "summarization":
        ext, cls = _span(trace, "extraction"), _span(trace, "classification")
        ents = (ext.output or {}).get("entities", []) if ext else []
        summ = " ".join([out["headline"], *out["bullets"]])
        leaked = [e["value"] for e in ents if not _grounded(e["value"], text) and e["value"] in summ]
        missing = [e["value"] for e in ents if e["type"] in ("date", "amount") and e["value"] not in summ]
        exp_type = trace.meta.get("golden_type") or H.top_type(text)[0]
        mixed = len(H.currencies_in(text)) > 1 and "currenc" not in summ.lower()
        if leaked:
            r = {"score": 0.3, "category": "propagation_error",
                 "note": "summary repeats unsupported upstream entities", "data": {"leaked": leaked}}
        elif missing:
            r = {"score": 0.4, "category": "context_loss",
                 "note": "summary dropped extracted dates/amounts", "data": {"missing": missing}}
        elif out["doc_type"] != exp_type:
            r = {"score": 0.3, "category": "propagation_error",
                 "note": f"summary tailored to '{out['doc_type']}'", "data": {}}
        elif mixed:
            r = {"score": 0.5, "category": "prompt_failure",
                 "note": "mixed currencies not flagged", "data": {"currencies": sorted(H.currencies_in(text))}}
    llm_score = llm.judge(span.step, span.input, out)
    if llm_score is not None and llm_score < r["score"]:
        r.update(score=llm_score, category=r["category"] or "prompt_failure", note="LLM judge: low quality")
    return r


def expected_output(trace, step, text):
    ext = _span(trace, "extraction")
    good = [e for e in H.extract_entities(text) if _grounded(e["value"], text)]
    if step == "extraction":
        return {"entities": good}
    exp_type = trace.meta.get("golden_type") or H.top_type(text)[0]
    if step == "classification":
        return {"doc_type": exp_type}
    if step == "summarization":
        return {**H.build_summary(exp_type, good), "doc_type": exp_type}
    return {}


def diagnose(trace) -> dict:
    t0 = time.perf_counter()
    intake = _span(trace, "intake")
    text = (intake.output or {}).get("text", "") if intake else ""
    judged = {}
    for s in trace.spans:
        s.judge = _judge(trace, s, text)
        judged[s.step] = s.judge
    # Walk backward from the last executed span; collect everything below threshold.
    failing = [s for s in reversed(trace.spans) if s.judge["score"] < THRESHOLD]  # backward walk
    ordered = list(reversed(failing))  # earliest first: ordered[0] is the root cause
    if failing:
        root = ordered[0]
        downstream = [s.step for s in ordered[1:]]
        cat, data = root.judge["category"], root.judge["data"]
    else:
        low = sorted([s for s in trace.spans if s.confidence is not None], key=lambda s: s.confidence)
        root = low[0] if low and low[0].confidence <= 2 else None
        downstream, cat, data = [], "no_defect_found", {}

    diag = {"root_step": root.step if root else None, "category": cat, "propagated_to": downstream,
            "scores": {s.step: s.judge["score"] for s in trace.spans}, "confirmed": False, "overridden": False}
    diag["evidence"] = [{"step": s.step, "input": s.input if s.step != "intake" else {"chars": len(text)},
                         "output": s.output, "judge": s.judge}
                        for s in trace.spans if root and s.step in [root.step, *downstream]]
    diag["expected"] = expected_output(trace, root.step, text) if root else None
    diag["explanation"] = _explain(trace, root, cat, data, downstream)
    # Failure-aware final score: mean of per-step quality.
    trace.final_score = round(sum(s.judge["score"] for s in trace.spans) / max(len(trace.spans), 1), 3)
    if cat != "no_defect_found":
        trace.status = "failure"
    diag["diagnosis_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return diag


def _num(step):
    return f"Step {STEPS.index(step) + 1} ({step.title()})"


def _explain(trace, root, cat, data, downstream):
    if cat == "no_defect_found":
        if root:
            return (f"No step produced an unfaithful output. {_num(root.step)} reported low confidence "
                    f"({root.confidence}/5), which usually means the source document lacks the information "
                    f"(for example, no dates) rather than a pipeline bug.")
        return "All steps are grounded in the source and no confidence drop was recorded."
    n = _num(root.step)
    prop = f" This propagated to {', '.join(_num(d) for d in downstream)}." if downstream else ""
    if cat == "extraction_hallucination":
        vals = ", ".join(f"'{v}'" for v in data["ungrounded"])
        tail = " The summary repeated it." if "summarization" in downstream else ""
        return f"{n} hallucinated {vals}, which does not appear in the source document.{tail or prop}"
    if cat == "misclassification":
        tail = " The summary was tailored to the wrong type." if "summarization" in downstream else ""
        return f"{n} {root.judge['note']}.{tail or prop}"
    if cat == "context_loss":
        return f"{n} dropped {', '.join(data['missing'])}, which Step 2 had extracted from the source."
    if cat == "prompt_failure" and root.status == "error":
        return f"{n} returned output that did not follow the required format: {root.error}"
    if cat == "prompt_failure":
        return f"{n} ignored an instruction: {root.judge['note']} ({', '.join(data.get('currencies', []))})."
    return f"{n} {root.judge['note']}.{prop}"
