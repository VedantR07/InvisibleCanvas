"""Voice writing (brain.md D77): the local AI corrects the words the recognizer misheard in a dictated sentence.

faster-whisper writes an unfamiliar name or term the way it sounds ("Rachi", "Bhupavneeshwar", "touchmail"); the local
model (`[ai] local_model`, through Ollama's local HTTP API: free, offline) reads the whole sentence and fixes the words
that do not fit it ("Ranchi", "Bhubaneswar", "Taj Mahal"). Measured on the user's 15 recorded sentences: 86.9 -> 93.5 %
of the words, 0.37 s a sentence, no correct word changed (§13.2).

It runs in the voice worker thread, after the recognizer, never in the camera loop. A command is never sent; an answer
that is not the same sentence with a few words fixed (`accept`) is not used, and every failure (Ollama not running, busy
past the timeout, an unreadable answer) leaves the sentence as heard. Standard library only.
"""

from __future__ import annotations

import difflib
import json
import urllib.request

from ..config import AIConfig
from .commands import correction, match

FIX_TIMEOUT_S = 3.0        # a busy model (an AI panel answer) past this: the sentence as heard
FIX_MAX_TOKENS = 200       # one sentence back (a long utterance ~60 tokens)
KEEP_ALIVE = "30m"
MIN_SIMILARITY = 0.6       # of the characters: "Bhupavneeshwar and Vishakapatna" -> "Bhubaneswar and Visakhapatnam" 0.82
SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
# D78 (wall test 16:08: "Should we done this project" -> "do"): names and terms only, never the grammar
SYSTEM = ("You correct speech-recognition text from a teacher speaking English in India. Fix only words that were "
          "clearly misheard: misspelled names of people, places or organisations, or science and technical terms, using "
          "the rest of the sentence as context. Never correct grammar, tense or word choice: the teacher's own words "
          "stay as said. Do not rephrase, add, remove or reorder words; keep the punctuation. If nothing is clearly "
          "wrong, return the text unchanged.")


def system_for(vocabulary=()) -> str:
    words = [str(w).strip() for w in vocabulary if str(w).strip()]
    return SYSTEM + (f" Words the teacher often uses: {', '.join(words)}." if words else "")


def build_fix_request(model: str, text: str, vocabulary=()) -> dict:
    """The JSON body of Ollama's /api/chat for one sentence. Pure."""
    return {"model": model, "stream": False, "format": SCHEMA, "keep_alive": KEEP_ALIVE,
            "options": {"temperature": 0, "num_predict": FIX_MAX_TOKENS},
            "messages": [{"role": "system", "content": system_for(vocabulary)}, {"role": "user", "content": text}]}


# D78: the model "fixed" the teacher's grammar although told not to ("Should we done this project" -> "do"); a change
# that only swaps, adds or drops these words is not a misheard name or term, so it is not used
GRAMMAR = frozenset(
    "a an the this that these those i you he she it we they me him her us them my your his its our their and or but "
    "so if is are was were be been being am do does did done doing have has had having will would can could shall "
    "should may might must go goes went gone come came make made get got say said see saw seen take took taken give "
    "gave given know knew known think thought to of in on at for with from by as not no".split())


def _words(text: str) -> list[str]:
    return [w for w in (w.strip(".,;:!?\"'()").lower() for w in text.split()) if w]


def accept(heard: str, fixed: str) -> bool:
    """Whether a correction may replace what was heard: the same sentence with a few words fixed. Not a command, the
    same kind of utterance ("I mean ..." stays a correction), about as many words, mostly the same letters, and no
    change that is only grammar words (D78). Pure."""
    fixed = fixed.strip()
    if not fixed or match(fixed) is not None or (correction(heard) is None) != (correction(fixed) is None):
        return False
    h, f = heard.split(), fixed.split()
    if abs(len(h) - len(f)) > 2 + len(h) // 4:
        return False
    hw, fw = _words(heard), _words(fixed)
    for op, i0, i1, j0, j1 in difflib.SequenceMatcher(None, hw, fw).get_opcodes():
        if op != "equal" and set(hw[i0:i1] + fw[j0:j1]) <= GRAMMAR:
            return False
    return difflib.SequenceMatcher(None, heard.lower(), fixed.lower()).ratio() >= MIN_SIMILARITY


class VoiceFixer:
    """`fixer(text)` -> the corrected sentence, or None (nothing to fix, refused, or failed). Blocking: call it in the
    voice worker thread."""

    def __init__(self, cfg: AIConfig, vocabulary=(), timeout_s: float = FIX_TIMEOUT_S, opener=urllib.request.urlopen):
        self.model, self.url = cfg.local_model, cfg.local_url.rstrip("/") + "/api/chat"
        self.vocabulary, self.timeout_s, self._open = list(vocabulary), timeout_s, opener

    def __call__(self, text: str) -> str | None:
        if not text.strip() or match(text) is not None:          # a command is never sent
            return None
        request = urllib.request.Request(self.url, method="POST", headers={"Content-Type": "application/json"},
                                         data=json.dumps(build_fix_request(self.model, text, self.vocabulary)).encode())
        try:
            with self._open(request, timeout=self.timeout_s) as response:
                data = json.loads(response.read().decode("utf-8"))
            fixed = str(json.loads(data["message"]["content"])["text"]).strip()
        except Exception:                                         # not running, busy, unreadable: as heard
            return None
        return fixed if fixed != text.strip() and accept(text, fixed) else None
