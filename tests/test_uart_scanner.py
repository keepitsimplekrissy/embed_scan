import time

from hardware_backend import HardwareBackend
from features.uart import UartScanner


class DummyCaptureBackend(HardwareBackend):
    def __init__(self, capture_data):
        super().__init__()
        self.capture_data = capture_data
        self.log = []

    def open_device(self, device_index=0):
        self.log.append(("open_device", device_index))
        return self

    def close_device(self):
        self.log.append("close_device")

    def runtime_ready(self):
        return True

    def get_channel_indices(self, pin_mask, pin_max, pin_mask_override=None, pin_max_override=None):
        return list(self.capture_data.keys())

    def resolve_device(self, device_or_index):
        return self

    def get_channel(self, pin):
        return None

    def configure_device(self):
        return True

    def ensure_initialized(self):
        return True

    def digital_write(self, pin, value):
        return value

    def digital_read(self, pin):
        return 1

    def pin_mode(self, pin, mode):
        return True

    def capture_digital_samples(self, pins, sample_rate_hz, duration_seconds):
        self.log.append(("capture", tuple(pins), sample_rate_hz, duration_seconds))
        return {pin: self.capture_data[pin] for pin in pins}

    def store_capture_data(self, capture_kind, payload, capture_path=None):
        self.log.append(("store_capture_data", capture_kind, payload, capture_path))
        return "/tmp/fake-uart-capture.json"


class DummyNoCaptureBackend(HardwareBackend):
    def __init__(self):
        super().__init__()
        self.log = []

    def open_device(self, device_index=0):
        self.log.append(("open_device", device_index))
        return self

    def close_device(self):
        self.log.append("close_device")

    def runtime_ready(self):
        return True

    def get_channel_indices(self, pin_mask, pin_max, pin_mask_override=None, pin_max_override=None):
        return [1]

    def resolve_device(self, device_or_index):
        return self

    def get_channel(self, pin):
        return None

    def configure_device(self):
        return True

    def ensure_initialized(self):
        return True

    def digital_write(self, pin, value):
        return value

    def digital_read(self, pin):
        return 1

    def pin_mode(self, pin, mode):
        return True


def _build_uart_line_samples(
    payload: bytes,
    sample_rate_hz: int,
    baud_rate: int,
    idle_bits: int = 3,
):
    samples_per_bit = max(1, int(round(sample_rate_hz / baud_rate)))
    line = [1] * (idle_bits * samples_per_bit)
    frame_ranges = []
    for value in payload:
        frame_start = len(line)
        bits = [0]
        bits.extend([(value >> bit_idx) & 1 for bit_idx in range(8)])
        bits.append(1)
        for bit in bits:
            line.extend([bit] * samples_per_bit)
        frame_ranges.append((frame_start, len(line)))
        line.extend([1] * samples_per_bit)
    line.extend([1] * (idle_bits * samples_per_bit))
    return line, frame_ranges


def test_capture_pins_uses_backend_capture_hook():
    backend = DummyCaptureBackend({3: [1, 0, 1], 4: [0, 1, 0]})
    scanner = UartScanner(backend)

    captured = scanner.capture_pins([3, 4], duration_seconds=0.001)

    assert captured == {3: [1, 0, 1], 4: [0, 1, 0]}
    assert ("open_device", 0) in backend.log
    assert ("capture", (3, 4), 8_000_000, 0.001) in backend.log
    assert "close_device" in backend.log


def test_capture_and_analyze_stores_capture_payload():
    sample_rate_hz = 8_000_000
    baud_rate = 115200
    rx_samples, _frame_ranges = _build_uart_line_samples(b"A", sample_rate_hz, baud_rate)
    backend = DummyCaptureBackend({3: rx_samples})
    scanner = UartScanner(backend)

    report = scanner.capture_and_analyze(
        pins=[3],
        duration_seconds=0.001,
        sample_rate_hz=sample_rate_hz,
        baud_rates=(baud_rate,),
        capture_path="/tmp/uart-out",
    )

    store_calls = [entry for entry in backend.log if isinstance(entry, tuple) and entry[0] == "store_capture_data"]
    assert len(store_calls) == 1
    _, capture_kind, payload, capture_path = store_calls[0]
    assert capture_kind == "uart_capture"
    assert capture_path == "/tmp/uart-out"
    assert payload["backend"] == backend.backend_name
    assert payload["pins"] == [3]
    assert payload["sample_rate_hz"] == sample_rate_hz
    assert 3 in payload["pin_samples"]
    assert report.capture_storage_path == "/tmp/fake-uart-capture.json"


