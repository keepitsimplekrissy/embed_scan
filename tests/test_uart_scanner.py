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
