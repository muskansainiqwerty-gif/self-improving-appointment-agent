"""The scheduling agent: a manual tool-use loop around Gemini with backend-derived session state."""
from __future__ import annotations

import os
import re

from google.genai import types

import llm
from agent.tools import DECLARATIONS, dispatch
from sim.clinic import TODAY, Clinic, _weekday

PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompt")
MAX_TOOL_STEPS = 8


def resolve_version(v: str) -> str:
    """'latest' -> highest vN.md present."""
    if v != "latest":
        return v
    nums = [int(m.group(1)) for f in os.listdir(PROMPT_DIR) if (m := re.fullmatch(r"v(\d+)\.md", f))]
    return f"v{max(nums)}"


def load_prompt(version: str) -> str:
    with open(os.path.join(PROMPT_DIR, f"{version}.md")) as f:
        return f.read()


class Agent:
    def __init__(self, system_prompt: str, clinic: Clinic):
        self.system_prompt = system_prompt
        self.clinic = clinic
        self.history: list[types.Content] = []
        self.transcript: list[dict] = []  # {"role","text"} plus {"role":"tool",...}
        self.turn = 0  # increments with each patient message; gates confirmation tokens

    def _state_block(self) -> str:
        """Authoritative state re-derived from the backend every turn (not from the model's memory)."""
        apts = self.clinic.active_appointments()
        lines = [f"[SESSION STATE - from the clinic system]", f"Today is {_weekday(TODAY)} {TODAY}.",
                 f"Patient's confirmed appointments: " + (
                     "; ".join(f"{a['appointment_id']}: {a['doctor']} {a['weekday']} {a['date']} {a['time']}" for a in apts)
                     if apts else "none")]
        return "\n".join(lines)

    def say(self, patient_text: str, on_text=None) -> str:
        self.turn += 1
        self.transcript.append({"role": "patient", "text": patient_text, "turn": self.turn})
        self.history.append(types.Content(role="user", parts=[types.Part(text=patient_text)]))
        system = self.system_prompt + "\n\n" + self._state_block()
        for _ in range(MAX_TOOL_STEPS):
            if on_text:  # interactive: stream tokens as they arrive
                content = llm.generate_stream(self.history, system=system, tools=[DECLARATIONS], on_text=on_text)
            else:
                resp = llm.generate(self.history, system=system, tools=[DECLARATIONS])
                content = resp.candidates[0].content if resp.candidates else None
            if not content or not content.parts:
                reply = "I'm sorry, I ran into a problem. Could you repeat that?"
                break
            self.history.append(content)  # keep as-is so thought signatures are preserved
            calls = [p.function_call for p in content.parts if p.function_call]
            if not calls:
                reply = "".join(p.text for p in content.parts if p.text and not getattr(p, "thought", False)).strip()
                break
            results = []
            for c in calls:
                args = dict(c.args or {})
                res = dispatch(self.clinic, c.name, args, self.turn)
                self.transcript.append({"role": "tool", "turn": self.turn, "name": c.name, "args": args, "result": res})
                results.append(types.Part(function_response=types.FunctionResponse(name=c.name, response=res)))
            self.history.append(types.Content(role="user", parts=results))
        else:
            reply = "I'm sorry, I couldn't complete that. Could you try again?"
        self.transcript.append({"role": "agent", "text": reply, "turn": self.turn})
        return reply
