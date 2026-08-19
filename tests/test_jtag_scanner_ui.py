import io
import sys
import logging
import types

import pytest

from jtag_scanner_ui import JtagScannerUI
from jtag_scanner import PROMPT, ROW_FORMAT, ROW_FORMAT_TDI


class FakeLogger:
    def __init__(self, level=logging.INFO, enabled_values=None):
        self.level = level
        # enabled_values: set of ints for which isEnabledFor returns True
        self.enabled_values = enabled_values if enabled_values is not None else set()

    def isEnabledFor(self, v):
        # If enabled_values empty, default to False except common checks
        if not self.enabled_values:
            return False
        return v in self.enabled_values


class FakeScanResult:
    def __init__(self, ok=True, mapping=None, reason="fail"):
        self.ok = ok
        self.mapping = mapping
        self.reason = reason


class FakeScanner:
    """Fake scanner class to simulate JtagScanner behavior for testing JtagScannerUI."""
    
    def __init__(self):
        self.output = None
        self.tck_pin = 1
        self.tms_pin = 2
        self.tdo_pin = 3
        self.tdi_pin = 4
        self.pin_blacklist = 0
        self.io_pin_list = []
        self.pin_mask = 0
        self.pin_max = 0
        self.clock_half_cycle_us = 0
        self.logger = FakeLogger()
        self.delay_called = 0

    def delay(self, _):
        """Keep simple: increment a counter so tests can assert it was invoked if needed."""
        self.delay_called += 1

    def bit_write(self, mask, pin, value):
        """Write a bit to the pin mask. If value is True, set the bit; if False, clear the bit."""
        if value:
            return mask | (1 << pin)
        return mask & (~(1 << pin))

    def identify_pins(self, count, test_func):
        """Identify pins return True when test_func is self.test_id_code or test_bypass in tests set
           tests can monkeypatch these methods to change behavior."""
        return True

    def test_id_code(self):
        """Test function for IDCODE search. In tests, this can be monkeypatched to simulate success or failure."""
        return True

    def test_bypass(self):
        """Test function for bypass."""
        return True

    def run_jtag_scan(self, candidate_channels=None, runtime_policy=None):
        return FakeScanResult(ok=True, mapping={"a": 1})

    def get_max_pin_from_mask(self, mask):
        return mask.bit_length()

    def set_log_level(self, level):
        # allow numeric or string
        if isinstance(level, str):
            level_map = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR}
            self.logger.level = level_map.get(level.upper(), logging.INFO)
        else:
            self.logger.level = level

    def get_log_level_name(self):
        return logging.getLevelName(self.logger.level)


# helpers to patch stdin/stdout
class StdIOCapture:
    """Helper class to capture stdin and stdout for testing. It uses BytesIO for stdin and StringIO for stdout."""

    def __init__(self, input_bytes=b""):
        self._stdin_buf = io.BytesIO(input_bytes)
        self.stdin = types.SimpleNamespace(buffer=self._stdin_buf, closed=False)
        self.stdout = io.StringIO()

    def apply(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", self.stdin)
        monkeypatch.setattr(sys, "stdout", self.stdout)

    def get_stdout(self):
        return self.stdout.getvalue()


def test_init_sets_output():
    """Test that JtagScannerUI init sets scanner.output to self."""
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)
    assert scanner.output is ui


def test_read_cli_byte(monkeypatch):
    """Test that read_cli_byte correctly reads a single byte from stdin."""
    sio = StdIOCapture(b"A")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    b = ui.read_cli_byte()
    assert b == ord("A")


def test_read_cli_unsigned_int(monkeypatch):
    """Test that read_cli_unsigned_int correctly reads an unsigned integer from stdin."""
    sio = StdIOCapture(b"123\n")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    val = ui.read_cli_unsigned_int()
    assert val == 123
    out = sio.get_stdout()
    assert "123" in out


def test_read_cli_pin_list_empty(monkeypatch):
    """Test that read_cli_pin_list returns empty list for empty input."""
    # readline returns empty => []
    sio = StdIOCapture(b"")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    pins = ui.read_cli_pin_list()
    assert pins == []


def test_read_cli_pin_list_whitespace(monkeypatch):
    """Test that read_cli_pin_list returns empty list for whitespace input."""
    sio = StdIOCapture(b"\n")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    pins = ui.read_cli_pin_list()
    assert pins == []


