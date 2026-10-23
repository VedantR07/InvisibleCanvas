"""Claude reads the selected writing and does one action on it (brain.md D51, §9.11).

The request is one Messages API call through the official `anthropic` SDK (imported only when the assistant is
created, so the rest of the project runs without it): an image of the selected strokes (PNG, black ink on white)
plus the action. Structured output (`output_config.format`) guarantees a JSON answer with what Claude read
(`transcription`) and the action's `result`. Server-side refusal fallbacks (`fallbacks: "default"`, beta
`server-side-fallback-2026-07-01`) re-run a declined request on another model. Every failure becomes an
`AIAnswer` with a message for the projected panel; nothing raises out of `ask`.

Credentials come from the environment (`ANTHROPIC_API_KEY`); without them the SDK raises TypeError at request
time ("Could not resolve authentication method"), mapped to a "no API key" message.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field

from ..config import AIConfig

ACTIONS = {
    "summarize": "Summarize what is written in one to three short sentences.",
    "explain": "Explain what is written so that a student can understand it. Keep it short.",
    "simplify": "Rewrite what is written in simpler words, keeping its meaning.",
    "examples": "Give two or three short, concrete examples of what is written.",
    "questions": "Write three short questions that check understanding of what is written.",
}

SYSTEM = (
    "You read writing from a projected interactive whiteboard. The image shows strokes drawn with a finger in "
    "the air in front of a wall, so the handwriting can be rough, shaky or slanted, and letters can be "
    "disconnected. First transcribe exactly what is written (keep the line breaks; write [?] for anything you "
    "cannot read). Then do the task on that content. The result is shown on the wall in a small panel: plain "
    "text, no markdown, at most about 80 words. If nothing readable is written, say so in the result."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "transcription": {"type": "string", "description": "What is written, as read from the image"},
        "result": {"type": "string", "description": "The task's answer, plain text, at most about 80 words"},
    },
    "required": ["transcription", "result"],
    "additionalProperties": False,
}

FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass
class AIAnswer:
    action: str
    ok: bool
    transcription: str = ""
    result: str = ""
    error: str = ""                       # panel message when not ok
    model: str = ""                       # the model that answered (a fallback model after a refusal)
    stop_reason: str = ""
    latency_s: float = 0.0
    usage: dict = field(default_factory=dict)
    request_id: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def build_request(cfg: AIConfig, action: str, png: bytes) -> dict:
    """The keyword arguments of `client.beta.messages.create` for one action on one image. Pure."""
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    request = {
        "model": cfg.model,
        "max_tokens": cfg.max_tokens,
        "system": SYSTEM,
        "output_config": {"effort": cfg.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.standard_b64encode(png).decode("ascii")}},
                {"type": "text", "text": f"Task: {ACTIONS[action]}"},
            ],
        }],
    }
    if cfg.fallbacks:
        request["betas"] = [FALLBACK_BETA]
        request["fallbacks"] = "default"
    return request


def parse_response(action: str, response) -> AIAnswer:
    """An SDK message -> AIAnswer. A refusal, a cut-off answer or invalid JSON become errors. Pure."""
    stop = getattr(response, "stop_reason", "") or ""
    usage = getattr(response, "usage", None)
    usage_d = {k: getattr(usage, k) for k in ("input_tokens", "output_tokens") if usage is not None and hasattr(usage, k)}
    base = dict(action=action, model=getattr(response, "model", "") or "", stop_reason=stop, usage=usage_d,
                request_id=getattr(response, "_request_id", "") or "")
    if stop == "refusal":
        return AIAnswer(ok=False, error="Claude declined this request.", **base)
    if stop == "max_tokens":
        return AIAnswer(ok=False, error="The answer was cut off (max_tokens); try a smaller selection.", **base)
    text = next((b.text for b in getattr(response, "content", []) if getattr(b, "type", "") == "text"), None)
    if text is None:
        return AIAnswer(ok=False, error="Claude returned no text.", **base)
    try:
        data = json.loads(text)
        return AIAnswer(ok=True, transcription=str(data["transcription"]).strip(), result=str(data["result"]).strip(),
                        **base)
    except (ValueError, KeyError, TypeError):
        return AIAnswer(ok=False, error="Claude's answer could not be read.", **base)


class ClaudeAssistant:
    """`ask(action, png)` -> AIAnswer. Blocking: run it in the AI worker thread, never in the frame loop."""

    def __init__(self, cfg: AIConfig, client=None):
        self.cfg = cfg
        if client is None:
            import anthropic                              # only when AI is switched on (S4)
            client = anthropic.Anthropic(timeout=cfg.timeout_s, max_retries=1)
        self.client = client

    def ask(self, action: str, png: bytes) -> AIAnswer:
        t0 = time.perf_counter()
        try:
            response = self.client.beta.messages.create(**build_request(self.cfg, action, png))
            answer = parse_response(action, response)
        except Exception as e:                          # every failure ends in the panel, never in the loop
            answer = AIAnswer(action=action, ok=False, error=error_message(e, self.cfg))
        answer.latency_s = time.perf_counter() - t0
        return answer


def error_message(e: Exception, cfg: AIConfig) -> str:
    """A short panel message for an exception from the SDK (checked by name: the SDK may not be installed)."""
    name = type(e).__name__
    if isinstance(e, TypeError) and "authentication" in str(e).lower():
        return "No API key: set ANTHROPIC_API_KEY on this laptop."
    messages = {
        "AuthenticationError": "The API key was not accepted.",
        "PermissionDeniedError": "This API key may not use this model.",
        "NotFoundError": f"Model {cfg.model!r} not found.",
        "RateLimitError": "Too many requests right now; try again in a moment.",
        "APITimeoutError": f"No answer within {cfg.timeout_s:g} s.",
        "APIConnectionError": "No connection to the Claude API: check the internet.",
        "BadRequestError": "The request was refused as invalid.",
    }
    if name in messages:
        return messages[name]
    status = getattr(e, "status_code", None)
    if status is not None:
        return f"Claude API error {status}; try again later." if status >= 500 else f"Claude API error {status}."
    return f"AI request failed: {name}."
