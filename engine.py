"""
engine.py - the core of finverify voice (v4, first principles)
-------------------------------------------------------------
Rule: a number is spoken only if it comes from facts.json (sourced, dated),
from the deterministic tax calculator, from the user's own question, or is
verified by finverify. Everything else is withheld.

Routes, in order:
  1. tax_estimate  - question has an income amount + "how much tax"  -> calculator
  2. fact          - question matches facts.json                       -> templates
  3. general       - no fact, LLM available                            -> LLM + number firewall
  4. no_answer     - honest "I don't have a verified figure"
"""
import datetime as dt
import json
import os
import re
import time

import sys

import dialog as dialog_mod
import finverify_adapter as fv
import style as style_mod

HERE = os.path.dirname(os.path.abspath(__file__))
FACTS_PATH = os.getenv("FACTS_PATH", os.path.join(HERE, "facts.json"))

DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


# ---------------- basics ----------------
def today() -> dt.date:
    t = os.getenv("FV_TODAY")  # override for tests/demos
    return dt.date.fromisoformat(t) if t else dt.date.today()


def detect_lang(text: str) -> str:
    return "hi" if re.search(r"[\u0900-\u097F]", text or "") else "en"


def norm(text: str) -> str:
    t = (text or "").translate(DEV_DIGITS).lower()
    t = re.sub(r"(?<!\d)[.,]|[.,](?!\d)", " ", t)          # keep 7.1 and 1,50,000 intact
    t = re.sub(r"[?!।:;\"'“”‘’()]", " ", t)
    return " " + re.sub(r"\s+", " ", t).strip() + " "


def inr(n: float) -> str:
    """Indian grouping with ₹: 1425000 -> ₹14,25,000 (TTS reads commas correctly)."""
    n = int(round(n))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if n < 0 else "") + "₹" + s


def load_store(path: str = FACTS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for fact in data["facts"]:
        for key in ("id", "title", "match", "values", "say", "valid_until", "sources", "period"):
            if key not in fact:
                raise ValueError(f"fact {fact.get('id')} is missing '{key}'")
        if not fact["sources"]:
            raise ValueError(f"fact {fact['id']} has no sources")
        fact["say"]["en"].format(**fact["values"])  # fails fast on a bad placeholder
        fact["say"]["hi"].format(**{**fact["values"], **fact.get("values_hi", {})})
        for k, v in fact.get("values_hi", {}).items():   # Hindi values must carry the same digits
            if re.sub(r"\D", "", v) != re.sub(r"\D", "", fact["values"][k]):
                raise ValueError(f"fact {fact['id']}: values_hi['{k}'] digits differ from values")
    return data


STORE = load_store()


# ---------------- route 2: fact matching ----------------
def _kw_in(kw: str, q: str) -> bool:
    if re.fullmatch(r"[a-z0-9 .()\-]+", kw):           # ASCII keyword: whole-word match
        return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", q) is not None
    return kw in q                                     # Devanagari: substring match


def match_facts(question: str, k: int = 2) -> list:
    q = norm(question)
    scored = []
    for fact in STORE["facts"]:
        best = 0
        for pattern in fact["match"]:
            hits = [sum(_kw_in(kw.lower(), q) for kw in group) for group in pattern]
            if all(h > 0 for h in hits):
                best = max(best, len(pattern) * 10 + sum(hits))
        if best:
            scored.append((best, fact))
    if not scored:
        return []
    scored.sort(key=lambda x: -x[0])
    top = scored[0][0]
    return [f for s, f in scored if s >= top - 5][:k]


STALE = {
    "en": "My last verified figure is for {period} and may have changed since. Please check the official website.",
    "hi": "मेरे पास {period} का आखिरी सत्यापित आंकड़ा है, जो अब बदल चुका हो सकता है। कृपया आधिकारिक वेबसाइट पर जाँच लें।",
}


def render_fact(fact: dict, lang: str) -> tuple[str, bool]:
    stale = today() > dt.date.fromisoformat(fact["valid_until"])
    values = {**fact["values"], **(fact.get("values_hi", {}) if lang == "hi" else {})}
    text = fact["say"][lang].format(**values)
    if stale:
        text += " " + STALE[lang].format(period=fact["period"][lang])
    return text, stale


# ---------------- route 1: tax calculators (new + old regime, comparison) ----------------
AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*"
    r"(lakhs?|lacs?|लाख|crores?|cr|करोड़|करोड|thousand|हज़ार|हजार|k)?(?![a-z0-9])",
    re.IGNORECASE,
)
UNIT = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "लाख": 1e5,
        "crore": 1e7, "crores": 1e7, "cr": 1e7, "करोड़": 1e7, "करोड": 1e7,
        "thousand": 1e3, "हज़ार": 1e3, "हजार": 1e3, "k": 1e3}
