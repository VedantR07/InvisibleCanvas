"""Voice writing (brain.md §9.19, D75): the microphone to text, in the background, never in the camera loop.

- The microphone: a sounddevice input stream (16 kHz mono, through Windows' MME, which converts the rate), chosen by
  a part of its name (`[voice] device`; "" = Windows' default input). Its callback runs in PortAudio's own thread
  and only measures and cuts the audio (`Segmenter`).
- Utterances: 30-ms frames whose loudness reaches the gate (`gate_dbfs`) are speech; an utterance begins with a few
  speech frames (and keeps `PRE_ROLL_S` before them), ends after `pause_ms` without speech, and is kept only with
  `MIN_SPEECH_FRAMES` speech frames in it (a cough, a click or a quieter voice in the room is not written; step V0: the
  user's speech -30..-36 dBFS at the mic, other people's -45..-63). A long one is cut at `max_utterance_s`.
- Text: one worker thread transcribes each utterance with faster-whisper (`model`, CPU int8, `threads`; loaded in that
  thread when the listener starts, so the camera loop never waits for it) and queues it with a number, so each
  utterance gives its text once, in order. `poll()` hands the main loop the events (text, status) without waiting.
  D77: with a `fixer` (voice/fix.py), the same thread then has the local AI correct misheard words before the text is
  queued (a command never; a failure leaves it as heard).
- Pause keeps listening (a "resume listening" said while paused must be heard); the controller ignores dictation
  while paused. Errors (no such microphone, the stream stopping: unplugged, the model missing) become a status for
  the panel; nothing raises into the drawing loop. `close()` stops the stream and the worker.
- The camera loop never waits for the microphone: it asks (`request("start" / "stop")`) and a control thread opens
  or closes it (200 ms on this laptop); recognition (faster-whisper) runs in the worker, outside Python's lock.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

RATE = 16000
FRAME = 480                    # 30 ms
PRE_ROLL_S = 0.5               # kept before the frames that begin an utterance (its first sound)
HOLD_DB = 8.0                  # once an utterance began, frames down to the gate - 8 dB keep it going
START_FRAMES = 2               # speech frames in a row that begin an utterance
MIN_SPEECH_FRAMES = 8          # speech frames an utterance needs (240 ms) to be written
# D76 wall test: the jack mic heard nothing for 73 s and the panel only said "Listening". Its level cannot tell why: in a
# silent room the working jack mic also gives about -96 dBFS (V1). So: nothing heard since the microphone opened, for
# this long = say so, with the usual fix; the first utterance ends it for good (the microphone works).
SILENT_AFTER_S = 10.0
SILENT_HINT = "Speaking? Set Headset in the Realtek Audio Console, or press MIC."     # the panel's two lines
STATES = ("off", "loading", "listening", "hearing", "writing", "silent", "unavailable", "error")
logging.getLogger("faster_whisper").setLevel(logging.WARNING)    # wall test 1: a console line per utterance


def dbfs(frame: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64)))) if len(frame) else 0.0
    return 20.0 * np.log10(rms) if rms > 1e-9 else -120.0


class Segmenter:
    """Cuts a stream of 16-kHz mono float samples into utterances at pauses, above a loudness gate. Pure."""

    def __init__(self, gate_dbfs: float = -42.0, pause_ms: int = 700, max_utterance_s: float = 15.0,
                 hold_db: float = HOLD_DB, pre_roll_s: float = PRE_ROLL_S):
        self.gate, self.pause_frames = gate_dbfs, max(int(pause_ms / 30), 1)
        self.hold = gate_dbfs - hold_db                  # once speaking, quieter frames still count as speech
        self.max_frames = int(max_utterance_s / 0.03)
        self.pre = deque(maxlen=int(pre_roll_s / 0.03))
        self.frames: list[np.ndarray] | None = None
        self.speech = self.quiet = self.run = 0
        self.rest = np.zeros(0, np.float32)
        self.level = -120.0
        self.samples = 0                         # samples seen: the time of the stream
        self.heard = False                       # an utterance has begun since this stream opened

    @property
    def speaking(self) -> bool:
        return self.frames is not None

    @property
    def silent(self) -> bool:
        """Nothing heard for SILENT_AFTER_S since the stream opened: a microphone that may not hear the speaker."""
        return not self.heard and self.samples >= SILENT_AFTER_S * RATE

    def feed(self, samples: np.ndarray) -> list[tuple[np.ndarray, float]]:
        """New samples; returns the utterances that ended in them: (audio, the stream time it ended, s)."""
        data = np.concatenate([self.rest, np.asarray(samples, np.float32).reshape(-1)])
        n = len(data) // FRAME * FRAME
        self.rest = data[n:]
        out = []
        for k in range(0, n, FRAME):
            frame = data[k:k + FRAME]
            self.samples += FRAME
            self.level = dbfs(frame)
            loud = self.level >= self.gate
            if self.frames is None:
                self.pre.append(frame)
                self.run = self.run + 1 if loud else 0
                if self.run >= START_FRAMES:
                    self.frames, self.speech, self.quiet = list(self.pre), self.run, 0
                    self.heard = True
                continue
            self.frames.append(frame)
            self.speech += loud
            self.quiet = 0 if self.level >= self.hold else self.quiet + 1
            if self.quiet >= self.pause_frames or len(self.frames) >= self.max_frames:
                if self.speech >= MIN_SPEECH_FRAMES:
                    out.append((np.concatenate(self.frames), self.samples / RATE))
                self.frames, self.run = None, 0
                self.pre.clear()
        return out


class WhisperTranscriber:
    """faster-whisper on the CPU (step V0: `base.en`, int8, 2 threads: 99 % of the user's words, 0.57 s per
    utterance). Loaded on first use, in the worker thread."""

    def __init__(self, model: str, threads: int = 2, root: Path | None = None, vocabulary=()):
        path = Path(model)
        self.path = path if path.is_absolute() or root is None else root / path
        self.threads = threads
        # wall test 1: names and places misheard ("Pratik" -> "Pertik", "Invisible Canvas" -> "a visible catalyst");
        # the words given to Whisper as the text that came before, so it expects them
        words = [str(w).strip() for w in vocabulary if str(w).strip()]
        self.prompt = (", ".join(words) + ".") if words else None
        self._model = None
        self._lock = threading.Lock()
        self.load_s: float | None = None

    def load(self) -> None:
        with self._lock:                                 # once, whichever thread asks first
            if self._model is not None:
                return
            if not self.path.exists():
                raise FileNotFoundError(f"speech model not found: {self.path}")
            t = time.perf_counter()
            from faster_whisper import WhisperModel     # only when voice writing is used
            self._model = WhisperModel(str(self.path), device="cpu", compute_type="int8", cpu_threads=self.threads)
            self.load_s = round(time.perf_counter() - t, 2)

    def preload(self) -> None:
        """Load in the background at the start of `draw`, before VOICE is pressed; a failure is reported then."""
        try:
            self.load()
        except Exception:
            pass

    def __call__(self, audio: np.ndarray) -> str:
        if self._model is None:
            self.load()
        parts, _ = self._model.transcribe(audio, language="en", beam_size=1, vad_filter=False,
                                          condition_on_previous_text=False, without_timestamps=True,
                                          initial_prompt=self.prompt)
        return " ".join(p.text.strip() for p in parts).strip()


def input_devices(sd=None) -> list[tuple[int, str]]:
    """(index, name) of the microphones, through MME (it converts to 16 kHz), without Windows' "Sound Mapper"."""
    if sd is None:
        import sounddevice as sd
    apis = sd.query_hostapis()
    return [(i, d["name"]) for i, d in enumerate(sd.query_devices())
            if d["max_input_channels"] > 0 and apis[d["hostapi"]]["name"] == "MME" and "Sound Mapper" not in d["name"]]


