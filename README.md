# finverify voice (v4)

A Hindi/English voice assistant for Indian savings rates and income tax that **only speaks numbers it can source or compute.**

## The idea, from first principles

1. A spoken number can't be re-read, so a wrong one gets trusted.
2. LLMs produce numbers from memory, and memory goes stale or is simply wrong.
3. Checking an LLM's numbers *after* it writes them still lets misses through.
4. **So the LLM never supplies numbers.** Every figure the assistant says comes from one of these:
   - `facts.json`: a sourced, dated record with an expiry date
   - an exact calculation (the new-regime tax calculator)
   - the user's own question
   - finverify, which must verify it
5. Anything else is **withheld, not spoken**. When a fact expires, the assistant says it may have changed.

## How a question is answered

| Route | When | Numbers come from |
|---|---|---|
| **Exact calculation** | "How much tax on a 15 lakh salary?", "Which regime is better for me?" | Deterministic calculators for both regimes: slabs (with senior and super-senior old-regime slabs), standard deductions (₹75,000 new / ₹50,000 old), rebates, marginal relief, 4% cess. A regime comparison also gives the **break-even deductions** above which the old regime wins |
| **Sourced fact** | "PPF rate?", "80C limit?" | `facts.json` templates (English and Hindi) |
| **General answer** | No fact matches and an LLM is configured | The LLM explains concepts; a firewall withholds any number not verified by finverify or present in the question |
| **No verified figure** | Nothing matches | An honest "I don't have a verified figure" plus a list of what it can answer |

The first two routes need **no LLM and no network**, so they're fast, deterministic and testable.

## What's covered (researched 19 Oct 2026)

- Small savings rates for Oct–Dec 2026: PPF, Sukanya Samriddhi, SCSS, NSC, KVP. These expire 31 Dec 2026.
- PPF deposit limits.
- New regime for tax year 2026-27: slabs, the ₹12 lakh tax-free limit and rebate, the ₹75,000 standard deduction.
- Section 123 (old 80C) ₹1.5 lakh limit and the extra NPS ₹50,000.
- Old regime rebate limit.
- HRA exemption calculator (old regime): the 8 cities at 50% under the Income-tax Rules 2026, 40% elsewhere, least-of-three formula. It asks for missing inputs instead of guessing.
- RBI repo rate (5.50% from 7 Oct 2026). Its expiry is set conservatively to 1 Dec 2026, because the next policy date is unverified.
- TDS on FD interest for 2026-27: 10% above ₹50,000 (₹1 lakh for seniors), 20% without PAN, Section 393, and Form 121 replacing 15G/15H.
- Tax estimates under either regime, plus an old-vs-new comparison with break-even deductions, for incomes up to ₹50 lakh. Age (60+ / 80+) and stated deductions are understood.

## Tax Checkup: a real conversation

Press **Start tax checkup** (or say "tax checkup" / "टैक्स चेकअप"). It asks one question per turn: salary or pension, age 60+, deductions, and rent/HRA. It echoes every amount back so you can correct it ("no, 18 lakh"), then gives a one-breath verdict ("The new regime saves you ₹55,120") and offers three choices: the working, what would change the answer, or a call when rates change.

- **Hands-free mode:** after it speaks, it listens again and stops recording when you pause, like a phone call.
- **Call me:** `POST /call` asks Bolna to ring the user now, or at 10:00 IST the day after the rates expire. It requires a consent tick and allows 3 requests per number per day. Set `BOLNA_API_KEY` and `BOLNA_AGENT_ID`.
- **Phone versions:** `bolna/checkup_prompt.txt` (inbound checkup) and `bolna/callback_prompt.txt` (the call it makes to you).
- **Natural numbers:** the voice says "14 lakh 25 thousand rupees"; the screen shows ₹14,25,000.

## Hand-sign demo (beta)

Open **Hand-sign demo** on the page, press **Start camera**, and teach 5 still hand shapes (yes, no, repeat, stop, start checkup) by holding each for about 2 seconds. Showing a taught sign then answers the Tax Checkup for you, and the app talks back. It's **demo only**: hand signs you teach it, not Indian Sign Language translation. It needs internet the first time, to load Google's MediaPipe hand tracker. Details and limits are in `RESEARCH.md`, section 8.

