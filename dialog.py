"""
dialog.py - "Tax Checkup": a real two-way voice conversation
-------------------------------------------------------------
Design rules (from voice-UX research, see RESEARCH.md section 7):
  - One question per turn, and every prompt ends with that question.
  - Echo what was heard ("Got it, ₹15 lakh a year") so a mishearing is caught early;
    the user can correct it any time ("no, 18 lakh").
  - The verdict fits in one breath, then offers at most three clear choices.
  - Repair gracefully: say what kind of answer is expected, never just repeat.
  - Numbers still come only from the engine's calculators (same rules as everywhere else).

The server is stateless: the client sends back the `state` it received on the last turn.
"""
import re

TRIGGER = re.compile(r"tax check ?up|check ?up|start (?:a )?checkup|टैक्स चेकअप|चेकअप|जाँच शुरू|टैक्स जाँच")
_END = r"(?=[\s,.।!?]|$)"   # \b does not work reliably on Devanagari, so use an explicit word end
YES = re.compile(r"^\s*(yes|yeah|yep|haan|han|ha|sure|correct|right|ok|okay|हाँ|हां|जी हाँ|जी|ठीक|सही)" + _END)
NO = re.compile(r"^\s*(no|nope|nahi|nahin|not really|none|नहीं|नही|ना)" + _END)
NONE = re.compile(r"none|nothing|no deductions|kuch nahi|कोई नहीं|कुछ नहीं|नहीं")
SKIP = re.compile(r"skip|don'?t know|not sure|pata nahi|पता नहीं|छोड़ो|स्किप")
REPEAT = re.compile(r"repeat|say (?:that|it) again|again|फिर से|दोबारा")
STOP = re.compile(r"stop|exit|quit|cancel|बंद करो|रुको|बस")
CORRECTION = re.compile(r"^\s*(no|actually|sorry|nahi|नहीं|असल में|माफ़)" + _END)

