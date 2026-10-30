"""Voice writing (brain.md §9.19, D75): the typed text and its layout, the commands, cutting speech at pauses above the
loudness gate, the background listener (a fake microphone and recognizer), the controller (panel, commands, pause,
undo, cancel, pages, documents) and the drawing. Real speech recognition is measured on the wall, not here."""

import threading
import time

import numpy as np
import pytest

from invisible_canvas.canvas.board import Board
from invisible_canvas.canvas.model import Canvas, Stroke
from invisible_canvas.canvas.panel import VoicePanel
from invisible_canvas.canvas.reference import Reference
from invisible_canvas.canvas.render import TOOL_SELECTED, CanvasRenderer
from invisible_canvas.canvas.toolbar import Toolbar
from invisible_canvas.canvas.voice_text import NEW_LINE, NEW_PARAGRAPH, VoiceLayout, VoiceText, render
from invisible_canvas.interaction.drawing import DrawingController
from invisible_canvas.interaction.engine import HOVER, STROKE_END, STROKE_POINT, STROKE_START, Event
from invisible_canvas.voice.commands import match
from invisible_canvas.voice.listener import RATE, Segmenter, VoiceListener, dbfs

SIZE = (1280, 720)
AREA = (40, 60, 952, 632)
LONG = ("Artificial intelligence is changing the way students learn and understand difficult concepts. "
        "Photosynthesis is the process by which plants make their own food using sunlight. The water cycle "
        "includes evaporation, condensation and precipitation. Today we will learn about the solar system and its "
        "eight planets. Please open your notebooks and write the date at the top of the page.")


# -- the text ------------------------------------------------------------------------------------------------------

def test_phrases_are_written_after_each_other_as_words_with_their_own_punctuation():
    t = VoiceText()
    assert t.write("  Good morning everyone.  ") and t.write("Let us begin today's lesson.")
    assert t.tokens == ["Good", "morning", "everyone.", "Let", "us", "begin", "today's", "lesson."]
    assert not t.write("   ") and t.version == 2
    assert t.punctuate(",") and t.tokens[-1] == "lesson,"                   # replaces the full stop
    assert t.punctuate("?") and t.tokens[-1] == "lesson?"


def test_new_line_new_paragraph_and_the_deletes():
    t = VoiceText()
    assert not t.new_line() and not t.delete_last_word()                     # nothing written yet
    t.write("The water cycle.")
    t.new_line()
    t.write("It includes evaporation. And condensation")
    assert t.tokens[3] == NEW_LINE
    t.new_paragraph()
    assert t.tokens[-1] == NEW_PARAGRAPH
    assert t.delete_last_word() and t.words[-1] == "And"                    # the word and the break after it
    assert t.delete_last_sentence() and t.words == ["The", "water", "cycle.", "It", "includes", "evaporation."]
    assert t.delete_last_sentence() and t.tokens == ["The", "water", "cycle.", NEW_LINE]
    t.write("Clouds form")
    assert t.clear_line() and t.tokens == ["The", "water", "cycle.", NEW_LINE]
    assert not t.clear_line()                                                # the line is empty


def test_every_change_is_one_undo_step_and_the_text_is_saved_with_the_board():
    t = VoiceText()
    t.write("One two.")
    t.new_line()
    t.write("Three.")
    assert t.undo() and t.tokens == ["One", "two.", NEW_LINE]
    assert t.undo() and t.undo() and t.tokens == [] and not t.undo()
    assert t.redo() and t.tokens == ["One", "two."]
    t.write("Four.")
    assert not t.redo()                                                      # a new change ends the redo
    board = Board(SIZE)
    board.page.voice = t
    board.add_page()
    board.page.voice = VoiceText(["Page", "two."])
    data = board.to_dict()
    back = Board.from_dict(data)
    assert [p.voice.tokens for p in back.pages] == [["One", "two.", "Four."], ["Page", "two."]]
    old = {k: v for k, v in data.items() if k != "voice"}                     # a board saved before D75
    assert all(p.voice is None for p in Board.from_dict(old).pages)
    assert "voice" not in Board(SIZE).to_dict()


