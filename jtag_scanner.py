import sys
import time
import itertools
import logging
from dataclasses import dataclass
from typing import Any

from hardware_backend import DwfHardwareInterface, HardwareBackend

LOW = 0
HIGH = 1

PIN_MASK = 0b11111100
PIN_NOT_USED = 0xff

IR_LEN_MIN = 2
IR_LEN_MAX = 10

BYPASS_LEN_MAX = 1024

CLOCK_HALF_CYCLE_US = 32

IDLE_TO_SHIFT_DR_CMD = 0b001
IDLE_TO_SHIFT_DR_LEN = 3

IDLE_TO_SHIFT_IR_CMD = 0b0011
IDLE_TO_SHIFT_IR_LEN = 4

EXIT_IR_TO_SHIFT_DR_CMD = 0b0011
EXIT_IR_TO_SHIFT_DR_LEN = 4

PROMPT = "> "
ROW_FORMAT = "|%4d |%4d |%4d |%12lx |\r\n"
ROW_FORMAT_TDI = "|%4d |%4d |%4d |%4d |%6ld |\r\n"


@dataclass
class JtagScanResult:
    """Result of a JTAG scan operation.

    Attributes:
        ok: True when the scan succeeded.
        status: Short status string (e.g., 'success', 'failed', 'simulation').
        mapping: Mapping of JTAG signals to channel indices when found, or None.
        channels: List of channel indices that were considered during the scan.
        reason: Human-readable reason for failure or additional details.
    """
    ok: bool
    status: str
    mapping: dict | None
    channels: list[int]
    reason: str