TAX_WORDS = re.compile(r"(?<![a-z])tax(?![a-z])|टैक्स|आयकर| कर ")
ASK_WORDS = re.compile(r"how much|calculate|what will|what is my|kitna|कितना|कितनी|लगेगा|लगेगी|बनेगा|बनेगी|देना|pay")
SALARY_WORDS = re.compile(r"salary|ctc|pension|सैलरी|वेतन|तनख्वाह|पेंशन")
OLD_REGIME_WORDS = re.compile(r"old regime|old tax|पुरानी")
COMPARE_WORDS = re.compile(r"which regime|which is better|better regime|compare|old or new|new or old|old vs|vs old|"
                           r"कौन सी|कौनसी|बेहतर|तुलना|पुरानी या नई|नई या पुरानी")
DEDUCTION_WORDS = re.compile(r"deduction|80c|80 c|80d|hra|home loan|investment|invest|section 123|"
                             r"कटौती|डिडक्शन|छूट|निवेश|होम लोन")
SUPER_SENIOR_WORDS = re.compile(r"super senior|अति वरिष्ठ|सुपर सीनियर")
SENIOR_WORDS = re.compile(r"senior citizen|senior|वरिष्ठ|सीनियर")
AGE_RE = re.compile(r"(?:age|aged|उम्र|i am|i'm|i m|im|मैं)\s*(\d{2})(?!\d|\s*(?:lakh|lac|लाख|k|%))|(\d{2})\s*(?:years? old|years|yrs|साल|वर्ष)")


def parse_amounts(question: str) -> list[float]:
    q = norm(question)
    out = []
    for m in AMOUNT_RE.finditer(q):
        try:
            n = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        n *= UNIT.get(unit, 1)
        if n >= 1000 and not (1900 <= n <= 2100 and not unit):   # skip years, section numbers, ages
            out.append(n)
    return out


def parse_income(question: str) -> float | None:
    amts = [a for a in parse_amounts(question) if a >= 10000]
    return max(amts) if amts else None


DEDUCTION_CATEGORIES = [   # first match wins, so specific phrases come first
    ("home_loan_interest", r"home loan interest|interest on (?:my )?home loan|housing loan interest|होम लोन (?:का )?ब्याज|होम लोन इंटरेस्ट"),
    ("sec123", r"principal|80 ?c|section 123|सेक्शन 123|धारा 123|80 ?सी|ppf|elss|lic|life insurance|tuition|sukanya|epf|पीपीएफ|एलआईसी|जीवन बीमा|सुकन्या"),
    ("nps", r"nps|80ccd|एनपीएस"),
    ("health_parents", r"parents?'? (?:health|medical|mediclaim|insurance)|(?:health|medical|mediclaim) insurance (?:for|of) (?:my )?parents|माता[- ]पिता"),
    ("health_self", r"80 ?d|health insurance|mediclaim|medical insurance|हेल्थ इंश्योरेंस|स्वास्थ्य बीमा|मेडिक्लेम"),
    ("home_loan_interest", r"home loan|housing loan|होम लोन"),        # plain "home loan" = interest
    ("hra", r"hra|house rent|एचआरए|किराया"),
    ("other", r"deduction|investment|invest|कटौती|डिडक्शन|छूट|निवेश"),
]
CLAUSE_SPLIT = re.compile(r",(?!\d)|;|\s(?:and|aur|plus|also)\s|\sऔर\s|\sतथा\s|\.\s|।")


def parse_deductions(question: str, user_group: str = "normal", has_income: bool = True) -> dict:
    """Split the question into clauses, assign each amount to a deduction category,
    and apply the legal cap per category (old regime, TY 2026-27)."""
    caps = STORE["old_regime_calculator"]["deduction_caps"]
    income = parse_income(question) if has_income else None
    raw = (question or "").lower()
    claimed: dict[str, float] = {}
    income_skipped = not has_income
    for clause in CLAUSE_SPLIT.split(raw):
        amts = parse_amounts(clause)
        if not amts:
            continue
        if not income_skipped and income in amts:
            amts.remove(income)
            income_skipped = True
        if not amts:
            continue
        q = norm(clause)
        cat = next((c for c, pat in DEDUCTION_CATEGORIES if re.search(pat, q)), None)
        if cat:
            claimed[cat] = claimed.get(cat, 0) + sum(amts)
    items, allowed_total, capped_any = [], 0.0, False
    for cat, amount in claimed.items():
        cfg = caps[cat]
        cap = cfg.get("cap_senior") if (cat == "health_self" and user_group != "normal") else cfg["cap"]
        if cat == "health_parents" and re.search(r"senior|60|वरिष्ठ|सीनियर", norm(question)):
            cap = cfg["cap_senior"]
        allowed = min(amount, cap) if cap else amount
        capped_any |= allowed < amount
        allowed_total += allowed
        items.append({"category": cat, "label_en": cfg["label_en"], "label_hi": cfg["label_hi"],
                      "claimed": round(amount), "allowed": round(allowed), "cap": cap})
    return {"items": items, "claimed": round(sum(claimed.values())), "allowed": round(allowed_total), "capped": capped_any}


