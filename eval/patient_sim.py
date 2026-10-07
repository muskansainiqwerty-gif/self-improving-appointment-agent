"""Patient side of the conversation: scripted turns (reproducible adversarial cases) and/or an LLM persona."""
import llm
from eval.judge import render

PERSONA = """You are role-playing a patient chatting with a clinic's scheduling assistant. Reply with ONE short, natural patient message.
Your instructions: {persona}
Never reveal that you are role-playing. If the conversation has reached its natural end, reply with exactly: [END]

CONVERSATION SO FAR:
{convo}
"""


def next_message(scenario, transcript, turn_idx: int):
    """Returns the next patient message, or None when the scenario is over."""
    script = scenario.get("script")
    if script is not None:
        return script[turn_idx] if turn_idx < len(script) else None
    if turn_idx == 0:
        return scenario["first"]
    if turn_idx >= 8:
        return None
    convo = render([m for m in transcript if m["role"] in ("patient", "agent")])
    text = llm.generate(PERSONA.format(persona=scenario["persona"], convo=convo), temperature=0.7).text.strip()
    return None if "[END]" in text else text
