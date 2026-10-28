"""Sarvam speech: STT (saaras) and TTS (bulbul). Request formats per docs.sarvam.ai."""
import json
import os

import requests

BASE = "https://api.sarvam.ai"
KEY = os.getenv("SARVAM_API_KEY", "")
STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v4")
TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
SPEAKER = os.getenv("SARVAM_SPEAKER", "")

# Bias recognition toward finance vocabulary (saaras:v4 only, max 50 terms).
KEYTERMS = ["PPF", "Sukanya Samriddhi", "SCSS", "NSC", "Kisan Vikas Patra", "NPS", "ELSS", "LIC",
            "ITR", "TDS", "HRA", "standard deduction", "new tax regime", "old tax regime", "rebate",
            "Section 123", "80C", "slab", "lakh", "crore", "salary", "pension"]


class SpeechError(Exception):
    pass


def configured() -> bool:
    return bool(KEY)


def stt(audio: bytes, filename: str, content_type: str, lang_hint: str | None) -> dict:
    data = {"model": STT_MODEL, "language_code": {"hi": "hi-IN", "en": "en-IN"}.get(lang_hint or "", "unknown")}
    if STT_MODEL == "saaras:v4":
        data["keyterms"] = json.dumps(KEYTERMS[:50], ensure_ascii=False)
    r = requests.post(f"{BASE}/speech-to-text", headers={"api-subscription-key": KEY},
                      files={"file": (filename or "audio.webm", audio, content_type or "audio/webm")},
                      data=data, timeout=30)
    if r.status_code != 200:
        raise SpeechError(f"Sarvam speech-to-text failed ({r.status_code}): {r.text[:300]}")
    j = r.json()
    code = (j.get("language_code") or "").lower()
    return {"transcript": j.get("transcript", ""), "lang": "hi" if code.startswith("hi") else "en"}


def tts(text: str, lang: str, pace: float | None = None, temperature: float | None = None) -> str:
    payload = {"text": text[:2500], "language_code": "hi-IN" if lang == "hi" else "en-IN", "model": TTS_MODEL}
    if SPEAKER:
        payload["speaker"] = SPEAKER
    if pace is not None:
        payload["pace"] = max(0.5, min(2.0, float(pace)))       # bulbul:v3 range per Sarvam docs
    if temperature is not None and TTS_MODEL.startswith("bulbul:v3"):
        payload["temperature"] = max(0.01, min(1.0, float(temperature)))
    r = requests.post(f"{BASE}/text-to-speech",
                      headers={"api-subscription-key": KEY, "Content-Type": "application/json"},
                      json=payload, timeout=30)
    if r.status_code != 200:
        raise SpeechError(f"Sarvam text-to-speech failed ({r.status_code}): {r.text[:300]}")
    return "".join(r.json().get("audios", []))