PARENT_AGE = re.compile(r"(?:senior(?: citizen)?|super senior|वरिष्ठ|सीनियर)\s*(?:citizen\s*)?(?:parents?|माता[- ]पिता)"
                        r"|(?:parents?|माता[- ]पिता)[^,.।]{0,30}?(?:senior|सीनियर|वरिष्ठ|\d{2}\s*(?:years|साल))")


def age_group(question: str) -> str:
    """The CALLER's age group. Mentions of parents' age are removed first."""
    q = norm(PARENT_AGE.sub(" ", (question or "").lower()))
    m = AGE_RE.search(q)
    age = int(m.group(1) or m.group(2)) if m else None
    if age is not None and not 18 <= age <= 110:
        age = None
    if SUPER_SENIOR_WORDS.search(q) or (age and age >= 80):
        return "super_senior"
    if SENIOR_WORDS.search(q) or (age and 60 <= age < 80):
        return "senior"
    return "normal"


def is_tax_question(question: str) -> bool:
    q = norm(question)
    if not parse_income(question):
        return False
    return bool((TAX_WORDS.search(q) and ASK_WORDS.search(q)) or COMPARE_WORDS.search(q))


def _slab_tax(taxable: float, slabs: list) -> float:
    tax, lower = 0.0, 0.0
    for upper, rate in slabs:
        upper = float("inf") if upper is None else upper
        if taxable > lower:
            tax += (min(taxable, upper) - lower) * rate
        lower = upper
    return tax


def new_regime_tax(taxable: float, cfg: dict) -> dict:
    slab_tax = _slab_tax(taxable, cfg["slabs"])
    limit = cfg["rebate_income_limit"]
    tax = 0.0 if taxable <= limit else min(slab_tax, taxable - limit)   # rebate, then marginal relief
    cess = tax * cfg["cess_rate"]
    return {"slab_tax": round(slab_tax), "after_rebate": round(tax), "cess": round(cess), "total": round(tax + cess)}


def old_regime_tax(taxable: float, cfg: dict, group: str = "normal") -> dict:
    slab_tax = _slab_tax(taxable, cfg["slabs"][group])
    tax = max(slab_tax - cfg["rebate_max"], 0.0) if taxable <= cfg["rebate_income_limit"] else slab_tax
    cess = tax * cfg["cess_rate"]
    return {"slab_tax": round(slab_tax), "after_rebate": round(tax), "cess": round(cess), "total": round(tax + cess)}


def compute_both(gross: float, salaried: bool, deductions: float, group: str) -> dict:
    new_cfg, old_cfg = STORE["tax_calculator"], STORE["old_regime_calculator"]
    new_taxable = max(gross - (new_cfg["standard_deduction"] if salaried else 0), 0)
    old_std = old_cfg["standard_deduction"] if salaried else 0
    old_taxable = max(gross - old_std - deductions, 0)
    new = new_regime_tax(new_taxable, new_cfg)
    old = old_regime_tax(old_taxable, old_cfg, group)

    # Break-even: the smallest deductions at which the old regime costs no more than the new one.
    # Compared on exact pre-cess tax (same cess rate on both sides), so no rounding drift.
    def old_pre(taxable):
        st = _slab_tax(taxable, old_cfg["slabs"][group])
        return max(st - old_cfg["rebate_max"], 0.0) if taxable <= old_cfg["rebate_income_limit"] else st
    nt = _slab_tax(new_taxable, new_cfg["slabs"])
    new_pre = 0.0 if new_taxable <= new_cfg["rebate_income_limit"] else min(nt, new_taxable - new_cfg["rebate_income_limit"])
    base = max(gross - old_std, 0)
    breakeven = None
    if new_pre > 0 and old_pre(0) <= new_pre:
        if old_pre(base) <= new_pre:
            breakeven = 0.0
        else:
            lo, hi = 0.0, base
            for _ in range(80):
                mid = (lo + hi) / 2
                if old_pre(max(base - mid, 0)) <= new_pre:
                    hi = mid
                else:
                    lo = mid
            breakeven = round(hi)
    return {"gross": round(gross), "salaried": salaried, "age_group": group, "deductions": round(deductions),
            "new": {**new, "taxable": round(new_taxable), "standard_deduction": new_cfg["standard_deduction"] if salaried else 0},
            "old": {**old, "taxable": round(old_taxable), "standard_deduction": old_std},
            "breakeven_deductions": breakeven}


GROUP_TEXT = {"normal": {"en": "", "hi": ""},
              "senior": {"en": " as a senior citizen", "hi": " सीनियर सिटीजन के रूप में"},
              "super_senior": {"en": " as a super senior citizen", "hi": " सुपर सीनियर सिटीजन के रूप में"}}


def _cap_note(ded: dict, lang: str) -> str:
    capped = [i for i in ded["items"] if i["cap"] and i["allowed"] < i["claimed"]]
    if not capped:
        return ""
    if lang == "hi":
        parts = [f"{i['label_hi']} को {inr(i['allowed'])} की सीमा तक" for i in capped]
        return " मैंने " + ", ".join(parts) + " रखा है, क्योंकि कानून में इतनी ही छूट है।"
    parts = [f"{i['label_en']} at the {inr(i['allowed'])} limit" for i in capped]
    return " I counted " + ", ".join(parts) + ", because that's the legal maximum."