def test_read_cli_pin_list_tokens(monkeypatch):
    """Test that read_cli_pin_list correctly parses a comma-separated list of integers, ignoring non-integer tokens."""
    sio = StdIOCapture(b"1,2,foo,3\n")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    pins = ui.read_cli_pin_list()
    assert pins == [1, 2, 3]


def test_read_cli_pin_list_supports_dash_ranges(monkeypatch):
    """Test that read_cli_pin_list expands dash-separated pin ranges."""
    sio = StdIOCapture(b"1-3,5,7-8\n")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    pins = ui.read_cli_pin_list()
    assert pins == [1, 2, 3, 5, 7, 8]


def test_print_prompt_and_banners(monkeypatch):
    """Test that print_prompt, id_code_banner, and width_banner print expected output."""
    sio = StdIOCapture()
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    # set logger to return True for the specific flag used in banners
    scanner.logger = FakeLogger(enabled_values={1 << 4, 20})
    ui = JtagScannerUI(scanner)

    ui.print_prompt()
    ui.id_code_banner()
    ui.width_banner()

    out = sio.get_stdout()
    assert PROMPT in out
    assert "IDCODE" in out or "TDI" in out


def test_print_result_row(monkeypatch):
    """Test that print_result_row prints the expected output format."""
    sio = StdIOCapture()
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    ui.print_result_row(include_tdi=False, value=0xdeadbeef)
    ui.print_result_row(include_tdi=True, value=0xcafe)

    out = sio.get_stdout()
    # check that tck,tms,tdo and value appear
    assert str(scanner.tck_pin) in out
    assert str(scanner.tms_pin) in out
    assert str(scanner.tdo_pin) in out
    assert format(0xdeadbeef, "x") in out.lower()


def test_print_identify_messages(monkeypatch):
    """Test that identify start, success, and fail messages print correctly."""
    sio = StdIOCapture()
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    ui.print_identify_start()
    ui.print_identify_success()
    ui.print_identify_fail()

    out = sio.get_stdout()
    assert "SUCCESS" in out
    assert "FAIL" in out


def test_setup_sets_pin_max_and_log_level(monkeypatch):
    """Test that setup sets pin_max and log level based on scanner state."""
    scanner = FakeScanner()
    scanner.pin_mask = 0b1011
    ui = JtagScannerUI(scanner)
    ui.setup()
    assert scanner.pin_max == scanner.get_max_pin_from_mask(scanner.pin_mask)
    assert scanner.logger.level == logging.INFO


def test_loop_calls_prompt_and_cli(monkeypatch):
    """Test that loop calls print_prompt and command_line_interface."""
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    called = {}

    def fake_print_prompt():
        called["prompt"] = True

    def fake_cli():
        called["cli"] = True

    monkeypatch.setattr(ui, "print_prompt", fake_print_prompt)
    monkeypatch.setattr(ui, "command_line_interface", fake_cli)

    ui.loop()
    assert called.get("prompt")
    assert called.get("cli")


def test_command_line_interface_unknown_command(monkeypatch):
    """Send unknown selection "x" -> should print unknown command."""
    sio = StdIOCapture(b"x")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    ui.command_line_interface()
    out = sio.get_stdout()
    assert "Unknown command: x\n" in out


def test_help_menu_displays_correctly(monkeypatch):
    """Send help display selection "h" -> should print help info."""
    sio = StdIOCapture(b"h")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    ui.command_line_interface()
    out = sio.get_stdout()

    assert "+-------------------------------+\n" in out
    assert "|  JTAGscan Jtag Pinout Finder  |\n" in out
    assert "+-------------------------------+\n" in out
    assert "a - Automatically find all pins\n" in out
    assert "i - IDCODE search for pins\n" in out
    assert "b - BYPASS search for pins\n" in out
    assert "t - TDI-only BYPASS search\n" in out
    assert "p - setup IO pin list\n" in out
    assert "m - set pin mask, current: 0x" in out
    assert "d - cycle log level. current: INFO\n" in out
    assert "c - half cycle us, current:" in out
    assert "L - set log level by name\n" in out
    assert "h - print this help\n" in out
    assert "q - quit\n" in out
    assert "+-------------------------------+\n" in out


def test_command_line_interface_p_add_pins_and_run_scan(monkeypatch):
    """Send "p" and pin list -> should call read_cli_pin_list and set io_pin_list."""
    # buffer: "p" then the pin list for readline
    sio = StdIOCapture(b"p1,5,7\n")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    ui.command_line_interface()
    out = sio.get_stdout()
    assert "IO pin list set to" in out
    assert "hardware mapping" in out
    assert 1 in scanner.io_pin_list or 5 in scanner.io_pin_list


