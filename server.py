"""
finverify voice - server (v4)
  GET  /             voice demo page
  GET  /facts        every figure the assistant can speak, with sources (transparency)
  POST /ask          {"question", "lang"?} -> answer from the engine
  POST /stt          multipart audio -> transcript (Sarvam)
  POST /tts          {"text", "lang"} -> base64 WAV (Sarvam)
  GET  /style/questions  the 3 talking-style questions (en + hi)
  POST /call         {"phone", "when": now|rates_change, "consent": true} -> Bolna outbound call
  POST /bolna/answer Bolna custom function -> {"answer": "..."}  (deterministic, fast)
  GET  /health
Run: uvicorn server:app --port 8000
"""
import datetime as dt
import os
import re
import time

import requests
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import engine  # noqa: E402
import finverify_adapter as fv  # noqa: E402
import speech  # noqa: E402
import style as style_mod  # noqa: E402

BOLNA_TOKEN = os.getenv("BOLNA_TOKEN", "")
BOLNA_API_KEY = os.getenv("BOLNA_API_KEY", "")          # for placing outbound calls
BOLNA_AGENT_ID = os.getenv("BOLNA_AGENT_ID", "")        # agent that runs the callback / reminder call
BOLNA_FROM_NUMBER = os.getenv("BOLNA_FROM_NUMBER", "")  # optional caller ID
_call_log: dict[str, list[float]] = {}                  # phone -> timestamps (simple abuse limit)
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app = FastAPI(title="finverify voice")
app.mount("/static", StaticFiles(directory=STATIC), name="static")   # serves static/signs.js


class AskIn(BaseModel):
    question: str
    lang: str | None = None
    context: dict | None = None   # previous turn: {"question", "route", "calc", "tax_mode"} for follow-ups
    style: dict | None = None     # {"energy": lively|calm, "detail": brief|standard|detailed, "warmth": friendly|neutral|formal}
    dialog_state: dict | None = None  # Tax Checkup conversation state, sent back each turn


class TtsIn(BaseModel):
    text: str
    lang: str = "en"
    pace: float | None = None
    temperature: float | None = None


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/health")
def health():
    return {"ok": True, "facts": len(engine.STORE["facts"]), "finverify_mode": fv.MODE,
            "llm": bool(os.getenv("LLM_API_KEY") or os.getenv("SARVAM_API_KEY")),
            "sarvam_speech": speech.configured(), "today": engine.today().isoformat()}


@app.get("/facts")
def facts():
    out = []
    for f in engine.STORE["facts"]:
        text, stale = engine.render_fact(f, "en")
        out.append({"id": f["id"], "title": f["title"], "says": text, "valid_until": f["valid_until"],
                    "stale": stale, "confidence": f.get("confidence", ""), "sources": f["sources"]})
    return {"facts": out, "tax_calculator_sources": engine.STORE["tax_calculator"]["sources"]}


@app.post("/ask")
def ask(body: AskIn):
    if not body.question.strip():
        raise HTTPException(400, "Question is empty.")
    return engine.answer(body.question, body.lang, context=body.context, style=body.style, dialog_state=body.dialog_state)


class CallIn(BaseModel):
    phone: str
    when: str = "now"            # "now" | "rates_change"
    consent: bool = False
    lang: str = "en"
    style: dict | None = None


def _rates_change_time() -> str:
    """10:00 IST on the day after the earliest small-savings rate expires (they're quarterly)."""
    ids = ("ppf_rate", "ssy_rate", "scss_rate", "nsc_rate", "kvp_rate")
    until = min(dt.date.fromisoformat(f["valid_until"]) for f in engine.STORE["facts"] if f["id"] in ids)
    day = until + dt.timedelta(days=1)
    return f"{day.isoformat()}T10:00:00+05:30"


