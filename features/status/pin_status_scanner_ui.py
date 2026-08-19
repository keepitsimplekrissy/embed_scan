import sys

from typing import Any

from ..scanner_ui import ScannerUI
from .pin_status_scanner import PinStatusScanner


class PinStatusScannerUI(ScannerUI):
    """Interactive UI for reading current digital levels of selected pins."""

    def __init__(self, scanner: PinStatusScanner):
        self.scanner = scanner
        super().__init__()
        self.device_index = 0
        self.pins: list[int] = []

    def set_pins(self):
        sys.stdout.write("Enter pins to read (comma list or range): ")
        sys.stdout.flush()
        pins = self.read_cli_pin_list()
        if pins:
            self.pins = pins
            sys.stdout.write("Pins set to " + str(self.pins) + "\n")
        else:
            sys.stdout.write("No valid pins supplied\n")
        sys.stdout.flush()

    def run_status_scan(self):
        if not self.pins:
            sys.stdout.write("No pins selected. Use 'p' to set pins first.\n")
            sys.stdout.flush()
            return

        report = self.scanner.read_pin_states(self.pins, device_index=self.device_index)
        sys.stdout.write("Pin status scan: " + report.status + "\n")
        sys.stdout.write("reason: " + report.reason + "\n")
        for pin in self.pins:
            if pin in report.pin_states:
                sys.stdout.write("pin " + str(pin) + ": " + report.pin_states[pin] + "\n")
        sys.stdout.flush()

    def display_help(self):
        title = "+-------------------------------+\n"
        sys.stdout.write(title)
        sys.stdout.write("|   Pin Status Scanner UI       |\n")
        sys.stdout.write(title)
        sys.stdout.write(" s - read pin states\n")
        sys.stdout.write(" p - set pin list\n")
        sys.stdout.write(" h - print this help\n")
        sys.stdout.write(" q - quit\n")
        sys.stdout.write(title)
        sys.stdout.flush()

    def command_line_interface(self):
        selection = self.read_cli_byte()
        if isinstance(selection, int):
            selection = chr(selection)
        if selection in ("\n", "\r"):
            return

        match selection:
            case "s":
                self.run_status_scan()
            case "p":
                self.set_pins()
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
        pin_spec = input_args.get("status_pins", "") or input_args.get("pins", "")
        if pin_spec:
            self.pins = self.parse_pin_spec(str(pin_spec))

