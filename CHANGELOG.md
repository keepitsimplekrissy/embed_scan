# Changelog

All notable changes to this project are documented here.
Versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- JTAG scanner with automatic pin discovery (IDCODE + BYPASS)
- Built-in JTAG chip identification database (ARM, ST, Nordic, Xilinx, Altera, RISC-V, …)
- UART capture and frame-format inference (baud rate, data bits, parity, stop bits, flow control)
- Pin status scanner (read high/low levels)
- Interactive selector UI combining all scanner modes
- Digilent DWF and Saleae hardware backends
- `embed-scan` CLI entrypoint
