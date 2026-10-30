"""Voice writing commands (brain.md §9.19, D75). Pure.

A transcribed utterance is a command only when the WHOLE utterance is the command, said alone between pauses (as
the recognizer writes it: "New line.", "Delete last word."), so a dictated sentence that contains the words ("draw a
new line under the title") stays text. Small recognition slips are allowed (a close match: `MATCH`), never a longer
sentence (at most `MAX_WORDS` words).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

COMMANDS = {
    "new line": "new_line", "next line": "new_line",
    "new paragraph": "new_paragraph", "next paragraph": "new_paragraph",
    "delete last word": "delete_word", "delete the last word": "delete_word",
    "delete last sentence": "delete_sentence", "delete the last sentence": "delete_sentence",
    "undo": "undo", "redo": "redo",
    "clear current line": "clear_line", "clear the current line": "clear_line", "clear line": "clear_line",
    "stop listening": "pause", "pause listening": "pause",
    "resume listening": "resume", "start listening": "resume", "continue listening": "resume",
    "comma": "comma", "full stop": "full_stop", "period": "full_stop",
    "question mark": "question_mark", "exclamation mark": "exclamation_mark",
}
MARKS = {"comma": ",", "full_stop": ".", "question_mark": "?", "exclamation_mark": "!"}
MAX_WORDS = 5
MATCH = 0.85           # similarity of the whole utterance to a command (difflib ratio)


def normalise(text: str) -> str:
    return " ".join(re.sub(r"[^a-z ]", " ", text.lower()).split())


def match(text: str) -> str | None:
    """The command the whole utterance says, or None (dictation)."""
    said = normalise(text)
    if not said or len(said.split()) > MAX_WORDS:
        return None
    if said in COMMANDS:
        return COMMANDS[said]
    best = max(COMMANDS, key=lambda c: SequenceMatcher(None, said, c).ratio())
    return COMMANDS[best] if SequenceMatcher(None, said, best).ratio() >= MATCH else None