def test_analyze_capture_detects_uart_and_flow_control_pin():
    sample_rate_hz = 8_000_000
    baud_rate = 115200
    rx_samples, frame_ranges = _build_uart_line_samples(b"Hi", sample_rate_hz, baud_rate)
    flow_samples = [1] * len(rx_samples)
    for start, end in frame_ranges:
        for idx in range(start, end):
            flow_samples[idx] = 0
    idle_samples = [1] * len(rx_samples)

    backend = DummyCaptureBackend({2: idle_samples, 3: rx_samples, 5: flow_samples})
    scanner = UartScanner(backend)
    report = scanner.analyze_capture({2: idle_samples, 3: rx_samples, 5: flow_samples}, sample_rate_hz=sample_rate_hz)

    assert report.ok is True
    assert report.rx_pin == 3
    assert report.baud_rate == baud_rate
    assert report.data_bits == 8
    assert report.stop_bits == 1
    assert report.parity == "none"
    assert report.flow_control_pin == 5
    assert report.decoded_bytes == b"Hi"


def test_capture_pins_fallback_is_time_bounded():
    backend = DummyNoCaptureBackend()
    scanner = UartScanner(backend)
    start_time = time.perf_counter()
    captured = scanner.capture_pins([1], duration_seconds=0.01, sample_rate_hz=8_000_000)
    elapsed = time.perf_counter() - start_time

    assert elapsed < 1.0
    assert 1 in captured
    assert len(captured[1]) > 0
    assert len(captured[1]) <= 250_000
    assert "close_device" in backend.log


# ---------------------------------------------------------------------------
# Inverted-polarity (idle-LOW) detection tests
# ---------------------------------------------------------------------------

def _invert_samples(samples: list[int]) -> list[int]:
    return [1 - s for s in samples]


def test_is_inverted_returns_true_for_mostly_low():
    from features.uart.uart_scanner import UartScanner
    scanner = UartScanner.__new__(UartScanner)
    assert UartScanner._is_inverted([0] * 900 + [1] * 100) is True


def test_is_inverted_returns_false_for_mostly_high():
    assert UartScanner._is_inverted([1] * 900 + [0] * 100) is False


def test_analyze_capture_detects_inverted_signal():
    """Analyzer must decode UART data when the signal idles LOW (inverted)."""
    sample_rate_hz = 8_000_000
    baud_rate = 115200
    normal_samples, _ranges = _build_uart_line_samples(b"A", sample_rate_hz, baud_rate)
    inverted_samples = _invert_samples(normal_samples)

    backend = DummyCaptureBackend({7: inverted_samples})
    scanner = UartScanner(backend)
    report = scanner.analyze_capture({7: inverted_samples}, sample_rate_hz=sample_rate_hz,
                                     baud_rates=(baud_rate,))

    assert report.ok is True
    assert report.inverted is True
    assert report.decoded_bytes == b"A"
    assert report.rx_pin == 7
    assert "inverted" in report.reason.lower()


def test_analyze_capture_normal_signal_not_flagged_inverted():
    """Normal idle-HIGH signal must not be flagged as inverted."""
    sample_rate_hz = 8_000_000
    baud_rate = 115200
    normal_samples, _ranges = _build_uart_line_samples(b"A", sample_rate_hz, baud_rate)

    backend = DummyCaptureBackend({3: normal_samples})
    scanner = UartScanner(backend)
    report = scanner.analyze_capture({3: normal_samples}, sample_rate_hz=sample_rate_hz,
                                     baud_rates=(baud_rate,))

    assert report.ok is True
    assert report.inverted is False
    assert report.decoded_bytes == b"A"


def test_analyze_capture_inverted_multi_byte():
    """Multi-byte inverted stream must decode correctly."""
    sample_rate_hz = 8_000_000
    baud_rate = 115200
    payload = b"Hi"
    normal_samples, _ranges = _build_uart_line_samples(payload, sample_rate_hz, baud_rate)
    inverted_samples = _invert_samples(normal_samples)

    backend = DummyCaptureBackend({4: inverted_samples})
    scanner = UartScanner(backend)
    report = scanner.analyze_capture({4: inverted_samples}, sample_rate_hz=sample_rate_hz,
                                     baud_rates=(baud_rate,))

    assert report.ok is True
    assert report.inverted is True
    assert report.decoded_bytes == payload


# ---------------------------------------------------------------------------
# Multi-channel / multi-configuration tests
# ---------------------------------------------------------------------------

from features.uart.uart_scanner import UartChannelResult


