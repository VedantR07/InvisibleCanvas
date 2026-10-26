"""The native Windows "Open" dialog (brain.md D60), on the laptop screen, for choosing a document to project.

tkinter (standard library) shows the system dialog; a hidden, topmost root window owns it so it opens in front of
the operator window. It blocks until the user chooses or cancels: the drawing tool lifts the pen first (D58's
`release`) and skips the frames that arrived meanwhile.
"""

from __future__ import annotations

from pathlib import Path

FILE_TYPES = [("Images and PDF", "*.png *.jpg *.jpeg *.pdf"), ("PDF", "*.pdf"), ("Images", "*.png *.jpg *.jpeg"),
              ("All files", "*.*")]


def choose_file(title: str = "Open an image or a PDF to project", initial_dir: Path | None = None) -> Path | None:
    """The chosen file, or None when the dialog was cancelled."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        name = filedialog.askopenfilename(parent=root, title=title, filetypes=FILE_TYPES,
                                          initialdir=str(initial_dir or Path.home()))
    finally:
        root.destroy()
    return Path(name) if name else None
