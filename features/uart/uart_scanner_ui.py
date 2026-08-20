import sys

from typing import Any

from .uart_scanner import COMMON_UART_BAUD_RATES, UartScanner
from ..scanner_ui import ScannerUI


class UartScannerUI(ScannerUI):
    """Interactive command-line UI for running UART capture and analysis."""

    def __init__(self, scanner: UartScanner):
        self.scanner = scanner
        super().__init__()
        self.device_index = 0
        self.pins: list[int] = []
        self.capture_seconds = 1.0
        self.sample_rate_hz = 8_000_000
        self.baud_rates = list(COMMON_UART_BAUD_RATES)
        self.capture_path: str | None = None

    @staticmethod
    def parse_baud_rates(baud_rates_spec: str) -> list[int]:
        parsed: list[int] = []
        for token in baud_rates_spec.replace(",", " ").split():
            try:
                value = int(token)
            except (TypeError, ValueError):
                continue
            if value > 0:
                parsed.append(value)
        return parsed

    def set_pins(self):
        sys.stdout.write("Enter UART candidate pins (comma list or range): ")
        sys.stdout.flush()
        pins = self.read_cli_pin_list()
        if pins:
            self.pins = pins
            sys.stdout.write("UART pins set to " + str(self.pins) + "\n")
        else:
            sys.stdout.write("No valid pins supplied\n")
        sys.stdout.flush()

    def set_capture_seconds(self):
        sys.stdout.write("Enter UART capture duration in seconds: ")
        sys.stdout.flush()
        value = self.read_cli_nonempty_line()
        try:
            parsed = float(value)
            if parsed > 0:
                self.capture_seconds = parsed
        except (TypeError, ValueError):
            pass
        sys.stdout.write("Capture duration set to " + str(self.capture_seconds) + "s\n")
        sys.stdout.flush()

    def set_sample_rate(self):
        sys.stdout.write("Enter UART sample rate in Hz: ")
        sys.stdout.flush()
        value = self.read_cli_nonempty_line()
        try:
            parsed = int(value)
            if parsed > 0:
                self.sample_rate_hz = parsed
        except (TypeError, ValueError):
            pass
        sys.stdout.write("Sample rate set to " + str(self.sample_rate_hz) + "Hz\n")
        sys.stdout.flush()

    def set_baud_rates(self):
        sys.stdout.write("Enter baud rates (comma separated): ")
        sys.stdout.flush()
        parsed = self.parse_baud_rates(self.read_cli_nonempty_line())
        if parsed:
            self.baud_rates = parsed
        sys.stdout.write("Baud rates set to " + str(self.baud_rates) + "\n")
        sys.stdout.flush()

    def set_capture_path(self):
        sys.stdout.write("Enter capture output folder path: ")
        sys.stdout.flush()
        value = self.read_cli_nonempty_line()
        self.capture_path = value if value else None
        sys.stdout.write("Capture path set to " + str(self.capture_path) + "\n")
        sys.stdout.flush()

    def run_uart_scan(self):
        if not self.pins:
            sys.stdout.write("No UART pins selected. Use 'p' to set pins first.\n")
            sys.stdout.flush()
            return

        sys.stdout.write("Starting UART scan with settings:\n")
        sys.stdout.write("device index: " + str(self.device_index) + "\n")
        sys.stdout.write("pins: " + str(self.pins) + "\n")
        sys.stdout.write("capture seconds: " + str(self.capture_seconds) + "\n")
        sys.stdout.write("sample rate hz: " + str(self.sample_rate_hz) + "\n")
        sys.stdout.write("baud rates: " + str(self.baud_rates) + "\n")
        sys.stdout.write("capture path: " + str(self.capture_path) + "\n")
        sys.stdout.flush()

        report = self.scanner.capture_and_analyze(
            pins=self.pins,
            duration_seconds=self.capture_seconds,
            sample_rate_hz=self.sample_rate_hz,
            device_index=self.device_index,
            baud_rates=tuple(self.baud_rates),
            capture_path=self.capture_path,
        )
        sys.stdout.write("UART scan status: " + report.status + "\n")
        sys.stdout.write("reason: " + report.reason + "\n")
        capture_storage_path = getattr(report, "capture_storage_path", None)
        if capture_storage_path:
            sys.stdout.write("capture data path (JSON): " + str(capture_storage_path) + "\n")
        capture_bson_path = getattr(report, "capture_bson_path", None)
        if capture_bson_path:
            sys.stdout.write("capture data path (BSON): " + str(capture_bson_path) + "\n")
        if report.ok:
            channels = getattr(report, "channels", [])
            if len(channels) > 1:
                sys.stdout.write(
                    "+--- All detected UART configurations ("
                    + str(len(channels)) + ") ---+\n"
                )
                for idx, ch in enumerate(channels):
                    sys.stdout.write(
                        "  [" + str(idx + 1) + "] pin=" + str(ch.rx_pin)
                        + " baud=" + str(ch.baud_rate)
                        + " " + str(ch.data_bits) + str(ch.parity[0].upper()) + str(ch.stop_bits)
                        + (" INV" if ch.inverted else "")
                        + " frames=" + str(ch.valid_frames)
                        + " text=" + repr(ch.decoded_text)
                        + "\n"
                    )
                sys.stdout.write("+--- Best result ---+\n")
            sys.stdout.write("rx pin: " + str(report.rx_pin) + "\n")
            sys.stdout.write("flow control pin: " + str(report.flow_control_pin) + "\n")
            sys.stdout.write("baud rate: " + str(report.baud_rate) + "\n")
            sys.stdout.write("data bits: " + str(report.data_bits) + "\n")
            sys.stdout.write("stop bits: " + str(report.stop_bits) + "\n")
            sys.stdout.write("parity: " + str(report.parity) + "\n")
            sys.stdout.write("signal inverted: " + str(getattr(report, "inverted", False)) + "\n")
            sys.stdout.write("valid frames: " + str(report.valid_frames) + "\n")
            sys.stdout.write("decoded text: " + report.decoded_text + "\n")
        sys.stdout.flush()

    def display_help(self):
        title = "+-------------------------------+\n"
        sys.stdout.write(title)
        sys.stdout.write("|   UART Scanner and Analyzer   |\n")
        sys.stdout.write(title)
        sys.stdout.write(" s - run UART scan\n")
        sys.stdout.write(" p - set candidate pins\n")
        sys.stdout.write(" t - set capture duration seconds\n")
        sys.stdout.write(" r - set sample rate Hz\n")
        sys.stdout.write(" b - set baud rates list\n")
        sys.stdout.write(" o - set capture output path\n")
        sys.stdout.write(" h - print this help\n")
        sys.stdout.write(" q - quit\n")
        sys.stdout.write(title)
        sys.stdout.flush()

    def command_line_interface(self):
        selection = self.read_cli_command()
        if not selection:
            return

        match selection:
            case "s":
                self.run_uart_scan()
            case "p":
                self.set_pins()
            case "t":
                self.set_capture_seconds()
            case "r":
                self.set_sample_rate()
            case "b":
                self.set_baud_rates()
            case "o":
                self.set_capture_path()
            case "h":
                self.display_help()
            case "q":
                self.run_loop = False
            case _:
                sys.stdout.write("Unknown command: " + str(selection) + "\n")
                sys.stdout.flush()

    def setup(self, input_args: dict[str, Any] | None = None) -> None:
        if not input_args:
            return
        self.device_index = int(input_args.get("device_index", 0))
        pins_spec = input_args.get("pins", "")
        if pins_spec:
            self.pins = self.parse_pin_spec(str(pins_spec))
        if input_args.get("seconds") is not None:
            try:
                seconds = float(input_args.get("seconds"))
                if seconds > 0:
                    self.capture_seconds = seconds
            except (TypeError, ValueError):
                pass
        if input_args.get("sample_rate") is not None:
            try:
                sample_rate = int(input_args.get("sample_rate"))
                if sample_rate > 0:
                    self.sample_rate_hz = sample_rate
            except (TypeError, ValueError):
                pass
        baud_spec = str(input_args.get("baud_rates", "") or "")
        parsed_baud_rates = self.parse_baud_rates(baud_spec)
        if parsed_baud_rates:
            self.baud_rates = parsed_baud_rates
        capture_path = str(input_args.get("capture_path", "") or "").strip()
        if capture_path:
            self.capture_path = capture_path

    def loop(self):
        super().loop()
