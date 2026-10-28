"""
Smoke test for a RUNNING server. Start the server first, then in a second terminal:
    python smoke_check.py            (default http://localhost:8000)
    python smoke_check.py https://your-live-url
Prints PASS/FAIL for each check. Send the output to Claude if anything fails.
"""
import sys

import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
ok = fail = 0


def check(name, fn):
    global ok, fail
    try:
        msg = fn()
        print(f"PASS  {name}" + (f"  ({msg})" if msg else ""))
        ok += 1
    except Exception as e:
        print(f"FAIL  {name}  ->  {e}")
        fail += 1


def post(path, body):
    r = requests.post(BASE + path, json=body, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def health():
    h = requests.get(BASE + "/health", timeout=10).json()
    return f"facts={h['facts']}, sarvam_speech={h['sarvam_speech']}, llm={h['llm']}, finverify={h['finverify_mode']}"


def page():
    r = requests.get(BASE + "/", timeout=10)
    assert r.status_code == 200 and "Start tax checkup" in r.text, "page didn't load"


def fact():
    d = post("/ask", {"question": "What is the PPF interest rate?"})
    assert d["route"] == "fact" and "7.1%" in d["spoken"], d["spoken"]
    return d["spoken"][:60] + "..."


def tax():
    d = post("/ask", {"question": "How much tax will I pay on salary 15 lakh?"})
    assert d["calc"]["new"]["total"] == 97500, d["calc"]
    assert "97 thousand 500 rupees" in d["speech"], d["speech"]


def hindi():
    d = post("/ask", {"question": "मेरी सैलरी 15 लाख है, कौन सी व्यवस्था बेहतर है?"})
    assert d["lang"] == "hi" and d["calc"]["breakeven_deductions"] == 543750


def checkup():
    st = None
    for u in ["start tax checkup", "15 lakh salary", "no", "none", "no"]:
        d = post("/ask", {"question": u, "dialog_state": st})
        st = d.get("dialog_state")
    assert "saves you" in d["spoken"] or "no tax" in d["spoken"], d["spoken"]
    return d["spoken"][:70] + "..."


def style_q():
    d = requests.get(BASE + "/style/questions", timeout=10).json()
    assert len(d["questions"]) == 3


def tts():
    h = requests.get(BASE + "/health", timeout=10).json()
    if not h["sarvam_speech"]:
        return "skipped: no SARVAM_API_KEY yet (browser voice will be used)"
    d = post("/tts", {"text": "PPF ki byaj dar 7.1 pratishat hai.", "lang": "hi", "pace": 1.0})
    assert len(d["audio_b64"]) > 1000, "no audio returned"
    return "Sarvam returned audio"


for name, fn in [("server is up", health), ("web page loads", page), ("sourced fact", fact),
                 ("tax calculation + spoken numbers", tax), ("Hindi regime comparison", hindi),
                 ("tax checkup conversation", checkup), ("talking-style questions", style_q),
                 ("Sarvam voice", tts)]:
    check(name, fn)
print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
