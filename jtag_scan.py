#!/usr/bin/env python3

import logging

from jtag_scanner import JtagScanner
from jtag_scanner_ui import JtagScannerUI

logging.basicConfig(
    filename="jtag_scan.log",
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

DEFAULT_SCANNER = JtagScanner()


def scan_dwf_jtag_pins(device_index=0, candidate_channels=None, pin_mask_override=None, pin_max_override=None, runtime_policy="hardware"):
    return DEFAULT_SCANNER.scan_dwf_jtag_pins(
        device_index=device_index,
        candidate_channels=candidate_channels,
        pin_mask_override=pin_mask_override,
        pin_max_override=pin_max_override,
        runtime_policy=runtime_policy,
    )


def run_jtag_scan(device_index=0, candidate_channels=None, pin_mask_override=None, pin_max_override=None, runtime_policy="hardware", device=None):
    return DEFAULT_SCANNER.run_jtag_scan(
        device_index=device_index,
        candidate_channels=candidate_channels,
        pin_mask_override=pin_mask_override,
        pin_max_override=pin_max_override,
        runtime_policy=runtime_policy,
        device=device,
    )


if __name__ == "__main__":
    scanner = JtagScanner()
    ui = JtagScannerUI(scanner)
    ui.setup()
    while True:
        ui.loop()
