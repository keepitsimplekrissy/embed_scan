# embed-scan

CLI toolkit for scanning and identifying embedded hardware interfaces — JTAG, UART and pin-status — via Digilent (DWF) and Saleae backends.

## Features

- **JTAG scanner** — auto-discover TCK/TMS/TDO/TDI pins, read IDCODE chains, identify connected chips from a built-in database (ARM, ST, Nordic, Xilinx, Altera, RISC-V and more)
- **UART scanner** — capture digital samples and infer baud rate, frame format, RX and flow-control pins
- **Pin status scanner** — read the current high/low level of any set of pins
- **Interactive UI** — unified selector menu combining all scanner modes

## Installation

```bash
# Core (no hardware dependencies)
pip install embed-scan

# With Digilent DWF support
pip install "embed-scan[dwf]"

# With Saleae support
pip install "embed-scan[saleae]"

# All backends
pip install "embed-scan[all]"
```

## Quick start

```bash
# Interactive UI (Digilent device 0)
embed-scan dwf 0 ui

# One-shot JTAG scan on pins 0-3
embed-scan dwf 0 jtag -c 0-3

# Detect connected chips on pins 0-3 (after pin assignment is known)
embed-scan dwf 0 jtag --tck-pin 0 --tms-pin 1 --tdo-pin 2 --tdi-pin 3

# UART capture on pins 2,3,5 for 2 seconds
embed-scan dwf 0 uart --pins 2,3,5 --seconds 2

# Read pin levels
embed-scan dwf 0 status --pins 0-7
```

## Requirements

- Python ≥ 3.11
- `dwfpy` (for Digilent Analog Discovery / Digital Discovery) — optional
- `saleae` (for Saleae Logic) — optional

## Release

Tag a commit `vX.Y.Z` and push; GitHub Actions will build and publish to PyPI automatically.

```bash
git tag v1.0.0
git push origin v1.0.0
```

## License

MIT
