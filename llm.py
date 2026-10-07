"""Thin Gemini wrapper: retries on overload/rate limits, optional model fallback."""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Primary model plus fallbacks (comma separated in GEMINI_MODELS). Preview models are often overloaded.
MODELS = [m.strip() for m in os.environ.get("GEMINI_MODELS", "gemma-4-26b-a4b-it").split(",")]  # agent + patient sim (high volume)
# Judge and improver need reliable structured JSON, which Gemma does not give; they are low volume and use a different
# model from the agent, which also reduces same-model bias in scoring.
JUDGE_MODELS = [m.strip() for m in os.environ.get("JUDGE_MODELS", "gemini-3.5-flash-lite").split(",")]

import threading

_client = None
_lock = threading.Lock()


class InfraError(RuntimeError):
    """LLM unavailable / quota / transport failure. Never an agent-behaviour failure."""


def client() -> genai.Client:
    global _client
    with _lock:  # one shared client; creating it from several threads at once closed it under the others
        if _client is None:
            _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        return _client


def reset_client():
    global _client
    with _lock:
        _client = None


def _config(system, tools, temperature, json_schema=None):
    return types.GenerateContentConfig(
        system_instruction=system, temperature=temperature, tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        response_mime_type="application/json" if json_schema else None, response_schema=json_schema)


def generate_stream(contents, system=None, tools=None, temperature: float = 0.3, on_text=None):
    """Streaming variant for interactive chat: calls on_text(chunk) as text arrives, returns the merged response content.
    Falls back through MODELS only if the stream fails before any output."""
    cfg = _config(system, tools, temperature)
    last = None
    for model in MODELS:
        for attempt in range(5):
            parts, started = [], False
            try:
                for chunk in client().models.generate_content_stream(model=model, contents=contents, config=cfg):
                    if not chunk.candidates or not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                        continue
                    for p in chunk.candidates[0].content.parts:
                        parts.append(p)
                        if p.text and not getattr(p, "thought", False) and on_text:
                            started = True
                            on_text(p.text)
                return types.Content(role="model", parts=parts)
            except Exception as e:  # noqa: BLE001
                last = e
                msg = str(e)
                if "client has been closed" in msg:
                    reset_client()
                    continue
                if started or "PerDay" in msg or "404" in msg:
                    if started:
                        raise
                    break  # daily quota / retired model: next model
                if any(c in msg for c in ("503", "429", "500", "UNAVAILABLE", "RESOURCE_EXHAUSTED")):
                    time.sleep(min(2 ** attempt, 10))
                    continue
                raise
    raise InfraError(f"All models unavailable (daily free-tier quota is 20 requests/model/day). Last error: {str(last)[:200]}")


def generate(contents, system: str | None = None, tools=None, temperature: float = 0.3,
             json_schema: dict | None = None, retries: int = 6, models: list[str] | None = None):
    models = models or MODELS
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        response_mime_type="application/json" if json_schema else None,
        response_schema=json_schema,
    )
    last = None
    for model in models:
        for attempt in range(max(1, retries // len(models))):
            try:
                return client().models.generate_content(model=model, contents=contents, config=cfg)
            except Exception as e:  # noqa: BLE001
                last = e
                msg = str(e)
                if "client has been closed" in msg:
                    reset_client()
                    continue
                if "PerDay" in msg or "404" in msg:  # daily quota gone / model retired: retrying is pointless, next model
                    break
                if any(c in msg for c in ("503", "429", "500", "UNAVAILABLE", "RESOURCE_EXHAUSTED")):
                    time.sleep(min(2 ** attempt * 2, 20))
                    continue
                raise
    raise InfraError(f"All models unavailable (daily free-tier quota is 20 requests/model/day; use a billed key "
                       f"or wait). Last error: {str(last)[:200]}")
