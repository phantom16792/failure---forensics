# PRD: FailureForensics, a Failure Forensics Tool for AI Pipelines

**Status:** v1.0 · **Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLite + JSON traces, React 19 + Vite + Motion + Recharts, Docker
**One-line pitch:** *I built an observability system that cuts mean time to root cause for AI pipeline failures from hours of manual debugging to seconds of automated diagnosis.*

---

## 1. Problem and opportunity
When a multi-step LLM pipeline emits a bad final answer, teams see only the symptom. Each step looks plausible in isolation, errors compound silently, and nobody knows *which step* broke. Debugging means re-reading prompts and outputs by hand.

FailureForensics is a mini LangSmith/Braintrust: it **traces** every step, **diagnoses** the first step where quality dropped, and **feeds confirmed failures back** into a growing regression dataset.

## 2. Goals and non-goals
| Goals | Non-goals (v1) |
|---|---|
| Trace every step of a 4-step document pipeline with a one-line decorator | Multi-tenant auth, RBAC |
| Locate the root-cause step and categorize the failure with evidence | Streaming/high-volume ingestion (>10k traces/day) |
| Human-in-the-loop confirm/override, producing eval cases automatically | Fine-tuning or auto-fixing the pipeline |
| Regression tracking and failure analytics | Supporting arbitrary DAG pipelines (the design allows it; the UI is linear) |
| Run fully offline (mock LLM) and with Anthropic when a key is set | Replacing OpenTelemetry (we export compatible span fields) |

## 3. Users
- **AI engineer (primary):** gets a bad output report, needs the failing step in seconds.
- **Product/QA reviewer:** flags bad outputs, supplies the corrected answer, never reads code.
- **Eng lead:** reads analytics to decide where to invest.

## 4. Success metrics
| Metric | Target |
|---|---|
| Root-cause step accuracy on the seeded 50-doc corpus | ≥ 90% for injected faults |
| Time from flag click to diagnosis | < 2 s (heuristic judge: ~1 ms; LLM judge: seconds) |
| Instrumenting a new step | 1 line (`@traced("name")`) |
| Eval cases created per confirmed flag | 1, with zero manual data entry |
| Demo corpus | 50 documents, ≥ 8 failures across ≥ 4 categories (shipped: 15 failures, 4 categories) |

## 5. System architecture
```
 Raw doc ─► [1 Intake] ─► [2 Extraction] ─► [3 Classification] ─► [4 Summarization] ─► Final output
               │              │                   │                     │
        @traced spans: input, output, prompt, raw response, tokens, latency, confidence, error
               └──────────────┴───────────┬───────┴─────────────────────┘
                                          ▼
                       Trace (JSON file)  +  SQLite index
                                          ▼
   Flag bad output ─► Backward Trace Analyzer ─► Diagnosis {root step, category, evidence, expected}
                                          ▼
             Human confirms / overrides ─► Eval case appended ─► Regression re-run ─► Analytics
```
**Repository layout**
```
backend/app/  models.py tracing.py pipeline.py llm.py heuristics.py analyzer.py storage.py samples.py main.py
frontend/src/ App.jsx api.js styles.css components/{Explorer,Evals,Analytics,ui}.jsx
data/         traces/*.json, forensics.db        docker-compose.yml
```

## 6. Data model
**Span:** `span_id, step, status, input, output, prompt, raw_response, tokens, latency_ms, confidence(1-5), error, judge{score,category,note}`
**Trace:** `trace_id, doc_id, ts, status(success|degraded|failure), spans[], final_output, final_score, meta{golden_type,fault}, diagnosis, flagged, confirmed`
**Diagnosis:** `root_step, category, propagated_to[], scores{}, evidence[{step,input,output,judge}], expected, explanation, diagnosis_ms, confirmed, overridden`
**SQLite:** `traces(trace_id, ts, doc_id, status, final_score, flagged, root_step, category, diagnosis_ms)`, `evals(eval_id, input_text, failing_step, bad_output, corrected_output, category, resolved, last_run)`, `runs(ts, total, resolved)`

---

## 7. Phase-by-phase requirements

### Phase 1: Multi-step pipeline (Days 1-3) · `pipeline.py`, `models.py`, `llm.py`, `samples.py`
**Why it matters:** if steps are not clean, typed and isolated, traces are meaningless.