def test_analyze_capture_returns_channels_list():
    """Report.channels must be populated with at least the best result."""
    sample_rate_hz = 8_000_000
    baud_rate = 115200
    samples, _ = _build_uart_line_samples(b"A", sample_rate_hz, baud_rate)

    backend = DummyCaptureBackend({3: samples})
    scanner = UartScanner(backend)
    report = scanner.analyze_capture({3: samples}, sample_rate_hz=sample_rate_hz,
                                     baud_rates=(baud_rate,))

    assert report.ok is True
    assert isinstance(report.channels, list)
    assert len(report.channels) >= 1
    best = report.channels[0]
    assert isinstance(best, UartChannelResult)
    assert best.rx_pin == 3
    assert best.baud_rate == baud_rate
    assert best.decoded_bytes == b"A"


def test_analyze_capture_channels_sorted_by_score_descending():
    """channels list must be sorted best-first (descending score)."""
    sample_rate_hz = 8_000_000
    baud_rate = 115200
    # Use a multi-byte payload so the best baud rate is clearly distinct
    samples, _ = _build_uart_line_samples(b"Hello", sample_rate_hz, baud_rate)

    backend = DummyCaptureBackend({1: samples})
    scanner = UartScanner(backend)
    report = scanner.analyze_capture({1: samples}, sample_rate_hz=sample_rate_hz)

    scores = [ch.score for ch in report.channels]
    assert scores == sorted(scores, reverse=True), "channels must be best-first"


def test_analyze_capture_multi_pin_each_pin_in_channels():
    """When multiple pins carry data, each should appear in channels."""
    sample_rate_hz = 8_000_000
    baud_rate = 115200
    samples_a, _ = _build_uart_line_samples(b"A", sample_rate_hz, baud_rate)
    samples_b, _ = _build_uart_line_samples(b"B", sample_rate_hz, baud_rate)

    backend = DummyCaptureBackend({2: samples_a, 3: samples_b})
    scanner = UartScanner(backend)
    report = scanner.analyze_capture(
        {2: samples_a, 3: samples_b},
        sample_rate_hz=sample_rate_hz,
        baud_rates=(baud_rate,),
    )

    assert report.ok is True
    pins_found = {ch.rx_pin for ch in report.channels}
    assert 2 in pins_found
    assert 3 in pins_found


def test_analyze_capture_no_duplicate_configurations():
    """channels must not contain the same (pin, baud, config, polarity) twice."""
    sample_rate_hz = 8_000_000
    baud_rate = 115200
    samples, _ = _build_uart_line_samples(b"X", sample_rate_hz, baud_rate)

    backend = DummyCaptureBackend({5: samples})
    scanner = UartScanner(backend)
    report = scanner.analyze_capture({5: samples}, sample_rate_hz=sample_rate_hz,
                                     baud_rates=(baud_rate,))

    seen = set()
    for ch in report.channels:
        key = (ch.rx_pin, ch.baud_rate, ch.data_bits, ch.parity, ch.stop_bits, ch.inverted)
        assert key not in seen, f"Duplicate channel configuration: {key}"
        seen.add(key)


def test_analyze_capture_channels_report_reason_contains_count():
    """reason string must mention the number of configurations found."""
    sample_rate_hz = 8_000_000
    baud_rate = 115200
    samples, _ = _build_uart_line_samples(b"Z", sample_rate_hz, baud_rate)

    backend = DummyCaptureBackend({0: samples})
    scanner = UartScanner(backend)
    report = scanner.analyze_capture({0: samples}, sample_rate_hz=sample_rate_hz,
                                     baud_rates=(baud_rate,))

    assert report.ok is True
    assert str(len(report.channels)) in report.reason


def test_channel_result_fields_are_correct_types():
    """UartChannelResult fields must have the right types."""
    sample_rate_hz = 8_000_000
    baud_rate = 115200
    samples, _ = _build_uart_line_samples(b"T", sample_rate_hz, baud_rate)

    backend = DummyCaptureBackend({1: samples})
    scanner = UartScanner(backend)
    report = scanner.analyze_capture({1: samples}, sample_rate_hz=sample_rate_hz,
                                     baud_rates=(baud_rate,))

    ch = report.channels[0]
    assert isinstance(ch.rx_pin, int)
    assert isinstance(ch.baud_rate, int)
    assert isinstance(ch.data_bits, int)
    assert isinstance(ch.stop_bits, int)
    assert isinstance(ch.parity, str)
    assert isinstance(ch.inverted, bool)
    assert isinstance(ch.valid_frames, int)
    assert isinstance(ch.decoded_bytes, bytes)
    assert isinstance(ch.decoded_text, str)
    assert isinstance(ch.score, float)
