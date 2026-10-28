"""
style.py - how the assistant talks, per user preference
--------------------------------------------------------
Research basis (see RESEARCH.md, section 6):
  - Nass & Lee (2001): people rate a synthetic voice as more attractive, credible and
    informative when its personality (extravert = louder/faster, introvert = softer/slower)
    matches their own: "similarity-attraction". Consistency between voice and words also helps.
  - Big Five is the best-validated personality model, but ultra-short tests (e.g. TIPI) are
    psychometrically weak. So we do NOT run a personality test or label anyone. We ask three
    everyday preference questions loosely based on Big Five dimensions, as Nass suggested.
  - Matching raises trust even when the content is not better (Dahlbäck et al.: accent
    similarity outweighed expertise). So style must never change numbers, sources or warnings.

Three dimensions:
  energy: lively | calm       (~ Extraversion)       -> TTS pace/expressiveness, exclamations
  detail: brief | detailed    (~ need for detail)    -> drop optional notes / add step-by-step working
  warmth: friendly | formal   (~ Agreeableness)      -> greeting, wording, sign-off

What style may change: openers, closers, optional notes (marked ⟦opt⟧ by the engine),
added step-by-step working computed from the same calculation, and voice pace.
What style may NOT change: any number, any source, any caveat or warning.
"""
import re
import zlib

DEFAULT = {"energy": "calm", "detail": "standard", "warmth": "neutral"}
CHOICES = {"energy": ("lively", "calm"), "detail": ("brief", "standard", "detailed"),
           "warmth": ("friendly", "neutral", "formal")}

QUESTIONS = [
    {"key": "energy",
     "en": "When you chat with a friend, do you like it lively and quick, or calm and slow?",
     "hi": "दोस्त से बात करते समय आपको कैसी बातचीत पसंद है: तेज़ और जोश वाली, या शांत और धीमी?",
     "options": [{"value": "lively", "en": "Lively and quick", "hi": "तेज़ और जोश वाली"},
                 {"value": "calm", "en": "Calm and slow", "hi": "शांत और धीमी"}]},
    {"key": "detail",
     "en": "Do you want just the answer, or the answer with the reasoning?",
     "hi": "आपको सिर्फ जवाब चाहिए, या जवाब के साथ पूरा हिसाब भी?",
     "options": [{"value": "brief", "en": "Just the answer", "hi": "सिर्फ जवाब"},
                 {"value": "detailed", "en": "Answer with reasoning", "hi": "जवाब और हिसाब"}]},
    {"key": "warmth",
     "en": "Should I talk like a friend, or like a professional advisor?",
     "hi": "मैं आपसे दोस्त की तरह बात करूँ, या एक प्रोफेशनल सलाहकार की तरह?",
     "options": [{"value": "friendly", "en": "Like a friend", "hi": "दोस्त की तरह"},
                 {"value": "formal", "en": "Like a professional", "hi": "प्रोफेशनल की तरह"}]},
]

# Voice: Sarvam bulbul:v3 supports pace 0.5-2.0 and a temperature (expressiveness) control.
VOICE = {"lively": {"pace": 1.15, "temperature": 0.75}, "calm": {"pace": 0.9, "temperature": 0.4}}

OPENERS = {
    ("friendly", "lively"): {"en": ["Sure!", "Good question!", "Here you go!"], "hi": ["ज़रूर!", "बढ़िया सवाल!", "ये लीजिए!"]},
    ("friendly", "calm"): {"en": ["Sure.", "Good question.", "Let me tell you."], "hi": ["ज़रूर।", "अच्छा सवाल है।", "बताता हूँ।"]},
    ("formal", "lively"): {"en": ["Certainly."], "hi": ["अवश्य।"]},
    ("formal", "calm"): {"en": ["Certainly. Here is the information."], "hi": ["अवश्य। यह रही जानकारी।"]},
}
# Voice-UX research: open-ended "anything else?" overloads memory; end with a question offering clear choices.
CLOSERS = {
    "friendly": {
        "tax_estimate": {"en": ["Want the working, or should I compare both regimes?"], "hi": ["पूरा हिसाब सुनना है, या दोनों व्यवस्थाओं की तुलना करूँ?"]},
        "fact": {"en": ["Want another rate, or a quick tax checkup?"], "hi": ["कोई और रेट जानना है, या एक छोटा टैक्स चेकअप करें?"]},
        "other": {"en": ["Want to try a quick tax checkup?"], "hi": ["एक छोटा टैक्स चेकअप करें?"]}},
    "formal": {
        "tax_estimate": {"en": ["Would you like the working, or a comparison of both regimes?"], "hi": ["क्या आप पूरा हिसाब या दोनों व्यवस्थाओं की तुलना चाहेंगे?"]},
        "fact": {"en": ["Would you like another rate, or a tax checkup?"], "hi": ["क्या आप कोई और रेट या टैक्स चेकअप चाहेंगे?"]},
        "other": {"en": ["Would you like to start a tax checkup?"], "hi": ["क्या आप टैक्स चेकअप शुरू करना चाहेंगे?"]}},
}