def _reach_note(c: dict, group: str, lang: str) -> str:
    """If the break-even is above what the common capped deductions can reach, say so."""
    be = c.get("breakeven_deductions")
    if not be:
        return ""
    caps = STORE["old_regime_calculator"]["deduction_caps"]
    health = caps["health_self"]["cap_senior"] if group != "normal" else caps["health_self"]["cap"]
    reach = caps["sec123"]["cap"] + caps["nps"]["cap"] + caps["home_loan_interest"]["cap"] + health
    if be <= reach:
        return ""
    if lang == "hi":
        return (f" ⟦opt⟧ध्यान दें: सेक्शन 123, NPS, होम लोन ब्याज और हेल्थ इंश्योरेंस की कुल सीमा {inr(reach)} है, "
                f"इसलिए पुरानी व्यवस्था के लिए आपको HRA जैसे और डिडक्शन भी चाहिए होंगे।⟦/opt⟧")
    return (f" ⟦opt⟧Note: Section 123, NPS, home loan interest and health insurance together are capped at {inr(reach)}, "
            f"so the old regime would also need HRA or other deductions.⟦/opt⟧")


def tax_estimate(question: str, lang: str) -> dict:
    q = norm(question)
    gross = parse_income(question)
    limit = STORE["tax_calculator"]["max_income_supported"]
    if gross > limit:
        msg = {"en": f"I can estimate tax for income up to {inr(limit)}. Above that, surcharge applies, which I don't calculate yet.",
               "hi": f"मैं {inr(limit)} तक की आय पर टैक्स का अनुमान लगा सकता हूँ। उससे ऊपर सरचार्ज लगता है, जिसकी गणना मैं अभी नहीं करता।"}
        return {"text": msg[lang], "calc": None, "mode": "refused"}
    salaried = bool(SALARY_WORDS.search(q))
    group = age_group(question)
    ded = parse_deductions(question, group)
    deductions = ded["allowed"]
    c = compute_both(gross, salaried, deductions, group)
    c["deduction_items"] = ded["items"]
    c["deductions_claimed"] = ded["claimed"]
    compare = bool(COMPARE_WORDS.search(q))
    old_only = bool(OLD_REGIME_WORDS.search(q)) and not compare
    n, o = c["new"], c["old"]
    g = GROUP_TEXT[group][lang]
    pension = bool(re.search(r"pension|पेंशन", q))
    kind_en = "pension" if pension else ("salary" if salaried else "taxable income")
    kind_hi = "पेंशन" if pension else ("सैलरी" if salaried else "टैक्सेबल आय")
    basis_en = f"On a {kind_en} of {inr(gross)}{g}"
    basis_hi = f"{inr(gross)} की {kind_hi} पर{g}"
    ded_en = f" with {inr(deductions)} of deductions" if deductions else ""
    ded_hi = f" {inr(deductions)} के डिडक्शन के साथ" if deductions else ""
    tail = {"en": "This is an estimate for tax year 2026-27, assuming the deductions you mentioned qualify and you have no other income.",
            "hi": "यह टैक्स ईयर 2026-27 के लिए एक अनुमान है, यह मानकर कि आपके बताए डिडक्शन मान्य हैं और कोई और आय नहीं है।"}[lang]
    amt_en = lambda r: f"{inr(r['total'])} in tax" if r["total"] else "no tax"
    amt_hi = lambda r: f"टैक्स {inr(r['total'])}" if r["total"] else "कोई टैक्स नहीं"

    if compare:
        diff = abs(n["total"] - o["total"])
        if lang == "hi":
            lead = f"{basis_hi}, नई व्यवस्था में {amt_hi(n)} और पुरानी व्यवस्था में{ded_hi} {amt_hi(o)} बनता है।"
            verdict = ("दोनों में टैक्स बराबर है।" if diff == 0 else
                       f"{'नई' if n['total'] < o['total'] else 'पुरानी'} व्यवस्था में {inr(diff)} कम टैक्स लगेगा।")
            be = c["breakeven_deductions"]
            extra = (f" पुरानी व्यवस्था तभी बेहतर होगी जब आपके डिडक्शन {inr(be)} से ज़्यादा हों।"
                     if be and n["total"] <= o["total"] else "")
            if n["total"] == 0:
                extra = " नई व्यवस्था में आपको पहले से ही कोई टैक्स नहीं देना है।"
        else:
            lead = f"{basis_en}, the new regime means {amt_en(n)}, and the old regime{ded_en} means {amt_en(o)}."
            verdict = ("Both come out the same." if diff == 0 else
                       f"The {'new' if n['total'] < o['total'] else 'old'} regime saves you {inr(diff)}.")
            be = c["breakeven_deductions"]
            extra = (f" The old regime only wins if your deductions are above {inr(be)}."
                     if be and n["total"] <= o["total"] else "")
            if n["total"] == 0:
                extra = " In the new regime you already pay no tax."
        return {"text": f"{lead} {verdict}{extra}{_cap_note(ded, lang)}{_reach_note(c, group, lang)} {tail}", "calc": c, "mode": "compare"}

    r, regime = (o, "old") if old_only else (n, "new")
    if lang == "hi":
        name = "पुरानी" if old_only else "नई"
        std = f", {inr(r['standard_deduction'])} का स्टैंडर्ड डिडक्शन" if salaried else ""
        dd = f" और {inr(deductions)} के डिडक्शन" if (old_only and deductions) else ""
        result = (f"कोई टैक्स नहीं लगेगा, क्योंकि रिबेट मिलती है।" if r["total"] == 0
                  else f"अनुमानित टैक्स 4% सेस मिलाकर {inr(r['total'])} है।")
        text = f"{basis_hi}, {name} टैक्स व्यवस्था में{std}{dd} घटाकर टैक्सेबल आय {inr(r['taxable'])} है। {result}"
    else:
        name = "old" if old_only else "new"
        parts = []
        if salaried:
            parts.append(f"the {inr(r['standard_deduction'])} standard deduction")
        if old_only and deductions:
            parts.append(f"{inr(deductions)} of deductions")
        after = f" after {' and '.join(parts)}" if parts else ""
        result = ("You pay no tax, because of the rebate." if r["total"] == 0
                  else f"The estimated tax is {inr(r['total'])}, including 4% cess.")
        text = f"{basis_en}, under the {name} regime your taxable income is {inr(r['taxable'])}{after}. {result}"
    if not old_only and deductions:
        text += (" ⟦opt⟧Most deductions don't apply in the new regime. Ask me to compare regimes to see if the old one is better.⟦/opt⟧"
                 if lang == "en" else " ⟦opt⟧नई व्यवस्था में ज़्यादातर डिडक्शन नहीं मिलते। पुरानी व्यवस्था बेहतर है या नहीं, यह जानने के लिए दोनों की तुलना पूछें।⟦/opt⟧")
    if old_only:
        text += _cap_note(ded, lang)
    return {"text": f"{text} {tail}", "calc": c, "mode": regime}


