"""Local AI backend (brain.md D52): free and offline. The same request as the Claude backend (system prompt, task,
image of the selection, JSON schema answer {transcription, result}) answered by a vision-language model on this
laptop through Ollama's local HTTP API (`POST /api/chat`). Standard library only; nothing leaves the machine
unless `[ai] local_url` points elsewhere.

`warm_up` loads the model into GPU memory at the start of a session (an empty `POST /api/generate`), so the first
question does not also pay the model load; `keep_alive` keeps it loaded between questions. Every failure becomes
an `AIAnswer` with a panel message (Ollama not running, model not downloaded, timeout); nothing raises.
"""

from __future__ import annotations

import base64
import json
import socket
import time
import urllib.error
import urllib.request

from ..config import AIConfig
from .client import ACTIONS, SCHEMA, SYSTEM, AIAnswer

KEEP_ALIVE = "30m"
# A hard cap on the generated tokens: a transcription plus an answer of <= ~80 words needs ~300. Without it, the
# thinking variant of qwen3-vl (tag qwen3-vl:8b) deliberated on rough finger-writing for 2,895 tokens / 88 s
# and never answered (2026-10-23 smoke test); the default is now the instruct variant (D52).
LOCAL_MAX_TOKENS = 1024


def build_local_request(cfg: AIConfig, action: str, png: bytes) -> dict:
    """The JSON body of Ollama's /api/chat for one action on one image. Pure."""
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    return {
        "model": cfg.local_model,
        "stream": False,
        "format": SCHEMA,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": 0, "num_predict": LOCAL_MAX_TOKENS},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Task: {ACTIONS[action]}",
             "images": [base64.standard_b64encode(png).decode("ascii")]},
        ],
    }


def parse_local_response(action: str, data: dict) -> AIAnswer:
    """Ollama's /api/chat reply -> AIAnswer. Pure."""
    usage = {k: data[k] for k in ("prompt_eval_count", "eval_count") if k in data}
    base = dict(action=action, model=str(data.get("model", "")), stop_reason=str(data.get("done_reason", "")),
                usage=usage)
    if data.get("done_reason") == "length":
        return AIAnswer(ok=False, error="The answer was cut off; try a smaller selection.", **base)
    content = (data.get("message") or {}).get("content")
    if not content:
        return AIAnswer(ok=False, error="The local AI returned no text.", **base)
    try:
        parsed = json.loads(content)
        return AIAnswer(ok=True, transcription=str(parsed["transcription"]).strip(),
                        result=str(parsed["result"]).strip(), **base)
    except (ValueError, KeyError, TypeError):
        return AIAnswer(ok=False, error="The local AI's answer could not be read.", **base)


class LocalAssistant:
    """`ask(action, png)` -> AIAnswer through Ollama. Blocking: run it in the AI worker thread."""

    def __init__(self, cfg: AIConfig, opener=urllib.request.urlopen):
        self.cfg = cfg
        self._open = opener
        self.base_url = cfg.local_url.rstrip("/")

    def _post(self, path: str, body: dict, timeout: float) -> dict:
        request = urllib.request.Request(self.base_url + path, data=json.dumps(body).encode("utf-8"),
                                         headers={"Content-Type": "application/json"}, method="POST")
        with self._open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def warm_up(self) -> bool:
        """Load the model now (best effort): True when Ollama answered."""
        try:
            self._post("/api/generate", {"model": self.cfg.local_model, "keep_alive": KEEP_ALIVE},
                       self.cfg.timeout_s)
            return True
        except Exception:
            return False

    def ask(self, action: str, png: bytes) -> AIAnswer:
        t0 = time.perf_counter()
        try:
            data = self._post("/api/chat", build_local_request(self.cfg, action, png), self.cfg.timeout_s)
            answer = parse_local_response(action, data)
        except Exception as e:                           # every failure ends in the panel, never in the loop
            answer = AIAnswer(action=action, ok=False, error=local_error_message(e, self.cfg))
        answer.latency_s = time.perf_counter() - t0
        return answer


def local_error_message(e: Exception, cfg: AIConfig) -> str:
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 404:
            return f"Model {cfg.local_model} is not downloaded: run `ollama pull {cfg.local_model}`."
        return f"Local AI error {e.code}."
    reason = getattr(e, "reason", e)
    if isinstance(reason, (TimeoutError, socket.timeout)) or isinstance(e, (TimeoutError, socket.timeout)):
        return f"No answer within {cfg.timeout_s:g} s."
    if isinstance(e, (urllib.error.URLError, ConnectionError)):
        return "The local AI is not running: start Ollama."
    return f"Local AI request failed: {type(e).__name__}."
