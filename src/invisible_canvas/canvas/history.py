"""Undo/redo of canvas actions (brain.md §5.1, D44). Pure.

Every user action is one command: a drawn stroke, one whole erase gesture (however many strokes it split),
one move, a clear. Commands that were applied live (erase, move) are `record`ed; others are `do`ne.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Canvas, Stroke

LIMIT = 200


class Command:
    name = "command"

    def apply(self, canvas: Canvas) -> None:
        raise NotImplementedError

    def revert(self, canvas: Canvas) -> None:
        raise NotImplementedError


@dataclass
class AddStroke(Command):
    stroke: Stroke
    name = "draw"

    def apply(self, canvas):
        canvas.add(self.stroke)

    def revert(self, canvas):
        canvas.remove(self.stroke.id)


@dataclass
class ReplaceStrokes(Command):
    """`removed` strokes replaced by `added` ones (an erase gesture; a clear has no `added`)."""
    removed: list
    added: list
    name: str = "erase"

    def apply(self, canvas):
        for s in self.removed:
            canvas.remove(s.id)
        for s in self.added:
            canvas.add(s)

    def revert(self, canvas):
        for s in self.added:
            canvas.remove(s.id)
        for s in self.removed:
            canvas.add(s)


@dataclass
class MoveStrokes(Command):
    ids: list
    dx: float
    dy: float
    name = "move"

    def apply(self, canvas):
        canvas.move(self.ids, self.dx, self.dy)

    def revert(self, canvas):
        canvas.move(self.ids, -self.dx, -self.dy)


class History:
    def __init__(self, limit: int = LIMIT):
        self.limit = limit
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    def do(self, command: Command, canvas: Canvas) -> None:
        command.apply(canvas)
        self.record(command)

    def record(self, command: Command) -> None:
        """A command whose effect is already on the canvas."""
        self._undo.append(command)
        del self._undo[:-self.limit]
        self._redo.clear()

    def undo(self, canvas: Canvas) -> Command | None:
        if not self._undo:
            return None
        command = self._undo.pop()
        command.revert(canvas)
        self._redo.append(command)
        return command

    def redo(self, canvas: Canvas) -> Command | None:
        if not self._redo:
            return None
        command = self._redo.pop()
        command.apply(canvas)
        self._undo.append(command)
        return command

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)