# ---------------- HRA exemption (old regime, TY 2026-27) ----------------
HRA_WORDS = re.compile(r"(?<![a-z])hra(?![a-z])|house rent allowance|एचआरए")
HRA_ASK = re.compile(r"exempt|exemption|how much|calculate|claim|tax free|tax-free|छूट|कितना|कितनी")
MONTHLY = re.compile(r"a month|per month|monthly|/month|pm(?![a-z])|महीना|महीने|प्रति माह|मासिक")
FIELD_PATTERNS = {
    "basic": r"basic(?: salary)?(?: plus da| \+ da| and da)?|बेसिक",
    "hra": r"(?<![a-z])hra(?! exemption)(?: received| i get| of)?|house rent allowance|एचआरए",
    "rent": r"rent(?: paid| i pay)?|किराया|किराये",
}


def _field_amount(clause: str, pat: str) -> float | None:
    m = re.search(pat, clause)
    if not m:
        return None
    amts = parse_amounts(clause[m.end():]) or parse_amounts(clause[:m.start()])
    if not amts:
        return None
    return amts[0] * (12 if MONTHLY.search(clause) else 1)


def hra_city(question: str) -> tuple[str | None, bool]:
    q = norm(question)
    for city, names in STORE["hra"]["metro_cities"].items():
        if any(_kw_in(n, q) for n in names):
            return city, True
    m = re.search(r"(?:in|at|city)\s+([a-z]{3,})", q)
    return (m.group(1) if m else None), False


def hra_exemption(basic_da: float, hra_received: float, rent: float, metro: bool) -> dict:
    cfg = STORE["hra"]
    pct = cfg["metro_rate"] if metro else cfg["other_rate"]
    a, b, c = hra_received, basic_da * pct, max(rent - basic_da * cfg["rent_minus_pct"], 0)
    exempt = min(a, b, c)
    limiting = ["the HRA you receive", f"{int(pct*100)}% of salary", "rent minus 10% of salary"][[a, b, c].index(exempt)]
    return {"actual_hra": round(a), "pct_of_salary": round(b), "rent_minus_10": round(c), "pct": pct,
            "exempt": round(exempt), "taxable_hra": round(max(hra_received - exempt, 0)), "limiting": limiting}


def is_hra_question(question: str) -> bool:
    q = norm(question)
    return bool(HRA_WORDS.search(q) and HRA_ASK.search(q) and not COMPARE_WORDS.search(q)
                and (parse_amounts(question) or re.search(r"how|कैसे|कितना|कितनी", q)) and len(parse_amounts(question)) >= 1)


