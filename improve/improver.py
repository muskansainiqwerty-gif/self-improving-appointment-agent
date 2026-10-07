"""Turn eval failures into structured, reviewable prompt patches, and apply them as a new prompt version.

A patch is data, not a rewrite: {scenarios, root_cause, rule_title, rule_text}. Applying appends it to a
'Learned Rules' section, so every behavioural change is traceable to the failures that motivated it.
"""
from __future__ import annotations

import json
import os
import re

import llm
from agent.agent import PROMPT_DIR, load_prompt
from eval.judge import render

PATCH_SCHEMA = {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "scenarios": {"type": "ARRAY", "items": {"type": "STRING"}},
    "root_cause": {"type": "STRING"},
    "rule_title": {"type": "STRING"},
    "rule_text": {"type": "STRING"}},
    "required": ["scenarios", "root_cause", "rule_title", "rule_text"]}}

INSTRUCTIONS = """You improve the system prompt of a healthcare appointment-scheduling agent using evidence from failed evaluation runs.

For the failures below, diagnose the ROOT CAUSE in the agent's behaviour (why did the prompt not prevent it?), then propose
a small number (max {max_patches}) of NEW prompt rules that would fix that class of failure.

Hard requirements for every rule:
- GENERAL: describe the behaviour, never mention specific scenario ids, patient names, doctor names, slot ids or dates from the failures
  (a rule that only fits the test would be overfitting).
- SPECIFIC & ACTIONABLE: say exactly what to do and what not to do, in 2-5 sentences of imperative prose.
- ADDITIVE: do not contradict or weaken existing rules (especially safety and confirmation rules). Do not repeat a rule already present
  unless the failure shows it is being ignored; then sharpen it instead.
- Respect that tools and a confirmation-token gate already exist; the rule should change the agent's conversational behaviour.
{rejected}
CURRENT SYSTEM PROMPT:
<<<
{prompt}
>>>

FAILED RUNS (one representative failing run per scenario; `failed criteria` are the exact checks that failed):
{failures}

Return a JSON array of patches: {{"scenarios": [ids it addresses], "root_cause", "rule_title", "rule_text"}}."""


def collect_failures(res: dict, per_scenario: int = 1) -> tuple[str, list[str]]:
    blocks, ids = [], []
    seen: dict[str, int] = {}
    for r in res["runs"]:
        if r["passed"] or "infra_error" in r or seen.get(r["scenario"], 0) >= per_scenario:
            continue
        seen[r["scenario"]] = seen.get(r["scenario"], 0) + 1
        ids.append(r["scenario"]) if r["scenario"] not in ids else None
        failed = [f"- {x['id']} ({x['kind']}): {x['reason']}" for x in r["results"] if not x["pass"]]
        blocks.append(f"### scenario `{r['scenario']}` (pass rate {res['summary'][r['scenario']]['pass_rate']:.0%})\n"
                      f"failed criteria:\n" + "\n".join(failed) + "\n\ntranscript:\n" + render(r["transcript"]))
    return "\n\n".join(blocks), ids


def propose_patches(prompt_text: str, res: dict, rejected_note: str = "", max_patches: int = 3) -> tuple[list[dict], list[str]]:
    failures, ids = collect_failures(res)
    if not ids:
        return [], []
    rej = f"\nA previous attempt was REJECTED by the regression gate:\n{rejected_note}\nAvoid repeating its mistake.\n" if rejected_note else ""
    prompt = INSTRUCTIONS.format(max_patches=max_patches, prompt=prompt_text, failures=failures, rejected=rej)
    patches = json.loads(llm.generate(prompt, temperature=0.2, json_schema=PATCH_SCHEMA, models=llm.JUDGE_MODELS).text)
    return patches[:max_patches], ids


def next_version(cur: str) -> str:
    return f"v{int(cur[1:]) + 1}"


def apply_patches(cur_version: str, patches: list[dict]) -> str:
    new = next_version(cur_version)
    base = load_prompt(cur_version)
    section = "\n\n---\n\n## Learned Rules\n\n" if "## Learned Rules" not in base else "\n\n"
    body = "".join(f"### {p['rule_title']}\n\n{p['rule_text'].strip()}\n\n" for p in patches).rstrip() + "\n"
    with open(os.path.join(PROMPT_DIR, f"{new}.md"), "w") as f:
        f.write(base.rstrip() + section + body)
    with open(os.path.join(PROMPT_DIR, f"{new}.patches.json"), "w") as f:
        json.dump({"from": cur_version, "patches": patches}, f, indent=1)
    return new