# -- the layout ----------------------------------------------------------------------------------------------------

def test_lines_wrap_at_whole_words_inside_the_area_with_one_line_height():
    layout = VoiceLayout(AREA)
    t = VoiceText()
    t.write(LONG)
    lines = layout.lines(t.tokens)
    assert len(lines) > 3
    for k, line in enumerate(lines):
        dx, last, _ = line.words[-1]
        assert dx + layout._w(last) <= layout.width                          # inside the area
        if k + 1 < len(lines) and lines[k + 1].words:                       # the next word did not fit here
            nxt = lines[k + 1].words[0][1]
            assert dx + layout._w(last) + layout.space + layout._w(nxt) > layout.width
    assert [p for line in lines for _, p, _ in line.words] == t.words        # every word whole, in order
    boxes = layout.word_boxes(t.tokens)
    assert len({b[3] - b[1] for _, b in boxes}) == 1                         # one line height


def test_only_a_word_wider_than_a_line_is_split():
    layout = VoiceLayout((0, 0, 260, 400), size=30)
    word = "Pneumonoultramicroscopicsilicovolcanoconiosis"
    pieces = [p for line in layout.lines(["A", word, "end."]) for _, p, _ in line.words]
    assert pieces[0] == "A" and pieces[-1] == "end." and "".join(pieces[1:-1]) == word and len(pieces) > 3


def test_the_view_follows_the_end_and_scrolls_back_without_drawing_outside_the_area():
    layout = VoiceLayout(AREA)
    t = VoiceText()
    for _ in range(4):
        t.write(LONG)
        t.new_paragraph()
    lines = layout.lines(t.tokens)
    assert len(lines) > layout.rows
    first, shown = layout.visible(lines)
    assert first + len(shown) == len(lines) and len(shown) == layout.rows   # the end in view
    assert layout.visible(lines, scroll=3)[0] == first - 3
    img = np.full((720, 1280, 3), 255, np.uint8)
    render(img, t, layout, active=True)
    x0, y0, x1, y1 = AREA
    outside = img.copy()
    outside[y0 - 2:y1 + 3, x0 - 2:x1 + 3] = 255
    assert (outside == 255).all()                                             # nothing outside the area
    assert (img[y0 + 20:y1 - 20, x0 + 20:x1 - 20] < 120).any()               # the text inside it


# -- commands ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("said, command", [
    ("New line.", "new_line"), ("new paragraph", "new_paragraph"), ("Delete last word.", "delete_word"),
    ("Delete the last sentence.", "delete_sentence"), ("Undo.", "undo"), ("Clear current line.", "clear_line"),
    ("Stop listening.", "pause"), ("Resume listening!", "resume"), ("Full stop.", "full_stop"),
    ("Comma.", "comma"), ("New lines.", "new_line"),
    ("Draw a new line under the title.", None), ("And do.", None), ("Photosynthesis is the process.", None),
    ("New line please and then the next one.", None), ("", None)])
def test_a_command_only_when_the_whole_utterance_is_one(said, command):
    assert match(said) == command


# -- speech cut at pauses ------------------------------------------------------------------------------------------

def speech(seconds, level_db, rng):
    return rng.normal(0, 10 ** (level_db / 20), int(seconds * RATE)).astype(np.float32)


def test_utterances_end_at_pauses_and_quieter_voices_and_clicks_are_not_written():
    rng = np.random.default_rng(1)
    audio = np.concatenate([speech(0.5, -90, rng), speech(1.5, -30, rng), speech(1.0, -90, rng),
                            speech(1.0, -32, rng), speech(1.0, -90, rng),
                            speech(1.5, -55, rng), speech(1.0, -90, rng),   # someone else in the room
                            speech(0.06, -25, rng), speech(1.0, -90, rng)])  # a click
    seg = Segmenter(gate_dbfs=-42, pause_ms=700)
    out = []
    for k in range(0, len(audio), 1920):                                     # as the microphone delivers it
        out += seg.feed(audio[k:k + 1920])
    assert len(out) == 2
    lengths = [len(a) / RATE for a, _ in out]
    assert 2.2 < lengths[0] < 2.8 and 1.7 < lengths[1] < 2.3                 # speech + pre-roll + the pause
    assert abs(dbfs(speech(1, -30, rng)) + 30) < 0.5