OPT_RE = re.compile(r"\s*⟦opt⟧(.*?)⟦/opt⟧", re.DOTALL)


def normalize(style: dict | None) -> dict:
    s = dict(DEFAULT)
    for k, v in (style or {}).items():
        if k in CHOICES and v in CHOICES[k]:
            s[k] = v
    return s


def _pick(options: list[str], seed: str) -> str:
    return options[zlib.crc32(seed.encode("utf-8")) % len(options)]   # varied but deterministic


def strip_markers(text: str, keep_optional: bool = True) -> str:
    text = OPT_RE.sub((lambda m: " " + m.group(1).strip()) if keep_optional else "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


# ---------- step-by-step working (detailed mode), computed from the same calc ----------
def _slab_lines(taxable: float, slabs: list, inr) -> list[tuple[float, float, float, float]]:
    out, lower = [], 0.0
    for upper, rate in slabs:
        up = float("inf") if upper is None else upper
        if taxable > lower:
            part = min(taxable, up) - lower
            out.append((lower, min(taxable, up), rate, part * rate))
        lower = up
    return out


def _walkthrough(res: dict, lang: str, store: dict, inr) -> str:
    calc, hra = res.get("calc"), res.get("hra")
    if hra and "exempt" in hra:
        pct = int(hra["pct"] * 100)
        if lang == "hi":
            return (f"हिसाब: मिलने वाला HRA {inr(hra['actual_hra'])}, सैलरी का {pct}% {inr(hra['pct_of_salary'])}, "
                    f"और किराया घटाकर 10% सैलरी {inr(hra['rent_minus_10'])}। इनमें सबसे कम {inr(hra['exempt'])} है, वही छूट है।")
        return (f"Here's the working: the HRA you receive is {inr(hra['actual_hra'])}, {pct}% of salary is "
                f"{inr(hra['pct_of_salary'])}, and rent minus 10% of salary is {inr(hra['rent_minus_10'])}. "
                f"The lowest, {inr(hra['exempt'])}, is your exemption.")
    if not calc or "new" not in calc:
        return ""
    mode = res.get("tax_mode")
    if mode == "compare":
        n, o = calc["new"], calc["old"]
        if lang == "hi":
            return (f"हिसाब: स्लैब के हिसाब से नई व्यवस्था में {inr(n['slab_tax'])} और पुरानी में {inr(o['slab_tax'])} बनता है, "
                    f"फिर रिबेट और 4% सेस लगाकर ऊपर वाले आंकड़े आते हैं।")
        return (f"Here's the working: by slabs, the new regime comes to {inr(n['slab_tax'])} and the old regime to "
                f"{inr(o['slab_tax'])}, then the rebate and 4% cess give the totals above.")
    key, cfg_key = ("old", "old_regime_calculator") if mode == "old" else ("new", "tax_calculator")
    r = calc[key]
    slabs = store[cfg_key]["slabs"]
    if key == "old":
        slabs = slabs[calc.get("age_group", "normal")]
    lines = _slab_lines(r["taxable"], slabs, inr)
    if lang == "hi":
        parts = [(f"पहले {inr(hi_ - lo)} पर कोई टैक्स नहीं" if rate == 0 else f"{inr(hi_ - lo)} पर {int(rate*100)}% = {inr(amt)}")
                 for lo, hi_, rate, amt in lines]
        return ("हिसाब: " + ", ".join(parts) + f"। कुल स्लैब टैक्स {inr(r['slab_tax'])}, रिबेट या राहत के बाद "
                f"{inr(r['after_rebate'])}, और 4% सेस {inr(r['cess'])}।")
    parts = [(f"the first {inr(hi_ - lo)} is tax-free" if rate == 0 else f"{inr(hi_ - lo)} at {int(rate*100)}% is {inr(amt)}")
             for lo, hi_, rate, amt in lines]
    return ("Here's the working: " + ", ".join(parts) + f". That's {inr(r['slab_tax'])} by slabs, "
            f"{inr(r['after_rebate'])} after the rebate or relief, plus {inr(r['cess'])} cess.")


# ---------- style commands ("keep it short", "थोड़ा डिटेल में") ----------
COMMANDS = [
    ("detail", "brief", r"keep it short|short answers?|be brief|shorter|less detail|just the answer|सिर्फ जवाब|छोटा जवाब|कम शब्दों"),
    ("detail", "detailed", r"more detail|in detail|step by step|explain more|show (me )?the working|डिटेल में|विस्तार से|पूरा हिसाब"),
    ("warmth", "formal", r"be (more )?formal|formal tone|more professional|प्रोफेशनल की तरह|औपचारिक"),
    ("warmth", "friendly", r"like a friend|be friendly|more casual|दोस्त की तरह|दोस्ताना"),
    ("energy", "calm", r"speak slower|talk slower|slow down|more calmly|धीरे बोल|आराम से बोल"),
    ("energy", "lively", r"speak faster|talk faster|more energy|तेज़ बोल|जल्दी बोल"),
]
CONFIRM = {
    ("detail", "brief"): {"en": "Okay, I'll keep answers short.", "hi": "ठीक है, अब मैं छोटे जवाब दूँगा।"},
    ("detail", "detailed"): {"en": "Okay, I'll show the working from now on.", "hi": "ठीक है, अब मैं पूरा हिसाब भी बताऊँगा।"},
    ("warmth", "formal"): {"en": "Certainly. I will keep a professional tone.", "hi": "अवश्य। मैं अब औपचारिक तरीके से बात करूँगा।"},
    ("warmth", "friendly"): {"en": "Sure, let's keep it friendly!", "hi": "बिल्कुल, अब दोस्त की तरह बात करेंगे!"},
    ("energy", "calm"): {"en": "Okay, I'll speak more slowly.", "hi": "ठीक है, मैं धीरे बोलूँगा।"},
    ("energy", "lively"): {"en": "Okay, I'll pick up the pace!", "hi": "ठीक है, थोड़ा तेज़ बोलूँगा!"},
}


def detect_command(text: str) -> list[tuple[str, str]]:
    t = (text or "").lower()
    return [(k, v) for k, v, pat in COMMANDS if re.search(pat, t)]


# ---------- apply ----------
def apply(res: dict, style: dict | None, store: dict, inr) -> dict:
    """Return {spoken, voice, style}. Never alters numbers or warnings in res['spoken']."""
    s = normalize(style)
    lang = res.get("lang", "en")
    base = res["spoken"]
    text = strip_markers(base, keep_optional=(s["detail"] != "brief"))
    if s["detail"] == "detailed" and res.get("route") == "tax_estimate":
        w = _walkthrough(res, lang, store, inr)
        if w:
            text = f"{text} {w}"
    seed = res.get("question", "")
    if res.get("route") not in ("style", "checkup", "no_answer", "out_of_scope"):   # these already end with their own question
        op = OPENERS.get((s["warmth"], s["energy"]))
        if op:
            text = f"{_pick(op[lang], seed)} {text}"
        cl = CLOSERS.get(s["warmth"])
        if cl:
            kind = res.get("route") if res.get("route") in ("tax_estimate", "fact") else "other"
            if res.get("tax_mode") == "compare" and kind == "tax_estimate":
                kind = "other" if s["detail"] == "detailed" else kind
            text = f"{text} {_pick(cl[kind][lang], seed + 'c')}"
    if s["energy"] == "calm":
        text = text.replace("!", ".")
    return {"spoken": text, "voice": VOICE[s["energy"]], "style": s}