@dataclass
class Status:
    state: str = "off"
    detail: str = ""
    device: str = ""
    level: float = -120.0
    since: float = field(default_factory=time.perf_counter)


class VoiceListener:
    def __init__(self, transcriber, *, gate_dbfs: float = -42.0, pause_ms: int = 700, max_utterance_s: float = 15.0,
                 sd=None, fixer=None):
        self.transcriber = transcriber
        self.fixer = fixer                               # D77: `fixer(text)` -> the corrected sentence or None
        self.gate_dbfs, self.pause_ms, self.max_utterance_s = gate_dbfs, pause_ms, max_utterance_s
        self._sd = sd
        self.status = Status()
        self.events: queue.Queue = queue.Queue()
        self._utterances: queue.Queue = queue.Queue()
        self._stream = None
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._segmenter: Segmenter | None = None
        self._number = 0
        self._started_at = 0.0
        self._control: threading.Thread | None = None   # opens / closes the microphone off the camera loop
        self._control_q: queue.Queue = queue.Queue()
        self.stats = {"utterances": 0, "texts": 0, "empty": 0, "errors": 0, "transcribe_ms": [], "latency_ms": [],
                      "audio_s": 0.0, "fix_ms": [], "fixes": []}

    @property
    def sd(self):
        if self._sd is None:
            import sounddevice as sd
            self._sd = sd
        return self._sd

    def _set(self, state: str, detail: str = "") -> None:
        if (state, detail) != (self.status.state, self.status.detail):
            self.status.state, self.status.detail, self.status.since = state, detail, time.perf_counter()
            self.events.put(("status", state, detail))

    def devices(self) -> list[tuple[int, str]]:
        try:
            return input_devices(self.sd)
        except Exception:
            return []

    def start(self, device: str = "") -> bool:
        """Open the microphone whose name contains `device` ("": Windows' default input) and start the worker."""
        self.stop()
        try:
            found = self.devices()
            index, name = None, "the default microphone"
            if device:
                hit = next(((i, n) for i, n in found if device.lower() in n.lower()), None)
                if hit is None:
                    names = ", ".join(n for _, n in found) or "none"
                    self._set("unavailable", f'no microphone named "{device}" (found: {names})')
                    return False
                index, name = hit
            self._segmenter = Segmenter(self.gate_dbfs, self.pause_ms, self.max_utterance_s)
            self._stream = self.sd.InputStream(device=index, samplerate=RATE, channels=1, dtype="float32",
                                               blocksize=FRAME * 4, callback=self._audio)
            self._stream.start()
        except Exception as e:                           # no device, busy, unplugged: shown, never raised
            self._stream = None
            self._set("unavailable", f"the microphone could not be opened: {e}"[:160])
            return False
        self.status.device = name
        self._stop.clear()
        self._started_at = time.perf_counter()
        self._worker = threading.Thread(target=self._work, name="voice-writer", daemon=True)
        self._worker.start()
        return True

    def _audio(self, indata, frames, time_info, status) -> None:      # PortAudio's thread: measure and cut only
        segmenter = self._segmenter
        if segmenter is None:
            return
        for audio, ended in segmenter.feed(indata[:, 0]):
            self._number += 1
            self._utterances.put((self._number, audio, time.perf_counter()))
        self.status.level = segmenter.level

    def _work(self) -> None:
        try:
            self._set("loading")
            if hasattr(self.transcriber, "load"):
                self.transcriber.load()
        except Exception as e:
            self.stats["errors"] += 1
            self._set("error", f"the speech model could not be loaded: {e}"[:160])
            return
        self._set("listening")
        while not self._stop.is_set():
            stream = self._stream
            if stream is not None and not stream.active:            # the device went away (unplugged)
                self._set("unavailable", "the microphone stopped (unplugged?): press MIC or RESUME to try again")
                return
            try:
                number, audio, ended = self._utterances.get(timeout=0.1)
            except queue.Empty:
                seg = self._segmenter
                if seg is not None and seg.silent:               # no sound at all: say why nothing is written
                    self._set("silent", SILENT_HINT)
                else:
                    self._set("hearing" if seg is not None and seg.speaking else "listening")
                continue
            self._set("writing")
            t = time.perf_counter()
            try:
                text = self.transcriber(audio)
            except Exception as e:
                self.stats["errors"] += 1
                self._set("error", f"recognition failed: {e}"[:160])
                continue
            done = time.perf_counter()
            self.stats["utterances"] += 1
            self.stats["audio_s"] += len(audio) / RATE
            self.stats["transcribe_ms"].append(round((done - t) * 1000, 1))
            if text and self.fixer is not None:              # D77: misheard names and terms, in this thread
                fixed = self.fixer(text)                     # (None: a command, nothing to fix, refused or failed)
                self.stats["fix_ms"].append(round((time.perf_counter() - done) * 1000, 1))
                if fixed:
                    self.stats["fixes"].append({"n": number, "heard": text, "text": fixed})
                    text = fixed
                done = time.perf_counter()
            self.stats["latency_ms"].append(round((done - ended) * 1000, 1))
            if text:
                self.stats["texts"] += 1
                self.events.put(("text", number, text, round((done - ended) * 1000, 1)))
            else:
                self.stats["empty"] += 1
            self._set("listening")

    def poll(self) -> list[tuple]:
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out

    def request(self, kind: str, device: str = "") -> None:
        """"start" (the microphone named `device`) or "stop", without waiting: opening a microphone took 200 ms on
        this laptop, so the camera loop only asks and a control thread does it, in order."""
        if self._control is None:
            self._control = threading.Thread(target=self._run_control, name="voice-control", daemon=True)
            self._control.start()
        self._control_q.put((kind, device))

    def _run_control(self) -> None:
        while True:
            kind, device = self._control_q.get()
            if kind == "start":
                self.start(device)
            elif kind == "stop":
                self.stop()
            if kind == "quit":
                return

    def stop(self) -> None:
        """Close the microphone and end the worker (the model stays loaded for the next start)."""
        self._stop.set()
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        worker, self._worker = self._worker, None
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=5.0)
        while not self._utterances.empty():
            self._utterances.get_nowait()
        self._segmenter = None
        if self.status.state not in ("unavailable", "error"):
            self._set("off")

    def close(self) -> None:
        """At the end of the session: whatever was asked is done, then the microphone is closed (waits)."""
        control, self._control = self._control, None
        if control is not None:
            self._control_q.put(("quit", ""))
            control.join(timeout=5.0)
        self.stop()