def test_a_quieter_end_of_a_sentence_stays_in_it_but_the_same_level_alone_starts_nothing():
    # V1 on the user's reading: "...their own food using sunlight" lost "using sunlight" (the voice trailing off below
    # the gate), 92 % of the words; with the 8-dB hold 98 %
    rng = np.random.default_rng(5)
    seg = Segmenter(gate_dbfs=-42, pause_ms=700)
    out = seg.feed(np.concatenate([speech(1.0, -32, rng), speech(0.8, -47, rng), speech(1.0, -90, rng),
                                   speech(1.0, -47, rng), speech(1.0, -90, rng)]))
    assert len(out) == 1 and 2.3 < len(out[0][0]) / RATE < 2.7              # one utterance, its quiet end in it
    # (1.0 s + the quiet 0.8 s + the 0.7-s pause; without the hold it ended after 1.7 s)


def test_a_long_utterance_is_cut():
    rng = np.random.default_rng(2)
    seg = Segmenter(gate_dbfs=-42, pause_ms=700, max_utterance_s=3.0)
    out = seg.feed(speech(7.0, -30, rng))
    assert len(out) == 2 and all(len(a) / RATE <= 3.05 for a, _ in out)


# -- the listener (a fake microphone and recognizer) -----------------------------------------------------------------

class FakeStream:
    def __init__(self, callback):
        self.callback, self.active, self.closed = callback, False, False

    def start(self):
        self.active = True

    def stop(self):
        self.active = False

    def close(self):
        self.closed = True

    def feed(self, audio):
        for k in range(0, len(audio), 1920):
            self.callback(audio[k:k + 1920].reshape(-1, 1), 1920, None, None)


class FakeSD:
    def __init__(self, names=("Microphone (Realtek(R) Audio)", "Microphone Array (Intel Smart Sound)"), fail=None):
        self.names, self.fail, self.opened, self.streams = names, fail, [], []

    def query_hostapis(self):
        return [{"name": "MME"}, {"name": "Windows WASAPI"}]

    def query_devices(self):
        return ([{"name": "Microsoft Sound Mapper - Input", "max_input_channels": 2, "hostapi": 0}]
                + [{"name": n, "max_input_channels": 2, "hostapi": 0} for n in self.names]
                + [{"name": "Speakers (Realtek(R) Audio)", "max_input_channels": 0, "hostapi": 0},
                   {"name": self.names[0], "max_input_channels": 2, "hostapi": 1}])

    def InputStream(self, device, samplerate, channels, dtype, blocksize, callback):
        if self.fail:
            raise RuntimeError(self.fail)
        assert (samplerate, channels, dtype) == (RATE, 1, "float32")
        self.opened.append(device)
        self.streams.append(FakeStream(callback))
        return self.streams[-1]


class FakeWhisper:
    def __init__(self, delay=0.0, fail_load=False):
        self.delay, self.fail_load, self.calls = delay, fail_load, []

    def load(self):
        if self.fail_load:
            raise FileNotFoundError("speech model not found: models/whisper/base.en")

    def __call__(self, audio):
        self.calls.append(threading.current_thread().name)
        time.sleep(self.delay)
        return f"phrase of {len(audio) / RATE:.1f} seconds."


def wait_for(listener, kind, n=1, timeout=5.0):
    got, t = [], time.perf_counter()
    while time.perf_counter() - t < timeout:
        got += listener.poll()
        if sum(e[0] == kind for e in got) >= n:
            return got
        time.sleep(0.02)
    return got


