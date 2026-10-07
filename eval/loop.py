"""Closed improvement loop:  eval -> structured patch -> new prompt version -> re-eval -> regression gate.

    python -m eval.loop [--prompt v1] [-n 3] [--rounds 2] [--reuse-baseline]
"""
from __future__ import annotations

import argparse
import json
import os

from eval.runner import RUNS_DIR, print_report, run_suite
from improve.improver import apply_patches, next_version, propose_patches
from agent.agent import PROMPT_DIR, load_prompt


def compare(before: dict, after: dict, targets: list[str]) -> dict:
    b, a = before["summary"], after["summary"]
    improved = [s for s in targets if a[s]["pass_rate"] > b[s]["pass_rate"]]
    regressed = [s for s in b if a[s]["pass_rate"] < b[s]["pass_rate"]]
    tmean = lambda d: sum(d[s]["pass_rate"] for s in targets) / len(targets) if targets else 0  # noqa: E731
    return {"improved": improved, "regressed": regressed, "target_before": tmean(b), "target_after": tmean(a)}


def confirm_regressions(version: str, regressed: list[str], n: int, workers: int):
    """A regression at small n can be noise: re-run just those scenarios with more samples before rejecting."""
    return run_suite(version, n=n * 2, only=regressed, workers=workers, tag=f"{version}_regression_recheck")


def table(before: dict, after: dict) -> str:
    rows = [f"{'scenario':32s} {before['prompt_version']:>6s} {after['prompt_version']:>6s}"]
    for s in before["summary"]:
        b, a = before["summary"][s]["pass_rate"], after["summary"][s]["pass_rate"]
        mark = "  ▲" if a > b else "  ▼ REGRESSION" if a < b else ""
        rows.append(f"{s:32s} {b:>6.0%} {a:>6.0%}{mark}")
    rows.append(f"{'OVERALL':32s} {before['overall']:>6.0%} {after['overall']:>6.0%}")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="v1")
    ap.add_argument("-n", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--reuse-baseline", action="store_true", help="reuse runs/<prompt>_eval.json instead of re-running")
    a = ap.parse_args()

    cur = a.prompt
    path = os.path.join(RUNS_DIR, f"{cur}_eval.json")
    if a.reuse_baseline and os.path.exists(path):
        base = json.load(open(path)); base["path"] = path
    else:
        base = run_suite(cur, a.n, workers=a.workers)
    print_report(base)
    report = [f"# Improvement loop report\n"]
    rejected_note = ""
    for rnd in range(1, a.rounds + 1):
        failing = [s for s, v in base["summary"].items() if v["pass_rate"] < 1]
        if not failing:
            print("All scenarios pass; nothing to improve."); break
        print(f"--- round {rnd}: failing scenarios: {failing}")
        patches, targets = propose_patches(load_prompt(cur), base, rejected_note)
        print(json.dumps(patches, indent=1))
        cand = apply_patches(cur, patches)
        new = run_suite(cand, a.n, workers=a.workers)
        cmp_ = compare(base, new, failing)
        if cmp_["regressed"]:
            print(f"possible regressions {cmp_['regressed']}; re-checking with n={a.n * 2}")
            rc = confirm_regressions(cand, cmp_["regressed"], a.n, a.workers)
            still = [s for s in cmp_["regressed"] if rc["summary"][s]["pass_rate"] < base["summary"][s]["pass_rate"]]
            for s in cmp_["regressed"]:
                new["summary"][s]["pass_rate"] = rc["summary"][s]["pass_rate"]
            new["overall"] = sum(v["pass_rate"] for v in new["summary"].values()) / len(new["summary"])
            cmp_ = compare(base, new, failing)
        print(table(base, new))
        accepted = bool(cmp_["improved"]) and not cmp_["regressed"]
        verdict = (f"ACCEPTED {cand}: targets {cmp_['target_before']:.0%} -> {cmp_['target_after']:.0%}, no regressions"
                   if accepted else f"REJECTED {cand}: improved={cmp_['improved']} regressed={cmp_['regressed']}")
        print("\n" + verdict + "\n")
        report += [f"## Round {rnd}: {base['prompt_version']} -> {cand}\n", "```", table(base, new), "```", f"\n**{verdict}**\n",
                   "Patches:\n```json\n" + json.dumps(patches, indent=1) + "\n```\n"]
        if accepted:
            base, cur = new, cand
        else:
            rejected_note = verdict
            os.rename(os.path.join(PROMPT_DIR, f"{cand}.md"), os.path.join(PROMPT_DIR, f"{cand}.rejected.md"))
            os.rename(os.path.join(PROMPT_DIR, f"{cand}.patches.json"), os.path.join(PROMPT_DIR, f"{cand}.rejected.patches.json"))
    open(os.path.join(RUNS_DIR, "loop_report.md"), "w").write("\n".join(report))
    print(f"Final prompt: {cur}. Report: runs/loop_report.md")


if __name__ == "__main__":
    main()
