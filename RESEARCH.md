# Research log (19 Oct 2026)

## 1. Facts: what's verified, and how

| Fact | Value | Best source | Status |
|---|---|---|---|
| Repo rate | 5.50% (from 5.25%, 7 Oct 2026) | RBI press release | **Official** |
| PPF / SSY / SCSS / NSC / KVP (Oct–Dec 2026) | 7.1% / 8.2% / 8.2% / 7.7% / 7.5% | DEA lists the Q3 notification; outlets quote it | Official listing seen, PDF not read |
| New regime slabs | 0 / 5 / 10 / 15 / 20 / 25 / 30% at ₹4L steps | Income Tax Dept page (AY 2026-27); several sites say unchanged for TY 2026-27 | Official for prior year |
| Rebate | up to ₹60,000, income ≤ ₹12 lakh; Section 156 (old 87A) | Several mapping tables | Secondary, consistent |
| Standard deduction (new) | ₹75,000 | Several sites | Secondary, consistent |
| Section 123 (old 80C) | ₹1.5 lakh, old regime only | Several sites | Secondary, consistent |
| TDS on FD interest | 10% above ₹50,000 (₹1 lakh seniors), Section 393, Form 121 | Several sites | Secondary, consistent |
| New-regime calculator | — | Matches 6 published worked examples (₹12.5L to ₹50L) | Golden-tested |
| Old regime | Slabs 0/5/20/30% (exemption ₹2.5L; ₹3L at 60+; ₹5L at 80+), ₹50,000 standard deduction, ₹12,500 rebate up to ₹5L | ClearTax, SBI General, Axis Max Life, TaxGuru | Secondary, consistent |
| Old-regime calculator | — | Matches 8 published worked examples (₹8L to ₹50L) | Golden-tested |
| HRA (old regime) | 50% of basic + DA in 8 cities (Mumbai, Delhi, Kolkata, Chennai + Bengaluru, Hyderabad, Pune, Ahmedabad), 40% elsewhere; least of HRA received / that % / rent − 10% of basic + DA; landlord relationship must be disclosed | Income-tax Rules 2026, Rule 279 (notified 20 Mar 2026) per TaxGuru, TaxFetch, EZHRM, JM Financial | Secondary, consistent |
| Deduction caps (old regime) | Section 123 ₹1.5L; extra NPS ₹50,000; health insurance ₹25,000 (₹50,000 if senior) + parents ₹25,000 (₹50,000 if senior); home loan interest (self-occupied) ₹2L | TaxGST, TaxClue, ClearTax, ARTH | Secondary, consistent |

**Still to do before the demo:** open the DEA Q3 PDF and the Income-tax Act 2025 text (s.156, s.202, s.123, s.393) and confirm each value. Then change `type` to `primary` in `facts.json`.

## 2. Things the research caught

- **Section numbers conflict across finance websites.** For the rebate, sites said 156, 157 and even 202. The correct one is **156**. 157 is arrears relief and 202 is the new regime itself. This is the kind of error finverify voice refuses to speak.
- **HRA attribution conflict:** most sources credit the 8-city change to the Income-tax Rules 2026 (Rule 279); one says Budget 2025. The app attributes it to the Rules.
- **More section-number conflicts:** home loan interest was "Section 22" on one site and "Section 72" on another; the extra NPS deduction was "124(3)" vs "125". The app now states neither number.
- **The rebate doesn't cover special-rate income** like LTCG on shares, so the "₹12 lakh tax-free" answer now says so.
- **Even the press disagreed on small details:** "ninth" vs "tenth" unchanged quarter, and one quote said the quarter ends 30 December instead of 31. Neither is used in answers.

## 3. Evidence for the pitch

- **Saturn benchmark (2026), reported by Wealth Professional and InvestmentNews:** across 17 models, average accuracy on financial questions was 43%. On hard questions with interacting tax rules and precise figures, it was 12%. Wrong answers came in the same confident tone as right ones.
  https://www.wealthprofessional.ca/news/industry-news/ai-chatbots-give-wrong-financial-answers-most-of-the-time-study-finds/393573
- **Taxmann.AI × IIT Kharagpur LE-BTL benchmark (Indian tax law, 12 LLMs):** the best models reached up to 72.84% on direct tax. Even the best get about 1 in 4 wrong.
  https://www.taxmann.com/post/blog/taxmann-ai-x-iit-kharagpur-llm-evaluation-le-btl-benchmark-study
