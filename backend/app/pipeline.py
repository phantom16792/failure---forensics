"""Phase 1: four isolated, typed steps. Each is wrapped by @traced so tracing is one line."""
import json
from . import llm
from .models import *
from .tracing import emit_event, traced, trace_context

EXTRACT_PROMPT = ("Extract entities from the document. Return JSON "
                  '{{"entities":[{{"type":"person|org|date|amount|term","value":"exact text from the document"}}],'
                  '"confidence":1-5}}. Only include values that appear in the text.\n\nDOCUMENT:\n{text}')
CLASSIFY_PROMPT = ('Classify the document as contract, invoice, report or correspondence. Return JSON '
                   '{{"doc_type":"...","rationale":"...","confidence":1-5}}.\n\nENTITIES: {ents}\nDOCUMENT:\n{text}')
SUMMARY_PROMPT = ('Write a structured summary for a {doc_type}. Always mention parties, dates, amounts and key terms; '
                  'flag mixed currencies. Return JSON {{"headline":"...","bullets":["..."],"doc_type":"{doc_type}",'
                  '"confidence":1-5}}.\n\nENTITIES: {ents}\nDOCUMENT:\n{text}')


@traced("intake")
def intake(inp: RawDoc) -> IntakeOut:
    text = " ".join(inp.text.split()) if "\f" in inp.text else inp.text.strip()
    fmt = "pdf_text" if "\f" in inp.text else "markdown" if text.startswith("#") or "**" in text else "text"
    return IntakeOut(doc_id=inp.doc_id, text=text, char_count=len(text), fmt=fmt)


@traced("extraction")
def extract(inp: ExtractionIn) -> ExtractionOut:
    raw = llm.complete("extraction", EXTRACT_PROMPT.format(text=inp.text), {"text": inp.text})
    return ExtractionOut(**llm.parse_json(raw))


@traced("classification")
def classify(inp: ClassificationIn) -> ClassificationOut:
    ents = json.dumps([e.model_dump() for e in inp.entities])
    raw = llm.complete("classification", CLASSIFY_PROMPT.format(text=inp.text, ents=ents), {"text": inp.text})
    return ClassificationOut(**llm.parse_json(raw))


@traced("summarization")
def summarize(inp: SummaryIn) -> SummaryOut:
    ents = [e.model_dump() for e in inp.entities]
    prompt = SUMMARY_PROMPT.format(doc_type=inp.doc_type, text=inp.text, ents=json.dumps(ents))
    raw = llm.complete("summarization", prompt, {"text": inp.text, "doc_type": inp.doc_type, "entities": ents})
    return SummaryOut(**llm.parse_json(raw))


def run_pipeline(doc_id: str, text: str, meta: dict | None = None, emit=None, pace: float = 0.0) -> Trace:
    with trace_context(doc_id, meta, emit, pace) as t:
        emit_event({"type": "trace_start", "trace_id": t.trace_id, "doc_id": doc_id, "text": text})
        try:
            doc = intake(RawDoc(doc_id=doc_id, text=text))
            ents = extract(ExtractionIn(text=doc.text))
            cls = classify(ClassificationIn(text=doc.text, entities=ents.entities))
            out = summarize(SummaryIn(text=doc.text, doc_type=cls.doc_type, entities=ents.entities))
            t.final_output = out.model_dump(mode="json")
        except Exception:
            pass  # the failing span already holds the error; later steps never ran
        confs = [s.confidence for s in t.spans if s.confidence is not None]
        if any(s.status == "error" for s in t.spans):
            t.status = "failure"
        elif confs and min(confs) <= 2:
            t.status = "degraded"
        t.final_score = round(sum(confs) / len(confs) / 5, 3) if confs else 0.0
    return t