## Talking styles

On first visit, the app asks three quick questions (in English or Hindi): lively or calm, just the answer or with the working, friend or professional. The choice changes the opener and sign-off, whether optional notes and step-by-step working are included, and the voice speed and expressiveness (Sarvam bulbul:v3). It **never** changes numbers, sources or warnings, and a test checks this across all 18 style combinations. Users can change it by voice ("keep it short", "be more formal", "थोड़ा डिटेल में बताओ"). The research basis is in `RESEARCH.md`, section 6.

## Follow-up questions

The web app sends the previous turn as `context`, so these work:
- "मेरी सैलरी 15 लाख है, कितना टैक्स लगेगा?" → "और 20 लाख पर?" keeps the salary basis and recalculates.
- "PPF rate?" → "and NSC?" switches scheme.
- "PPF rate?" → "what about the maximum deposit?" switches aspect.

A follow-up with no context gets the honest "no verified figure" reply. On the phone, the Bolna prompt rewrites follow-ups into full questions.

## Keeping facts fresh

`python check_freshness.py [days]` lists facts expiring soon and flags single-source ones. It exits with code 1 if anything has expired, so a CI job or cron can block a deploy. Set `FV_TODAY=2027-01-02` to preview what callers would hear after expiry.

**Sources:** the repo rate is confirmed by RBI's press release, and the small savings Q3 notice is listed by the DEA. Other figures come from **secondary sources** (news and finance sites) that agree with each other. Two facts rely on a single source and are marked that way. Before the demo, confirm each against the official notification or incometax.gov.in. Every fact lists its URLs, and `/facts` shows them all. The rebate is Section 156 (old 87A), confirmed across several mapping tables; one site wrongly said 157. See `RESEARCH.md` for the full log and `SUBMISSION.md` for the Oct 31 checklist.

## Run it

1. `pip install -r requirements.txt`
2. `python -m pytest -q tests` (69 tests, including golden tests against 14 published tax examples: 6 new-regime, 8 old-regime)
3. `cp .env.example .env`. **No keys are needed** for typed questions. Add `SARVAM_API_KEY` for Sarvam voice in and out, plus the LLM fallback.
4. `uvicorn server:app --port 8000`, then open http://localhost:8000

Each answer shows its route badge, sources, validity date and, for tax, the full calculation table.

## Phone (Bolna)

1. Deploy (Dockerfile) or tunnel (`cloudflared tunnel --url http://localhost:8000`).
2. Set `BOLNA_TOKEN` in `.env`.
3. Paste `bolna/function.json` (with your URL and token filled in) as a custom function, and `bolna/prompt.txt` as the prompt.

The common path has no LLM call, so it's fast. Bolna's docs confirm the schema and that POST sends JSON with a Bearer header. **Unverified:** the tool timeout, and whether Bolna's LLM rewords numbers when reading them out, so check your test-call transcripts.

## Adding or updating facts

Edit `facts.json` only, never the code. Each fact needs `match` keywords (English and Hindi), `values`, `say` templates, `period`, `valid_until` and `sources`. The loader refuses a fact with no sources, a bad template, or Hindi values whose digits differ from the English ones. Run `python eval_questions.py` to check coverage.

## Where finverify fits

`finverify_adapter.py` is the firewall's verifier for any number an LLM writes on the general route. Connect it there (HTTP or Python). With it off, every LLM-written number is withheld.

## Limits

- Tax calculators: resident individual, income up to ₹50 lakh (no surcharge). Stated deductions are sorted into categories and capped at the legal limit (Section 123 ₹1.5L, NPS ₹50,000, health insurance ₹25,000/₹50,000 for self and parents, home loan interest ₹2L). The answer says when it capped something. HRA is formula-based and is taken as stated. The marginal-relief and cess order follows the cited worked examples; treat the output as an estimate.
- Fact matching is keyword-based. Add keywords when `eval_questions.py` shows gaps.
- Each question is answered on its own. On the phone, the Bolna prompt rewrites follow-ups into full questions.
