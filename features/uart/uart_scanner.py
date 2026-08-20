import math
import time
from dataclasses import dataclass, field

from hardware_backend import DwfHardwareInterface, HardwareBackend

COMMON_UART_BAUD_RATES: tuple[int, ...] = (
    110,
    300,
    600,
    1200,
    2400,
    4800,
    9600,
    19200,
    38400,
    57600,
    115200,
    230400,
    460800,
    921600,
    1000000,
    1500000,
    2000000,
    3000000,
    4000000,
)

FALLBACK_MAX_SAMPLES = 250_000
MAX_ANALYSIS_SAMPLES = 250_000


@dataclass
class UartChannelResult:
    """Decoded UART configuration found on a single pin.

    Each entry in UartAnalysisReport.channels represents one pin/configuration
    combination that produced valid frames from the captured data.

    Attributes:
        rx_pin:        Pin index the data was received on.
        baud_rate:     Detected baud rate in bits per second.
        data_bits:     Number of data bits per frame (7 or 8).
        stop_bits:     Number of stop bits per frame (1 or 2).
        parity:        Parity mode: "none", "even", or "odd".
        inverted:      True when the signal idles LOW (polarity inverted).
        valid_frames:  Number of valid frames decoded.
        decoded_bytes: Raw bytes decoded from the frames.
        decoded_text:  decoded_bytes interpreted as ASCII (replacement for non-printable).
        score:         Internal confidence score used to rank candidates.
    """
    rx_pin: int
    baud_rate: int
    data_bits: int
    stop_bits: int
    parity: str
    inverted: bool
    valid_frames: int
    decoded_bytes: bytes
    decoded_text: str
    score: float


@dataclass
class UartAnalysisReport:
    """Result of a full UART capture analysis.

    The ``channels`` list contains every pin/configuration combination that
    successfully decoded frames, ordered by descending confidence score.  The
    top-level fields mirror the best (highest-scoring) channel so that existing
    code that only inspects a single result still works without changes.

    Attributes:
        ok:                   True when at least one channel decoded valid frames.
        status:               Short status string ("success" or "failed").
        channels:             All decoded configurations, best-first.
        rx_pin:               Best channel's RX pin (None on failure).
        flow_control_pin:     Flow-control pin associated with the best channel.
        baud_rate:            Best channel's baud rate.
        data_bits:            Best channel's data bits.
        stop_bits:            Best channel's stop bits.
        parity:               Best channel's parity.
        valid_frames:         Best channel's frame count.
        decoded_bytes:        Best channel's decoded bytes.
        decoded_text:         Best channel's decoded text.
        inverted:             True when best channel's signal is polarity-inverted.
        reason:               Human-readable summary.
        capture_storage_path: Path where the raw capture was written.
    """
    ok: bool
    status: str
    channels: list[UartChannelResult]
    rx_pin: int | None
    flow_control_pin: int | None
    baud_rate: int | None
    data_bits: int | None
    stop_bits: int | None
    parity: str | None
    valid_frames: int
    decoded_bytes: bytes
    decoded_text: str
    reason: str
    inverted: bool = False
    capture_storage_path: str | None = None