def test_the_listener_opens_the_named_microphone_and_gives_each_utterance_once_in_order():
    sd, whisper = FakeSD(), FakeWhisper()
    listener = VoiceListener(whisper, sd=sd)
    assert [n for _, n in listener.devices()] == list(sd.names)               # MME, no Sound Mapper, no speakers
    assert listener.start("realtek") and sd.opened == [1] and listener.status.device == sd.names[0]
    assert wait_for(listener, "status") and listener.status.state in ("loading", "listening")
    rng = np.random.default_rng(3)
    sd.streams[0].feed(np.concatenate([speech(1.0, -30, rng), speech(1.0, -90, rng), speech(0.8, -31, rng),
                                       speech(1.0, -90, rng)]))
    events = wait_for(listener, "text", 2)
    texts = [e for e in events if e[0] == "text"]
    assert [e[1] for e in texts] == [1, 2] and all(e[2].startswith("phrase of") for e in texts)
    assert all(name == "voice-writer" for name in whisper.calls)            # recognition off the caller's thread
    assert listener.stats["texts"] == 2 and len(listener.stats["latency_ms"]) == 2
    listener.close()
    assert sd.streams[0].closed and listener._worker is None and listener.status.state == "off"


def test_recognition_never_holds_up_the_audio_or_the_caller():
    sd, whisper = FakeSD(), FakeWhisper(delay=0.5)
    listener = VoiceListener(whisper, sd=sd)
    listener.start("Realtek")
    rng = np.random.default_rng(4)
    t = time.perf_counter()
    sd.streams[0].feed(np.concatenate([speech(1.0, -30, rng), speech(1.0, -90, rng)]))
    feed_s = time.perf_counter() - t
    t = time.perf_counter()
    listener.poll()
    poll_s = time.perf_counter() - t
    assert feed_s < 0.2 and poll_s < 0.01                                    # the recognizer takes 0.5 s meanwhile
    assert any(e[0] == "text" for e in wait_for(listener, "text"))
    listener.close()


def test_asking_to_open_or_close_the_microphone_never_waits():
    class SlowSD(FakeSD):
        def InputStream(self, *args, **kwargs):
            time.sleep(0.3)                                                  # opening took 200 ms on the laptop
            return super().InputStream(*args, **kwargs)

    sd = SlowSD()
    listener = VoiceListener(FakeWhisper(), sd=sd)
    t = time.perf_counter()
    listener.request("start", "Realtek")
    listener.request("stop")
    listener.request("start", "Intel")
    assert time.perf_counter() - t < 0.05                                    # the camera loop goes on
    t = time.perf_counter()
    while len(sd.streams) < 2 and time.perf_counter() - t < 3:
        time.sleep(0.02)
    assert sd.opened == [1, 2] and sd.streams[0].closed                      # in order: opened, closed, the other
    listener.close()
    assert sd.streams[1].closed and listener._control is None


def test_a_missing_microphone_or_model_and_an_unplugged_one_are_a_status_not_a_crash():
    listener = VoiceListener(FakeWhisper(), sd=FakeSD())
    assert not listener.start("Blue Yeti")
    assert listener.status.state == "unavailable" and "Realtek" in listener.status.detail
    busy = VoiceListener(FakeWhisper(), sd=FakeSD(fail="Device unavailable"))
    assert not busy.start("Realtek") and "could not be opened" in busy.status.detail
    broken = VoiceListener(FakeWhisper(fail_load=True), sd=FakeSD())
    broken.start("Realtek")
    wait_for(broken, "status", 2)
    assert broken.status.state == "error" and "model" in broken.status.detail
    broken.close()
    sd = FakeSD()
    unplugged = VoiceListener(FakeWhisper(), sd=sd)
    unplugged.start("Realtek")
    wait_for(unplugged, "status")
    sd.streams[0].active = False                                             # the device went away
    t = time.perf_counter()
    while unplugged.status.state != "unavailable" and time.perf_counter() - t < 3:
        time.sleep(0.02)
    assert unplugged.status.state == "unavailable" and "unplugged" in unplugged.status.detail
    unplugged.close()


# -- the controller ------------------------------------------------------------------------------------------------

def voice_controller():
    return DrawingController(Canvas(SIZE), Toolbar(SIZE, ai=True, voice=True), voice_layout=VoiceLayout(AREA))


def say(ctl, *phrases):
    for text in phrases:
        ctl._test_n = getattr(ctl, "_test_n", 0) + 1
        ctl.voice_result(ctl._test_n, text, 500.0)