@app.post("/call")
def request_call(body: CallIn):
    """Ask Bolna to call the user now, or when the rates change (Bolna POST /call)."""
    if not (BOLNA_API_KEY and BOLNA_AGENT_ID):
        raise HTTPException(501, "Calling isn't set up: add BOLNA_API_KEY and BOLNA_AGENT_ID to .env.")
    if not body.consent:
        raise HTTPException(400, "Please tick the box to agree to receive the call.")
    phone = re.sub(r"[\s\-()]", "", body.phone)
    if re.fullmatch(r"[6-9]\d{9}", phone):
        phone = "+91" + phone                       # Indian mobile without country code
    if not re.fullmatch(r"\+\d{10,15}", phone):
        raise HTTPException(400, "Please enter the number with country code, like +91 98765 43210.")
    now = time.time()
    recent = [t for t in _call_log.get(phone, []) if now - t < 86400]
    if len(recent) >= 3:
        raise HTTPException(429, "That number already has 3 call requests today.")
    st = style_mod.normalize(body.style)
    payload = {"agent_id": BOLNA_AGENT_ID, "recipient_phone_number": phone,
               "user_data": {"purpose": "rate_update" if body.when == "rates_change" else "checkup",
                             "lang": "Hindi" if body.lang == "hi" else "English",
                             "detail": st["detail"], "warmth": st["warmth"], "energy": st["energy"]}}
    if BOLNA_FROM_NUMBER:
        payload["from_phone_number"] = BOLNA_FROM_NUMBER
    if body.when == "rates_change":
        payload["scheduled_at"] = _rates_change_time()
    r = requests.post("https://api.bolna.ai/call", json=payload, timeout=15,
                      headers={"Authorization": f"Bearer {BOLNA_API_KEY}", "Content-Type": "application/json"})
    if r.status_code >= 300:
        raise HTTPException(502, f"Bolna couldn't place the call ({r.status_code}): {r.text[:200]}")
    _call_log[phone] = recent + [now]
    j = r.json()
    return {"status": j.get("status"), "execution_id": j.get("execution_id"), "scheduled_at": payload.get("scheduled_at")}


@app.get("/style/questions")
def style_questions():
    """The three onboarding questions (English + Hindi) and the default style."""
    return {"questions": style_mod.QUESTIONS, "default": style_mod.DEFAULT}


@app.post("/stt")
async def stt(file: UploadFile = File(...), lang: str | None = Form(None)):
    if not speech.configured():
        raise HTTPException(501, "SARVAM_API_KEY is not set.")
    audio = await file.read()
    if len(audio) < 1000:
        raise HTTPException(400, "Recording was too short. Hold the mic a little longer.")
    try:
        return speech.stt(audio, file.filename, file.content_type, lang)
    except speech.SpeechError as e:
        raise HTTPException(502, str(e))


@app.post("/tts")
def tts(body: TtsIn):
    if not speech.configured():
        raise HTTPException(501, "SARVAM_API_KEY is not set.")
    try:
        return {"audio_b64": speech.tts(body.text, body.lang, body.pace, body.temperature)}
    except speech.SpeechError as e:
        raise HTTPException(502, str(e))


@app.post("/bolna/answer")
async def bolna_answer(request: Request, authorization: str | None = Header(None)):
    """Bolna sends a JSON body with the mapped params (confirmed in Bolna's docs)."""
    if BOLNA_TOKEN and authorization != f"Bearer {BOLNA_TOKEN}":
        raise HTTPException(401, "Bad or missing token.")
    try:
        data = await request.json()
    except Exception:
        data = dict(request.query_params)
    q = data.get("question") or (data.get("arguments") or {}).get("question") or ""
    words = str(data.get("style") or "").lower().replace(" ", "").split(",")
    st = {k: w for w in words for k, opts in style_mod.CHOICES.items() if w in opts}
    r = engine.answer(q, style=st)
    return {"answer": r["spoken"], "kind": r["route"],
            "instruction": "Read 'answer' to the caller exactly as written. Do not change, round, add or drop any number."}
