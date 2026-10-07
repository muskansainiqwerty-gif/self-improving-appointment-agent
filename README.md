# Self-improving appointment-scheduling agent

**Result:** prompt v1 → v2 improved the pass rate from 78.1% to 88.5% with no regressions (see `runs/loop_report.md` and `DESIGN.md`).

A patient-scheduling agent (Gemini, native tool use) plus an evaluation harness that turns its own failures into
structured prompt patches, re-runs every scenario, and only keeps a patch if it improves the failures **without regressing** anything.

## Setup
```bash
pip install --user google-genai pyyaml python-dotenv      # Python 3.10+
echo 'GEMINI_API_KEY=...' > .env                          # .env is gitignored
# optional model overrides (defaults shown):
#   GEMINI_MODELS=gemma-4-26b-a4b-it      (agent + patient sim)
#   JUDGE_MODELS=gemini-3.5-flash-lite    (judge + improver)
```

## Run
```bash
python -m agent.chat                 # talk to the agent (uses the latest accepted prompt; --prompt v1 for the baseline)
python -m eval.loop                  # eval v1 -> failures -> structured patch -> v2 -> re-eval -> regression gate
python -m eval.loop --reuse-baseline # same, reusing runs/v1_eval.json
python -m unittest discover tests    # offline backend tests, no API key needed
python -m eval.runner --prompt v2    # just score one prompt version (-n runs per scenario, --only <ids>)
```
Artifacts land in `runs/` (`v1_eval.json`, `v2_eval.json`, `loop_report.md` = the before/after table and the patches, `before_after_transcripts.md` = real v1-vs-v2 conversations).
Prompt versions are `agent/prompt/vN.md`; `v1.md` is the original prompt verbatim, later versions append a `## Learned Rules` section,
and each has a `vN.patches.json` recording which failure produced which rule. Rejected candidates are kept as `*.rejected.md`.

## Layout
| path | what |
|---|---|
| `sim/clinic.py` | Mock clinic backend = source of truth. Fault injection (error / timeout-with-unknown-outcome / slot race). |
| `agent/tools.py`, `agent/agent.py` | Tool schema + manual tool-use loop. Session state (today, patient's real appointments) is re-injected from the backend each turn. |
| `eval/scenarios.py` | 16 scenarios incl. emergencies, injection, ambiguous "yes", timeouts, reschedule failure. |
| `eval/checks.py` | Deterministic checks on backend log/state (primary signal). |
| `eval/judge.py` | LLM judge for language-only criteria; sees tool log + final state. |
| `improve/improver.py` | Failure -> root cause -> general rule patch -> new prompt version. |
| `eval/loop.py` | The closed loop + regression gate. |

See `DESIGN.md` for the design note and assumptions.
