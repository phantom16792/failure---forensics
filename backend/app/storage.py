# """Phase 2.4 / Phase 5: JSON trace files (human-readable, git-friendly) + SQLite index and eval tables."""
# import json, os, sqlite3
# from pathlib import Path

# DATA = Path(os.getenv("FF_DATA", Path(__file__).resolve().parents[2] / "data"))
# TRACES = DATA / "traces"
# DB = DATA / "forensics.db"


# def db():
#     c = sqlite3.connect(DB)
#     c.row_factory = sqlite3.Row
#     return c


# def init():
#     TRACES.mkdir(parents=True, exist_ok=True)
#     with db() as c:
#         c.executescript("""
#         CREATE TABLE IF NOT EXISTS traces(trace_id TEXT PRIMARY KEY, ts TEXT, doc_id TEXT, status TEXT,
#           final_score REAL, flagged INT DEFAULT 0, root_step TEXT, category TEXT, diagnosis_ms REAL);
#         CREATE TABLE IF NOT EXISTS evals(eval_id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, trace_id TEXT,
#           input_text TEXT, failing_step TEXT, bad_output TEXT, corrected_output TEXT, category TEXT,
#           meta TEXT, resolved INT DEFAULT 0, last_run TEXT);
#         CREATE TABLE IF NOT EXISTS runs(run_id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, total INT, resolved INT);
#         """)


# def reset():
#     for f in TRACES.glob("*.json"):
#         f.unlink()
#     with db() as c:
#         c.executescript("DELETE FROM traces; DELETE FROM evals; DELETE FROM runs;")


# def save_trace(t):
#     (TRACES / f"{t.trace_id}.json").write_text(t.model_dump_json(indent=2))
#     d = t.diagnosis or {}
#     with db() as c:
#         c.execute("INSERT OR REPLACE INTO traces VALUES(?,?,?,?,?,?,?,?,?)",
#                   (t.trace_id, t.ts, t.doc_id, t.status, t.final_score, int(t.flagged),
#                    d.get("root_step"), d.get("category"), d.get("diagnosis_ms")))


# def load_trace(trace_id):
#     p = TRACES / f"{trace_id}.json"
#     return json.loads(p.read_text()) if p.exists() else None


# def list_traces(status=None):
#     q, args = "SELECT * FROM traces", ()
#     if status:
#         q, args = q + " WHERE status=?", (status,)
#     with db() as c:
#         return [dict(r) for r in c.execute(q + " ORDER BY ts DESC", args)]


# def add_eval(trace, step, bad, corrected, category):
#     with db() as c:
#         cur = c.execute("INSERT INTO evals(ts,trace_id,input_text,failing_step,bad_output,corrected_output,category,meta)"
#                         " VALUES(datetime('now'),?,?,?,?,?,?,?)",
#                         (trace["trace_id"], trace["spans"][0]["output"]["text"], step, json.dumps(bad),
#                          json.dumps(corrected), category, json.dumps(trace["meta"])))
#         return cur.lastrowid


# def list_evals():
#     with db() as c:
#         rows = [dict(r) for r in c.execute("SELECT * FROM evals ORDER BY eval_id DESC")]
#     for r in rows:
#         for k in ("bad_output", "corrected_output", "meta"):
#             r[k] = json.loads(r[k]) if r[k] else None
#     return rows


# def mark_eval(eval_id, resolved):
#     with db() as c:
#         c.execute("UPDATE evals SET resolved=?, last_run=datetime('now') WHERE eval_id=?", (int(resolved), eval_id))


# def add_run(total, resolved):
#     with db() as c:
#         c.execute("INSERT INTO runs(ts,total,resolved) VALUES(datetime('now'),?,?)", (total, resolved))


# def list_runs():
#     with db() as c:
#         return [dict(r) for r in c.execute("SELECT * FROM runs ORDER BY run_id")]


# def analytics():
#     with db() as c:
#         rows = [dict(r) for r in c.execute("SELECT * FROM traces ORDER BY ts")]
#     defects = [r for r in rows if r["category"] and r["category"] != "no_defect_found"]
#     count = lambda key: [{"name": k, "count": sum(1 for r in defects if r[key] == k)}
#                          for k in sorted({r[key] for r in defects})]
#     buckets = []
#     for i in range(0, len(rows), 10):
#         chunk = rows[i:i + 10]
#         bad = sum(1 for r in chunk if r["category"] and r["category"] != "no_defect_found")
#         buckets.append({"name": f"{i + 1}-{i + len(chunk)}", "rate": round(100 * bad / len(chunk), 1)})
#     ms = [r["diagnosis_ms"] for r in defects if r["diagnosis_ms"] is not None]
#     evals = list_evals()
#     return {"total": len(rows), "defects": len(defects), "by_category": count("category"),
#             "by_step": count("root_step"), "failure_rate": buckets,
#             "avg_diagnosis_ms": round(sum(ms) / len(ms), 2) if ms else 0,
#             "evals": len(evals), "resolved": sum(e["resolved"] for e in evals)}


from .database import SessionLocal

class Storage:
    def save_trace(self, trace_id: str, data: dict):
        db = SessionLocal()
        try:
            # Insert or update record in PostgreSQL table
            pass
        finally:
            db.close()

    def get_trace(self, trace_id: str):
        db = SessionLocal()
        try:
            # Fetch record by trace_id from PostgreSQL
            pass
        finally:
            db.close()

storage = Storage()