"""Claude reads the selected writing and does one action on it (brain.md D51, §9.11).

The request is one Messages API call through the official `anthropic` SDK (imported only when the assistant is
created, so the rest of the project runs without it): an image of the selected strokes (PNG, black ink on white)
plus the action. Structured output (`output_config.format`) guarantees a JSON answer with what Claude read
(`transcription`) and the action's `result`. Server-side refusal fallbacks (`fallbacks: "default"`, beta
`server-side-fallback-2026-07-01`) re-run a declined request on another model. Every failure becomes an
`AIAnswer` with a message for the projected panel; nothing raises out of `ask`.

EXPLORE (D54) goes beyond the writing (topic, background, key facts, a connected concept) in the same single
request; its answer format adds `readable` and `topic`, and an answer without a topic read with confidence is
replaced by a fixed message (`UNREADABLE`), so no guessed topic reaches the panel. The other actions are unchanged.

D61: a request has a context. On an opened document (`{"source": "document"}`) the image is the shown page itself
(a picture, or a PDF page rendered by PDFium) and the system prompt and tasks speak of a page (`SYSTEM_DOCUMENT`,
`DOCUMENT_ACTIONS`) instead of finger-writing; the answer format is the same. ASK carries a question typed on the
laptop (`{"question": ...}`) and answers it about the writing or the page.

Credentials come from the environment (`ANTHROPIC_API_KEY`); without them the SDK raises TypeError at request
time ("Could not resolve authentication method"), mapped to a "no API key" message.
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass, field

from ..config import AIConfig

ACTIONS = {
    # D76 (user, 2026-10-31: "very light and little" answers): the main idea and key points, how and why, an
    # example; each point on its own line
    # D76 wall test: "The text asks for an explanation of SQL ..." opened the summary of "WHAT IS SQL"; answering about
    # the topic made the model invent ("CaT, a program developed by ...") until the facts rule was added
    "summarize": ("Give the main idea of the topic in one sentence that states it directly, about the topic itself "
                  "rather than the writing (if the writing asks a question or makes a request, answer it), then 2 or "
                  "3 key points about it, each on its own line starting with '- '. Use only well-established facts: "
                  "when the words are unclear, take their most common everyday meaning; never invent names, dates "
                  "or organisations, and never guess anything about a person named in the writing."),
    "explain": ("Explain the topic of what is written so that a student understands it: what it is, how or why "
                "it works, and one concrete example, in 3 or 4 lines each starting with '- '."),
    "simplify": ("Explain what is written in very simple words, as to a 10-year-old, keeping every important "
                 "idea, in 3 or 4 short lines each starting with '- '."),
    "examples": ("Give three concrete, real-world examples of the topic of what is written, each on its own line "
                 "starting with '- ', with one short detail about each."),
    "questions": ("Write three questions that check understanding of what is written, from easy to harder, each "
                  "on its own line starting with '- '."),
    # D54: beyond the writing; its own answer format (EXPLORE_SCHEMA) says whether a topic was read at all
    "explore": ("Find the topic of what is written and help the reader explore it beyond the written words: "
                "3 or 4 short lines, each starting with '- ' and at most 12 words, giving background, key facts "
                "and one connected concept worth exploring next. Do not repeat or summarize the writing. Only "
                "state well-established facts. Never state anything about a person named in the writing (for "
                "example where the name comes from or whether it is male or female): explore the general topic "
                "instead. Put the topic itself (1 to 4 words) in the topic field. In the "
                "transcription write a single [?] for each part you cannot read. If the writing cannot be read "
                "with confidence, names no clear topic, or names something you do not know as a real subject "
                "(for example a misspelled word or an unknown name), set readable to false and leave the topic "
                "empty: never guess a topic or invent facts."),
    # D61: a question typed on the laptop keyboard; {question} is filled in by task_for
    "ask": ("Answer the question below about what is written clearly and specifically, with the reason or an "
            "example where it helps, in at most about 100 words. Use what is written and well-established facts "
            "only; if you cannot answer it, say so. Question: {question}"),
}

# D61: the same actions on a page of an opened document (an image, or a rendered PDF page)
DOCUMENT_ACTIONS = {
    # D76: as the handwriting tasks, on the page
    "summarize": ("Give the main idea of this page in one sentence, then 2 or 3 key points from it, each on its "
                  "own line starting with '- '."),
    "explain": ("Explain what this page shows so that a student understands it: what it is, how or why it "
                "works, and one concrete example, in 3 or 4 lines each starting with '- '."),
    "simplify": ("Explain the content of this page in very simple words, as to a 10-year-old, keeping every "
                 "important idea, in 3 or 4 short lines each starting with '- '."),
    "examples": ("Give three concrete, real-world examples of what this page is about, each on its own line "
                 "starting with '- ', with one short detail about each."),
    "questions": ("Write three questions that check understanding of this page, from easy to harder, each on "
                  "its own line starting with '- '."),
    "explore": ("Find the topic of this page and help the reader explore it beyond what the page says: 3 or 4 short "
                "lines, each starting with '- ' and at most 12 words, giving background, key facts and one "
                "connected concept worth exploring next. Do not repeat or summarize the page. Only state "
                "well-established facts. Never state anything about a person named on the page (for example where "
                "the name comes from or whether it is male or female): explore the general topic instead. Put the "
                "topic itself (1 to 4 words) in the topic field. If the page cannot be read with confidence or "
                "shows no clear topic, set readable to false and leave the topic empty: never guess a topic or "
                "invent facts."),
    "ask": ("Answer the question below about this page clearly and specifically, in at most about 100 words. Use "
            "what the page shows and well-established facts only; say whether the answer is on the page, and if you "
            "cannot answer it, say so. Question: {question}"),
}

# D79 (wall test 2026-10-31 20:38, ASK "where is this institute situated": "located in Chennai, Tamil Nadu, India, based
# on well-established facts"; it is in Raipur): a guess is never stated as a fact, and the teacher's own facts
# (`[ai] facts`) are given with every request (`system_for`)
NO_GUESS = (" Never present a guess as a fact: for a specific detail you do not know for certain (where a particular "
            "school, college, company or small place is, or details about a person), say that you do not know it.")

SYSTEM = (
    "You read writing from a projected interactive whiteboard. The image shows strokes drawn with a finger in "
    "the air in front of a wall, so the handwriting can be rough, shaky or slanted, and letters can be "
    "disconnected. First transcribe exactly what is written (keep the line breaks; write [?] for anything you "
    "cannot read). Then do the task on that content: answer about the content itself with specific, useful "
    "information (facts, reasons, an example), never describe the handwriting, the letters or the image. The "
    "result is shown on the wall in a small panel: plain text, no markdown, at most about 100 words. If nothing "
    "readable is written, say so in the result."
    + NO_GUESS
)

# D61: an opened document's page. The transcription is only a short line (the panel shows it above the answer, and a
# whole page copied out would use up the answer's tokens).
SYSTEM_DOCUMENT = (
    "You read a page shown on a projected interactive whiteboard: a picture or a page of a PDF document chosen by "
    "the teacher (printed text, diagrams, tables or photos). In the transcription, do not copy the page: write its "
    "title or first line, or for a picture one short line saying what it shows (at most 15 words; write [?] for "
    "anything you cannot read). Then do the task on the page's content with specific, useful information "
    "(facts, reasons, an example). The result is shown on the wall in a small panel: plain text, no markdown, "
    "at most about 100 words. If the page shows nothing you can read or recognise, say so in the result."
    + NO_GUESS
)
# D74: added only when the teacher selected a part of the page (whole-page requests are unchanged)
SYSTEM_REGION = (" The image is only the part of the page that the teacher selected: in the task, 'this page' means "
                 "that part.")
# D75 V2: added for the typed text written on the board by voice (or the words of it the teacher selected)
SYSTEM_TYPED = (" The image is text the teacher dictated onto the whiteboard (or the words of it the teacher "
                "selected): in the task, 'this page' means that text.")

SCHEMA = {
    "type": "object",
    "properties": {
        "transcription": {"type": "string", "description": "What is written, as read from the image"},
        "result": {"type": "string", "description": "The task's answer, plain text, at most about 100 words"},
    },
    "required": ["transcription", "result"],
    "additionalProperties": False,
}

# D54: EXPLORE also reports whether the writing named a topic it could read; the other actions keep SCHEMA
EXPLORE_SCHEMA = {
    "type": "object",
    "properties": {
        "transcription": SCHEMA["properties"]["transcription"],
        "readable": {"type": "boolean",
                     "description": "true only if the writing was read with confidence and names a clear topic"},
        "topic": {"type": "string", "description": "The topic in 1 to 4 words; empty when readable is false"},
        "result": {"type": "string", "description": "3 or 4 short lines starting with '- ', plain text"},
    },
    "required": ["transcription", "readable", "topic", "result"],
    "additionalProperties": False,
}

# Shown instead of the model's text when EXPLORE found no topic it could read: nothing is invented on the wall
UNREADABLE = "Could not read a clear topic. Write it larger, or select just the topic word, and try again."

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def schema_for(action: str) -> dict:
    return EXPLORE_SCHEMA if action == "explore" else SCHEMA


def is_document(context: dict | None) -> bool:
    return (context or {}).get("source") == "document"


def is_printed(context: dict | None) -> bool:
    """A page's printed content: a document (D61), or the typed text written by voice (D75 V2)."""
    return (context or {}).get("source") in ("document", "voice")