def hra_answer(question: str, lang: str) -> dict:
    fields = {}
    for clause in CLAUSE_SPLIT.split((question or "").lower()):
        cl = norm(clause)
        for name, pat in FIELD_PATTERNS.items():
            if name not in fields:
                v = _field_amount(cl, pat)
                if v:
                    fields[name] = v
                    break
    city, metro = hra_city(question)
    missing = [k for k in ("basic", "hra", "rent") if k not in fields]
    if missing or city is None:
        need_en = {"basic": "your yearly basic salary plus DA", "hra": "the HRA you receive in a year", "rent": "the rent you pay"}
        need_hi = {"basic": "आपकी सालाना बेसिक सैलरी और DA", "hra": "साल में मिलने वाला HRA", "rent": "आप कितना किराया देते हैं"}
        items_en = [need_en[k] for k in missing] + (["which city you live in"] if city is None else [])
        items_hi = [need_hi[k] for k in missing] + (["आप किस शहर में रहते हैं"] if city is None else [])
        join_en = lambda xs: xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]
        text = ("To work out your HRA exemption I need " + join_en(items_en) + "."
                if lang == "en" else "HRA छूट निकालने के लिए मुझे ये चाहिए: " + ", ".join(items_hi) + "।")
        return {"text": text, "hra": {"missing": missing + ([] if city else ["city"]), "inputs": {k: round(v) for k, v in fields.items()}}}
    r = hra_exemption(fields["basic"], fields["hra"], fields["rent"], metro)
    r.update({"city": city, "metro": metro, "inputs": {k: round(v) for k, v in fields.items()}})
    HI_CITY = {"mumbai": "मुंबई", "delhi": "दिल्ली", "kolkata": "कोलकाता", "chennai": "चेन्नई", "bengaluru": "बेंगलुरु",
               "hyderabad": "हैदराबाद", "pune": "पुणे", "ahmedabad": "अहमदाबाद"}
    city_hi = HI_CITY.get(city, city.title())
    cat_en = "one of the eight 50% cities" if metro else "not in the 50% list, so 40% applies"
    cat_hi = "50% वाले आठ शहरों में से एक है" if metro else "50% वाली सूची में नहीं है, इसलिए 40% लागू है"
    if lang == "hi":
        text = (f"{city_hi} {cat_hi}। आपकी HRA छूट {inr(r['exempt'])} बनती है, और {inr(r['taxable_hra'])} HRA पर टैक्स लगेगा। "
                f"यह पुरानी व्यवस्था में ही मिलती है, टैक्स ईयर 2026-27 के नियमों के हिसाब से। अगर मकान मालिक परिवार का सदस्य है, तो रिश्ता बताना ज़रूरी है।")
    else:
        text = (f"{city.title()} is {cat_en}. Your HRA exemption works out to {inr(r['exempt'])}, limited by {r['limiting']}, "
                f"so {inr(r['taxable_hra'])} of your HRA is taxable. This applies only in the old regime, under the tax year 2026-27 rules. "
                f"If your landlord is a family member, you now have to disclose that relationship.")
    return {"text": text, "hra": r}


# ---------------- route 3: LLM + number firewall ----------------
FIREWALL_RE = re.compile(
    r"(?:₹|rs\.?\s?|inr\s?)?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|percent|प्रतिशत|lakhs?|lacs?|crores?|cr|लाख|करोड़|करोड))?",
    re.IGNORECASE,
)
NUMBER_WORDS = re.compile(
    r"(?<![a-z])(lakh|lakhs|crore|crores|percent|thousand|hundred)(?![a-z])|लाख|करोड़|प्रतिशत|हज़ार|हजार",
    re.IGNORECASE,
)
WITHHELD = {"en": "a figure I can't verify", "hi": "एक आंकड़ा जिसकी मैं पुष्टि नहीं कर सकता"}
WITHHELD_NOTE = {"en": "I left out a number I couldn't verify. Please check the official website for exact figures.",
                 "hi": "मैंने एक ऐसा आंकड़ा छोड़ दिया जिसकी पुष्टि नहीं हो सकी। सटीक आंकड़ों के लिए आधिकारिक वेबसाइट देखें।"}