def stroke(ctl, points):
    ctl.handle([Event(STROKE_START, 0.0, points[0])] + [Event(STROKE_POINT, 0.0, p) for p in points[1:]]
               + [Event(STROKE_END, 0.0)])


def test_voice_opens_its_panel_listens_and_writes_each_utterance_once():
    ctl = voice_controller()
    ctl.press("ai")
    ctl.press("voice")
    assert ctl.voice_open and ctl.panel is None and ctl.take_voice_requests() == ["start"]   # one panel at a time
    say(ctl, "Photosynthesis is the process by which plants make their own food.")
    ctl.voice_result(1, "Photosynthesis is the process by which plants make their own food.")   # the same again
    assert ctl.page_voice().words[0] == "Photosynthesis" and len(ctl.page_voice().words) == 11
    assert ctl.log["voice:duplicates"] == 1 and ctl.voice_log[0]["latency_ms"] == 500.0
    ctl.press("voice")
    assert not ctl.voice_open and ctl.take_voice_requests() == ["stop"]
    say(ctl, "This is not written.")                                          # a late text after closing
    assert len(ctl.page_voice().words) == 11 and ctl.voice_log[-1]["ignored"] == "closed"


def test_commands_pause_and_the_commands_switch():
    ctl = voice_controller()
    ctl.press("voice")
    say(ctl, "Good morning everyone.", "New line.", "Let us begin.", "Delete last word.")
    assert ctl.page_voice().tokens == ["Good", "morning", "everyone.", NEW_LINE, "Let", "us"]
    say(ctl, "Stop listening.", "This is said while paused.", "Delete last word.")
    assert ctl.voice_paused and ctl.page_voice().tokens[-1] == "us"        # dictation and edits ignored
    say(ctl, "Resume listening.", "begin", "Full stop.")
    assert not ctl.voice_paused and ctl.page_voice().tokens[-1] == "begin."
    ctl.press("voice:commands")
    say(ctl, "New line.")
    assert ctl.page_voice().tokens[-2:] == ["New", "line."] and not ctl.voice_commands
    ctl.press("voice:pause")
    assert ctl.voice_paused and ctl.voice_label("voice:pause") == "RESUME"


def test_clear_current_line_must_be_said_twice():
    ctl = voice_controller()
    ctl.press("voice")
    say(ctl, "First line.", "New line.", "Second line is long")
    ctl.now = 10.0
    say(ctl, "Clear current line.")
    assert ctl.page_voice().words[-1] == "long" and "again" in ctl.notice["text"]
    ctl.now = 20.0                                                            # too late: asks again
    say(ctl, "Clear current line.")
    assert ctl.page_voice().words[-1] == "long"
    ctl.now = 22.0
    say(ctl, "Clear current line.")
    assert ctl.page_voice().tokens == ["First", "line.", NEW_LINE]


def test_undo_redo_and_clear_act_on_the_typed_text_while_voice_is_on_and_on_ink_after():
    ctl = voice_controller()
    stroke(ctl, [(300.0, 500.0), (400.0, 500.0)])
    ctl.press("voice")
    say(ctl, "One.", "Two.")
    ctl.press("undo")
    assert ctl.page_voice().words == ["One."] and len(ctl.canvas.strokes) == 1
    ctl.press("redo")
    assert ctl.page_voice().words == ["One.", "Two."]
    say(ctl, "Undo.")
    assert ctl.page_voice().words == ["One."]
    ctl.press("clear")
    assert ctl.page_voice().words == [] and len(ctl.canvas.strokes) == 1
    ctl.press("undo")
    assert ctl.page_voice().words == ["One."]
    ctl.press("voice")
    ctl.press("undo")
    assert ctl.canvas.strokes == {} and ctl.page_voice().words == ["One."]   # voice off: the ink


def test_cancel_puts_back_what_the_pages_had():
    ctl = voice_controller()
    ctl.press("voice")
    say(ctl, "Kept from before.")
    ctl.press("voice:done")
    ctl.press("voice")
    say(ctl, "Written now.")
    ctl.press("pages")                                                        # PAGES closes voice writing
    assert not ctl.voice_open
    ctl.press("pages")
    ctl.press("voice")
    say(ctl, "Again.", "New paragraph.")
    ctl.press("voice:cancel")
    assert not ctl.voice_open and ctl.page_voice().words == ["Kept", "from", "before.", "Written", "now."]


