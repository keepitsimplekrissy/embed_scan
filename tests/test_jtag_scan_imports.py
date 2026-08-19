import pytest
import types

import embed_scan
from embed_scan import DEFAULT_SCANNER, run_jtag_scan, scan_jtag_pins
from features.jtag.jtag_scanner import JtagScanner
from features.jtag.jtag_scanner_ui import JtagScannerUI
from hardware_backend import DwfHardwareInterface, HardwareBackend, SaleaeHardwareInterface


def test_jtag_scan_module_imports():
    assert isinstance(DEFAULT_SCANNER, JtagScanner)
    assert run_jtag_scan is not None
    assert scan_jtag_pins is not None


def test_jtag_scanner_ui_initialization():
    scanner = JtagScanner(backend=DwfHardwareInterface())
    ui = JtagScannerUI(scanner)
    assert ui.scanner is scanner
    assert scanner.output is ui


def test_hardware_backend_exports():
    assert issubclass(DwfHardwareInterface, HardwareBackend)
    assert issubclass(SaleaeHardwareInterface, HardwareBackend)


def test_main_program_closes_device_on_exit(monkeypatch):
    class FakeScanner:
        last_instance = None

        def __init__(self, backend):
            self.backend = backend
            self.closed = False
            FakeScanner.last_instance = self

        def close_runtime_device(self):
            self.closed = True

    class FakeUI:
        def __init__(self, scanner):
            self.scanner = scanner
            self.run_loop = True

        def setup(self, _input_args):
            return None

        def display_help(self):
            return None

        def loop(self):
            self.run_loop = False

    monkeypatch.setattr(
        embed_scan,
        "parse_arguments",
        lambda _argv: types.SimpleNamespace(hardware_backend="dwf", device_index=0),
    )
    monkeypatch.setattr(embed_scan, "JtagScanner", FakeScanner)
    monkeypatch.setattr(embed_scan, "JtagScannerUI", FakeUI)

    embed_scan.main_program()

    assert FakeScanner.last_instance is not None
    assert FakeScanner.last_instance.closed is True


def test_parse_arguments_supports_uart_subcommand():
    args = embed_scan.parse_arguments(
        ["dwf", "0", "uart", "--pins", "0-3,5", "--seconds", "2", "--sample-rate", "8000000"]
    )
    assert args.hardware_backend == "dwf"
    assert args.device_index == 0
    assert args.scanner_mode == "uart"
    assert args.pins == "0-3,5"
    assert args.seconds == 2.0
    assert args.sample_rate == 8_000_000


def test_parse_arguments_supports_uart_ui_subcommand():
    args = embed_scan.parse_arguments(
        ["dwf", "0", "uart-ui", "--pins", "0-3,5", "--seconds", "3", "--sample-rate", "4000000"]
    )
    assert args.hardware_backend == "dwf"
    assert args.device_index == 0
    assert args.scanner_mode == "uart-ui"
    assert args.pins == "0-3,5"
    assert args.seconds == 3.0
    assert args.sample_rate == 4_000_000


def test_parse_arguments_supports_jtag_subcommand():
    args = embed_scan.parse_arguments(
        ["dwf", "0", "jtag", "-c", "0-3,5", "-m", "0xff", "-p", "8"]
    )
    assert args.hardware_backend == "dwf"
    assert args.device_index == 0
    assert args.scanner_mode == "jtag"
    assert args.candidate_channels == "0-3,5"
    assert args.pin_mask_override == 0xFF
    assert args.pin_max_override == 8


def test_main_program_uart_mode(monkeypatch):
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
        valid_frames = 10
        decoded_text = "HELLO"

    class FakeUartScanner:
        calls = []

        def __init__(self, _backend):
            pass

        def capture_and_analyze(self, **kwargs):
            FakeUartScanner.calls.append(kwargs)
            return FakeUartReport()

    monkeypatch.setattr(
        embed_scan,
        "parse_arguments",
        lambda _argv: types.SimpleNamespace(
            hardware_backend="dwf",
            device_index=0,
            scanner_mode="uart",
            pins="2,3,5",
            seconds=1.5,
            sample_rate=8_000_000,
            baud_rates="9600,115200",
        ),
    )
    monkeypatch.setattr(embed_scan, "UartScanner", FakeUartScanner)

    embed_scan.main_program()

    assert len(FakeUartScanner.calls) == 1
    call = FakeUartScanner.calls[0]
    assert call["pins"] == [2, 3, 5]
    assert call["duration_seconds"] == 1.5
    assert call["sample_rate_hz"] == 8_000_000
    assert call["baud_rates"] == (9600, 115200)


def test_main_program_uart_ui_mode(monkeypatch):
    class FakeUartUI:
        created = None

        def __init__(self, _scanner):
            FakeUartUI.created = self
            self.run_loop = True

        def setup(self, _input_args):
            return None

        def display_help(self):
            return None

        def loop(self):
            self.run_loop = False

    monkeypatch.setattr(
        embed_scan,
        "parse_arguments",
        lambda _argv: types.SimpleNamespace(
            hardware_backend="dwf",
            device_index=0,
            scanner_mode="uart-ui",
            pins="2,3,5",
            seconds=1.5,
            sample_rate=8_000_000,
            baud_rates="9600,115200",
        ),
    )
    monkeypatch.setattr(embed_scan, "UartScannerUI", FakeUartUI)

    embed_scan.main_program()
    assert FakeUartUI.created is not None


def test_main_program_jtag_mode(monkeypatch):
    class FakeJtagReport:
        ok = True
        status = "success"
        reason = "ok"
        mapping = {"TCK": 2, "TMS": 3, "TDO": 4, "TDI": 5}

    class FakeJtagScanner:
        calls = []

        def __init__(self, _backend):
            pass

        def run_jtag_scan(self, **kwargs):
            FakeJtagScanner.calls.append(kwargs)
            return FakeJtagReport()

        def close_runtime_device(self):
            return None

    monkeypatch.setattr(
        embed_scan,
        "parse_arguments",
        lambda _argv: types.SimpleNamespace(
            hardware_backend="dwf",
            device_index=0,
            scanner_mode="jtag",
            candidate_channels="2,3,4,5",
            pin_mask_override=None,
            pin_max_override=None,
        ),
    )
    monkeypatch.setattr(embed_scan, "JtagScanner", FakeJtagScanner)

    embed_scan.main_program()

    assert len(FakeJtagScanner.calls) == 1
    call = FakeJtagScanner.calls[0]
    assert call["device_index"] == 0
    assert call["candidate_channels"] == [2, 3, 4, 5]
