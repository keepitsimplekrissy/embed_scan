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


def parse_arguments(input_arguments):
    """Parse input arguments."""
    parser = argparse.ArgumentParser(description="JTAG Scanner CLI")
    parser.add_argument("hardware_backend", type=str, choices=["dwf", "saleae"],
                        help="Hardware backend")
    parser.add_argument("device_index", type=int, help="Device index for the scanner")
    parser.add_argument("-c", "--candidate-channels", type=str,
                        help="Comma-separated list of candidate channels")
    parser.add_argument("-m", "--pin-mask-override", type=lambda x: int(x, 0),
                        help="Pin mask override (hex or decimal)")
    parser.add_argument("-p", "--pin-max-override", type=int,
                        help="Pin max override")
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
        
        # Jtag
        scanner = JtagScanner(hardware_backend)
        ui = JtagScannerUI(scanner)
        
        ui.setup(input_args)
        ui.display_help()
        while ui.run_loop:
            ui.loop()
    finally:
        if scanner is not None:
            scanner.close_runtime_device()


if __name__ == "__main__":
    main_program()

