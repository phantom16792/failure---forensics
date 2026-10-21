"""Deterministic helpers shared by the offline mock LLM and the analyzer's ground-truth checks."""
import re

MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
STOP = {"This", "The", "Dear", "Sincerely", "Regards", "Invoice", "Payment", "Terms", "Agreement",
        "Total", "Bill", "Quarterly", "Report", "Summary", "Services", "Service", "Effective", "Date",
        "Amount", "Due", "Thank", "Thanks", "Best", "Statement", "Revenue", "Please", "Further",
        "Attached", "Net", "Fee", "Term", "Key", "Findings", "Notes", "Subject", "Hi", "Hello", "To",
        "From", "Re", "Prepared", "Overview", "Metrics", "Customer", "Churn", "Issued", "Signed", "Published",
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"}
ORG_SUFFIX = {"Corp", "Inc", "LLC", "Ltd", "GmbH", "Labs", "Co", "Holdings", "Partners"}
TERMS = ["termination", "indemnity", "confidentiality", "net 30", "renewal", "penalty", "warranty",
         "revenue", "churn", "forecast", "deliverables"]
KW = {
    "contract": ["agreement", "parties", "hereby", "terminat", "indemn"],
    "invoice": ["invoice", "bill to", "amount due", "net 30", "subtotal", "payment due"],
    "report": ["report", "quarter", "findings", "revenue", "analysis", "metrics"],
    "correspondence": ["dear", "writing to", "regards", "thanks", "sincerely"],
}
CURRENCIES = "$€£₹"


def extract_entities(text: str) -> list[dict]:
    out, seen = [], set()

    def add(t, v):
        if (t, v) not in seen:
            seen.add((t, v))
            out.append({"type": t, "value": v})

    for m in re.finditer(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)+\b", text):
        words = m.group(0).split()
        while words and words[0] in STOP:
            words = words[1:]
        if len(words) < 2 or any(w in STOP for w in words):
            continue
        add("org" if words[-1] in ORG_SUFFIX else "person", " ".join(words))
    for m in re.finditer(rf"\b\d{{4}}-\d{{2}}-\d{{2}}\b|\b(?:{MONTHS})[a-z]* \d{{1,2}}, \d{{4}}\b", text):
        add("date", m.group(0))
    for m in re.finditer(rf"[{CURRENCIES}]\s?\d[\d,]*(?:\.\d+)?", text):
        add("amount", m.group(0))
    low = text.lower()
    for t in TERMS:
        if t in low:
            add("term", t)
    return out


def currencies_in(text: str) -> set[str]:
    return {c for c in text if c in CURRENCIES}


def keyword_scores(text: str) -> dict[str, int]:
    low = text.lower()
    return {k: sum(w in low for w in ws) for k, ws in KW.items()}


def top_type(text: str) -> tuple[str, int]:
    s = keyword_scores(text)
    ranked = sorted(s.items(), key=lambda kv: -kv[1])  # stable: ties keep KW order
    return ranked[0][0], ranked[0][1] - ranked[1][1]


def build_summary(doc_type: str, ents: list[dict], drop: tuple = ()) -> dict:
    g = lambda t: [e["value"] for e in ents if e["type"] == t]
    parties = g("person") + g("org")
    bullets = [f"Parties: {', '.join(parties) or 'none found'}"]
    if "date" not in drop:
        bullets.append(f"Dates: {', '.join(g('date')) or 'none found'}")
    if "amount" not in drop:
        bullets.append(f"Amounts: {', '.join(g('amount')) or 'none found'}")
    bullets.append(f"Key terms: {', '.join(g('term')) or 'none found'}")
    return {"headline": f"{doc_type.title()} summary", "bullets": bullets}