| ID | Requirement |
|---|---|
| P1-1 | Four steps: **Intake** (normalize text/markdown/PDF-text), **Extraction** (people, orgs, dates, amounts, terms), **Classification** (contract, invoice, report, correspondence), **Summarization** (type-specific summary). |
| P1-2 | Every step is a pure function `TypedIn -> TypedOut`, both Pydantic models. Invalid LLM output raises a validation error at the boundary. |
| P1-3 | LLM access goes through one wrapper (`llm.complete`). Anthropic is used when `ANTHROPIC_API_KEY` is set; otherwise a deterministic mock keeps the project runnable offline. |
| P1-4 | Prompts ask the model for a self-reported `confidence` (1-5) inside the JSON. |
| P1-5 | Failure corpus: contracts with no dates, invoices with mixed currencies, documents ambiguous between two types, plus injected faults (hallucination, misclassification, context loss, malformed output). |

**Build notes:** `samples.py` generates 50 documents (32 clean, 18 failure scenarios) with a golden type. Faults are *mock-only demo injections* stored in trace `meta`; they simulate real bugs and can be "patched" to demonstrate regression tracking.
**Acceptance:** `run_pipeline()` returns typed output for all 50 docs; malformed LLM output fails loudly in the right span.

### Phase 2: Tracing layer (Days 3-6) · `tracing.py`, `storage.py`
| ID | Requirement |
|---|---|
| P2-1 | Each run creates a `Trace` with a unique `trace_id`, a span per step, final output and status. |
| P2-2 | `@traced("step")` records input, output, prompt, raw response, token count, latency and error automatically. Prompt/response/tokens are captured via `contextvars`, so step code never touches the tracer. |
| P2-3 | Confidence (1-5) is stored on the span. Status rules: any span error → `failure`; any confidence ≤ 2 → `degraded`; otherwise `success`. |
| P2-4 | Each trace is written to `data/traces/<id>.json` (inspectable, git-friendly) and indexed in SQLite for queries. |

**Design decision:** self-reported confidence is only a *hint*. The seeded hallucination reports confidence 4, which is why Phase 3 does not trust it.
**Acceptance:** adding a new step requires one decorator line; a failed step still produces a span with the error and later steps are marked "did not run".

### Phase 3: Backward trace analyzer (Days 6-9) · `analyzer.py`
**Algorithm**
1. Judge every span for quality given its input (deterministic grounding checks; optionally `min()` with an LLM-as-judge when a key is set).
2. Walk spans **backward** from the last step, collecting those below the 0.6 threshold.
3. The **earliest** failing span is the root cause; later failing spans are recorded as `propagated_to`.
4. If nothing fails but a span has confidence ≤ 2, report `no_defect_found` with an honest note: the source likely lacks the information (e.g. no dates).

**Per-step checks**
| Step | Check | Category |
|---|---|---|
| Any | span error / unparseable output | `prompt_failure` |
| Extraction | entity value not present in source text | `extraction_hallucination` |
| Classification | label ≠ golden type (or keyword ground truth) | `misclassification` |
| Summarization | repeats an ungrounded upstream entity, or tailored to the wrong type | `propagation_error` |
| Summarization | omits extracted dates/amounts | `context_loss` |
| Summarization | mixed currencies not flagged (instruction ignored) | `prompt_failure` |

**Evidence chain:** every diagnosis carries a natural-language explanation (e.g. *"Step 2 (Extraction) hallucinated 'John Smith', which does not appear in the source document. The summary repeated it."*), the input/output pairs of the root and downstream spans, and an `expected` output used by the diff view.
**Acceptance (verified on the shipped corpus):** all 15 seeded/real defects are diagnosed in ~1 ms each; the 3 no-date contracts are correctly reported as `no_defect_found`, not as bugs.

### Phase 4: Visual trace explorer (Days 9-11) · `frontend/`
**Design direction:** a dark "forensics bench" surface. The one bold moment is the **pipeline graph**: four asymmetric nodes joined by wires; a light pulse travels forward when a trace loads, and when you flag a trace the pulse runs **backward** node by node until the root cause lights up with a pulsing red halo. Everything else stays quiet. Typography: Bricolage Grotesque (headings) + Instrument Sans (body). Motion library: `motion/react`, with `prefers-reduced-motion` respected globally.

| ID | Requirement |
|---|---|
| P4-1 | Trace view: each step is a node. Green healthy, amber low confidence, red root cause, dashed red propagated, grey did-not-run. Click a node for input, output, prompt, raw response, tokens, latency, judge score. |
| P4-2 | Diff view for diagnosed failures: **Received · Produced · Should have produced**, with divergent lines highlighted red (wrong) and green (missing). |
| P4-3 | Flag button runs the backward analysis, animates the scan, and shows the diagnosis. The user confirms, or overrides the category, and can edit the corrected output JSON. |
| P4-4 | Left rail lists traces with status filters; shared-layout animation moves the active nav pill. |
**Accessibility:** keyboard focus rings, semantic buttons, responsive down to mobile (graph stacks vertically).

