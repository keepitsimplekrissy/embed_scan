import sys

from jtag_scanner import JtagScanner, PROMPT, ROW_FORMAT, ROW_FORMAT_TDI


class JtagScannerUI:
    def __init__(self, scanner: JtagScanner):
        self.scanner = scanner
        self.scanner.output = self

    def read_cli_byte(self):
        while True:
            if sys.stdin is not None and not sys.stdin.closed:
                try:
                    input_value = sys.stdin.buffer.read(1)
                    if input_value:
                        byte = input_value[0]
                        sys.stdout.write(chr(byte if 0x20 <= byte <= 0x7e else 0x20))
                        sys.stdout.flush()
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                        return byte
                except Exception:
                    pass
            self.scanner.delay(100)

    def read_cli_unsigned_int(self):
        buffer = ""
        idx = 0

        while True:
            if sys.stdin is not None and not sys.stdin.closed:
                try:
                    input_value = sys.stdin.buffer.read(1)
                    if input_value:
                        byte = input_value[0]
                        sys.stdout.write(chr(byte if 0x20 <= byte <= 0x7e else 0x20))
                        sys.stdout.flush()
                        if idx < 20 - 1 and byte not in (0x0d, 0x0a):
                            if 0x30 <= byte <= 0x7a:
                                buffer = buffer + chr(byte)
                                idx += 1
                        else:
                            sys.stdout.write("\n")
                            sys.stdout.flush()
                            return int(buffer, 0) if buffer else 0
                except Exception:
                    pass
            self.scanner.delay(100)

    def read_cli_pin_list(self):
        try:
            line = sys.stdin.buffer.readline()
        except Exception:
            return []

        if not line:
            return []

        text = line.decode("utf-8", errors="ignore").strip()
        if not text:
            return []

        pins: list[int] = []
        for token in text.replace(",", " ").split():
            try:
                value = int(token)
            except (TypeError, ValueError):
                continue
            if value >= 0:
                pins.append(value)
        return pins

    def print_prompt(self):
        sys.stdout.write(PROMPT)
        sys.stdout.flush()

    def id_code_banner(self):
        sys.stdout.write("| TCK | TMS | TDO |      IDCODE |")
        sys.stdout.flush()
        if self.scanner.logger.isEnabledFor(1 << 4):
            sys.stdout.write("tms|tdi|tdo|\n")
        else:
            sys.stdout.write("\n")
        sys.stdout.flush()

    def width_banner(self):
        sys.stdout.write("| TCK | TMS | TDO | TDI | Width |")
        sys.stdout.flush()
        if self.scanner.logger.isEnabledFor(1 << 4):
            sys.stdout.write("tms|tdi|tdo|\n")
        else:
            sys.stdout.write("\n")
        sys.stdout.flush()

    def print_result_row(self, include_tdi, value):
        if include_tdi:
            dbgBuffer = ROW_FORMAT_TDI % (
                self.scanner.tck_pin,
                self.scanner.tms_pin,
                self.scanner.tdo_pin,
                self.scanner.tdi_pin,
                value,
            )
        else:
            dbgBuffer = ROW_FORMAT % (
                self.scanner.tck_pin,
                self.scanner.tms_pin,
                self.scanner.tdo_pin,
                value,
            )
        sys.stdout.write(dbgBuffer)
        sys.stdout.flush()

    def print_identify_start(self):
        sys.stdout.write("+-------------------------------+\n")
        sys.stdout.flush()

    def print_identify_success(self):
        sys.stdout.write("+----------- SUCCESS -----------+\n")
        sys.stdout.flush()

    def print_identify_fail(self):
        sys.stdout.write("+------------ FAIL -------------+\n")
        sys.stdout.flush()

    def command_line_interface(self):
        selection = self.read_cli_byte()
        if isinstance(selection, int):
            selection = chr(selection)

        if selection == 'a':
            id_hit = False
            tdi_found = False

            sys.stdout.write("     Automatically searching\n")
            sys.stdout.write("+-- Starting with IDCODE scan --+\n")
            sys.stdout.flush()
            self.id_code_banner()

            id_hit = self.scanner.identify_pins(3, self.scanner.test_id_code)

            if self.scanner.logger.isEnabledFor(20):
                self.id_code_banner()
                sys.stdout.write("+------ IDCODE complete --------+\n")
                sys.stdout.flush()

            if id_hit:
                sys.stdout.write("    TCK, TMS, and TDO found.\n")
                sys.stdout.write("\n")
                sys.stdout.write("+-- BYPASS searching, just TDI -+\n")
                sys.stdout.flush()
                self.width_banner()
                self.scanner.pin_blacklist = self.scanner.bit_write(self.scanner.pin_blacklist, self.scanner.tck_pin, 1)
                self.scanner.pin_blacklist = self.scanner.bit_write(self.scanner.pin_blacklist, self.scanner.tms_pin, 1)
                self.scanner.pin_blacklist = self.scanner.bit_write(self.scanner.pin_blacklist, self.scanner.tdo_pin, 1)
                tdi_found = self.scanner.identify_pins(1, self.scanner.test_bypass)
                self.scanner.pin_blacklist = 0

            if not id_hit or not tdi_found:
                sys.stdout.write(" No valid TCK, TMS, and TDO found\n")
                sys.stdout.write("  Press 'b' for full bypass scan\n")
                sys.stdout.flush()

        elif selection == 'i':
            sys.stdout.write("+------ IDCODE searching -------+\n")
            sys.stdout.flush()
            self.id_code_banner()
            self.scanner.identify_pins(3, self.scanner.test_id_code)
            if self.scanner.logger.isEnabledFor(20):
                self.id_code_banner()
                sys.stdout.write("+------ IDCODE complete --------+\n")
                sys.stdout.flush()

        elif selection == 'b':
            sys.stdout.write("+------ BYPASS searching -------+\n")
            sys.stdout.flush()
            self.width_banner()
            self.scanner.identify_pins(4, self.scanner.test_bypass)
            if self.scanner.logger.isEnabledFor(20):
                self.width_banner()
                sys.stdout.write("+------ BYPASS complete --------+\n")
                sys.stdout.flush()

        elif selection == 't':
            sys.stdout.write("+-- BYPASS searching, just TDI -+\n")
            sys.stdout.flush()
            self.width_banner()
            self.scanner.pin_blacklist = self.scanner.bit_write(self.scanner.pin_blacklist, self.scanner.tck_pin, 1)
            self.scanner.pin_blacklist = self.scanner.bit_write(self.scanner.pin_blacklist, self.scanner.tms_pin, 1)
            self.scanner.pin_blacklist = self.scanner.bit_write(self.scanner.pin_blacklist, self.scanner.tdo_pin, 1)
            self.scanner.identify_pins(1, self.scanner.test_bypass)
            self.scanner.pin_blacklist = 0

        elif selection == 'l':
            sys.stdout.write("Enter IO pin list (comma separated): ")
            sys.stdout.flush()
            pins = self.read_cli_pin_list()
            if pins:
                for pin in pins:
                    if pin not in self.scanner.io_pin_list:
                        self.scanner.io_pin_list.append(pin)
                sys.stdout.write("IO pin list set to ")
                sys.stdout.write(str(self.scanner.io_pin_list) + "\n")
                sys.stdout.flush()

                hardware_result = self.scanner.run_jtag_scan(
                    candidate_channels=self.scanner.io_pin_list,
                    runtime_policy="hardware",
                )
                if hardware_result.ok:
                    sys.stdout.write("hardware mapping: " + str(hardware_result.mapping) + "\n")
                else:
                    sys.stdout.write("hardware scan failed: " + hardware_result.reason + "\n")
                sys.stdout.flush()
            else:
                sys.stdout.write("No IO pins were accepted from the CLI input\n")
                sys.stdout.flush()

        elif selection == 'm':
            sys.stdout.write("Enter pin mask ")
            sys.stdout.flush()
            self.scanner.pin_mask = self.read_cli_unsigned_int()
            self.scanner.pin_max = self.scanner.get_max_pin_from_mask(self.scanner.pin_mask)
            sys.stdout.write("Pin mask set to ")
            sys.stdout.write(bin(self.scanner.pin_mask) + "\n")
            sys.stdout.flush()

        elif selection in ('v', 'd'):
            current = self.scanner.logger.level
            new_level = {
                logging.ERROR: logging.WARNING,
                logging.WARNING: logging.INFO,
                logging.INFO: logging.DEBUG,
                logging.DEBUG: logging.ERROR,
            }[current]
            self.scanner.set_log_level(new_level)
            sys.stdout.write("Log level set to ")
            sys.stdout.write(self.scanner.get_log_level_name() + "\n")
            sys.stdout.flush()

        elif selection == 'L':
            sys.stdout.write("Enter log level (DEBUG, INFO, WARNING, ERROR): ")
            sys.stdout.flush()
            level = self.read_cli_pin_list()
            if level:
                level_name = str(level[0]).upper()
                try:
                    self.scanner.set_log_level(level_name)
                    sys.stdout.write("Log level set to ")
                    sys.stdout.write(self.scanner.get_log_level_name() + "\n")
                except (TypeError, ValueError) as exc:
                    sys.stdout.write("Invalid log level: " + str(level_name) + "\n")
            else:
                sys.stdout.write("No log level entered\n")
            sys.stdout.flush()

        elif selection == 'c':
            sys.stdout.write("Enter clock half cycle in microseconds ")
            sys.stdout.flush()
            self.scanner.clock_half_cycle_us = self.read_cli_unsigned_int()
            sys.stdout.write("Clock half cycle set to ")
            sys.stdout.write(str(self.scanner.clock_half_cycle_us) + "\n")
            sys.stdout.flush()

        else:
            sys.stdout.write("+-------------------------------+\n")
            sys.stdout.write("|  JTAGscan Jtag Pinout Finder  |\n")
            sys.stdout.write("+-------------------------------+\n")
            sys.stdout.write(" a - Automatically find all pins\n")
            sys.stdout.write(" i - IDCODE search for pins\n")
            sys.stdout.write(" b - BYPASS search for pins\n")
            sys.stdout.write(" t - TDI-only BYPASS search\n")
            sys.stdout.write(" l - add a comma-separated IO pin list\n")
            sys.stdout.write(" m - set pin mask, current: 0x")
            sys.stdout.write(hex(self.scanner.pin_mask) + "\n")
            sys.stdout.write(" d - cycle log level. current: ")
            sys.stdout.write(self.scanner.get_log_level_name() + "\n")
            sys.stdout.write(" c - half cycle us, current: ")
            sys.stdout.write(str(self.scanner.clock_half_cycle_us) + "\n")
            sys.stdout.write(" L - set log level by name\n")
            sys.stdout.write(" h - print this help\n")
            sys.stdout.write("+-------------------------------+\n")
            sys.stdout.flush()

    def setup(self):
        self.scanner.pin_max = self.scanner.get_max_pin_from_mask(self.scanner.pin_mask)
        self.scanner.set_log_level(logging.INFO)

    def loop(self):
        self.print_prompt()
        self.command_line_interface()
