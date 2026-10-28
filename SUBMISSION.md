# Submission checklist (due 31 Oct 2026)

Submit at https://www.bolna.ai/symphony/buildathon/submit, using the **same email you applied with**.

## 1. Project description (max 200 characters): pick one

- **D (169 chars, conversation-first):** A Hindi/English voice agent that runs a 1-minute tax checkup by talking to you, then calls you back when rates change. It only speaks numbers it can source or calculate.

- **A (152 chars):** A Hindi/English voice assistant for Indian savings and tax questions that only speaks numbers it can source or calculate, and refuses to guess the rest.
- **B (160 chars):** Ask about PPF rates or your income tax in Hindi or English, by phone or web. Every number it says comes from a dated source or exact calculation, never a guess.
- **C (150 chars):** Voice AI for Indian money questions that won't guess numbers: sourced rates, exact tax estimates, Hindi and English, on the web and over a phone call.

## 2. Submission link
Push this folder to a public GitHub repo. Deploy the Dockerfile for a live link if you can. Never commit `.env`.

## 3. Pitch video (2 minutes), suggested outline

1. **Problem (20s).** In one benchmark of 17 AI models, accuracy on hard tax questions with precise figures was 12%, and wrong answers sounded just as confident (Saturn, 2026). On a call, you can't re-read a number.
2. **Idea (15s).** The AI never supplies numbers. Every figure comes from a dated source or an exact calculation; anything else is withheld.
3. **Demo (60s): lead with the conversation; it's what "just make it talk" asks for.**
   - Hands-free Tax Checkup in Hindi: it asks, you answer, you correct it ("नहीं, 18 लाख"), you get a one-breath verdict, then "call me when rates change".
   - Hindi: "मेरी सैलरी 15 लाख है, कितना टैक्स लगेगा?" gives the exact answer with a breakdown.
   - Follow-up: "और 20 लाख पर?"
   - "Which regime is better for a salary of 15 lakh?" gives both taxes and says the old regime only wins above ₹5,43,750 of deductions.
   - "Basic 6 lakh, HRA 3.6 lakh, rent 40,000 a month in Pune" gives ₹3 lakh exempt, using the new 2026 rule that put Pune in the 50% list.
   - Talking style: pick "Like a friend + With working", then switch to "keep it short". Same numbers, different voice. Mention that it's based on Nass & Lee's similarity-attraction research.
   - "PPF rate?" shows the official source and its valid-until date.
   - Ask something not covered: it says it has no verified figure.
   - Show `FV_TODAY=2027-01-02`: the stale rate is flagged.
   - Bolna phone call (if ready).
4. **Proof (15s).** Both calculators match 14 published worked examples, and deductions are capped at legal limits; 64 automated tests. Finance websites disagreed on a section number (156/157/202), which is exactly why it doesn't trust the web blindly.
5. **Different from Kar Saathi / TaxHummer (10s).** They help you file; this makes sure the numbers you hear are right.
6. **Why you (10s).** Built by the solo founder of finverify. Next: connect finverify and add more facts.

Only show results you actually ran. Re-run `pytest -q` and `check_freshness.py` on the day you record.