class UartScanner:
    def __init__(self, backend: HardwareBackend):
        self.backend = backend or DwfHardwareInterface()

    def capture_pins(
        self,
        pins: list[int],
        duration_seconds: float,
        sample_rate_hz: int = 8_000_000,
        device_index: int = 0,
    ) -> dict[int, list[int]]:
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be > 0")
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be > 0")

        selected_pins = [int(pin) for pin in pins]
        if not selected_pins:
            return {}

        device = self.backend.open_device(device_index)
        if device is None:
            raise RuntimeError("backend could not open a device for UART capture")

        try:
            capture_hook = getattr(self.backend, "capture_digital_samples", None)
            if callable(capture_hook):
                captured = capture_hook(
                    pins=selected_pins,
                    sample_rate_hz=int(sample_rate_hz),
                    duration_seconds=float(duration_seconds),
                )
                return {int(pin): [1 if sample else 0 for sample in samples] for pin, samples in captured.items()}
            return self._capture_with_digital_reads(selected_pins, duration_seconds, sample_rate_hz)
        finally:
            self.backend.close_device()

    def _capture_with_digital_reads(
        self,
        pins: list[int],
        duration_seconds: float,
        sample_rate_hz: int,
    ) -> dict[int, list[int]]:
        pin_samples: dict[int, list[int]] = {pin: [] for pin in pins}

        start_time = time.perf_counter()
        end_time = start_time + duration_seconds
        sample_period = 1.0 / float(sample_rate_hz)
        next_sample_time = start_time
        samples_taken = 0

        while True:
            now = time.perf_counter()
            if now >= end_time or samples_taken >= FALLBACK_MAX_SAMPLES:
                break
            if now < next_sample_time:
                continue
            for pin in pins:
                level = self.backend.digital_read(pin)
                pin_samples[pin].append(1 if level else 0)
            next_sample_time += sample_period
            samples_taken += 1

        if not pin_samples[pins[0]]:
            for pin in pins:
                level = self.backend.digital_read(pin)
                pin_samples[pin].append(1 if level else 0)

        return pin_samples

    def capture_and_analyze(
        self,
        pins: list[int],
        duration_seconds: float,
        sample_rate_hz: int = 8_000_000,
        device_index: int = 0,
        baud_rates: tuple[int, ...] = COMMON_UART_BAUD_RATES,
        capture_path: str | None = None,
    ) -> UartAnalysisReport:
        captured = self.capture_pins(
            pins=pins,
            duration_seconds=duration_seconds,
            sample_rate_hz=sample_rate_hz,
            device_index=device_index,
        )
        capture_storage_path = self.backend.store_capture_data(
            capture_kind="uart_capture",
            payload={
                "backend": self.backend.backend_name,
                "device_index": int(device_index),
                "pins": [int(pin) for pin in pins],
                "sample_rate_hz": int(sample_rate_hz),
                "duration_seconds": float(duration_seconds),
                "pin_samples": captured,
            },
            capture_path=capture_path,
        )
        report = self.analyze_capture(captured, sample_rate_hz=sample_rate_hz, baud_rates=baud_rates)
        report.capture_storage_path = capture_storage_path
        return report

    @staticmethod
    def _is_inverted(samples: list[int]) -> bool:
        """Return True when the signal appears to be inverted (idles LOW).

        Normal UART idles HIGH. When the dominant level is LOW (more zeros than
        ones) the signal is almost certainly inverted — e.g. connected via an
        RS-232 driver, a MAX232, or a logic-level converter that inverts polarity.
        """
        if not samples:
            return False
        return samples.count(0) > samples.count(1)

    def analyze_capture(
        self,
        pin_samples: dict[int, list[int]],
        sample_rate_hz: int = 8_000_000,
        baud_rates: tuple[int, ...] = COMMON_UART_BAUD_RATES,
    ) -> UartAnalysisReport:
        if not pin_samples:
            return UartAnalysisReport(
                ok=False,
                status="failed",
                channels=[],
                rx_pin=None,
                flow_control_pin=None,
                baud_rate=None,
                data_bits=None,
                stop_bits=None,
                parity=None,
                valid_frames=0,
                decoded_bytes=b"",
                decoded_text="",
                reason="no pin samples were provided",
            )

        decimation_step = 1
        first_samples = next(iter(pin_samples.values()))
        if len(first_samples) > MAX_ANALYSIS_SAMPLES:
            decimation_step = max(1, int(math.ceil(len(first_samples) / MAX_ANALYSIS_SAMPLES)))
            pin_samples = {
                pin: samples[::decimation_step]
                for pin, samples in pin_samples.items()
            }
            sample_rate_hz = max(1, int(round(sample_rate_hz / decimation_step)))

        frame_configs = (
            (8, "none", 1),
            (8, "even", 1),
            (8, "odd", 1),
            (7, "none", 1),
            (7, "even", 1),
            (7, "odd", 1),
            (8, "none", 2),
        )

        # Collect every (pin, config, polarity) combination that decodes frames.
        # Key: (pin, baud_rate, data_bits, parity, stop_bits, inverted) to
        # deduplicate when both polarities happen to decode the same config.
        seen: set[tuple] = set()
        all_candidates: list[tuple] = []

        for pin, samples in pin_samples.items():
            if not samples:
                continue

            inverted_flag = self._is_inverted(samples)
            # Preferred polarity listed first so it wins on equal scores
            if inverted_flag:
                polarities: list[tuple[bool, list[int]]] = [
                    (True, [1 - s for s in samples]),
                    (False, samples),
                ]
            else:
                polarities = [
                    (False, samples),
                    (True, [1 - s for s in samples]),
                ]

            for is_inverted, effective_samples in polarities:
                for baud_rate in baud_rates:
                    for data_bits, parity, stop_bits in frame_configs:
                        decoded = self._decode_uart_stream(
                            samples=effective_samples,
                            sample_rate_hz=sample_rate_hz,
                            baud_rate=baud_rate,
                            data_bits=data_bits,
                            parity=parity,
                            stop_bits=stop_bits,
                        )
                        if decoded is None:
                            continue
                        valid_frames, decoded_bytes, frame_ranges = decoded
                        if valid_frames == 0:
                            continue

                        dedup_key = (pin, baud_rate, data_bits, parity, stop_bits, is_inverted)
                        if dedup_key in seen:
                            continue
                        seen.add(dedup_key)

                        printable_count = sum(
                            1 for byte in decoded_bytes
                            if byte in (9, 10, 13) or 32 <= byte <= 126
                        )
                        printable_ratio = printable_count / max(1, len(decoded_bytes))
                        samples_per_bit = sample_rate_hz / float(baud_rate)
                        timing_weight = max(0.25, min(4.0, samples_per_bit / 16.0))
                        score = (valid_frames * timing_weight) + printable_ratio

                        all_candidates.append((
                            score,
                            pin,
                            baud_rate,
                            data_bits,
                            parity,
                            stop_bits,
                            valid_frames,
                            decoded_bytes,
                            frame_ranges,
                            is_inverted,
                        ))

        if not all_candidates:
            return UartAnalysisReport(
                ok=False,
                status="failed",
                channels=[],
                rx_pin=None,
                flow_control_pin=None,
                baud_rate=None,
                data_bits=None,
                stop_bits=None,
                parity=None,
                valid_frames=0,
                decoded_bytes=b"",
                decoded_text="",
                reason="no valid UART framing found in captured data",
            )

        # Sort all candidates best-first
        all_candidates.sort(key=lambda c: c[0], reverse=True)

        # Build UartChannelResult list — all unique configurations
        channels: list[UartChannelResult] = []
        for (
            score, pin, baud_rate, data_bits, parity, stop_bits,
            valid_frames, decoded_bytes, _frame_ranges, is_inverted,
        ) in all_candidates:
            channels.append(UartChannelResult(
                rx_pin=pin,
                baud_rate=baud_rate,
                data_bits=data_bits,
                stop_bits=stop_bits,
                parity=parity,
                inverted=is_inverted,
                valid_frames=valid_frames,
                decoded_bytes=bytes(decoded_bytes),
                decoded_text=bytes(decoded_bytes).decode("ascii", errors="replace"),
                score=score,
            ))

        # Best candidate drives the top-level report fields
        (
            _score,
            rx_pin,
            baud_rate,
            data_bits,
            parity,
            stop_bits,
            valid_frames,
            decoded_bytes,
            best_frame_ranges,
            result_inverted,
        ) = all_candidates[0]

        # Use the same polarity for flow-control detection as was used for RX
        if result_inverted:
            flow_samples = {p: [1 - s for s in samps] for p, samps in pin_samples.items()}
        else:
            flow_samples = pin_samples
        flow_pin = self._find_flow_control_pin(rx_pin, best_frame_ranges, flow_samples)

        reason = (
            f"{len(channels)} UART configuration(s) found across "
            f"{len({c.rx_pin for c in channels})} pin(s)"
        )
        if result_inverted:
            reason += " (best channel: signal polarity inverted — idle-LOW detected)"

        return UartAnalysisReport(
            ok=True,
            status="success",
            channels=channels,
            rx_pin=rx_pin,
            flow_control_pin=flow_pin,
            baud_rate=baud_rate,
            data_bits=data_bits,
            stop_bits=stop_bits,
            parity=parity,
            valid_frames=valid_frames,
            decoded_bytes=bytes(decoded_bytes),
            decoded_text=bytes(decoded_bytes).decode("ascii", errors="replace"),
            reason=reason,
            inverted=result_inverted,
        )

    def _decode_uart_stream(
        self,
        samples: list[int],
        sample_rate_hz: int,
        baud_rate: int,
        data_bits: int,
        parity: str,
        stop_bits: int,
    ) -> tuple[int, list[int], list[tuple[int, int]]] | None:
        samples_per_bit = sample_rate_hz / float(baud_rate)
        parity_bits = 0 if parity == "none" else 1
        frame_bits = 1 + data_bits + parity_bits + stop_bits
        frame_span = int(math.ceil(frame_bits * samples_per_bit))
        if frame_span <= 0:
            return None

        decoded_bytes: list[int] = []
        frame_ranges: list[tuple[int, int]] = []
        valid_frames = 0
        next_start_index = 1

        for idx in range(1, len(samples)):
            if idx < next_start_index:
                continue
            if samples[idx - 1] != 1 or samples[idx] != 0:
                continue
            high_run = 0
            for back_idx in range(idx - 1, -1, -1):
                if samples[back_idx] != 1:
                    break
                high_run += 1
            if high_run < int(samples_per_bit * 0.8):
                continue

            start_center_idx = int(round(idx + (0.5 * samples_per_bit)))
            if start_center_idx >= len(samples) or samples[start_center_idx] != 0:
                continue

            bit_values: list[int] = []
            frame_ok = True
            for bit_idx in range(data_bits):
                sample_idx = int(round(idx + ((1.5 + bit_idx) * samples_per_bit)))
                if sample_idx >= len(samples):
                    frame_ok = False
                    break
                bit_values.append(1 if samples[sample_idx] else 0)

            if not frame_ok:
                continue

            parity_sample_idx = int(round(idx + ((1.5 + data_bits) * samples_per_bit)))
            if parity != "none":
                if parity_sample_idx >= len(samples):
                    continue
                parity_value = 1 if samples[parity_sample_idx] else 0
                ones = sum(bit_values) & 1
                expected = ones if parity == "even" else 1 - ones
                if parity_value != expected:
                    next_start_index = idx + max(1, int(samples_per_bit * 0.5))
                    continue

            stop_start = idx + (1.5 + data_bits + parity_bits) * samples_per_bit
            for stop_idx in range(stop_bits):
                sample_idx = int(round(stop_start + (stop_idx * samples_per_bit)))
                if sample_idx >= len(samples) or samples[sample_idx] != 1:
                    frame_ok = False
                    break
            if not frame_ok:
                next_start_index = idx + max(1, int(samples_per_bit * 0.5))
                continue

            value = 0
            for bit_idx, bit_value in enumerate(bit_values):
                value |= (bit_value << bit_idx)
            decoded_bytes.append(value)
            valid_frames += 1
            frame_end = min(len(samples), idx + frame_span)
            frame_ranges.append((idx, frame_end))
            next_start_index = frame_end

        return valid_frames, decoded_bytes, frame_ranges

    def _find_flow_control_pin(
        self,
        rx_pin: int,
        frame_ranges: list[tuple[int, int]],
        pin_samples: dict[int, list[int]],
    ) -> int | None:
        if not frame_ranges:
            return None

        sample_count = len(pin_samples[rx_pin])
        active_mask = [False] * sample_count
        for start, end in frame_ranges:
            bounded_start = max(0, start)
            bounded_end = min(sample_count, end)
            for idx in range(bounded_start, bounded_end):
                active_mask[idx] = True

        best_pin = None
        best_score = 0.0

        for pin, samples in pin_samples.items():
            if pin == rx_pin or len(samples) != sample_count:
                continue

            active_transitions = 0
            idle_transitions = 0
            active_levels = 0
            idle_levels = 0
            active_count = 0
            idle_count = 0

            for idx in range(sample_count):
                if active_mask[idx]:
                    active_levels += samples[idx]
                    active_count += 1
                else:
                    idle_levels += samples[idx]
                    idle_count += 1

            for idx in range(1, sample_count):
                if samples[idx] == samples[idx - 1]:
                    continue
                if active_mask[idx]:
                    active_transitions += 1
                else:
                    idle_transitions += 1

            if active_count == 0 or idle_count == 0:
                continue

            active_mean = active_levels / active_count
            idle_mean = idle_levels / idle_count
            score = (active_transitions - idle_transitions) + (2.0 * abs(active_mean - idle_mean))
            if score > best_score and active_transitions > 0:
                best_pin = pin
                best_score = score

        return best_pin
