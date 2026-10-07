"""Interactive chat with the scheduling agent:  python -m agent.chat [--prompt v1]"""
import argparse

from agent.agent import Agent, load_prompt
from sim.clinic import Clinic


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="latest", help="prompt version file in agent/prompt (e.g. v1, v2) or 'latest'")
    a = ap.parse_args()
    from agent.agent import resolve_version
    v = resolve_version(a.prompt)
    clinic = Clinic(initial_appointments=[{"doctor_id": "D4", "date": "2026-10-13", "time": "14:00"}])
    agent = Agent(load_prompt(v), clinic)
    print(f"[prompt {v}] Scheduling assistant (you have one existing appointment). Ctrl-C to quit.\n")
    while True:
        try:
            msg = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if msg:
            print("\nAssistant: ", end="", flush=True)
            try:
                agent.say(msg, on_text=lambda t: print(t, end="", flush=True))
            except RuntimeError as e:
                print(f"\n[error] {e}")
            print("\n")


if __name__ == "__main__":
    main()