def strip_thinking(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"^.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.strip()


def firewall(text: str, question: str, lang: str) -> dict:
    """Every number in LLM text must come from the user's question or be verified
    by finverify (corrected if finverify knows the right value). Otherwise withheld."""
    text = text.translate(DEV_DIGITS)
    allowed = {re.sub(r"[\s,₹]|rs\.?|inr", "", m.group(0).lower())
               for m in FIREWALL_RE.finditer(norm(question))}
    found = [m.group(0).strip() for m in FIREWALL_RE.finditer(text)]
    found = [f for f in found if not re.fullmatch(r"(19|20)\d\d", f)]   # plain years are fine
    claims_by_text = {c.text: c for c in fv.check(question, text)} if found else {}
    log, out, withheld = [], text, 0
    for fig in dict.fromkeys(found):
        key = re.sub(r"[\s,₹]|rs\.?|inr", "", fig.lower())
        c = claims_by_text.get(fig)
        if key in allowed:
            log.append({"text": fig, "status": "from_question"})
        elif c and c.status == "verified":
            log.append({"text": fig, "status": "verified", "source": c.source})
        elif c and c.status == "wrong" and c.correct:
            out = out.replace(fig, c.correct)
            log.append({"text": fig, "status": "corrected", "correct": c.correct, "source": c.source})
        else:
            out = out.replace(fig, WITHHELD[lang])
            withheld += 1
            log.append({"text": fig, "status": "withheld"})
    if NUMBER_WORDS.search(out.lower()) and withheld == 0 and not log:
        # spelled-out amounts like "one and a half lakh" with no digits: also unverifiable
        out_sentences = re.split(r"(?<=[.।!?])\s+", out)
        kept = [s for s in out_sentences if not NUMBER_WORDS.search(s.lower())]
        withheld += len(out_sentences) - len(kept)
        out = " ".join(kept)
        log.append({"text": "(spelled-out number)", "status": "withheld"})
    if withheld:
        out = (out + " " + WITHHELD_NOTE[lang]).strip()
    return {"text": out.strip(), "figures": log}


GENERAL_PROMPT = """You explain Indian personal finance and tax concepts for a VOICE assistant.
- Reply in the same language as the question (Hindi in Devanagari, or English). 2-3 short sentences, plain text.
- Do NOT state any number, amount, rate, limit or date. If the answer needs a figure, say you don't have a verified figure and suggest the official website.
- No legal, tax-filing or investment advice."""


def llm_general(question: str) -> str | None:
    key = os.getenv("LLM_API_KEY") or os.getenv("SARVAM_API_KEY")
    if not key:
        return None
    using_sarvam = not os.getenv("LLM_API_KEY")
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=os.getenv("LLM_BASE_URL") or ("https://api.sarvam.ai/v1" if using_sarvam else None))
    resp = client.chat.completions.create(
        model=os.getenv("LLM_MODEL") or ("sarvam-30b" if using_sarvam else "gpt-4o-mini"),
        temperature=0.2,
        messages=[{"role": "system", "content": GENERAL_PROMPT}, {"role": "user", "content": question}],
    )
    return strip_thinking(resp.choices[0].message.content or "")


# Voice research: offer at most three clear choices, and end on the question.
NO_ANSWER = {
    "en": "I don't have a verified figure for that yet. Want a savings scheme rate, your tax estimate, or a quick tax checkup?",
    "hi": "इसके लिए मेरे पास अभी सत्यापित आंकड़ा नहीं है। कोई बचत योजना की दर, आपके टैक्स का अनुमान, या एक छोटा टैक्स चेकअप?",
}
OUT_OF_SCOPE = {
    "en": "I only help with Indian savings rates and income tax, so I can't answer that one. Want a savings scheme rate, your tax estimate, or a quick tax checkup?",
    "hi": "मैं सिर्फ बचत योजनाओं की दरों और इनकम टैक्स में मदद करता हूँ, इसलिए इसका जवाब नहीं दे सकता। कोई बचत योजना की दर, आपके टैक्स का अनुमान, या एक छोटा टैक्स चेकअप?",
}
FINANCE_WORDS = re.compile(
    r"tax|rate|interest|ppf|ssy|sukanya|scss|nsc|kvp|nps|epf|elss|lic|fd|fixed deposit|deposit|saving|invest|"
    r"deduction|rebate|regime|slab|salary|pension|income|hra|rent|loan|emi|tds|itr|gst|repo|rbi|bank|scheme|"
    r"80c|section|lakh|crore|rupee|money|finance|\d|₹|"
    r"टैक्स|कर|ब्याज|दर|बचत|निवेश|सैलरी|पेंशन|आय|किराया|लोन|बैंक|योजना|लाख|करोड़|पैसा|पैसे|रुपये|डिडक्शन|छूट|"
    r"पीपीएफ|सुकन्या|एफडी|रेपो|स्लैब|व्यवस्था", re.IGNORECASE)


def is_finance(question: str) -> bool:
    return bool(FINANCE_WORDS.search(question or ""))


# ---------------- follow-ups ----------------
def _fact_keywords_hit(fact: dict, question: str) -> bool:
    q = norm(question)
    return any(_kw_in(kw.lower(), q) for pattern in fact["match"] for group in pattern for kw in group)


def resolve_followup(question: str, context: dict | None) -> tuple[str, list | None]:
    """Turn 'and for 20 lakh?' / 'and NSC?' / 'what about the limit?' into a full question
    using the previous turn. Returns (question_for_tax_route, facts_or_None)."""
    if not context or not context.get("question"):
        return question, None
    prev_q, prev_route = context["question"], context.get("route")
    if prev_route == "tax_estimate" and parse_income(question) and not is_tax_question(question):
        calc = context.get("calc") or {}
        salary = " salary" if calc.get("salaried") else ""
        senior = {"senior": " senior citizen", "super_senior": " super senior"}.get(calc.get("age_group"), "")
        mode = " which regime is better" if context.get("tax_mode") == "compare" else " how much tax"
        return f"{question}{salary}{senior}{mode}", None
    if prev_route == "fact" and not match_facts(question):
        combined = [f for f in match_facts(question + " " + prev_q, k=4) if _fact_keywords_hit(f, question)]
        return question, (combined[:2] or None)
    return question, None


