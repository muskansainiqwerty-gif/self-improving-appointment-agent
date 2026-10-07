# Design note: self-improving appointment-scheduling agent

**What it is.** A multi-turn scheduling agent (Gemini API, native tool calling) over a mock clinic, an eval harness with 16 scenarios, and a loop that turns failures into structured prompt patches, re-runs every scenario, and keeps a patch only if it fixes failures without regressing anything. Baseline prompt `v1` is the provided one, unchanged.

## Design decisions
- **Safety in code, not only the prompt.** Booking, cancel and reschedule need a single-use `confirmation_token` bound to one exact action and target, redeemable only after a *later* patient message. Rescheduling is atomic (the original is released only after the new slot is secured).
- **Backend is the source of truth.** Every tool call is logged; today's date and the patient's real appointments are re-injected each turn.
- **Failures injected on purpose:** clean errors, a slot taken mid-booking, and timeouts with unknown outcome (committed or not).
- **Two-layer scoring.** Deterministic checks on backend state/tool log are primary (mutation without confirmation, blind retry after a timeout, original lost after a failed reschedule). An LLM judge covers only language (emergency wording, advice boundary, prompt leak) and sees the tool log, so "booked!" after a failed call can't fool it. Agent (`gemma-4-26b-a4b-it`) and judge/improver (`gemini-3.5-flash-lite`) are different models, which also reduces same-model bias.
- **Patches are data.** The improver emits `{scenarios, root_cause, rule_title, rule_text}`; rules must be general (no scenario ids/names, to limit overfitting). The gate accepts a version only if targets improve and none regress; apparent regressions get a double-sample recheck. Infrastructure errors (quota, 503) are retried, then excluded from scores and improver input.

## Result (n=3 per scenario, one model throughout)
**v1 78.1% → v2 88.5%, no scenario regressed** (`runs/loop_report.md`; side-by-side transcripts in `runs/before_after_transcripts.md`).

| scenario | v1 | v2 |
|---|---|---|
| timeout_but_committed | 0% (0/3) | 50% (1/2) |
| book_slot_taken | 0% (0/3) | 67% (2/3) |
| reschedule_slot_taken | 50% (1/2) | 100% (2/2) |
| cancel_happy | 0% (0/3) | 0% (0/3) |
| other 12 scenarios | 100% | 100% |

The gains came from three improver rules about not asking the patient to confirm twice. **Trust level:** small sample. Infrastructure errors removed 2 runs from v1 and 4 from v2, so some scenarios have 2 valid runs; the 78→88 move is about three scenarios — direction, not effect size. A round-2 candidate (v3) was generated but its gate did not finish and I stopped the loop; v3 is not part of the result. An earlier v1 baseline on `gemini-3.1-flash-lite` scored 88% on 14 valid scenarios; I changed models only because free-tier quota ran out.

## Findings
1. **Double confirmation was the dominant failure on both models.** The agent asks "shall I book?" *before* calling `request_confirmation`, so the patient's "yes" triggers a second confirmation request and the action never runs. Partly my design: the two-step token flow makes the wrong order easy.
2. **The improver's diagnosis was half wrong, the rule still worked.** It said the agent skips the execution tool; the real cause is asking twice. Its three rules overlap, so v2 is wordier than needed.
3. **`cancel_happy` is still 0%:** the agent asks "is this the one?" and only then calls `request_confirmation`; the scripted patient has two messages, so the run ends. Part agent, part scenario limit.
4. **My first eval was wrong, not the agent.** It scored 56% because my harness's own errors (a client shared across threads, 503s) counted as agent failures — fixed by excluding infra errors.
5. Most scenarios pass at v1, so the loop had few real failures; I did not add scenarios just to make v1 fail.

## Known limits
The gate checks that a patient turn happened, not that the reply was an explicit "yes" (only the judge covers that). n=3 is noisy and most patients are scripted. The improver sees the scenarios it is scored on (no held-out set). The judge was not calibrated against human labels; all models are Google's. Assumptions: synthetic data, one patient per session, no auth, "today" fixed at 2026-10-06.

## Where AI helped, and where my judgment overrode it
**AI help.** Claude Code wrote nearly all the code (clinic, tool loop, harness, judge, improver, tests); in the loop, a Gemini model diagnosed failures and wrote the rules. The task framing and baseline prompt were mine.

**My decisions.** The AI proposed the Anthropic API; I supplied a Gemini key and built on Gemini. It presented a design before coding and I approved it first. When free-tier quota blocked the eval I chose a billed key, then told it to use `gemini-3.1-flash-lite`, later moving the agent to Gemma when that quota ran out. I asked for streaming in chat, asked the AI to critique and rate its own architecture, and decided to stop the loop at v2 once it had a clean accepted before/after.

**Where the AI was wrong.** Its first eval counted its own infra errors as agent failures (caught by reading failing runs). The improver's diagnosis was only half right (Finding 2); I kept the working rule and recorded the discrepancy. Its "safety enforced in code" claim was stronger than the code: the gate does not verify an explicit yes (Known limits).