T = {
    "en": {
        "start": "Let's do a quick tax checkup. It takes about a minute, one question at a time. First, what is your yearly salary or pension?",
        "income_repair": "Sorry, I didn't catch an amount. You can say something like 12 lakh. What is your yearly salary or pension?",
        "income_ok": "{ack} {amount} a year.",
        "age_q": "Are you 60 or older?",
        "age_repair": "Just yes or no is fine. Are you 60 or older?",
        "ded_q": "Next, deductions. Tell me the amounts, or just say none. Do you claim PPF or LIC, health insurance, or home loan interest?",
        "ded_repair": "Which is that for: PPF or LIC, health insurance, or home loan interest?",
        "ded_ok": "{ack} {amount} in deductions.",
        "ded_none": "{ack} no deductions.",
        "rent_q": "Do you live on rent and get HRA from your employer?",
        "rent_repair": "Just yes or no. Do you live on rent and get HRA?",
        "basic_q": "What is your yearly basic salary, including DA?",
        "hra_q": "How much HRA do you get in a year?",
        "rentamt_q": "You can say it per month. How much rent do you pay?",
        "city_q": "Which city do you live in?",
        "amount_repair": "Sorry, I need an amount, like 6 lakh or 25 thousand a month. {q}",
        "hra_ok": "{ack} your HRA exemption is {amount}.",
        "verdict_new": "The new regime saves you {diff}. You'd pay {new} instead of {old}.",
        "verdict_old": "The old regime saves you {diff}. You'd pay {old} instead of {new}.",
        "verdict_same": "Both regimes come out the same, at {new}.",
        "verdict_zero": "In the new regime you pay no tax at all.",
        "choices": "Want the working, what would change the answer, or a call when rates change?",
        "breakeven": "The old regime would only win if your deductions were above {be}. You have {ded} after legal limits.",
        "breakeven_none": "At this income, the old regime can't beat the new one, whatever your deductions.",
        "call": "Sure. Please type your number on screen. Should I call now, or when the rates change?",
        "done_choices": "Want the working, what would change the answer, or should we start again?",
        "stopped": "Okay, stopping the checkup. You can ask me anything else.",
        "ack": {"friendly": ["Got it,", "Okay,", "Great,"], "formal": ["Noted:", "Understood:"], "neutral": ["Okay,"]},
    },
    "hi": {
        "start": "चलिए एक छोटा टैक्स चेकअप करते हैं। लगभग एक मिनट लगेगा, एक-एक सवाल। पहला सवाल: आपकी सालाना सैलरी या पेंशन कितनी है?",
        "income_repair": "माफ़ कीजिए, मुझे रकम समझ नहीं आई। आप कह सकते हैं, जैसे 12 लाख। आपकी सालाना सैलरी या पेंशन कितनी है?",
        "income_ok": "{ack} {amount} सालाना।",
        "age_q": "क्या आपकी उम्र 60 साल या उससे ज़्यादा है?",
        "age_repair": "बस हाँ या ना कहिए। क्या आपकी उम्र 60 साल या उससे ज़्यादा है?",
        "ded_q": "अब डिडक्शन। रकम बताइए, या बस कहिए कोई नहीं। क्या आप PPF या LIC, हेल्थ इंश्योरेंस, या होम लोन ब्याज का डिडक्शन लेते हैं?",
        "ded_repair": "यह किसके लिए है: PPF या LIC, हेल्थ इंश्योरेंस, या होम लोन ब्याज?",
        "ded_ok": "{ack} {amount} के डिडक्शन।",
        "ded_none": "{ack} कोई डिडक्शन नहीं।",
        "rent_q": "क्या आप किराये पर रहते हैं और कंपनी से HRA मिलता है?",
        "rent_repair": "बस हाँ या ना कहिए। क्या आप किराये पर रहते हैं और HRA मिलता है?",
        "basic_q": "आपकी सालाना बेसिक सैलरी, DA मिलाकर, कितनी है?",
        "hra_q": "आपको साल में कितना HRA मिलता है?",
        "rentamt_q": "महीने का भी बता सकते हैं। आप कितना किराया देते हैं?",
        "city_q": "आप किस शहर में रहते हैं?",
        "amount_repair": "माफ़ कीजिए, मुझे रकम चाहिए, जैसे 6 लाख या 25 हज़ार महीना। {q}",
        "hra_ok": "{ack} आपकी HRA छूट {amount} है।",
        "verdict_new": "नई व्यवस्था में आपके {diff} बचेंगे। टैक्स {old} की जगह {new} लगेगा।",
        "verdict_old": "पुरानी व्यवस्था में आपके {diff} बचेंगे। टैक्स {new} की जगह {old} लगेगा।",
        "verdict_same": "दोनों व्यवस्थाओं में टैक्स बराबर है, {new}।",
        "verdict_zero": "नई व्यवस्था में आपको कोई टैक्स नहीं देना है।",
        "choices": "क्या आप पूरा हिसाब सुनना चाहेंगे, क्या बदलने से जवाब बदलेगा, या रेट बदलने पर मैं आपको कॉल करूँ?",
        "breakeven": "पुरानी व्यवस्था तभी बेहतर होगी जब आपके डिडक्शन {be} से ज़्यादा हों। कानूनी सीमा के बाद आपके {ded} हैं।",
        "breakeven_none": "इस आय पर पुरानी व्यवस्था किसी भी डिडक्शन से बेहतर नहीं होगी।",
        "call": "ज़रूर। स्क्रीन पर अपना नंबर डालिए। अभी कॉल करूँ, या रेट बदलने पर?",
        "done_choices": "पूरा हिसाब सुनना है, क्या बदलने से जवाब बदलेगा, या फिर से शुरू करें?",
        "stopped": "ठीक है, चेकअप बंद करता हूँ। आप कुछ और पूछ सकते हैं।",
        "ack": {"friendly": ["ठीक है,", "बढ़िया,", "समझ गया,"], "formal": ["नोट किया:", "समझ गया:"], "neutral": ["ठीक है,"]},
    },
}

STEPS = ["income", "age", "deductions", "rent", "basic", "hra", "rentamt", "city", "done"]
PROMPT_OF = {"income": "start", "age": "age_q", "deductions": "ded_q", "rent": "rent_q",
             "basic": "basic_q", "hra": "hra_q", "rentamt": "rentamt_q", "city": "city_q", "done": "done_choices"}