def test_each_page_keeps_its_own_text_and_a_document_ends_voice_writing(tmp_path):
    ctl = voice_controller()
    ctl.press("voice")
    say(ctl, "Page one text.")
    ctl.board.add_page()
    ctl._leave_layer()
    say(ctl, "Page two text.")
    assert [p.voice.words for p in ctl.board.pages] == [["Page", "one", "text."], ["Page", "two", "text."]]
    ctl.board.previous()
    assert ctl.page_voice().words[1] == "one"
    import cv2
    path = tmp_path / "p.png"
    cv2.imencode(".png", np.full((100, 100, 3), 200, np.uint8))[1].tofile(str(path))
    ctl.set_reference(Reference.open(path))
    assert not ctl.voice_open and "whiteboard" in ctl.notice["text"]
    ctl.press("voice")
    assert not ctl.voice_open and ctl.log["voice:refused_doc"] == 1
    ctl.press("board:view") if ctl.board_open else None
    ctl.view = "board"
    ctl.press("lines")
    ctl.press("voice")                                                         # LINES gives way to voice writing
    assert ctl.voice_open and ctl.tool == "pen"
    ctl.press("lines")
    assert not ctl.voice_open and ctl.tool == "lines"


def test_the_panel_is_pressed_by_holding_and_never_drawn_on():
    ctl = voice_controller()
    ctl.press("voice")
    b = ctl.voice_panel.button("voice:pause")
    ctl.update_pointer(0.0, b.centre)
    ctl.update_pointer(1.05, b.centre)
    assert ctl.voice_paused
    stroke(ctl, [b.centre, (500.0, 300.0)])
    assert ctl.canvas.strokes == {} and ctl.log["strokes_refused_on_panel"] == 1
    x0, y0, x1, y1 = VoicePanel(SIZE).rect
    assert x0 > AREA[2] and y1 < Toolbar(SIZE).top                            # beside the writing area


def test_the_panel_and_the_text_are_drawn_and_the_text_stays_after_voice_writing():
    ctl = voice_controller()
    ctl.press("voice")
    ctl.voice_status_update("listening", device="Microphone (Realtek(R) Audio)", level=-33.0)
    say(ctl, LONG)
    renderer = CanvasRenderer(SIZE)
    img = renderer.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    x0, y0, x1, y1 = ctl.voice_panel.rect
    assert (img[y0 + 5:y1 - 5, x0 + 5:x1 - 5] < 200).any()                     # the panel's text and buttons
    assert tuple(int(v) for v in img[AREA[1], (AREA[0] + AREA[2]) // 2]) != (255, 255, 255)   # the frame
    vb = ctl.toolbar.button("voice").rect
    assert tuple(int(v) for v in img[(vb[1] + vb[3]) // 2, vb[0] + 1]) == TOOL_SELECTED      # VOICE outlined
    text_area = img[AREA[1] + 20:AREA[3] - 20, AREA[0] + 20:AREA[2] - 20]
    ctl.press("voice")
    img = renderer.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    changed = (img[AREA[1] + 20:AREA[3] - 20, AREA[0] + 20:AREA[2] - 20] != text_area).any(axis=2)
    assert (text_area < 120).any() and changed.sum() < 120          # the text still there; only the writing mark gone
    assert (img[y0 + 5:y1 - 5, x0 + 5:x1 - 5] == 255).all()                   # no panel
    assert tuple(int(v) for v in img[AREA[1], (AREA[0] + AREA[2]) // 2]) == (255, 255, 255)   # no frame
    ink = Stroke(1, (25, 25, 25), 8.0, [(100.0, 100.0), (200.0, 100.0)])
    ctl.canvas.add(ink)
    img = renderer.render(ctl.canvas, ctl, ctl.toolbar, mode=HOVER, cursor=None)
    assert (img[100, 150] < 60).all()                                          # the ink over the text
