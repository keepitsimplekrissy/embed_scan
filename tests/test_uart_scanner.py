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

