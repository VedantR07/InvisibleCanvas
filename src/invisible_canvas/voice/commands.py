"""Voice writing commands (brain.md §9.19, D75). Pure.

A transcribed utterance is a command only when the WHOLE utterance is the command, said alone between pauses (as
the recognizer writes it: "New line.", "Delete last word."), so a dictated sentence that contains the words ("draw a
new line under the title") stays text. Small recognition slips are allowed (a close match: `MATCH`), never a longer
sentence (at most `MAX_WORDS` words).

A correction (user request 2026-10-31) is the one command at the START of an utterance: "I mean ...", "sorry, I
mean ...", "no, I meant ...", "correction ..." followed by the right text (`correction`): it replaces the last phrase
written. With commands off it is dictation like any other sentence.
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
    "scratch that": "scratch", "delete that": "scratch",                       # the last phrase written
    "remove that": "scratch", "erase that": "scratch",                         # D78: said on the wall
    "splash that": "scratch",                                                  # D78: "scratch that" misheard
    "delete selection": "delete_selection", "delete the selection": "delete_selection",
    "delete selected words": "delete_selection",                              # V2: the words chosen with SELECT
}
# "I mean ..." (user, 2026-10-31): an utterance that starts with one of these replaces the last phrase written
CORRECTIONS = ("sorry i meant", "sorry i mean", "no i meant", "no i mean", "i meant", "i mean", "correction")
MARKS = {"comma": ",", "full_stop": ".", "question_mark": "?", "exclamation_mark": "!"}
MAX_WORDS = 5
MATCH = 0.85           # similarity of the whole utterance to a command (difflib ratio)


def normalise(text: str) -> str:
    return " ".join(re.sub(r"[^a-z ]", " ", text.lower()).split())


def correction(text: str) -> str | None:
    """The new text of a correction ("I mean the capital is New Delhi." -> "The capital is New Delhi."), or None:
    the utterance does not start with a correction, or says nothing after it."""
    words = text.split()
    plain = [normalise(w) for w in words]
    for phrase in CORRECTIONS:
        n = len(phrase.split())
        if [w for w in plain[:n]] == phrase.split():
            rest = " ".join(words[n:]).lstrip(" ,.:;-")
            if not normalise(rest):
                return None
            return rest[0].upper() + rest[1:]
    return None


def match(text: str) -> str | None:
    """The command the whole utterance says, or None (dictation)."""
    said = normalise(text)
    if not said or len(said.split()) > MAX_WORDS:
        return None
    if said in COMMANDS:
        return COMMANDS[said]
    best = max(COMMANDS, key=lambda c: SequenceMatcher(None, said, c).ratio())
    if SequenceMatcher(None, said, best).ratio() >= MATCH:
        return COMMANDS[best]
    # wall test 2026-10-31 04:10: "that" misheard ("Scratch date.", "Scratch back.", "Scratch down.", "Scratch deck.")
    # 5 times out of 21: a short utterance (at most 3 words) that begins with "scratch" is the command
    words = said.split()
    if len(words) <= 3 and SequenceMatcher(None, words[0], "scratch").ratio() >= MATCH:
        return "scratch"
    return None