### Phase 4b: Live workflow view (added) · `POST /api/stream`, `Live.jsx`
Shows exactly what happens to one document as it moves through the pipeline, in real time.
| ID | Requirement |
|---|---|
| P4b-1 | The backend streams Server-Sent Events from inside the tracing layer: `trace_start`, then per step `start` → `prompt` → `response` → `end`, then `analysis_start` and `done`. |
| P4b-2 | Each stage card shows what the step received, the prompt sent, the raw model reply (typewriter reveal), the validated output, confidence, tokens and latency. |
| P4b-3 | The document panel highlights extracted entities by type as extraction completes; entities that do not appear in the document are shown as red "not in document" chips, so hallucinations are visible live. |
| P4b-4 | The quality check stage animates per-step judge scores and colours the failing stage red; the run is saved and opens in the trace explorer for flagging and confirming. |
| P4b-5 | Input can be a sample (including seeded failures), an uploaded .txt/.md/.pdf, or pasted text. A speed control paces the mock LLM so steps are watchable; real model latency is used when an API key is set. |

### Phase 5: Feedback-to-eval loop (Days 11-13) · `main.py`, `storage.py`, `Evals.jsx`, `Analytics.jsx`
| ID | Requirement |
|---|---|
| P5-1 | Confirming a diagnosis auto-creates an eval case: original input, failing step, bad output, corrected output, category. |
| P5-2 | **Regression re-run** replays every case through the *current* pipeline. A case is *resolved* when its failing step is no longer the root cause. Each run is stored, powering a "known issues resolved" trend line. |
| P5-3 | Analytics: failure types, step that fails most, failure rate over time (per batch of 10), average time to root cause, eval resolution rate. |
| P5-4 | Demo helper "Ship a fix": marks a fault class as patched, so re-running shows cases flipping to resolved. Cases that remain (ambiguous documents, mixed currencies) show real unfixed issues. |

### Phase 6: Portfolio polish (Days 13-14)
- **Demo scenario:** run the 50-doc batch (15 defects), open a failed trace, flag, watch the backward scan, confirm, show the eval set grow, ship a fix, re-run, show the trend.
- **Loom script (3 min):** bad output → explorer → flag → diagnosis → confirm → eval set → analytics.
- **Architecture doc:** reuse §5, add the algorithm in Phase 3.
- **Packaging:** `docker compose up --build` (UI :8080, API :8000, Swagger at `/docs`).

---

## 8. API (FastAPI)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/run` | Run one document through the pipeline and store its trace |
| POST | `/api/run-batch` | Run the 50-doc corpus; judge sweeps every trace |
| GET | `/api/traces[?status=]`, `/api/traces/{id}` | List and fetch traces |
| POST | `/api/traces/{id}/flag` | Mark as bad and run backward analysis |
| POST | `/api/traces/{id}/confirm` | Confirm/override diagnosis and create an eval case |
| GET | `/api/evals` | Cases and regression runs |
| POST | `/api/evals/rerun` | Replay the eval dataset against the current pipeline |
| GET | `/api/analytics` | Aggregates for the dashboard |
| POST | `/api/demo/patch`, `/api/demo/reset` | Demo helpers |

## 9. Test plan
- **Unit:** each heuristic (`extract_entities`, `top_type`), `traced` records error spans, status rules.
- **Golden:** the 50-doc corpus must yield the expected category per scenario (hallucination → extraction_hallucination, etc.).
- **Integration:** run → flag → confirm → rerun → analytics through `TestClient` (done as a smoke test: 50 traces, 15 defects, 15 evals, 0 → 9 resolved after patches).
- **UI:** manual walkthrough of the Loom script; keyboard-only pass; reduced-motion pass.

## 10. Risks and mitigations
| Risk | Mitigation |
|---|---|
| LLM judge is itself noisy | Deterministic grounding checks come first; the LLM score can only *lower* a score; humans confirm before anything enters the eval set |
| Self-reported confidence is unreliable | Treated as a hint only; judge catches confidently wrong outputs |
| Mock LLM hides real-model behavior | Same code path with `ANTHROPIC_API_KEY`; faults are explicitly labeled as demo injections |
| JSON file growth | Fine for portfolio scale; storage layer is isolated for a Postgres swap |

## 11. Future work
Pluggable DAG pipelines, OpenTelemetry export, golden-dataset import, CI gate that fails builds on eval regressions, prompt-version diffing, cost tracking per span.

## 12. Interview talking points
1. *Why observability for AI?* Failures are silent and compounding; the first wrong step is rarely the one that looks wrong.
2. *Why backward analysis?* The last step is the symptom; the earliest quality drop is the cause.
3. *Why not trust confidence?* The seeded hallucination reports 4/5; grounding checks caught it.
4. *Why the human-in-the-loop?* Confirmed cases become trustworthy evals, which turns every incident into a permanent regression test.
