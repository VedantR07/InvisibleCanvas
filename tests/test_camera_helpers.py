import cv2

from invisible_canvas.camera.directshow import parse_vid_pid
from invisible_canvas.camera.probe import configure, decode_fourcc


def test_parse_vid_pid_from_device_path():
    path = r"\\?\usb#vid_322e&pid_2515&mi_00#6&13fc9cd&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
    assert parse_vid_pid(path) == ("322e", "2515")


def test_parse_vid_pid_is_case_insensitive():
    assert parse_vid_pid(r"\\?\USB#VID_046D&PID_094C#X") == ("046d", "094c")


def test_parse_vid_pid_missing():
    assert parse_vid_pid("") == (None, None)
    assert parse_vid_pid("root#image#0000") == (None, None)


def test_decode_fourcc():
    assert decode_fourcc(cv2.VideoWriter_fourcc(*"MJPG")) == "MJPG"
    assert decode_fourcc(cv2.VideoWriter_fourcc(*"YUY2")) == "YUY2"
    assert decode_fourcc(0) == ""
    assert decode_fourcc(-1) == ""


def test_configure_sets_fourcc_last():
    # DirectShow drops a FOURCC that is followed by a size or fps change.
    class Recorder:
        def __init__(self):
            self.calls = []

        def set(self, prop, value):
            self.calls.append((prop, value))
            return True

    cap = Recorder()
    configure(cap, "MJPG", 1920, 1080, 30)
    assert cap.calls == [
        (cv2.CAP_PROP_FRAME_WIDTH, 1920),
        (cv2.CAP_PROP_FRAME_HEIGHT, 1080),
        (cv2.CAP_PROP_FPS, 30),
        (cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")),
    ]
