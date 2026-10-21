# FailureForensics

Observability for multi-step AI pipelines: trace every step, find the root cause of a bad output, and turn confirmed failures into a growing eval set. Full spec in [PRD.md](PRD.md).

## Run locally
```bash
# backend (works offline with a deterministic mock LLM; set ANTHROPIC_API_KEY to use Claude)
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
# frontend
cd frontend && npm install && npm run dev      # http://localhost:5173
```
Or `docker compose up --build` (UI on :8080, API on :8000, API docs at :8000/docs).

## Demo in 2 minutes
0. Open **Live workflow**, pick a sample marked *hallucination*, press **Run sample**, and watch each step stream in.
1. Click **Run 50-document batch**. 15 traces are diagnosed as failures.
2. Open a failed trace, click **Flag as bad output**, watch the backward scan land on the root cause.
3. Confirm the diagnosis: the case lands in **Eval dataset**.
4. In Eval dataset, **Ship a fix** for a failure class, then **Re-run regression** and watch the trend line climb.