def is_trigger(text: str) -> bool:
    return bool(TRIGGER.search((text or "").lower()))


def _ack(lang, warmth, n):
    opts = T[lang]["ack"].get(warmth, T[lang]["ack"]["neutral"])
    return opts[n % len(opts)]


def _monthly_to_year(eng, text, amount):
    return amount * 12 if eng.MONTHLY.search(text) else amount


def handle(eng, utterance: str, state: dict | None, lang: str, style: dict) -> dict:
    """One turn. Returns {say, state, done, action?, result?}."""
    text = (utterance or "").strip()
    low = text.lower()
    warmth = (style or {}).get("warmth", "neutral")
    if not state or state.get("mode") != "checkup":
        state = {"mode": "checkup", "step": "income", "slots": {}, "lang": lang, "turn": 0}
        say = T[lang]["start"]
        state["last"] = say
        return {"say": say, "state": state, "done": False}
    lang = state.get("lang", lang)
    t, s, step = T[lang], state["slots"], state["step"]
    state["turn"] = state.get("turn", 0) + 1
    ack = _ack(lang, warmth, state["turn"])

    def ask(next_step, prefix=""):
        state["step"] = next_step
        q = t[PROMPT_OF[next_step]]
        say = f"{prefix} {q}".strip()
        state["last"] = say
        return {"say": say, "state": state, "done": False}

    # global intents
    if STOP.search(low) and step != "done":
        return {"say": t["stopped"], "state": None, "done": True}
    if REPEAT.search(low) and not eng.parse_amounts(text):
        return {"say": state.get("last", t[PROMPT_OF[step]]), "state": state, "done": False}
    # correction of the income at any later step: "no, 18 lakh"
    if step != "income" and CORRECTION.search(low) and eng.parse_income(text) and step in ("age", "deductions"):
        s["income"] = eng.parse_income(text)
        return ask(step, t["income_ok"].format(ack=ack, amount=eng.inr(s["income"])))

    if step == "income":
        inc = eng.parse_income(text)
        if not inc:
            state["last"] = t["income_repair"]
            return {"say": t["income_repair"], "state": state, "done": False}
        s["income"] = inc
        s["pension"] = bool(re.search(r"pension|पेंशन", low))
        group = eng.age_group(text)
        if group != "normal":                       # "I'm 65, pension 9 lakh" answers two questions at once
            s["age_group"] = group
            return ask("deductions", t["income_ok"].format(ack=ack, amount=eng.inr(inc)))
        return ask("age", t["income_ok"].format(ack=ack, amount=eng.inr(inc)))

    if step == "age":
        group = eng.age_group(text)
        has_age = bool(eng.AGE_RE.search(eng.norm(text))) or bool(re.fullmatch(r"\s*\d{2}\s*", low))
        if YES.search(low):
            group = "super_senior" if eng.SUPER_SENIOR_WORDS.search(low) else "senior"
        elif NO.search(low):
            group = "normal"
        elif re.fullmatch(r"\s*\d{2}\s*", low):
            a = int(low.strip()); group = "super_senior" if a >= 80 else ("senior" if a >= 60 else "normal")
        elif not has_age and group == "normal":
            state["last"] = t["age_repair"]                    # never assume an age we didn't hear
            return {"say": t["age_repair"], "state": state, "done": False}
        s["age_group"] = group
        return ask("deductions")

    if step == "deductions":
        if (NONE.search(low) or NO.search(low)) and not eng.parse_amounts(text):
            s["deductions"] = {"items": [], "allowed": 0, "claimed": 0, "capped": False}
            return ask("rent", t["ded_none"].format(ack=ack))
        d = eng.parse_deductions(text, s.get("age_group", "normal"), has_income=False)
        if not d["items"]:
            if SKIP.search(low):
                s["deductions"] = {"items": [], "allowed": 0, "claimed": 0, "capped": False}
                return ask("rent")
            state["last"] = t["ded_repair"]
            return {"say": t["ded_repair"], "state": state, "done": False}
        s["deductions"] = d
        note = ""
        if d["capped"]:
            note = " " + ("I've counted it at the legal limit." if lang == "en" else "मैंने इसे कानूनी सीमा तक गिना है।")
        return ask("rent", t["ded_ok"].format(ack=ack, amount=eng.inr(d["allowed"])) + note)

    if step == "rent":
        if YES.search(low):
            return ask("basic")
        if NO.search(low) or SKIP.search(low):
            return _finish(eng, state, lang, ack)
        state["last"] = t["rent_repair"]
        return {"say": t["rent_repair"], "state": state, "done": False}

    if step in ("basic", "hra", "rentamt"):
        amts = eng.parse_amounts(text)
        if not amts:
            if SKIP.search(low):
                return _finish(eng, state, lang, ack)
            say = t["amount_repair"].format(q=t[PROMPT_OF[step]])
            state["last"] = say
            return {"say": say, "state": state, "done": False}
        val = _monthly_to_year(eng, low, amts[0])
        s[step] = val
        nxt = {"basic": "hra", "hra": "rentamt", "rentamt": "city"}[step]
        return ask(nxt, f"{ack} {eng.inr(val)}" + (" a year." if lang == "en" else " सालाना।"))

    if step == "city":
        city, metro = eng.hra_city("in " + text)
        if not city:
            city, metro = (low.split()[0] if low.split() else None), False
        if not city:
            state["last"] = t["city_q"]
            return {"say": t["city_q"], "state": state, "done": False}
        h = eng.hra_exemption(s["basic"], s["hra"], s["rentamt"], metro)
        s["hra_result"] = {**h, "city": city, "metro": metro}
        return _finish(eng, state, lang, t["hra_ok"].format(ack=ack, amount=eng.inr(h["exempt"])))

    if step == "done":
        res = state.get("result") or {}
        if re.search(r"working|hisab|हिसाब|calculation|how", low):
            return {"say": res.get("working", ""), "state": state, "done": False, "result": res}
        if re.search(r"call|remind|कॉल|फोन|याद", low):
            return {"say": t["call"], "state": state, "done": False, "action": "show_call_form", "result": res}
        if re.search(r"change|break|बदल|क्या बदल", low):
            say = res.get("breakeven_say", "")
            return {"say": say, "state": state, "done": False, "result": res}
        if re.search(r"again|restart|start over|फिर से शुरू|दोबारा शुरू", low):
            return handle(eng, "", None, lang, style)
        return {"say": t["done_choices"], "state": state, "done": False, "result": res}

    return ask(step)


