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
