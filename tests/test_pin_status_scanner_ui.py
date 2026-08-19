import io
import sys
import types

from features.status import PinStatusScannerUI


class FakeStatusReport:
    ok = True
    status = "success"
    reason = "ok"
    pin_states = {1: "high", 2: "low"}


class FakeStatusScanner:
    def __init__(self):
        self.calls = []

    def read_pin_states(self, pins, device_index=0):
        self.calls.append((pins, device_index))
        return FakeStatusReport()


class StdIOCapture:
    def __init__(self, input_bytes=b""):
        self._stdin_buf = io.BytesIO(input_bytes)
        self.stdin = types.SimpleNamespace(buffer=self._stdin_buf, closed=False)
        self.stdout = io.StringIO()

    def apply(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", self.stdin)
        monkeypatch.setattr(sys, "stdout", self.stdout)

    def get_stdout(self):
        return self.stdout.getvalue()


def test_status_ui_set_pins_command(monkeypatch):
    sio = StdIOCapture(b"p1-2\n")
    sio.apply(monkeypatch)
    scanner = FakeStatusScanner()
    ui = PinStatusScannerUI(scanner)

    ui.command_line_interface()
    assert ui.pins == [1, 2]
    assert "Pins set to [1, 2]\n" in sio.get_stdout()


def test_status_ui_scan_command(monkeypatch):
    sio = StdIOCapture(b"s")
    sio.apply(monkeypatch)
    scanner = FakeStatusScanner()
    ui = PinStatusScannerUI(scanner)
    ui.pins = [1, 2]

    ui.command_line_interface()

    assert scanner.calls == [([1, 2], 0)]
    out = sio.get_stdout()
    assert "Pin status scan: success\n" in out
    assert "pin 1: high\n" in out
    assert "pin 2: low\n" in out