- **CA-Ben (arXiv 2506.21031), Indian CA exam benchmark:** models struggled most with numerical, multi-step calculations.
  https://arxiv.org/pdf/2506.21031

Use these as quoted, with the source named. Don't round them up.

## 4. The buildathon (from the official pages)

- Apply form: name, email, project name, since when, what you're building and where voice comes in.
- **A separate submit form**, due 31 Oct (https://www.bolna.ai/symphony/buildathon/submit):
  - project description, 1–2 lines, **max 200 characters**
  - submission link: GitHub repo, live app or demo
  - pitch deck or pitch video link (Drive/Luma, "Anyone with the link")
  - the **same email** you registered with
- Timeline: shortlist emails 3 Nov, interviews 5–7 Nov, finalists 8 Nov (top 10 get Symphony tickets), top 3 pitch on 20 Nov in Bengaluru with travel covered.
- Prizes: ₹50,000 + YC interview with YC partner Grey Baker / ₹40,000 / ₹30,000.
- Sponsors: Plivo, Exotel, **Sarvam**, Cartesia, Deepgram, Kalpa Labs. This build uses Sarvam speech plus Bolna.
- No judging criteria are published. Unverified, but likely: a working demo, real-world use, and use of voice.

## 5. Competitors (what exists in India)

| Product | What it is | Voice? | Speaks only sourced numbers? |
|---|---|---|---|
| Kar Saathi (Income Tax Dept, Apr 2026) | Chatbot for ITR filing, refunds and notices; Hindi and English | Not stated in coverage | Not claimed |
| TaxHummer | Says it does voice ITR filing in Hindi, Assamese and English (self-description, unverified) | Yes (claimed) | Not claimed |
| jAI (Finvasia + YES Bank) | Voice finance assistant in Hindi/English | Yes | Not claimed |
| **finverify voice** | Q&A + tax/regime calculator by web voice and phone (Bolna) | Yes | **Yes, by design**: sourced, dated facts and exact maths; unverified numbers withheld |

**Positioning line:** others help you *file*; this one makes sure the *numbers you hear are right*, and says when it can't be sure. It could work alongside them, not against them.

## 6. Talking styles: the psychology behind the feature

**What the research says**
- **Similarity-attraction with voices (Nass & Lee, 2001, J. Experimental Psychology: Applied).** People recognised extravert (louder, faster) vs introvert (softer, slower) personality in synthetic speech. When the voice matched their own personality, they rated it as more attractive, credible and informative. Nass & Lee advise setting parameters like words per minute to fit the user *and* the content (consistency-attraction).
  https://sciencedaily.com/releases/2001/10/011001072153.htm
- **Social presence (Lee & Nass, 2005):** matching felt more "present", especially for extraverted users.
- **Chatbots:** a later study found a similarity effect for agreeableness (agreeable users preferred the agreeable bot), but not the reverse for disagreeable users.
  https://unpaywall.org/10.1145%2F3469595.3469633
- **Warning, similarity can beat expertise (Dahlbäck et al., CHI 2007):** same-accent voices were judged more knowledgeable even when the other speaker would clearly know more.
  https://unpaywall.org/10.1145%2F1240624.1240859
- **Measuring personality:** Big Five is the best-validated model. But the 10-item TIPI shows acceptable test-retest reliability, mixed validity and weak internal consistency (Frontiers in Psychology scoping review, 2023). So a 3-question "personality test" would be unreliable, and labelling people from it would be misleading.
  https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2023.1202953/pdf
- **Voice controls:** Sarvam bulbul:v3 supports pace 0.5–2.0 and a temperature (expressiveness) control. Pitch and loudness are v2-only.
  https://docs.sarvam.ai/api-reference-docs/getting-started/models/bulbul

**Design decisions that follow**
1. **Ask about preferences, not personality.** Three everyday questions, loosely based on Big Five dimensions: Extraversion → lively/calm, need for detail → brief/detailed, Agreeableness/warmth → friendly/formal. No scores, no labels, and the user can change it anytime by voice ("keep it short", "थोड़ा डिटेल में बताओ").
2. **Voice and words stay consistent:** lively means a faster pace, more expressiveness and exclamations; calm means slower, steadier speech with no exclamations.
3. **Style never touches substance.** Because matching raises trust *independent of correctness*, style may only change openers, closers, optional notes and voice pace, and may add step-by-step working from the same calculation. A test checks 6 questions × 18 styles to confirm no number or warning is ever lost.
4. **No manipulation:** style is never used to push a decision (such as a regime choice). The verdict is the same in every style.

**Limits (honest)**
- The core studies are from 2001–2007, with mostly Western, often student, samples, and none were in Indian languages. Whether the effects hold for Hindi-speaking callers is unverified, so test it with real users.
- Effects were measured in shopping and auction tasks, not finance.

## 7. "Just make it talk": voice conversation design

**First principle:** the buildathon's brief is *"Build anything. Just make it talk."* A voice product isn't a chatbot that reads paragraphs aloud. Spoken words live in working memory and disappear, so the conversation has to be short, two-way and step by step.

**Research → design**

| Finding | Source | What the app now does |
|---|---|---|
| Longer responses are harder to follow; use the "one-breath test" | Amazon Alexa design guide | The checkup verdict is one sentence: "The new regime saves you ₹55,120." |
| End with a question; open-ended "anything else?" overloads memory | Amazon Alexa design guide | Every prompt ends with a question (tested); the old "Anything else?" was replaced with three specific choices |
| Ask for one piece of information at a time | VUI best-practice guides | The Tax Checkup asks one question per turn |
| Mirror the user's words to confirm you heard right | VUI design principles | Echoes every amount ("Got it, ₹18,00,000 a year") and accepts "no, 18 lakh" |
| People naturally list in threes | Google Design, "Rule of Three" | Choices are offered in threes |
| Don't give everything at once; handle errors gracefully | uxdesign.cc summary of VUI research | Working, break-even and call are opt-in; repairs explain what answer is expected, never just repeat |
| Bolna can place outbound and scheduled calls (`POST /call`: `agent_id`, `recipient_phone_number`, optional `scheduled_at`, `user_data`) | Bolna API docs | "Call me now" or "call me when the rates change" (10:00 IST the day after the earliest rate expires) |

**Also new:** amounts are *spoken* the way Indians say them ("14 lakh 25 thousand rupees" / "14 लाख 25 हज़ार रुपये"), while the screen keeps exact digits. A round-trip test checks the spoken value equals the number.

**Honest limits**
- Most VUI guidance is industry design guides, not controlled studies.
- Indian phone-calling rules (consent, calling hours, DND) are **unverified** here. The app requires a consent tick, limits each number to 3 requests a day, and Bolna offers calling-hour guardrails. Check the rules before going live.
- Hands-free silence detection is a simple loudness threshold, so noisy rooms may cut off early or late. Test on real phones.

## 8. Hand-sign demo (beta): what it is and isn't

**Research reality**
- Continuous, fluent sign-language recognition is still an unsolved research problem, for ISL or any sign language.
- ISL is among the most under-resourced sign languages for AI. INCLUDE (AI4Bharat / IIT Madras) has 263 word signs from 7 signers; the best reported model reached 94.5% on INCLUDE-50 and 85.6% on all 263 signs, on isolated words recorded in a lab.
  https://zenodo.org/records/4010759
- Small custom vocabularies work: one study recognised 11 isolated ISL signs at 97% on its own dataset (Deepsign, Electronics 2022).
- An ISL interpreter product already exists (Silent Interpreter on Product Hunt), trained on INCLUDE.

**So the demo is deliberately small and honest**
- The user teaches 5 still hand shapes (yes, no, repeat, stop, start checkup) with their own webcam; samples stay in their browser.
- MediaPipe Hand Landmarker finds 21 hand points; recognition is nearest-neighbour on wrist-relative, size-normalised points, mirrored so either hand works. A sign must hold steady for about 0.5 s, it rejects shapes it wasn't taught, and there's a 2 s cooldown.
- Each sign becomes a phrase ("yes" / "हाँ") that drives the same Tax Checkup, so someone can answer without speaking while the app still talks.
- Offline test with synthetic hands: 120/120 taught shapes recognised (moved, scaled, left hand), 50/50 random shapes rejected. **Real-webcam accuracy is untested.**
- On-screen label: "Demo only… not Indian Sign Language translation."

**If this ever becomes real:** work with Deaf signers (for example, a school for the Deaf), use INCLUDE/CISLR under their licences, and treat it as its own product, not a voice-demo add-on.
