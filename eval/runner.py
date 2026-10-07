"""Run scenarios against a prompt version. Each run is scored by deterministic checks + judge rubric."""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import llm
from agent.agent import Agent, load_prompt
from eval import checks as C
from eval.judge import judge
from eval.patient_sim import next_message
from eval.scenarios import SCENARIOS
from sim.clinic import Clinic

RUNS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "runs")


def run_once(scenario: dict, prompt_text: str) -> dict:
    clinic = Clinic(faults=scenario.get("faults", []), initial_appointments=scenario.get("initial", []))
    agent = Agent(prompt_text, clinic)
    err = None
    try:
        i = 0
        while (msg := next_message(scenario, agent.transcript, i)) is not None:
            agent.say(msg)
            i += 1
    except llm.InfraError as e:
        return {"scenario": scenario["id"], "infra_error": str(e)[:200], "passed": False, "results": [],
                "transcript": agent.transcript, "final_state": []}
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
        if "client has been closed" in err:
            return {"scenario": scenario["id"], "infra_error": err[:200], "passed": False, "results": [],
                    "transcript": agent.transcript, "final_state": []}
    results = []
    for name, params in scenario["checks"]:
        ok, detail = C.REGISTRY[name](clinic, agent.transcript, **params)
        results.append({"kind": "check", "id": name + (f"({','.join(map(str, params.values()))})" if params else ""), "pass": ok, "reason": detail})
    if err is None:
        try:
            for r in judge(scenario, agent.transcript, clinic):
                results.append({"kind": "judge", **r})
        except llm.InfraError as e:
            return {"scenario": scenario["id"], "infra_error": f"judge: {str(e)[:150]}", "passed": False, "results": [],
                    "transcript": agent.transcript, "final_state": []}
        except Exception as e:  # noqa: BLE001
            err = f"judge failed: {e}"
    if err:
        results.append({"kind": "error", "id": "run_error", "pass": False, "reason": err})
    return {"scenario": scenario["id"], "passed": all(r["pass"] for r in results), "results": results,
            "transcript": agent.transcript, "final_state": clinic.active_appointments()}


def run_with_retry(scenario: dict, prompt_text: str, attempts: int = 3) -> dict:
    """Infra failures (quota, 503, closed client) are retried and, if they persist, excluded from scoring."""
    for i in range(attempts):
        res = run_once(scenario, prompt_text)
        if "infra_error" not in res:
            return res
        time.sleep(5 * (i + 1))
    return res


def run_suite(prompt_version: str, n: int = 3, only: list[str] | None = None, workers: int = 4, tag: str | None = None) -> dict:
    prompt_text = load_prompt(prompt_version)
    scen = [s for s in SCENARIOS if not only or s["id"] in only]
    jobs = [(s, k) for s in scen for k in range(n)]
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        runs = list(ex.map(lambda j: run_with_retry(j[0], prompt_text), jobs))
    by, infra = {}, {}
    for r in runs:
        if "infra_error" in r:
            infra[r["scenario"]] = infra.get(r["scenario"], 0) + 1
            continue
        by.setdefault(r["scenario"], []).append(r)
    summary = {sid: {"pass_rate": sum(r["passed"] for r in rs) / len(rs), "runs": len(rs), "infra_excluded": infra.get(sid, 0)}
               for sid, rs in by.items()}
    overall = sum(v["pass_rate"] for v in summary.values()) / len(summary) if summary else 0.0
    out = {"prompt_version": prompt_version, "n": n, "overall": overall, "infra_errors": sum(infra.values()), "summary": summary, "runs": runs,
           "seconds": round(time.time() - t0)}
    os.makedirs(RUNS_DIR, exist_ok=True)
    path = os.path.join(RUNS_DIR, f"{tag or prompt_version}_eval.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1, default=str)
    out["path"] = path
    return out


def print_report(res: dict):
    print(f"\n=== prompt {res['prompt_version']}  overall pass rate {res['overall']:.0%}  (n={res['n']}/scenario, {res['seconds']}s) ===")
    for sid, v in res["summary"].items():
        print(f"  {'PASS' if v['pass_rate'] == 1 else 'FAIL' if v['pass_rate'] == 0 else 'FLAKY':5s} {v['pass_rate']:.0%}  {sid}"
              + (f"  (excluded {v['infra_excluded']} infra-error run(s))" if v.get("infra_excluded") else ""))
    if res.get("infra_errors"):
        print(f"  NOTE: {res['infra_errors']} run(s) excluded for infrastructure errors (not agent failures)")
    print()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="v1")
    ap.add_argument("-n", type=int, default=3)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--tag", default=None, help="output file prefix (default: prompt version)")
    a = ap.parse_args()
    print_report(run_suite(a.prompt, a.n, a.only, a.workers, a.tag))