def facts_text(facts=()) -> str:
    """D79: the teacher's own facts (`[ai] facts`), true for this class, added to the system text."""
    given = [str(f).strip() for f in facts if str(f).strip()]
    # D79 check: "located in Raipur, Chhattisgarh, as confirmed by teacher's fact" with "the teacher gave you"
    return (" True facts about this class; when the question is about them, state them as plain facts, without "
            "saying where they came from: " + " ".join(given)) if given else ""


def system_for(context: dict | None, facts=()) -> str:
    if is_document(context) and (context or {}).get("region"):       # D74: a part of the page the teacher selected
        base = SYSTEM_DOCUMENT + SYSTEM_REGION
    elif (context or {}).get("source") == "voice":                     # D75 V2: the typed text
        base = SYSTEM_DOCUMENT + SYSTEM_TYPED
    else:
        base = SYSTEM_DOCUMENT if is_document(context) else SYSTEM
    return base + facts_text(facts)                                   # D79


def task_for(action: str, context: dict | None = None) -> str:
    """The task of one request (D61): the action on writing or on a document page; ASK with its typed question."""
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    task = (DOCUMENT_ACTIONS if is_printed(context) else ACTIONS)[action]
    if action != "ask":
        return task
    question = " ".join(str((context or {}).get("question", "")).split())
    if not question:
        raise ValueError("ASK needs a question")
    return task.format(question=question)