# ---------------- speakable numbers (for the voice only; the screen keeps exact digits) ----------------
RUPEE_RE = re.compile(r"₹\s?(\d+(?:,\d{2,3})*(?:\.\d+)?)(\s?(?:lakh|लाख|crore|करोड़))?")


def _words_for(n: int, lang: str) -> str:
    units = [(10_000_000, "crore", "करोड़"), (100_000, "lakh", "लाख"), (1_000, "thousand", "हज़ार")]
    parts, rest = [], n
    for size, en, hi in units:
        if rest >= size:
            q, rest = divmod(rest, size)
            parts.append(f"{q} {en if lang == 'en' else hi}")
    if rest or not parts:
        parts.append(str(rest))
    return " ".join(parts)


def speakable(text: str, lang: str) -> str:
    """₹14,25,000 -> '14 lakh 25 thousand rupees' / '14 लाख 25 हज़ार रुपये' (how people say it in India)."""
    rupees = "rupees" if lang == "en" else "रुपये"
    def repl(m):
        num, unit = m.group(1), (m.group(2) or "").strip()
        if unit:                                   # already "₹1.5 lakh" -> "1.5 lakh rupees"
            return f"{num} {unit} {rupees}"
        v = float(num.replace(",", ""))
        if v != int(v):
            return f"{num} {rupees}"
        return f"{_words_for(int(v), lang)} {rupees}"
    return RUPEE_RE.sub(repl, text)


# ---------------- the one entry point ----------------
def answer(question: str, lang: str | None = None, use_llm: bool = True, context: dict | None = None,
           style: dict | None = None, dialog_state: dict | None = None) -> dict:
    t0 = time.perf_counter()
    question = (question or "").strip()
    lang = lang or detect_lang(question)
    res = {"question": question, "lang": lang, "facts": [], "figures": [], "calc": None}
    tax_q, followup_facts = resolve_followup(question, context)
    commands = style_mod.detect_command(question)
    new_style = style_mod.normalize(style)
    for k, v in commands:
        new_style[k] = v

    in_dialog = bool(dialog_state and dialog_state.get("mode") == "checkup")
    if in_dialog or dialog_mod.is_trigger(question):
        d = dialog_mod.handle(sys.modules[__name__], question if in_dialog else "", dialog_state if in_dialog else None,
                              (dialog_state or {}).get("lang", lang), new_style)
        res.update(route="checkup", spoken=d["say"], dialog_state=d["state"], dialog_done=d["done"],
                   action=d.get("action"), sources=STORE["tax_calculator"]["sources"])
        if d.get("result"):
            res["calc"] = d["result"]["calc"]
        res["lang"] = (d["state"] or {}).get("lang", lang)
    elif commands and not parse_amounts(question) and not match_facts(question):
        res.update(route="style", sources=[],
                   spoken=" ".join(style_mod.CONFIRM[(k, v)][lang] for k, v in commands))
    elif question and is_hra_question(question):
        r = hra_answer(question, lang)
        res.update(route="tax_estimate", tax_mode="hra", spoken=r["text"], hra=r["hra"], sources=STORE["hra"]["sources"])
    elif question and is_tax_question(tax_q):
        r = tax_estimate(tax_q, lang)
        srcs = STORE["tax_calculator"]["sources"] + (STORE["old_regime_calculator"]["sources"] if r["mode"] in ("old", "compare") else [])
        res.update(route="tax_estimate", spoken=r["text"], calc=r["calc"], tax_mode=r["mode"], sources=srcs)
    elif question and (facts := (followup_facts or match_facts(question))):
        parts, used = [], []
        for f in facts:
            text, stale = render_fact(f, lang)
            parts.append(text)
            used.append({"id": f["id"], "title": f["title"], "values": f["values"], "valid_until": f["valid_until"],
                         "confidence": f.get("confidence", ""), "stale": stale, "sources": f["sources"],
                         "official": any(s.get("type") == "primary" for s in f["sources"])})
        res.update(route="fact", spoken=" ".join(parts), facts=used,
                   sources=[s for f in facts for s in f["sources"]])
    elif question and not is_finance(question):          # checked before any LLM call: stay on topic
        res.update(route="out_of_scope", spoken=OUT_OF_SCOPE[lang], sources=[])
    else:
        draft = llm_general(question) if (use_llm and question) else None
        if draft:
            fw = firewall(draft, question, lang)
            res.update(route="general", spoken=fw["text"], figures=fw["figures"], draft=draft, sources=[])
        else:
            res.update(route="no_answer", spoken=NO_ANSWER[lang], sources=[])
    styled = style_mod.apply(res, new_style, STORE, inr)
    res["spoken_plain"] = style_mod.strip_markers(res["spoken"])               # everything, unstyled
    res["spoken_core"] = style_mod.strip_markers(res["spoken"], keep_optional=False)  # required content only
    res.update(spoken=styled["spoken"], voice=styled["voice"], style=styled["style"])
    res["speech"] = speakable(res["spoken"], res["lang"])
    res["ms"] = round((time.perf_counter() - t0) * 1000)
    return res