class JtagScanner:
    """Core JTAG scanning logic and hardware abstraction.

    This class coordinates access to a hardware backend (DWF by default) to
    discover which digital I/O channels correspond to JTAG signals (TCK, TMS,
    TDO, and optionally TDI). The scanner provides both simulation helpers and
    hardware-driven scan flows.
    """
    def __init__(
        self,
        backend: HardwareBackend,
        pin_mask: int = PIN_MASK,
        pin_max: int = 0,
        clock_half_cycle_us: int = CLOCK_HALF_CYCLE_US,
        bypass_pattern: int = 0b10011101001101101000010111001001,
        ir_length: int = 2,
        log_level: int = logging.WARNING,
    ):
        """Initialize a JtagScanner.

        Args:
            pin_mask: Bitmask indicating which DWF channels are usable.
            pin_max: Maximum number of pins (channels) to consider.
            clock_half_cycle_us: Clock half-cycle in microseconds used for timing.
            bypass_pattern: Known bypass pattern used to detect TDI/TDO when
                shifting bypass data.
            ir_length: Expected length of the JTAG IR register when probing.
            log_level: Initial logging level (int or name string accepted by
                set_log_level).
            backend: Optional custom HardwareBackend implementation. When None
                the default DwfHardwareInterface is used.
        """
        self.pin_mask = int(pin_mask)
        self.pin_max = int(pin_max)
        self.clock_half_cycle_us = int(clock_half_cycle_us)
        self.bypass_pattern = int(bypass_pattern)
        self.ir_length = int(ir_length)
        self.tck_pin = 2
        self.tms_pin = 3
        self.tdo_pin = 4
        self.tdi_pin = 5
        self.pin_blacklist = 0
        self.io_pin_list: list[int] = []

        self._soft_pin_mode: dict[int, object] = {}
        self._soft_pin_level: dict[int, bool] = {}

        self.backend = backend or DwfHardwareInterface()
        self.logger = logging.getLogger(__name__)
        self.set_log_level(log_level)
        self.output = None

    def set_log_level(self, log_level):
        """Set the logging level for the scanner.

        Accepts either an integer logging level (e.g. logging.DEBUG) or a
        case-insensitive string name such as 'DEBUG' or 'INFO'. Raises
        ValueError if a string name does not map to a valid logging level and
        TypeError if the final value is not an integer.
        """

        if isinstance(log_level, str):
            level = getattr(logging, log_level.upper(), None)
            if level is None:
                raise ValueError("invalid logging level")
            log_level = level

        if not isinstance(log_level, int):
            raise TypeError("log_level must be an int or valid logging level name")

        self.logger.setLevel(log_level)

    def get_log_level_name(self):
        """Return the human-readable name of the current log level."""
        return logging.getLevelName(self.logger.level)

    @staticmethod
    def get_version(value):
        """Extract JTAG IDCODE version field.

        IDCODE is a 32-bit value; the version is stored in bits 28-31.
        """
        return (value >> 28) & 0xf

    @staticmethod
    def get_part_no(value):
        """Extract the part number field from a 32-bit IDCODE.

        The part number is typically stored in bits 12-27.
        """
        return (value >> 12) & 0xffff

    @staticmethod
    def get_manufacturer(value):
        """Extract the manufacturer code from a 32-bit IDCODE.

        The manufacturer ID is typically stored in bits 1-11.
        """
        return (value >> 1) & 0x7ff

    @staticmethod
    def bit_read(value, bit_index):
        """Read a single bit from an integer at the given index.

        Returns 1 or 0. Raises TypeError if value is not an int.
        """
        if isinstance(value, int):
            return 1 if ((value >> bit_index) & 1) else 0
        raise TypeError("bitRead expects an integer mask/value")

    @staticmethod
    def bit_write(value, bit_index, bit_val):
        """Set or clear a single bit in an integer and return the new value.

        bit_val truthy sets the bit, falsy clears it.
        """
        if bit_val:
            return value | (1 << bit_index)
        return value & ~(1 << bit_index)

    def scan_channel_combinations(self, candidate_channels, evaluator, width):
        """Try permutations of candidate_channels and invoke evaluator until one succeeds.

        The evaluator is called as evaluator(width, proposal_list) and should
        return a truthy value to indicate a successful mapping. Returns the
        successful proposal as a list, or None when no permutation matches.
        """

        ordered = []
        for channel in candidate_channels:
            try:
                ordered.append(int(channel))
            except (TypeError, ValueError):
                continue

        seen = set()
        deduped = []
        for channel in ordered:
            if channel not in seen:
                seen.add(channel)
                deduped.append(channel)

        for proposal in itertools.permutations(deduped, width):
            result = evaluator(width, list(proposal))
            if result:
                return list(proposal)

        return None

    def simulate_jtag_pin_mapping(self, candidate_channels):
        """Synthesize a plausible JTAG mapping from candidate channels.

        This function does not probe hardware; it creates a simple mapping based
        on ordering of supplied candidate channels: first three map to TCK/TMS/TDO
        and the fourth, if present, maps to TDI.
        """

        channels = self._coerce_candidate_list(candidate_channels)
        if not channels:
            return None

        if len(channels) >= 4:
            return {
                "TCK": channels[0],
                "TMS": channels[1],
                "TDO": channels[2],
                "TDI": channels[3],
            }

        if len(channels) >= 3:
            return {
                "TCK": channels[0],
                "TMS": channels[1],
                "TDO": channels[2],
            }

        return None

    def find_jtag_pin_mapping(self, candidate_channels):
        """Attempt to discover a JTAG mapping from candidate channels.

        Tries an IDCODE-based discovery for TCK/TMS/TDO and then attempts to
        discover TDI via a bypass test. Falls back to a full bypass scan when
        IDCODE-based discovery fails.
        Returns a mapping dict or None when no mapping is found.
        """

        channels = self._coerce_candidate_list(candidate_channels)
        if not channels:
            return None

        idcode_result = self.scan_channel_combinations(channels, self.test_id_code, 3)
        if idcode_result:
            mapping = {
                "TCK": idcode_result[0],
                "TMS": idcode_result[1],
                "TDO": idcode_result[2],
            }

            remaining = [idx for idx in channels if idx not in idcode_result]
            tdi_result = self.scan_channel_combinations(remaining, self.test_bypass, 1)

            if tdi_result:
                mapping["TDI"] = tdi_result[0]
                return mapping

            full_bypass_result = self.scan_channel_combinations(channels, self.test_bypass, 4)
            if full_bypass_result:
                return {
                    "TCK": full_bypass_result[0],
                    "TMS": full_bypass_result[1],
                    "TDO": full_bypass_result[2],
                    "TDI": full_bypass_result[3],
                }

            return None

        full_bypass_result = self.scan_channel_combinations(channels, self.test_bypass, 4)
        if full_bypass_result:
            return {
                "TCK": full_bypass_result[0],
                "TMS": full_bypass_result[1],
                "TDO": full_bypass_result[2],
                "TDI": full_bypass_result[3],
            }

        return None

    def open_dwf_device(self, device_index=0):
        """Open a DWF device by index via the configured backend.

        Returns a device object or None on failure.
        """
        return self.backend.open_device(device_index)

    def close_dwf_device(self):
        """Close the previously opened DWF device via the backend."""
        return self.backend.close_device()

    def get_dwf_channel_indices(self, pin_mask_override=None, pin_max_override=None):
        """Return a list of available DWF channel indices from the backend.

        Accepts optional overrides for pin_mask and pin_max.
        """
        return self.backend.get_channel_indices(
            self.pin_mask,
            self.pin_max,
            pin_mask_override=pin_mask_override,
            pin_max_override=pin_max_override,
        )

    def dwf_runtime_ready(self):
        """Query the backend to determine whether the hardware runtime is ready."""
        return self.backend.runtime_ready()

    def _coerce_candidate_list(self, candidate_channels):
        """Normalize candidate_channels into a list of ints.

        Accepts None, a single value, or an iterable of values. Returns an empty
        list when candidate_channels is None.
        """
        if candidate_channels is None:
            return []
        if isinstance(candidate_channels, (list, tuple, set)):
            return [int(value) for value in candidate_channels]
        return [int(candidate_channels)]

    def _resolve_runtime_device(self, device_or_index):
        """Resolve a runtime device descriptor using the backend.

        The backend may accept either an index or an existing device object and
        returns a device instance suitable for use with low-level backend calls.
        """
        return self.backend.resolve_device(device_or_index)

    def scan_dwf_jtag_pins(self, device_index=0, candidate_channels=None, pin_mask_override=None, pin_max_override=None, runtime_policy="hardware"):
        """Convenience wrapper: scan DWF-attached device for JTAG pins.

        Delegates to run_jtag_scan() preserving a similar API surface.
        """
        return self.run_jtag_scan(
            device_index=device_index,
            candidate_channels=candidate_channels,
            pin_mask_override=pin_mask_override,
            pin_max_override=pin_max_override,
            runtime_policy=runtime_policy,
        )

    def run_jtag_scan(self, device_index=0, candidate_channels=None, pin_mask_override=None, pin_max_override=None, runtime_policy="hardware", device=None):
        """Run a full JTAG scan using either hardware or simulation.

        Parameters mirror the public API: device_index chooses a DWF device by
        index, candidate_channels may be provided to avoid querying hardware
        channel lists, and runtime_policy selects between 'hardware' and
        'simulation'. When a device object is provided it is validated and used
        directly. Returns a JtagScanResult instance describing the outcome.
        """

        if runtime_policy not in {"hardware", "simulation"}:
            runtime_policy = "hardware"

        if candidate_channels is None and device is not None:
            device = self._resolve_runtime_device(device)
            if device is None:
                return JtagScanResult(
                    ok=False,
                    status="failed",
                    mapping=None,
                    channels=[],
                    reason="caller supplied a device object that was not acceptable to dwfpy",
                )

        if candidate_channels is not None:
            channels = self._coerce_candidate_list(candidate_channels)
            if runtime_policy == "simulation":
                mapping = self.simulate_jtag_pin_mapping(channels)
                if mapping:
                    return JtagScanResult(
                        ok=True,
                        status="simulation",
                        mapping=mapping,
                        channels=channels,
                        reason="simulation mapping synthesized from candidate channels",
                    )
                return JtagScanResult(
                    ok=False,
                    status="failed",
                    mapping=None,
                    channels=channels,
                    reason="simulation mode could not synthesize a mapping from the supplied candidate list",
                )
        elif runtime_policy == "simulation":
            return JtagScanResult(
                ok=False,
                status="failed",
                mapping=None,
                channels=[],
                reason="simulation mode requested without a candidate list",
            )
        elif device is not None:
            device = self._resolve_runtime_device(device)
            if device is None:
                return JtagScanResult(
                    ok=False,
                    status="failed",
                    mapping=None,
                    channels=[],
                    reason="caller device object is not acceptable to dwfpy",
                )

            self._dwf_device = device
            self._dwf_connected = getattr(device, "is_open", False)
            if not self._dwf_connected:
                return JtagScanResult(
                    ok=False,
                    status="failed",
                    mapping=None,
                    channels=[],
                    reason="caller device object is not open",
                )

            try:
                channels = self.get_dwf_channel_indices(
                    pin_mask_override=pin_mask_override,
                    pin_max_override=pin_max_override,
                )
            finally:
                self._dwf_device = None
                self._dwf_connected = False
        else:
            device = self.open_dwf_device(device_index)
            if device is None:
                return JtagScanResult(
                    ok=False,
                    status="failed",
                    mapping=None,
                    channels=[],
                    reason="DWF runtime could not open a device",
                )

            if not self.dwf_runtime_ready():
                self.close_dwf_device()
                return JtagScanResult(
                    ok=False,
                    status="failed",
                    mapping=None,
                    channels=[],
                    reason="DWF runtime is not ready for JTAG scanning",
                )

            try:
                channels = self.get_dwf_channel_indices(
                    pin_mask_override=pin_mask_override,
                    pin_max_override=pin_max_override,
                )
            finally:
                self.close_dwf_device()

        if not channels:
            return JtagScanResult(
                ok=False,
                status="failed",
                mapping=None,
                channels=channels,
                reason="No usable DWF or candidate channels were found",
            )

        mapping = self.find_jtag_pin_mapping(channels)
        if mapping:
            return JtagScanResult(
                ok=True,
                status="success",
                mapping=mapping,
                channels=channels,
                reason="JTAG mapping found",
            )

        return JtagScanResult(
            ok=False,
            status="failed",
            mapping=None,
            channels=channels,
            reason="No valid JTAG pin mapping found for the supplied channel list",
        )

    def _get_dwf_root(self):
        """Return the dwfpy root module used by legacy helpers.

        Kept for internal compatibility with code expecting a dwfpy symbol.
        """
        return dwfpy

    def _get_dwf_channel(self, pin):
        """Return a backend channel object for the given pin index."""
        return self.backend.get_channel(pin)

    def _configure_dwf_device(self):
        """Configure the backend device for JTAG scanning.

        Delegates to the backend implementation.
        """
        return self.backend.configure_device()

    def _ensure_dwf_initialized(self):
        """Ensure the backend library has been initialized."""
        return self.backend.ensure_initialized()

    def digital_write(self, pin, value):
        """Write a digital output to the given pin via the backend.

        The method stores the level in an internal soft cache so reads can fall
        back to the last known value when the backend returns None.
        """
        value = bool(value)
        result = self.backend.digital_write(pin, value)
        self._soft_pin_level[pin] = value
        return result

    def digital_read(self, pin):
        """Read a digital input from the backend, falling back to cached level.

        If the backend returns None this method returns the previously cached
        soft level (or LOW if unknown).
        """
        result = self.backend.digital_read(pin)
        if result is None:
            return bool(self._soft_pin_level.get(pin, LOW))
        self._soft_pin_level[pin] = result
        return result

    def pin_mode(self, pin, mode):
        """Set the pin mode through the backend and cache the requested mode."""
        result = self.backend.pin_mode(pin, mode)
        self._soft_pin_mode[pin] = mode
        return result

    def delay_microseconds(self, us):
        """Sleep for the requested number of microseconds."""
        time.sleep(us / 1000000.0)

    def delay(self, ms):
        """Sleep for the requested number of milliseconds."""
        time.sleep(ms / 1000.0)

    def move_bit(self, tms_val, tdi_val):
        """Toggle TMS/TDI/TCK to perform a single JTAG bit transfer.

        Drives TMS and TDI, pulses TCK, then reads and returns TDO. Timing is
        controlled by the scanner's clock_half_cycle_us setting.
        """
        self.digital_write(self.tms_pin, tms_val)
        self.digital_write(self.tdi_pin, tdi_val)
        self.digital_write(self.tck_pin, HIGH)
        self.delay_microseconds(self.clock_half_cycle_us)
        self.digital_write(self.tck_pin, LOW)
        tdo_val = self.digital_read(self.tdo_pin)
        self.delay_microseconds(self.clock_half_cycle_us)

        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(
                "| --- | --- | --- | --- | ----- |%2d |%2d |%2d |",
                tms_val,
                tdi_val,
                tdo_val,
            )

        return tdo_val

    def move_bits(self, tms_val, tdi_val, tdo_val, width):
        """Shift multiple bits through JTAG by repeated move_bit calls.

        tms_val and tdi_val are treated as bitfields. If tdo_val is a mutable
        sequence it is used to return the collected TDO bitfield in index 0.
        """
        tdo_temp_val = 0
        for i in range(width):
            bit = self.move_bit((tms_val >> i) & 1, (tdi_val >> i) & 1)
            if bit:
                tdo_temp_val |= (1 << i)

        if tdo_val is not None:
            tdo_val[0] = tdo_temp_val

    def reset_test_logic(self):
        """Drive the TAP controller to the Test-Logic-Reset state sequence."""
        self.move_bits(0b011111, 0, None, 6)

    def setup_pins(self):
        """Configure pin directions and initial levels for scanning.

        Sets all channels indicated by pin_mask to INPUT, then configures the
        canonical JTAG pins (TCK/TMS/TDO/TDI) to their required modes.
        """
        for idx in range(self.pin_max):
            if self.bit_read(self.pin_mask, idx):
                self.pin_mode(idx, "INPUT")

        self.pin_mode(self.tck_pin, "OUTPUT")
        self.pin_mode(self.tms_pin, "OUTPUT")
        self.pin_mode(self.tdo_pin, "INPUT_PULLUP")

        self.digital_write(self.tck_pin, LOW)
        self.digital_write(self.tms_pin, LOW)

        if self.tdi_pin != PIN_NOT_USED:
            self.digital_write(self.tdi_pin, LOW)
            self.pin_mode(self.tdi_pin, "OUTPUT")

    def reset_pins(self):
        """Reset standard JTAG pin modes to inputs."""
        self.pin_mode(self.tck_pin, "INPUT")
        self.pin_mode(self.tms_pin, "INPUT")
        self.pin_mode(self.tdi_pin, "INPUT")
        self.pin_mode(self.tdo_pin, "INPUT")

    def bit_count(self, value, bitState):
        """Count the number of bits in 'value' equal to bitState (0 or 1).

        Only examines the low 32 bits.
        """
        count = 0
        for i in range(32):
            value_bit = self.bit_read(value, i)
            if value_bit == bitState:
                count += 1
        return count

    def verify_id_code(self, id_code):
        """Validate an IDCODE value for basic plausibility.

        Returns True when the provided id_code looks like a valid IDCODE based
        on manufacturer, part number, version, and bit distribution checks.
        """
        return not (
            self.bit_read(id_code, 0) == 0 or
            self.get_manufacturer(id_code) == 0 or
            self.get_manufacturer(id_code) == 0x7ff or
            self.get_part_no(id_code) == 0 or
            self.get_part_no(id_code) == 0xffff or
            self.get_version(id_code) == 0xf or
            self.bit_count(id_code, HIGH) < 10 or
            self.bit_count(id_code, LOW) < 10
        )

    def read_id_code(self):
        """Read the IDCODE register from the JTAG chain.

        Returns the IDCODE (32-bit int) when it passes verification or 0 when
        the IDCODE appears invalid.
        """
        self.setup_pins()
        self.reset_test_logic()
        self.move_bits(IDLE_TO_SHIFT_DR_CMD, 0, None, IDLE_TO_SHIFT_DR_LEN - 1)
        tdo = [0]
        self.move_bits(1 << 31, 0, tdo, 32)
        id_code = tdo[0]
        return id_code if self.verify_id_code(id_code) else 0

    def passthrough_data(self):
        """Shift data through the BYPASS/IR path to detect bypass pattern length.

        Returns the number of bits shifted until the observed bypass pattern
        repeats (or 0 if not detected within BYPASS_LEN_MAX).
        """
        self.setup_pins()
        self.reset_test_logic()
        self.move_bits(IDLE_TO_SHIFT_IR_CMD, 0, None, IDLE_TO_SHIFT_IR_LEN)
        self.move_bits(1 << 7, 0b11111111, None, 8)
        self.move_bits(EXIT_IR_TO_SHIFT_DR_CMD, 0, None, EXIT_IR_TO_SHIFT_DR_LEN)

        bypass_value = 0
        for i in range(BYPASS_LEN_MAX):
            bit_value = self.move_bit(0, (self.bypass_pattern >> (i % 32)) & 1)
            bypass_value = (bypass_value >> 1) & 0xffffffff
            if bit_value:
                bypass_value |= (1 << 31)

            if bypass_value == self.bypass_pattern:
                return i

        return 0

    def get_next_pin(self, pinIndex, pinCount, pinArray):
        """Return the next candidate pin index for the given slot.

        Scans from pinArray[pinIndex] up to pin_max and returns the first index
        that is enabled in pin_mask, not blacklisted, and not already present in
        pinArray. Returns -1 when no candidate is found.
        """
        candidate = -1
        for idx in range(pinArray[pinIndex], self.pin_max):
            if self.bit_read(self.pin_mask, idx) and not self.bit_read(self.pin_blacklist, idx):
                duplicate = False
                for j in range(pinCount):
                    if pinArray[j] == idx:
                        duplicate = True
                        break
                if not duplicate:
                    candidate = idx
                    break

        return candidate

    def identify_pins(self, pinCount, evaluator):
        """Brute-force search for a set of pins that satisfy evaluator.

        The evaluator is called repeatedly with (pinCount, counters) where
        counters is a list of candidate pin indices. If the evaluator returns a
        truthy value it is returned immediately. The function prints a simple
        ASCII banner to stdout to indicate progress and returns False on failure.
        """
        counters = [-1] * pinCount
        noMoreCandidates = False

        sys.stdout.write("+-------------------------------+\n")
        sys.stdout.flush()

        for idx in range(pinCount):
            counters[idx] = self.get_next_pin(idx, pinCount, counters)

        counterIndex = pinCount - 1
        while True:
            result = evaluator(pinCount, counters)
            if result:
                sys.stdout.write("+----------- SUCCESS -----------+\n")
                sys.stdout.flush()
                return result

            while True:
                candidate = self.get_next_pin(counterIndex, pinCount, counters)
                if candidate < 0:
                    if counterIndex == 0:
                        noMoreCandidates = True
                        break

                    counters[counterIndex] = 0xff
                    counterIndex -= 1
                else:
                    counters[counterIndex] = candidate
                    counterIndex += 1

                    for idx in range(counterIndex, pinCount):
                        counters[idx] = self.get_next_pin(idx, pinCount, counters)

                    counterIndex = pinCount - 1
                    break

            if noMoreCandidates:
                break

        sys.stdout.write("+------------ FAIL -------------+\n")
        sys.stdout.flush()
        return False

    def print_result_row(self, include_tdi, value):
        """Print a formatted result row either to the UI output object or stdout.

        When an external UI object is attached to self.output and provides a
        print_result_row method the UI will be used; otherwise the scanner prints
        directly to stdout using ROW_FORMAT/_TDI constants.
        """
        dbgBuffer = (
            ROW_FORMAT_TDI % (self.tck_pin, self.tms_pin, self.tdo_pin, self.tdi_pin, value)
            if include_tdi
            else ROW_FORMAT % (self.tck_pin, self.tms_pin, self.tdo_pin, value)
        )

        if self.output and hasattr(self.output, 'print_result_row'):
            self.output.print_result_row(include_tdi, value)
        else:
            sys.stdout.write(dbgBuffer)
            sys.stdout.flush()

    def test_id_code(self, pinCount, counters):
        """Evaluator used during identification that reads and validates IDCODE.

        Expects counters to contain at least three indices for TCK/TMS/TDO. The
        method attempts to read a stable IDCODE value and prints the result row
        before returning True when a plausible IDCODE is observed.
        """
        self.tck_pin = counters[0]
        self.tms_pin = counters[1]
        self.tdo_pin = counters[2]
        self.tdi_pin = PIN_NOT_USED

        status = False
        id_code = self.read_id_code()
        id_code_prev = id_code

        if id_code != 0 and id_code != 4294967295:
            status = True
            for _ in range(2):
                id_code = self.read_id_code()
                if id_code != id_code_prev:
                    status = False
                    break

        if status or self.logger.isEnabledFor(logging.INFO):
            self.print_result_row(False, id_code)

        return status

    def test_bypass(self, pinCount, counters):
        """Evaluator used during identification that exercises the BYPASS path.

        When pinCount == 1 the single counter is treated as the TDI pin, otherwise
        counters are used for TCK/TMS/TDO/TDI. The function returns True when a
        non-zero bypass width is detected and prints the result row.
        """
        if pinCount == 1:
            self.tdi_pin = counters[0]
        else:
            self.tck_pin = counters[0]
            self.tms_pin = counters[1]
            self.tdo_pin = counters[2]
            self.tdi_pin = counters[3]

        status = False
        width = self.passthrough_data()
        if width > 0:
            status = True

        if status or self.logger.isEnabledFor(logging.INFO):
            self.print_result_row(True, width)

        return status

    def get_max_pin_from_mask(self, pin_mask_value):
        """Return one plus the highest pin index set in pin_mask_value.

        This is used to derive a sensible pin_max when only a mask is provided.
        """
        highest_pin = 0
        for i in range(64):
            if self.bit_read(pin_mask_value, i) == HIGH:
                highest_pin = i
        return highest_pin + 1
