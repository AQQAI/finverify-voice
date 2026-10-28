"""
finverify adapter
-----------------
Used by the number firewall (engine.firewall) to check any figure an LLM writes.
Edit ONE place to connect your real finverify.

check(question, answer) -> list[Claim], one per figure in `answer`.

Modes (FINVERIFY_MODE in .env):
  off    -> every figure is "unverified" (so the firewall withholds it). Safe default.
  http   -> POST to FINVERIFY_URL; adjust _from_http() to your real API shape.
  python -> import finverify directly; fill in _from_python().
"""
import os
import re
from dataclasses import asdict, dataclass

import requests

MODE = os.getenv("FINVERIFY_MODE", "off").lower()
URL = os.getenv("FINVERIFY_URL", "http://localhost:9000/check")
TIMEOUT = float(os.getenv("FINVERIFY_TIMEOUT", "5"))


@dataclass
class Claim:
    text: str                   # exact substring of the answer, e.g. "₹1.5 lakh"
    status: str                 # "verified" | "wrong" | "unverified"
    correct: str | None = None  # replacement when status == "wrong"
    source: str | None = None

    def to_dict(self):
        return asdict(self)


_NUM = r"\d+(?:,\d{2,3})*(?:\.\d+)?"   # never swallows a trailing comma
FIGURE_RE = re.compile(
    rf"(?:₹|Rs\.?|INR)\s?{_NUM}(?:\s?(?:lakh|lac|crore|cr|लाख|करोड़))?"
    rf"|{_NUM}\s?(?:%|percent|प्रतिशत|lakh|lac|crore|लाख|करोड़)"
    r"|\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b",
    re.IGNORECASE,
)


def extract_figures(answer: str) -> list[str]:
    seen, out = set(), []
    for m in FIGURE_RE.finditer(answer):
        t = m.group(0).strip()
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _off(question, answer):
    return [Claim(text=f, status="unverified") for f in extract_figures(answer)]


def _from_http(question, answer):
    # PLACEHOLDER request/response shape: change to match your finverify API.
    r = requests.post(URL, json={"question": question, "answer": answer}, timeout=TIMEOUT)
    r.raise_for_status()
    return [Claim(text=c["text"], status=c.get("status", "unverified"),
                  correct=c.get("correct"), source=c.get("source"))
            for c in r.json().get("claims", [])]


def _from_python(question, answer):
    # import finverify
    # return [Claim(...) for ... in finverify.check(answer)]
    raise NotImplementedError("Fill in _from_python() in finverify_adapter.py")


def check(question: str, answer: str) -> list[Claim]:
    try:
        if MODE == "http":
            claims = _from_http(question, answer)
        elif MODE == "python":
            claims = _from_python(question, answer)
        else:
            claims = _off(question, answer)
    except Exception as e:   # finverify down -> fail safe (everything unverified -> withheld)
        print(f"[finverify] error, treating all figures as unverified: {e}")
        claims = _off(question, answer)
    return claims
