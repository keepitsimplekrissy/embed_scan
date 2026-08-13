import pytest

from jtag_scan import DEFAULT_SCANNER, run_jtag_scan, scan_dwf_jtag_pins
from jtag_scanner import JtagScanner
from jtag_scanner_ui import JtagScannerUI
from hardware_backend import DwfHardwareInterface, HardwareBackend, SaleaeHardwareInterface


def test_jtag_scan_module_imports():
    assert isinstance(DEFAULT_SCANNER, JtagScanner)
    assert run_jtag_scan is not None
    assert scan_dwf_jtag_pins is not None


def test_jtag_scanner_ui_initialization():
    scanner = JtagScanner(backend=DwfHardwareInterface())
    ui = JtagScannerUI(scanner)
    assert ui.scanner is scanner
    assert scanner.output is ui


def test_hardware_backend_exports():
    assert issubclass(DwfHardwareInterface, HardwareBackend)
    assert issubclass(SaleaeHardwareInterface, HardwareBackend)