def test_setup_pin_list_with_comma_input_runs_scan(monkeypatch):
    """setup_pin_list should accept comma-separated pins and pass them to scan."""
    sio = StdIOCapture(b"1,5,7\n")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)
    scan_calls = []

    def fake_run_jtag_scan(candidate_channels=None, runtime_policy=None):
        scan_calls.append((candidate_channels, runtime_policy))
        return FakeScanResult(ok=True, mapping={"a": 1})

    scanner.run_jtag_scan = fake_run_jtag_scan

    ui.setup_pin_list()

    assert scanner.io_pin_list == [1, 5, 7]
    assert scan_calls == [([1, 5, 7], "hardware")]
    out = sio.get_stdout()
    assert "IO pin list set to [1, 5, 7]" in out
    assert "hardware mapping" in out


def test_setup_pin_list_with_range_input_runs_scan(monkeypatch):
    """setup_pin_list should accept mixed list and range pin input."""
    sio = StdIOCapture(b"0-2,5\n")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)
    scan_calls = []

    def fake_run_jtag_scan(candidate_channels=None, runtime_policy=None):
        scan_calls.append((candidate_channels, runtime_policy))
        return FakeScanResult(ok=True, mapping={"a": 1})

    scanner.run_jtag_scan = fake_run_jtag_scan

    ui.setup_pin_list()

    assert scanner.io_pin_list == [0, 1, 2, 5]
    assert scan_calls == [([0, 1, 2, 5], "hardware")]
    out = sio.get_stdout()
    assert "IO pin list set to [0, 1, 2, 5]" in out
    assert "hardware mapping" in out


def test_setup_pin_list_ignores_leading_newline(monkeypatch):
    """setup_pin_list should ignore a leading empty line before parsing pins."""
    sio = StdIOCapture(b"\n1,2\n")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)
    scan_calls = []

    def fake_run_jtag_scan(candidate_channels=None, runtime_policy=None):
        scan_calls.append((candidate_channels, runtime_policy))
        return FakeScanResult(ok=True, mapping={"a": 1})

    scanner.run_jtag_scan = fake_run_jtag_scan

    ui.setup_pin_list()

    assert scanner.io_pin_list == [1, 2]
    assert scan_calls == [([1, 2], "hardware")]


def test_command_line_interface_m_sets_mask(monkeypatch):
    """Send 'm' and bit maks to set pin mask -> should call read_cli_unsigned_int and set pin_mask."""
    sio = StdIOCapture(b"m\x05\n")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    # monkeypatch read_cli_unsigned_int to return 5 directly to avoid encoding issues
    monkeypatch.setattr(ui, "read_cli_unsigned_int", lambda: 5)
    ui.command_line_interface()
    out = sio.get_stdout()
    assert "Pin mask set to" in out
    assert scanner.pin_mask == 5


def test_command_line_interface_toggle_log_level(monkeypatch):
    """Send "d" to toggle log level -> should change log level and print new level."""
    sio = StdIOCapture(b"d")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    # start at INFO
    scanner.logger.level = logging.INFO
    ui = JtagScannerUI(scanner)

    ui.command_line_interface()
    out = sio.get_stdout()
    assert "Log level set to" in out


def test_command_line_interface_set_log_level_by_name(monkeypatch):
    # send "L" and then provide level name via read_cli_pin_list
    sio = StdIOCapture(b"LDEBUG\n")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    ui = JtagScannerUI(scanner)

    # patch read_cli_pin_list to return ["DEBUG"]
    monkeypatch.setattr(ui, "read_cli_pin_list", lambda: ["DEBUG"]) 
    ui.command_line_interface()
    out = sio.get_stdout()
    assert "Log level set to" in out


def test_command_line_interface_a_search_success(monkeypatch):
    # test "a" branch where identify_pins returns True for both calls
    sio = StdIOCapture(b"a")
    sio.apply(monkeypatch)
    scanner = FakeScanner()
    # ensure identify_pins returns True
    scanner.identify_pins = lambda count, func: True
    ui = JtagScannerUI(scanner)

    ui.command_line_interface()
    out = sio.get_stdout()
    assert "Automatically searching" in out
    assert "TCK, TMS, and TDO found" in out