def legible(text: str) -> bool:
    """At least two letters or digits outside the [?] marks the model writes for what it cannot read."""
    return sum(ch.isalnum() for ch in text.replace("[?]", "")) >= 2


def point_lines(text: str) -> str:
    """Each '- ' point of an EXPLORE answer on its own line: the model sometimes runs them together in one line
    (EXPLORE physical run 1: 'databases. - Standardized by ...'), which the panel wrapped into one paragraph."""
    return re.sub(r"[ \t]+-[ \t]+(?=[A-Z0-9])", "\n- ", text)


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
    topic: str = ""                       # EXPLORE only (D54)
    readable: bool | None = None          # EXPLORE only: False = no topic read with confidence; None = not asked
    context: dict = field(default_factory=dict)   # D61: what was asked about (source, page, question); set by the worker

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def answer_from_json(data, **base) -> AIAnswer:
    """The structured answer's JSON object -> AIAnswer (`base`: action, model, ...); raises KeyError / TypeError /
    ValueError when malformed.

    EXPLORE (D54) counts as read only when the model says so, names a topic and transcribed more than [?] marks;
    otherwise its text is replaced by UNREADABLE, so no guessed topic or facts reach the panel."""
    transcription, result = str(data["transcription"]).strip(), str(data["result"]).strip()
    if base["action"] != "explore":
        return AIAnswer(ok=True, transcription=transcription, result=result, **base)
    topic = str(data["topic"]).strip()
    if data["readable"] is True and topic and legible(transcription):
        return AIAnswer(ok=True, transcription=transcription, result=point_lines(result), topic=topic, readable=True,
                        **base)
    return no_topic(transcription, **base)


def no_topic(transcription: str = "", **base) -> AIAnswer:
    """EXPLORE without a topic read with confidence (D54): the fixed note, never the model's text. Also used for
    an EXPLORE answer cut off at the token limit: on scribbles the model repeated '[?]' until the limit
    (dry run 2026-10-25), an answer that is only a few short lines never needs it."""
    return AIAnswer(ok=True, transcription=transcription, result=UNREADABLE, readable=False, **base)


def build_request(cfg: AIConfig, action: str, png: bytes, context: dict | None = None) -> dict:
    """The keyword arguments of `client.beta.messages.create` for one action on one image. Pure."""
    task = task_for(action, context)
    request = {
        "model": cfg.model,
        "max_tokens": cfg.max_tokens,
        "system": system_for(context, getattr(cfg, "facts", ())),     # D79
        "output_config": {"effort": cfg.effort, "format": {"type": "json_schema", "schema": schema_for(action)}},
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                             "data": base64.standard_b64encode(png).decode("ascii")}},
                {"type": "text", "text": f"Task: {task}"},
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
        if action == "explore":
            return no_topic(**base)
        return AIAnswer(ok=False, error="The answer was cut off (max_tokens); try a smaller selection.", **base)
    text = next((b.text for b in getattr(response, "content", []) if getattr(b, "type", "") == "text"), None)
    if text is None:
        return AIAnswer(ok=False, error="Claude returned no text.", **base)
    try:
        return answer_from_json(json.loads(text), **base)
    except (ValueError, KeyError, TypeError):
        return AIAnswer(ok=False, error="Claude's answer could not be read.", **base)


class ClaudeAssistant:
    """`ask(action, png, context)` -> AIAnswer. Blocking: run it in the AI worker thread, never in the frame loop."""

    def __init__(self, cfg: AIConfig, client=None):
        self.cfg = cfg
        if client is None:
            import anthropic                              # only when AI is switched on (S4)
            client = anthropic.Anthropic(timeout=cfg.timeout_s, max_retries=1)
        self.client = client

    def ask(self, action: str, png: bytes, context: dict | None = None) -> AIAnswer:
        t0 = time.perf_counter()
        try:
            response = self.client.beta.messages.create(**build_request(self.cfg, action, png, context))
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
