"""LLM wrapper. Uses Anthropic when ANTHROPIC_API_KEY is set; otherwise a deterministic mock so the
whole system (and the demo) runs offline. Mock-only `fault` injection simulates real pipeline bugs."""
from __future__ import annotations
import json, os, re
from . import heuristics as H
import time
from .tracing import current_trace, emit_event, pace, record_llm

MODEL = os.getenv("FF_MODEL", "claude-sonnet-4-6")
try:
    import anthropic
    client = anthropic.Anthropic() if os.getenv("ANTHROPIC_API_KEY") else None
except ImportError:
    client = None

PATCHED: set[str] = set()  # demo: faults that have been "fixed" in the pipeline


def parse_json(raw: str) -> dict:
    s = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    return json.loads(s)


def complete(step: str, prompt: str, payload: dict) -> str:
    emit_event({"type": "prompt", "prompt": prompt})
    if client:
        msg = client.messages.create(model=MODEL, max_tokens=800,
                                     system="Respond with a single JSON object only.",
                                     messages=[{"role": "user", "content": prompt}])
        raw = msg.content[0].text
        tokens = msg.usage.input_tokens + msg.usage.output_tokens
    else:
        time.sleep(pace() * 0.8)  # mock only: simulate model latency so the live view is watchable
        raw = _mock(step, payload)
        tokens = (len(prompt) + len(raw)) // 4
    record_llm(prompt, raw, tokens)
    emit_event({"type": "response", "raw": raw, "tokens": tokens})
    return raw


def judge(step: str, inp: dict, out: dict) -> float | None:
    """Optional LLM-as-judge (0..1). Returns None offline; the analyzer then relies on grounding checks."""
    if not client:
        return None
    prompt = (f"Step: {step}\nInput: {json.dumps(inp)[:3000]}\nOutput: {json.dumps(out)[:2000]}\n"
              'Is the output a faithful, reasonable transformation of the input? Reply {"score": 0..1}.')
    try:
        msg = client.messages.create(model=MODEL, max_tokens=100, system="JSON only.",
                                     messages=[{"role": "user", "content": prompt}])
        return float(parse_json(msg.content[0].text)["score"])
    except Exception:
        return None


def _mock(step: str, p: dict) -> str:
    t = current_trace()
    fault = (t.meta.get("fault") if t else None)
    if fault in PATCHED:
        fault = None
    text = p.get("text", "")

    if step == "extraction":
        if fault == "prompt_failure":
            return "Sure! Here are the entities I found: the two companies and a fee."
        ents = H.extract_entities(text)
        conf = 5
        has_date = any(e["type"] == "date" for e in ents)
        if not has_date and any(w in text.lower() for w in ("agreement", "effective")):
            conf = 2
        if len(H.currencies_in(text)) > 1 or not ents:
            conf = 2
        if fault == "hallucination":
            ents.append({"type": "person", "value": "John Smith"})
            conf = 4  # confidently wrong: only the judge can catch this
        return json.dumps({"entities": ents, "confidence": conf})

    if step == "classification":
        top, margin = H.top_type(text)
        conf = 5 if margin >= 3 else 4 if margin >= 2 else 2
        if fault == "misclassify":
            top, conf = ("report" if top != "report" else "invoice"), 4
        return json.dumps({"doc_type": top, "rationale": f"keyword evidence for {top} (margin {margin})",
                           "confidence": conf})

    if step == "summarization":
        drop = ("date", "amount") if fault == "context_loss" else ()
        s = H.build_summary(p["doc_type"], p["entities"], drop)
        none_found = sum("none found" in b for b in s["bullets"])
        return json.dumps({**s, "doc_type": p["doc_type"], "confidence": 5 if not none_found else 3})
    raise ValueError(step)
