"""Phase 1.3: demo corpus of 50 documents (32 clean + 18 deliberate failure cases)."""
import random

ORGS = ["Acme Corp", "Globex Corp", "Initech Inc", "Umbra Labs", "Vandelay Ltd", "Stark Holdings",
        "Wayne Partners", "Hooli Inc", "Soylent Co", "Tyrell Corp"]
PEOPLE = ["Priya Rao", "Marcus Lee", "Elena Petrova", "Tomas Berg", "Aisha Khan", "Daniel Okafor",
          "Sofia Rossi", "Kenji Mori"]


def _d(r):
    return f"{r.choice(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'])} {r.randint(1, 28)}, 2025"


def _amt(r, cur="$"):
    return f"{cur}{r.randint(2, 90) * 100:,}"


def contract(r, dated=True):
    a, b = r.sample(ORGS, 2)
    when = f"on {_d(r)} " if dated else "effective upon signature "
    return (f"MASTER SERVICES AGREEMENT\nThis Agreement is made {when}between {a} and {b} (the parties). "
            f"The parties hereby agree to a term of 12 months. Either party may terminate with 30 days notice. "
            f"Confidentiality and indemnity obligations apply. Fee: {_amt(r)}. Signed by {r.choice(PEOPLE)}.")


def invoice(r, mixed=False):
    a, b = r.sample(ORGS, 2)
    second = "€" if mixed else "$"
    return (f"INVOICE #{r.randint(1000, 9999)}\nBill To: {a}\nIssued by {b} on {_d(r)}\nPayment due: {_d(r)}\n"
            f"Subtotal: {_amt(r)}\nAmount due: {_amt(r, second)}\nNet 30 payment terms apply.")


def report(r):
    return (f"QUARTERLY REPORT Q{r.randint(1, 4)}\nPrepared by {r.choice(PEOPLE)} for {r.choice(ORGS)}. "
            f"Findings: revenue grew 12% quarter over quarter; churn fell. Revenue reached {_amt(r)}. "
            f"Analysis of metrics shows a steady forecast. Published {_d(r)}.")


def letter(r):
    a, b = r.sample(PEOPLE, 2)
    return (f"Dear {a},\nI am writing to follow up on our call last week. Thanks for sending the files over. "
            f"Let me know a good time to talk, and I will share the updates by {_d(r)}.\nRegards,\n{b}")


def ambiguous(r):
    a, b = r.sample(PEOPLE, 2)
    o1, o2 = r.sample(ORGS, 2)
    return (f"Dear {a},\nFurther to our call, the parties hereby agree to the attached Agreement between "
            f"{o1} and {o2}. Thanks again.\nRegards,\n{b}")


def build() -> list[dict]:
    r = random.Random(7)
    spec = ([("contract", lambda: contract(r), None)] * 9 + [("invoice", lambda: invoice(r), None)] * 8 +
            [("report", lambda: report(r), None)] * 8 + [("correspondence", lambda: letter(r), None)] * 7 +
            [("contract", lambda: contract(r, False), "no_dates")] * 3 +
            [("invoice", lambda: invoice(r, True), "mixed_currency")] * 3 +
            [("correspondence", lambda: ambiguous(r), "ambiguous")] * 3 +
            [("contract", lambda: contract(r), "hallucination")] * 1 +
            [("invoice", lambda: invoice(r), "hallucination")] * 1 +
            [("report", lambda: report(r), "hallucination")] * 1 +
            [("invoice", lambda: invoice(r), "misclassify")] * 1 +
            [("report", lambda: report(r), "misclassify")] * 1 +
            [("invoice", lambda: invoice(r), "context_loss")] * 2 +
            [("contract", lambda: contract(r), "prompt_failure")] * 2)
    docs = []
    for i, (golden, make, scenario) in enumerate(spec):
        fault = scenario if scenario in ("hallucination", "misclassify", "context_loss", "prompt_failure") else None
        docs.append({"text": make(), "golden_type": golden, "scenario": scenario or "clean", "fault": fault})
    r.shuffle(docs)
    for i, d in enumerate(docs, 1):
        d["doc_id"] = f"doc-{i:03d}"
    return docs
