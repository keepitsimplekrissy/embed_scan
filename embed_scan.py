#!/usr/bin/env python3
"""Small CLI entry points for invoking JTAG scans.

This module exposes convenience functions that call into a module-global
JtagScanner instance. The file also contains a simple interactive loop when
executed as a script.
"""
import logging
import argparse
import sys

from features.jtag.jtag_scanner import JtagScanner
from features.jtag.jtag_scanner_ui import JtagScannerUI
from features.uart.uart_scanner import COMMON_UART_BAUD_RATES, UartScanner
from features.uart.uart_scanner_ui import UartScannerUI
from hardware_backend import DwfHardwareInterface

logging.basicConfig(
    filename="jtag_scan.log",
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

DEFAULT_SCANNER = JtagScanner(DwfHardwareInterface())


def run_jtag_scan(*args, **kwargs):
    """Module-level compatibility wrapper for scanner.run_jtag_scan()."""
    return DEFAULT_SCANNER.run_jtag_scan(*args, **kwargs)


def scan_jtag_pins(*args, **kwargs):
    """Module-level wrapper for scanner.scan_jtag_pins()."""
    return DEFAULT_SCANNER.scan_jtag_pins(*args, **kwargs)


def _parse_pin_spec(pin_spec: str) -> list[int]:
    pins: list[int] = []
    for token in pin_spec.replace(",", " ").split():
        if "-" in token:
            parts = token.split("-")
            if len(parts) != 2:
                continue
            try:
                start = int(parts[0])
                end = int(parts[1])
            except (TypeError, ValueError):
                continue
            if start < 0 or end < 0:
                continue
            step = 1 if end >= start else -1
            pins.extend(range(start, end + step, step))
            continue
        try:
            value = int(token)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            pins.append(value)
    deduped: list[int] = []
    seen = set()
    for pin in pins:
        if pin not in seen:
            seen.add(pin)
            deduped.append(pin)
    return deduped


def parse_arguments(input_arguments):
    """Parse input arguments."""
    parser = argparse.ArgumentParser(description="JTAG Scanner CLI")
    parser.add_argument("hardware_backend", type=str, choices=["dwf", "saleae"],
                        help="Hardware backend")
    parser.add_argument("device_index", type=int, help="Device index for the scanner")
    parser.set_defaults(
        scanner_mode="jtag-ui",
        candidate_channels=None,
        pin_mask_override=None,
        pin_max_override=None,
    )
    subparsers = parser.add_subparsers(dest="scanner_mode")

    jtag_parser = subparsers.add_parser("jtag", help="Run one-shot JTAG scan")
    jtag_parser.add_argument("-c", "--candidate-channels", type=str,
                             help="Comma-separated list of candidate channels")
    jtag_parser.add_argument("-m", "--pin-mask-override", type=lambda x: int(x, 0),
                             help="Pin mask override (hex or decimal)")
    jtag_parser.add_argument("-p", "--pin-max-override", type=int,
                             help="Pin max override")
    
    jtag_ui_parser = subparsers.add_parser("jtag-ui", help="Run interactive JTAG scanner UI")
    jtag_ui_parser.add_argument("-m", "--pin-mask-override", type=lambda x: int(x, 0),
                                help="Pin mask override (hex or decimal)")
    jtag_ui_parser.add_argument("-p", "--pin-max-override", type=int,
                                help="Pin max override")

    uart_parser = subparsers.add_parser("uart", help="Run UART scanner")
    uart_parser.add_argument(
        "--pins",
        required=True,
        type=str,
        help="Pins to sample (comma-separated and ranges like 0-7)",
    )
    uart_parser.add_argument(
        "--seconds",
        type=float,
        default=1.0,
        help="Capture duration in seconds",
    )
    uart_parser.add_argument(
        "--sample-rate",
        type=int,
        default=8_000_000,
        help="Capture sample rate in Hz",
    )
    uart_parser.add_argument(
        "--baud-rates",
        type=str,
        default="",
        help="Comma-separated UART baud rates to test",
    )

    uart_ui_parser = subparsers.add_parser("uart-ui", help="Run interactive UART scanner UI")
    uart_ui_parser.add_argument(
        "--pins",
        default="",
        type=str,
        help="Optional initial pins (comma-separated and ranges like 0-7)",
    )
    uart_ui_parser.add_argument(
        "--seconds",
        type=float,
        default=1.0,
        help="Initial capture duration in seconds",
    )
    uart_ui_parser.add_argument(
        "--sample-rate",
        type=int,
        default=8_000_000,
        help="Initial capture sample rate in Hz",
    )
    uart_ui_parser.add_argument(
        "--baud-rates",
        type=str,
        default="",
        help="Optional initial comma-separated UART baud rates",
    )
    return parser.parse_args(input_arguments)


def main_program():
    """Main program entry point."""
    scanner = None
    try:
        # argument parser
        input_args = sys.argv[1:]
        args = parse_arguments(input_args)
        input_args = vars(args)

        #
        if input_args["hardware_backend"] == "dwf":
            from hardware_backend.dwf import DwfHardwareInterface as HardwareBackend
        elif input_args["hardware_backend"] == "saleae":
            from hardware_backend.saleae import SaleaeHardwareInterface as HardwareBackend
        else:
            raise ValueError(f"Unsupported hardware backend: {input_args.hardware_backend}")
        hardware_backend = HardwareBackend()

        scanner_mode = input_args.get("scanner_mode") or "jtag-ui"
        if scanner_mode == "uart":
            # Uart command line interface
            uart_scanner = UartScanner(hardware_backend)
            pins = _parse_pin_spec(input_args.get("pins", ""))
            baud_rates_spec = input_args.get("baud_rates", "")
            if baud_rates_spec:
                baud_rates = tuple(
                    int(token.strip()) for token in baud_rates_spec.split(",") if token.strip()
                )
            else:
                baud_rates = COMMON_UART_BAUD_RATES
            report = uart_scanner.capture_and_analyze(
                pins=pins,
                duration_seconds=float(input_args.get("seconds", 1.0)),
                sample_rate_hz=int(input_args.get("sample_rate", 8_000_000)),
                device_index=int(input_args.get("device_index", 0)),
                baud_rates=baud_rates,
            )
            sys.stdout.write("UART scan status: " + report.status + "\n")
            sys.stdout.write("reason: " + report.reason + "\n")
            if report.ok:
                sys.stdout.write("rx pin: " + str(report.rx_pin) + "\n")
                sys.stdout.write("flow control pin: " + str(report.flow_control_pin) + "\n")
                sys.stdout.write("baud rate: " + str(report.baud_rate) + "\n")
                sys.stdout.write("data bits: " + str(report.data_bits) + "\n")
                sys.stdout.write("stop bits: " + str(report.stop_bits) + "\n")
                sys.stdout.write("parity: " + str(report.parity) + "\n")
                sys.stdout.write("valid frames: " + str(report.valid_frames) + "\n")
                sys.stdout.write("decoded text: " + report.decoded_text + "\n")
            sys.stdout.flush()
            return

        if scanner_mode == "uart-ui":
            # Uart command line ui
            uart_scanner = UartScanner(hardware_backend)
            uart_ui = UartScannerUI(uart_scanner)
            uart_ui.setup(input_args)
            uart_ui.display_help()
            while uart_ui.run_loop:
                uart_ui.loop()
            return

        if scanner_mode == "jtag":
            scanner = JtagScanner(hardware_backend)
            candidate_channels = _parse_pin_spec(input_args.get("candidate_channels", ""))
            if not candidate_channels:
                candidate_channels = None
            report = scanner.run_jtag_scan(
                device_index=int(input_args.get("device_index", 0)),
                candidate_channels=candidate_channels,
                pin_mask_override=input_args.get("pin_mask_override"),
                pin_max_override=input_args.get("pin_max_override"),
            )
            sys.stdout.write("JTAG scan status: " + report.status + "\n")
            sys.stdout.write("reason: " + report.reason + "\n")
            if report.ok and report.mapping:
                for signal_name in ("TCK", "TMS", "TDO", "TDI"):
                    if signal_name in report.mapping:
                        sys.stdout.write(signal_name.lower() + " pin: " + str(report.mapping[signal_name]) + "\n")
            sys.stdout.flush()
            return

        if scanner_mode == "jtag-ui":
            # Jtag command line ui
            scanner = JtagScanner(hardware_backend)
            ui = JtagScannerUI(scanner)
            ui.setup(input_args)
            ui.display_help()
            while ui.run_loop:
                ui.loop()
            return

        raise ValueError(f"Unsupported scanner mode: {scanner_mode}")
    finally:
        if scanner is not None:
            scanner.close_runtime_device()


if __name__ == "__main__":
    main_program()
