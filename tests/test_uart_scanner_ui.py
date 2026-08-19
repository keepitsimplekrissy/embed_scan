import io
import sys
import types

from features.uart import UartScannerUI


class FakeUartReport:
    ok = True
    status = "success"
    reason = "ok"
    rx_pin = 3
    flow_control_pin = 5
    baud_rate = 115200
    data_bits = 8
    stop_bits = 1
    parity = "none"
    valid_frames = 4
    decoded_text = "TEST"


class FakeUartScanner:
    def __init__(self):
        self.calls = []

    def capture_and_analyze(self, **kwargs):
        self.calls.append(kwargs)
        return FakeUartReport()


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


def test_uart_ui_setup_from_args():
    scanner = FakeUartScanner()
    ui = UartScannerUI(scanner)

    ui.setup(
        {
            "device_index": 1,
            "pins": "0-2,5",
            "seconds": 2.0,
            "sample_rate": 4_000_000,
            "baud_rates": "9600,115200",
        }
    )

    assert ui.device_index == 1
    assert ui.pins == [0, 1, 2, 5]
    assert ui.capture_seconds == 2.0
    assert ui.sample_rate_hz == 4_000_000
    assert ui.baud_rates == [9600, 115200]


def test_uart_ui_set_pins_command(monkeypatch):
    sio = StdIOCapture(b"p0-2,5\n")
    sio.apply(monkeypatch)
    scanner = FakeUartScanner()
    ui = UartScannerUI(scanner)

    ui.command_line_interface()

    assert ui.pins == [0, 1, 2, 5]
    assert "UART pins set to [0, 1, 2, 5]\n" in sio.get_stdout()


def test_uart_ui_scan_command(monkeypatch):
    sio = StdIOCapture(b"s")
    sio.apply(monkeypatch)
    scanner = FakeUartScanner()
    ui = UartScannerUI(scanner)
    ui.pins = [2, 3, 5]
    ui.capture_seconds = 1.5
    ui.sample_rate_hz = 8_000_000
    ui.baud_rates = [9600, 115200]

    ui.command_line_interface()

    assert len(scanner.calls) == 1
    call = scanner.calls[0]
    assert call["pins"] == [2, 3, 5]
    assert call["duration_seconds"] == 1.5
    assert call["sample_rate_hz"] == 8_000_000
    assert call["device_index"] == 0
    assert call["baud_rates"] == (9600, 115200)

    out = sio.get_stdout()
    assert "Starting UART scan with settings:\n" in out
    assert "device index: 0\n" in out
    assert "pins: [2, 3, 5]\n" in out
    assert "capture seconds: 1.5\n" in out
    assert "sample rate hz: 8000000\n" in out
    assert "baud rates: [9600, 115200]\n" in out
    assert "UART scan status: success\n" in out
    assert "rx pin: 3\n" in out


def test_uart_ui_ignores_newline_command(monkeypatch):
    sio = StdIOCapture(b"\n")
    sio.apply(monkeypatch)
    scanner = FakeUartScanner()
    ui = UartScannerUI(scanner)

    ui.command_line_interface()
    assert "Unknown command:" not in sio.get_stdout()


def test_uart_ui_set_time_skips_leading_newline(monkeypatch):
    sio = StdIOCapture(b"t\n2.5\n")
    sio.apply(monkeypatch)
    scanner = FakeUartScanner()
    ui = UartScannerUI(scanner)

    ui.command_line_interface()
    assert ui.capture_seconds == 2.5