def _finish(eng, state, lang, prefix):
    t, s = T[lang], state["slots"]
    group = s.get("age_group", "normal")
    ded = s.get("deductions") or {"items": [], "allowed": 0}
    allowed = ded["allowed"]
    if s.get("hra_result"):
        allowed += s["hra_result"]["exempt"]
    c = eng.compute_both(s["income"], True, allowed, group)
    n, o = c["new"]["total"], c["old"]["total"]
    fmt = eng.inr
    if n == 0:
        verdict = t["verdict_zero"]
    elif n < o:
        verdict = t["verdict_new"].format(diff=fmt(o - n), new=fmt(n), old=fmt(o))
    elif o < n:
        verdict = t["verdict_old"].format(diff=fmt(n - o), new=fmt(n), old=fmt(o))
    else:
        verdict = t["verdict_same"].format(new=fmt(n))
    be = c["breakeven_deductions"]
    be_say = (t["breakeven"].format(be=fmt(be), ded=fmt(allowed)) if be else t["breakeven_none"])
    res_like = {"route": "tax_estimate", "tax_mode": "compare", "calc": c, "lang": lang}
    import style as style_mod
    working = style_mod._walkthrough(res_like, lang, eng.STORE, eng.inr)
    tail = ("This is an estimate for tax year 2026-27." if lang == "en" else "यह टैक्स ईयर 2026-27 के लिए एक अनुमान है।")
    if prefix.endswith(",") and verdict[:1].isupper():
        verdict = verdict[0].lower() + verdict[1:]
    say = f"{prefix} {verdict} {tail} {t['choices']}".strip()
    state["step"] = "done"
    state["result"] = {"calc": c, "working": working, "breakeven_say": be_say, "verdict": verdict}
    state["last"] = say
    return {"say": say, "state": state, "done": False, "result": state["result"]}
