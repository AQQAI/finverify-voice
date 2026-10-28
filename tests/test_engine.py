"""Offline tests for the engine (no LLM, Sarvam or finverify calls). Run: pytest -q"""
import os, sys
os.environ["FINVERIFY_MODE"] = "off"
os.environ["FV_TODAY"] = "2026-10-19"
os.environ.pop("LLM_API_KEY", None); os.environ.pop("SARVAM_API_KEY", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine


def ask(q):
    return engine.answer(q, use_llm=False)


# ---- routing & facts ----
def test_ppf_rate_english_and_hindi():
    assert ask("What is the PPF interest rate?")["route"] == "fact"
    assert "7.1%" in ask("What is the PPF interest rate?")["spoken"]
    assert "7.1%" in ask("PPF में कितना ब्याज मिलता है?")["spoken"]

def test_rate_vs_limit_disambiguation():
    r = ask("What is the maximum I can deposit in PPF?")
    assert [f["id"] for f in r["facts"]] == ["ppf_deposit_limit"]

def test_every_fact_has_sources_and_period():
    for f in engine.STORE["facts"]:
        assert f["sources"] and f["valid_until"] and f["period"]["en"] and f["period"]["hi"]

def test_hindi_answers_use_lakh_in_devanagari():
    s = ask("80C की सीमा क्या है?")["spoken"]
    assert "₹1.5 लाख" in s and "lakh" not in s

def test_unknown_question_is_honest():
    r = ask("What is the GST rate on gold?")
    assert r["route"] == "no_answer" and "verified figure" in r["spoken"]

def test_stale_fact_says_it_may_have_changed(monkeypatch=None):
    os.environ["FV_TODAY"] = "2027-01-15"
    try:
        s = ask("PPF interest rate?")["spoken"]
        assert "may have changed" in s
    finally:
        os.environ["FV_TODAY"] = "2026-10-19"

# ---- tax calculator (new regime, TY 2026-27) ----
def calc(q):
    """New-regime view of a tax answer."""
    r = ask(q); assert r["route"] == "tax_estimate", r
    return {**r["calc"]["new"], "salaried": r["calc"]["salaried"]}

def test_salary_12_75_lakh_is_tax_free():
    c = calc("How much tax on a salary of 12.75 lakh?")
    assert c["taxable"] == 1200000 and c["total"] == 0

def test_salary_15_lakh():
    c = calc("How much tax will I pay on salary 15 lakh?")
    # taxable 14.25L: 20,000 + 40,000 + 33,750 = 93,750 + 4% cess = 97,500
    assert (c["taxable"], c["after_rebate"], c["total"]) == (1425000, 93750, 97500)

def test_taxable_16_lakh():
    c = calc("How much tax on taxable income of ₹16,00,000?")
    assert c["slab_tax"] == 120000 and c["total"] == 124800

def test_marginal_relief_just_above_12_lakh():
    c = calc("how much tax on income of 12.1 lakh")
    # slab tax 20,000 + 40,000 + 1,500 = 61,500, but relief caps it at the 10,000 excess over 12 lakh
    assert c["slab_tax"] == 61500 and c["after_rebate"] == 10000 and c["total"] == 10400

def test_hindi_tax_question():
    c = calc("मेरी सैलरी 15 लाख है, कितना टैक्स लगेगा?")
    assert c["total"] == 97500

def test_devanagari_digits():
    assert engine.parse_income("मेरी सैलरी १५ लाख है") == 1500000

def test_amount_formats():
    assert engine.parse_income("salary of Rs 15,00,000") == 1500000
    assert engine.parse_income("1.2 crore") == 12000000
    assert engine.parse_income("in 2026 i earn 9 lakh") == 900000

def test_over_limit_refuses_honestly_and_old_regime_is_computed():
    assert "surcharge" in ask("How much tax on 80 lakh salary?")["spoken"]
    r = ask("How much tax on 15 lakh in old regime?")
    assert r["tax_mode"] == "old" and r["calc"]["old"]["total"] == 273000

# ---- number firewall (LLM route) ----
def test_firewall_withholds_unverified_numbers():
    fw = engine.firewall("PPF gives 7.6% and you can put ₹2 lakh.", "tell me about ppf", "en")
    assert "7.6%" not in fw["text"] and "2 lakh" not in fw["text"] and "can't verify" in fw["text"]

def test_firewall_allows_numbers_from_question():
    fw = engine.firewall("On ₹15 lakh, the regime choice depends on your deductions.", "I earn 15 lakh, which regime?", "en")
    assert "₹15 lakh" in fw["text"] and fw["figures"][0]["status"] == "from_question"

def test_firewall_spelled_out_numbers():
    fw = engine.firewall("You can invest one and a half lakh. PPF is a long-term scheme.", "ppf?", "en")
    assert "lakh" not in fw["text"] and "long-term" in fw["text"]

def test_firewall_keeps_plain_years():
    fw = engine.firewall("The new Act applies from 2026.", "what changed?", "en")
    assert "2026" in fw["text"]

def test_strip_thinking():
    assert engine.strip_thinking("<think>x</think>Answer.") == "Answer."
    assert engine.strip_thinking("Answer.<think>never closed") == "Answer."

def test_inr_formatting():
    assert engine.inr(1425000) == "₹14,25,000" and engine.inr(500) == "₹500"


# ---- new facts ----
def test_repo_rate_and_fd_tds():
    assert "5.50%" in ask("What is the repo rate?")["spoken"]
    s = ask("FD ब्याज पर TDS कब कटता है?")["spoken"]
    assert "10%" in s and "₹50,000" in s and "₹1 लाख" in s
    assert [f["id"] for f in ask("Can I still submit Form 15H?")["facts"]] == ["fd_tds"]

# ---- follow-ups ----
def ctx(q):
    r = ask(q); return {"question": q, "route": r["route"], "calc": r["calc"]}

def test_followup_new_amount_keeps_salary_basis():
    r = engine.answer("और 20 लाख पर?", use_llm=False, context=ctx("मेरी सैलरी 15 लाख है, कितना टैक्स लगेगा?"))
    # taxable 19.25L: 20,000+40,000+60,000+65,000 = 1,85,000 + 4% cess = 1,92,400
    assert r["route"] == "tax_estimate" and r["calc"]["salaried"] and r["calc"]["new"]["total"] == 192400
    assert r["lang"] == "hi"

def test_followup_switch_scheme():
    r = engine.answer("and NSC?", use_llm=False, context=ctx("What is the PPF interest rate?"))
    assert [f["id"] for f in r["facts"]] == ["nsc_rate"]

def test_followup_switch_aspect():
    r = engine.answer("what about the maximum deposit?", use_llm=False, context=ctx("PPF interest rate?"))
    assert [f["id"] for f in r["facts"]] == ["ppf_deposit_limit"]

def test_no_context_followup_is_honest():
    assert ask("and for 20 lakh?")["route"] == "no_answer"

# ---- freshness ----
def test_freshness_checker_flags_expired():
    import check_freshness
    os.environ["FV_TODAY"] = "2027-01-02"
    try:
        assert check_freshness.main(30) == 1
    finally:
        os.environ["FV_TODAY"] = "2026-10-19"
    assert check_freshness.main(30) == 0


# ---- golden tests: published worked examples from independent sites (taxable income -> total tax incl. cess) ----
# TaxBadi "Tax at a glance" (new regime, TY 2026-27) and Bajaj Housing Finance table.
GOLDEN = {1250000: 52000, 1275000: 74100, 1500000: 109200, 2000000: 208000, 2500000: 343200, 5000000: 1123200}

def test_calculator_matches_published_examples():
    cfg = engine.STORE["tax_calculator"]
    for taxable, expected in GOLDEN.items():
        assert engine.new_regime_tax(taxable, cfg)["total"] == expected, taxable


# ---- old regime + comparison ----
OLD_GOLDEN = {800000: 75400, 1000000: 117000, 1200000: 179400, 1500000: 273000,
              2000000: 429000, 2500000: 585000, 3000000: 741000, 5000000: 1365000}   # TaxBadi table, below-60

def test_old_regime_matches_published_examples():
    cfg = engine.STORE["old_regime_calculator"]
    for taxable, expected in OLD_GOLDEN.items():
        assert engine.old_regime_tax(taxable, cfg)["total"] == expected, taxable

def test_old_regime_rebate_and_senior_slabs():
    cfg = engine.STORE["old_regime_calculator"]
    assert engine.old_regime_tax(500000, cfg)["total"] == 0                       # rebate up to ₹5 lakh
    assert engine.old_regime_tax(500001, cfg)["total"] > 0                        # no marginal relief in old regime
    assert engine.old_regime_tax(850000, cfg, "senior")["total"] == 83200         # 10,000 + 70,000 + 4% cess
    assert engine.old_regime_tax(500000, cfg, "super_senior")["slab_tax"] == 0

def test_compare_and_breakeven_15_lakh():
    r = ask("Which regime is better for a salary of 15 lakh?")
    c = r["calc"]
    assert r["tax_mode"] == "compare" and c["new"]["total"] == 97500 and c["old"]["total"] == 257400
    # hand check: old pre-cess must equal 93,750 -> taxable 9,06,250 -> deductions 14,50,000 - 9,06,250
    assert c["breakeven_deductions"] == 543750

def test_compare_breakeven_30_lakh():
    assert ask("Which regime is better for salary 30 lakh?")["calc"]["breakeven_deductions"] == 800000

def test_deductions_parsed_and_used():
    r = ask("Salary 15 lakh, 80C 1.5 lakh and home loan interest 2 lakh, HRA 1 lakh. Which regime is better?")
    assert r["calc"]["deductions"] == 450000 and r["calc"]["old"]["total"] == 117000

def test_age_detection():
    assert engine.age_group("I am 65, pension 9 lakh") == "senior"
    assert engine.age_group("मैं 82 साल का हूँ") == "super_senior"
    assert engine.age_group("salary 15 lakh") == "normal"
    assert engine.age_group("I am 15 lakh in debt") == "normal"

def test_zero_tax_new_regime_has_no_breakeven():
    r = ask("I am 65, pension 9 lakh, compare old and new regime")
    assert r["calc"]["new"]["total"] == 0 and r["calc"]["breakeven_deductions"] is None
    assert "already pay no tax" in r["spoken"]

def test_followup_keeps_compare_mode():
    first = ask("Which regime is better for a salary of 15 lakh?")
    ctx = {"question": first["question"], "route": first["route"], "calc": first["calc"], "tax_mode": first["tax_mode"]}
    r = engine.answer("and 30 lakh?", use_llm=False, context=ctx)
    assert r["tax_mode"] == "compare" and r["calc"]["breakeven_deductions"] == 800000


# ---- deduction caps ----
def test_caps_applied_per_category():
    r = ask("Salary 15 lakh, 80C 3 lakh, health insurance 40,000 and home loan interest 2.5 lakh. Which regime is better?")
    items = {i["category"]: (i["claimed"], i["allowed"]) for i in r["calc"]["deduction_items"]}
    assert items == {"sec123": (300000, 150000), "health_self": (40000, 25000), "home_loan_interest": (250000, 200000)}
    assert r["calc"]["deductions"] == 375000 and "legal maximum" in r["spoken"]

def test_senior_health_cap_is_higher():
    d = engine.parse_deductions("I am 66, pension 10 lakh, health insurance 45,000", "senior")
    assert d["items"][0]["allowed"] == 45000

def test_parents_age_does_not_make_caller_senior():
    assert engine.age_group("salary 30 lakh, parents health insurance 50,000 senior parents") == "normal"
    assert engine.age_group("मेरे माता-पिता 70 साल के हैं, सैलरी 15 लाख") == "normal"
    d = engine.parse_deductions("salary 30 lakh, parents health insurance 50,000 senior parents")
    assert d["items"][0]["category"] == "health_parents" and d["items"][0]["allowed"] == 50000

def test_hindi_80c_cap():
    r = ask("मेरी सैलरी 20 लाख है, 80C में 2 लाख और होम लोन ब्याज 2 लाख, कौन सी व्यवस्था बेहतर है?")
    assert r["calc"]["deductions"] == 350000 and "सीमा तक" in r["spoken"]

def test_income_not_counted_as_deduction():
    d = engine.parse_deductions("salary of 12 lakh with deductions of 2 lakh")
    assert d["allowed"] == 200000


# ---- HRA (old regime, TY 2026-27; 8 cities at 50% under Income-tax Rules 2026) ----
def test_hra_metro_city_50pct():
    r = ask("My basic is 6 lakh, HRA 3.6 lakh and rent 40,000 a month in Pune. How much HRA exemption?")
    h = r["hra"]
    # lowest of 3,60,000 / 50% x 6,00,000 = 3,00,000 / 4,80,000 - 60,000 = 4,20,000
    assert h["metro"] and h["exempt"] == 300000 and h["taxable_hra"] == 60000 and h["inputs"]["rent"] == 480000

def test_hra_non_metro_40pct():
    h = ask("Basic 6 lakh, HRA 3.6 lakh, rent 40,000 per month in Jaipur, how much HRA is exempt?")["hra"]
    assert not h["metro"] and h["exempt"] == 240000

def test_hra_rent_is_the_limit():
    h = engine.hra_exemption(600000, 300000, 240000, True)
    assert h["exempt"] == 180000 and h["limiting"] == "rent minus 10% of salary"

def test_hra_hindi_and_bangalore_alias():
    r = ask("मेरी बेसिक 6 लाख, एचआरए 3.6 लाख और किराया 40,000 महीना, पुणे में। HRA छूट कितनी है?")
    assert r["hra"]["exempt"] == 300000 and "पुणे" in r["spoken"]
    assert engine.hra_city("I live in Bangalore")[1] is True

def test_hra_asks_for_missing_inputs():
    r = ask("How much HRA exemption can I claim? rent 20000 a month")
    assert set(r["hra"]["missing"]) == {"basic", "hra", "city"} and "I need" in r["spoken"]

def test_hra_cities_fact():
    assert [f["id"] for f in ask("Which cities get 50% HRA?")["facts"]] == ["hra_metro_cities"]


# ---- talking styles: tone changes, numbers and warnings never do ----
import itertools, re as _re
import style as style_mod

ALL_STYLES = [dict(energy=e, detail=d, warmth=w) for e, d, w in
              itertools.product(*[style_mod.CHOICES[k] for k in ("energy", "detail", "warmth")])]
STYLE_QS = ["What is the PPF interest rate?", "मेरी सैलरी 15 लाख है, कितना टैक्स लगेगा?",
            "Salary 15 lakh, 80C 3 lakh, health insurance 40,000 and home loan interest 2.5 lakh. Which regime is better?",
            "Basic 6 lakh, HRA 3.6 lakh, rent 40,000 a month in Pune. How much HRA exemption?",
            "What is the GST rate on gold?", "and for 20 lakh?"]
MUST_KEEP = ["legal maximum", "may have changed", "verified figure", "estimate", "disclose", "I need",
             "सीमा तक", "अनुमान", "पुष्टि"]
FIG = _re.compile(r"₹\d[\d,]*\d|₹\d|\d+(?:\.\d+)?%")

def _figs_without_optional(r):
    core = style_mod.strip_markers(engine.answer(r["question"], use_llm=False)["spoken_plain"])
    return core

def test_styles_never_change_numbers_or_warnings():
    for q in STYLE_QS:
        base = engine.answer(q, use_llm=False)
        # every number in the REQUIRED content must survive every style
        core_figs = set(FIG.findall(base["spoken_core"]))
        assert core_figs or "verified figure" in base["spoken_core"] or "I need" in base["spoken_core"], q
        for st in ALL_STYLES:
            r = engine.answer(q, use_llm=False, style=st)
            assert core_figs <= set(FIG.findall(r["spoken"])), (q, st)
            for phrase in MUST_KEEP:
                if phrase in base["spoken_plain"]:
                    assert phrase in r["spoken"], (q, st, phrase)
            assert "⟦" not in r["spoken"]

def test_brief_drops_only_optional_note():
    q = "Which regime is better for a salary of 15 lakh?"
    brief = engine.answer(q, use_llm=False, style={"detail": "brief"})["spoken"]
    std = engine.answer(q, use_llm=False)["spoken"]
    assert "capped at" in std and "capped at" not in brief and "₹5,43,750" in brief

def test_detailed_working_adds_up():
    r = engine.answer("How much tax will I pay on salary 15 lakh?", use_llm=False, style={"detail": "detailed"})
    amounts = [int(a.replace(",", "")) for a in _re.findall(r"is ₹([\d,]+)", r["spoken"].split("Here's the working:")[1].split("That's")[0])]
    assert sum(amounts) == r["calc"]["new"]["slab_tax"] == 93750
    assert "the first ₹4,00,000 is tax-free" in r["spoken"]

def test_voice_follows_energy():
    assert engine.answer("PPF rate?", use_llm=False, style={"energy": "lively"})["voice"]["pace"] > 1
    assert engine.answer("PPF rate?", use_llm=False, style={"energy": "calm"})["voice"]["pace"] < 1

def test_style_commands_en_and_hi():
    r = engine.answer("keep it short please", use_llm=False)
    assert r["route"] == "style" and r["style"]["detail"] == "brief"
    r = engine.answer("थोड़ा डिटेल में बताओ", use_llm=False, style={"warmth": "friendly"})
    assert r["style"] == {"energy": "calm", "detail": "detailed", "warmth": "friendly"}

def test_style_command_inside_real_question_still_answers():
    r = engine.answer("Explain in detail: how much tax on salary 15 lakh?", use_llm=False)
    assert r["route"] == "tax_estimate" and r["style"]["detail"] == "detailed" and "Here's the working" in r["spoken"]

def test_bad_style_values_fall_back_to_default():
    assert style_mod.normalize({"energy": "shouty", "warmth": "rude"}) == style_mod.DEFAULT


# ---- Tax Checkup conversation ----
def run(lines, style=None):
    st, out = None, []
    for u in lines:
        r = engine.answer(u, use_llm=False, style=style, dialog_state=st)
        st = r.get("dialog_state"); out.append(r)
    return out

def test_checkup_one_question_per_turn_and_ends_with_question():
    for r in run(["start tax checkup", "15 lakh salary", "no", "none", "no"]):
        assert r["route"] == "checkup" and r["spoken"].rstrip().endswith("?")
        assert r["spoken"].count("?") <= 2   # a question, or a verdict + one choice question

def test_checkup_echoes_and_accepts_correction():
    rs = run(["checkup", "15 lakh salary", "no, 18 lakh"])
    assert "₹15,00,000" in rs[1]["spoken"] and "₹18,00,000" in rs[2]["spoken"]
    assert rs[2]["dialog_state"]["slots"]["income"] == 1800000

def test_checkup_full_renter_matches_calculators():
    rs = run(["start tax checkup", "15 lakh salary", "no, 18 lakh", "no",
              "PPF 1.5 lakh and health insurance 30,000", "yes", "basic 7 lakh", "HRA 3.5 lakh",
              "rent 30,000 a month", "Pune"])
    c = rs[-1]["calc"]
    # HRA exempt 2,90,000 + deductions 1,75,000 (health capped at 25,000)
    assert c["deductions"] == 465000 and c["new"]["total"] == 150800 and c["old"]["total"] == 205920
    assert "₹55,120" in rs[-1]["spoken"]

def test_checkup_hindi_senior_no_tax():
    rs = run(["टैक्स चेकअप", "पता नहीं", "मेरी पेंशन 9 लाख है", "हाँ", "कोई नहीं", "नहीं"])
    assert "समझ नहीं आई" in rs[1]["spoken"]                 # repair, not a guess
    assert rs[-1]["calc"]["age_group"] == "senior" and rs[-1]["calc"]["new"]["total"] == 0
    assert "कोई टैक्स नहीं" in rs[-1]["spoken"]

def test_checkup_never_assumes_age():
    rs = run(["checkup", "20 lakh", "health insurance 45,000"])
    assert "yes or no" in rs[-1]["spoken"] and rs[-1]["dialog_state"]["step"] == "age"

def test_checkup_choices_after_verdict():
    rs = run(["checkup", "20 lakh", "no", "none", "no", "what would change the answer", "call me when rates change"])
    assert "above" in rs[-2]["spoken"] and rs[-1]["action"] == "show_call_form"

def test_checkup_stop_and_repeat():
    rs = run(["checkup", "repeat that", "stop"])
    assert rs[1]["spoken"] == rs[0]["spoken"] and rs[2]["dialog_state"] is None

# ---- speakable numbers (voice only; screen keeps digits) ----
def _value(words):
    total, unit = 0, {"crore": 10**7, "lakh": 10**5, "thousand": 10**3, "करोड़": 10**7, "लाख": 10**5, "हज़ार": 10**3}
    toks = words.split()
    for i, tok in enumerate(toks):
        if tok.isdigit():
            total += int(tok) * unit.get(toks[i + 1], 1) if i + 1 < len(toks) else int(tok)
    return total

def test_speakable_round_trip():
    for n in [500, 97500, 192400, 1425000, 10000000, 11232000]:
        for lang in ("en", "hi"):
            spoken = engine.speakable(engine.inr(n), lang)
            assert "₹" not in spoken and _value(spoken.replace("rupees", "").replace("रुपये", "")) == n, (n, lang, spoken)
    assert engine.speakable("₹500, ₹1.5 lakh", "en") == "500 rupees, 1.5 lakh rupees"

def test_answers_include_speech_field():
    r = engine.answer("How much tax will I pay on salary 15 lakh?", use_llm=False)
    assert "97 thousand 500 rupees" in r["speech"] and "₹97,500" in r["spoken"]

def test_no_open_ended_closers():
    for w in ("friendly", "formal"):
        s = engine.answer("PPF rate?", use_llm=False, style={"warmth": w})["spoken"]
        assert "anything else" not in s.lower() and s.rstrip().endswith("?")

def test_every_dialog_prompt_ends_with_a_question():
    import dialog
    for lang in ("en", "hi"):
        for key in ("start", "income_repair", "age_q", "age_repair", "ded_q", "ded_repair", "rent_q", "rent_repair",
                    "basic_q", "hra_q", "rentamt_q", "city_q", "choices", "done_choices", "call"):
            assert dialog.T[lang][key].rstrip().endswith("?"), (lang, key)

def test_off_topic_is_out_of_scope_without_cheerful_opener():
    for st in ({"warmth": "friendly", "energy": "lively"}, {"warmth": "formal"}, None):
        r = engine.answer("who is pm of india", use_llm=False, style=st)
        assert r["route"] == "out_of_scope" and "only help" in r["spoken"]
        assert not r["spoken"].startswith(("Good question", "Sure", "Here you go", "Certainly"))
        assert r["spoken"].count("?") == 1 and r["spoken"].rstrip().endswith("?")
    assert engine.answer("भारत के प्रधानमंत्री कौन हैं", use_llm=False)["route"] == "out_of_scope"

def test_finance_without_fact_offers_three_choices():
    r = engine.answer("What is the GST rate on gold?", use_llm=False, style={"warmth": "friendly"})
    assert r["route"] == "no_answer" and r["spoken"].count(",") <= 3 and r["spoken"].rstrip().endswith("?")

def test_off_topic_never_reaches_the_llm(monkeypatch=None):
    called = []
    orig = engine.llm_general
    engine.llm_general = lambda q: called.append(q) or "Some answer."
    try:
        r = engine.answer("who is pm of india", use_llm=True)
        assert r["route"] == "out_of_scope" and called == []
    finally:
        engine.llm_general = orig


# ---- hand-sign demo: each sign's phrase must drive the conversation (static/signs.js SIGNS[].say) ----
def test_sign_phrases_drive_the_checkup_en():
    rs = run(["start tax checkup", "15 lakh salary", "no", "no", "no"])   # 🤟start, typed amount, 🤟no x3
    assert rs[0]["route"] == "checkup" and "saves you" in rs[-1]["spoken"]
    r = run(["start tax checkup", "repeat that"]); assert r[1]["spoken"] == r[0]["spoken"]
    r = run(["start tax checkup", "stop"]); assert r[1]["dialog_state"] is None

def test_sign_phrases_drive_the_checkup_hi():
    rs = run(["टैक्स चेकअप", "मेरी पेंशन 9 लाख है", "हाँ", "नहीं", "नहीं"])
    assert rs[-1]["calc"]["age_group"] == "senior" and rs[-1]["route"] == "checkup"
    r = run(["टैक्स चेकअप", "फिर से"]); assert r[1]["spoken"] == r[0]["spoken"]
    r = run(["टैक्स चेकअप", "बंद करो"]); assert r[1]["dialog_state"] is None
