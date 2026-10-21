"""FastAPI surface for the pipeline, trace explorer, flagging, eval loop and analytics."""
from __future__ import annotations
from typing import Any, Optional
import asyncio, io, json, time
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from . import analyzer, llm, samples, storage
from .models import Trace
from .pipeline import run_pipeline

storage.init()
app = FastAPI(title="FailureForensics", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# Allow requests from your Vercel frontend URL and local dev servers
origins = [
    "https://https://failure-forensics.vercel.app/",  # Replace with your actual frontend Vercel URL
    "http://localhost:5173",
    "http://localhost:8080",
    "*"  # Use "*" temporarily if you want to allow all origins during testing
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RunReq(BaseModel):
    text: str
    doc_id: Optional[str] = None
    golden_type: Optional[str] = None
    fault: Optional[str] = None


class ConfirmReq(BaseModel):
    category: Optional[str] = None
    step: Optional[str] = None
    corrected_output: Optional[Any] = None


class PatchReq(BaseModel):
    fault: str


def _meta(golden, fault, scenario=None):
    return {k: v for k, v in {"golden_type": golden, "fault": fault, "scenario": scenario}.items() if v}


def _get(trace_id) -> Trace:
    raw = storage.load_trace(trace_id)
    if not raw:
        raise HTTPException(404, "trace not found")
    return Trace(**raw)


@app.get("/api/health")
def health():
    return {"ok": True, "llm": "anthropic" if llm.client else "mock"}


@app.post("/api/run")
def run(req: RunReq):
    t = run_pipeline(req.doc_id or "adhoc", req.text, _meta(req.golden_type, req.fault))
    storage.save_trace(t)
    return t


async def _read_upload(file: UploadFile) -> str:
    data, name = await file.read(), file.filename or "upload"
    if name.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            return "\f".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(data)).pages)
        except Exception as e:
            raise HTTPException(400, f"Could not read this PDF: {e}")
    return data.decode("utf-8", errors="replace")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), golden_type: Optional[str] = Form(None)):
    """Upload a .txt / .md / .pdf document; it runs through the traced pipeline immediately."""
    text = await _read_upload(file)
    if not text.strip():
        raise HTTPException(400, "No readable text found (scanned PDFs need OCR first).")
    t = run_pipeline(file.filename or "upload", text[:20000], _meta(golden_type or None, None))
    storage.save_trace(t)
    return t


@app.post("/api/stream")
async def stream(file: Optional[UploadFile] = File(None), text: Optional[str] = Form(None),
                 doc_id: Optional[str] = Form(None), golden_type: Optional[str] = Form(None),
                 fault: Optional[str] = Form(None), pace: float = Form(0.7)):
    """Server-sent events: every step start/prompt/response/end as it happens, then the quality check."""
    if file is not None:
        text = await _read_upload(file)
    if not text or not text.strip():
        raise HTTPException(400, "No readable text found (scanned PDFs need OCR first).")
    name = doc_id or (file.filename if file else "pasted-document")
    loop, q = asyncio.get_running_loop(), asyncio.Queue()
    emit = lambda ev: loop.call_soon_threadsafe(q.put_nowait, ev)

    def work():
        try:
            t = run_pipeline(name, text[:20000], _meta(golden_type or None, fault or None), emit=emit, pace=pace)
            emit({"type": "analysis_start"})
            time.sleep(pace * 0.8)
            t.diagnosis = analyzer.diagnose(t)
            storage.save_trace(t)
            emit({"type": "done", "trace": t.model_dump(mode="json")})
        except Exception as e:
            emit({"type": "error", "message": str(e)})
        finally:
            emit(None)

    loop.run_in_executor(None, work)

    async def gen():
        while (ev := await q.get()) is not None:
            yield f"data: {json.dumps(ev)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/run-batch")
def run_batch(triage: bool = True):
    """Runs the 50-doc corpus. With triage=True the judge sweeps every trace (a nightly eval job)."""
    out = []
    for d in samples.build():
        t = run_pipeline(d["doc_id"], d["text"], _meta(d["golden_type"], d["fault"], d["scenario"]))
        if triage:
            t.diagnosis = analyzer.diagnose(t)
        storage.save_trace(t)
        out.append(t.trace_id)
    return {"traces": len(out)}


@app.get("/api/samples")
def get_samples():
    return samples.build()


@app.get("/api/traces")
def traces(status: Optional[str] = None):
    return storage.list_traces(status)


@app.get("/api/traces/{trace_id}")
def trace(trace_id: str):
    return _get(trace_id)


@app.post("/api/traces/{trace_id}/flag")
def flag(trace_id: str):
    """User marks the output as bad -> backward trace analysis runs immediately."""
    t = _get(trace_id)
    t.flagged = True
    t.diagnosis = analyzer.diagnose(t)
    storage.save_trace(t)
    return t


@app.post("/api/traces/{trace_id}/confirm")
def confirm(trace_id: str, req: ConfirmReq):
    """Human confirms (or overrides) the diagnosis -> an eval case is appended to the dataset."""
    t = _get(trace_id)
    if not t.diagnosis:
        raise HTTPException(400, "flag the trace first")
    d = t.diagnosis
    step, cat = req.step or d["root_step"], req.category or d["category"]
    d["overridden"] = (step, cat) != (d["root_step"], d["category"])
    d["root_step"], d["category"], d["confirmed"] = step, cat, True
    span = next((s for s in t.spans if s.step == step), None)
    corrected = req.corrected_output if req.corrected_output is not None else d.get("expected")
    t.confirmed = True
    t.status = "failure"
    storage.save_trace(t)
    eid = storage.add_eval(t.model_dump(), step, span.output if span else None, corrected, cat)
    return {"eval_id": eid, "trace": t}


@app.get("/api/evals")
def evals():
    return {"cases": storage.list_evals(), "runs": storage.list_runs()}


@app.post("/api/evals/rerun")
def rerun():
    """Regression: replay every eval input through the CURRENT pipeline; resolved = failing step now healthy."""
    cases = storage.list_evals()
    resolved = 0
    for e in cases:
        t = run_pipeline(f"eval-{e['eval_id']}", e["input_text"], e["meta"])
        d = analyzer.diagnose(t)
        ok = d["category"] == "no_defect_found" or d["root_step"] != e["failing_step"]
        storage.mark_eval(e["eval_id"], ok)
        resolved += ok
    storage.add_run(len(cases), resolved)
    return {"total": len(cases), "resolved": resolved}


@app.post("/api/demo/patch")
def patch(req: PatchReq):
    """Demo helper: simulate shipping a fix for one injected fault class."""
    llm.PATCHED.add(req.fault)
    return {"patched": sorted(llm.PATCHED)}


@app.post("/api/demo/reset")
def reset():
    llm.PATCHED.clear()
    storage.reset()
    return {"ok": True}


@app.get("/api/analytics")
def analytics():
    return storage.analytics()
