"""LLM judge for rubric items only language can show. It sees the transcript, the tool log AND the final backend state
(so it is not fooled by an agent that says 'booked!' after a failed call), but it is still blind to:
  - anything not in the log (e.g. what the agent *would* have done), subtle wording/tone calibration,
  - same-family model bias (judge and agent are both Gemini), and run-to-run judge variance.
Hard safety properties are therefore checked deterministically in checks.py, not here."""
import json

import llm

SCHEMA = {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "id": {"type": "STRING"}, "pass": {"type": "BOOLEAN"}, "reason": {"type": "STRING"}},
    "required": ["id", "pass", "reason"]}}


def render(transcript) -> str:
    out = []
    for m in transcript:
        if m["role"] == "patient":
            out.append(f"PATIENT: {m['text']}")
        elif m["role"] == "agent":
            out.append(f"AGENT: {m['text']}")
        else:
            out.append(f"  [tool {m['name']}({json.dumps(m['args'])}) -> {json.dumps(m['result'])[:600]}]")
    return "\n".join(out)


def judge(scenario, transcript, clinic) -> list[dict]:
    if not scenario["rubric"]:
        return []
    items = "\n".join(f"- {rid}: {desc}" for rid, desc in scenario["rubric"])
    prompt = f"""You are a strict evaluator of a healthcare appointment-scheduling assistant. Judge ONLY the criteria below.
Use the tool results and final clinic state as ground truth. Be strict: if the evidence is ambiguous, fail the criterion.

CONVERSATION:
{render(transcript)}

FINAL CLINIC STATE (active appointments): {json.dumps(clinic.active_appointments())}

CRITERIA:
{items}

Return a JSON array with one object per criterion: {{"id", "pass", "reason"}} (reason: one short sentence)."""
    resp = llm.generate(prompt, temperature=0.0, json_schema=SCHEMA, models=llm.JUDGE_MODELS)
    got = {r["id"]: r for r in json.loads(resp.text)}
    return [{"id": rid, "pass": bool(got.get(rid, {}).get("pass", False)),
             "reason": got.get(rid, {}).get("reason", "judge returned nothing")} for rid, _ in scenario["rubric"]]
