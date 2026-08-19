from hardware_backend import HardwareBackend
from features.status import PinStatusScanner


class DummyStatusBackend(HardwareBackend):
    def __init__(self, values: dict[int, bool | None]):
        super().__init__()
        self.values = values
        self.log = []

    def open_device(self, device_index=0):
        self.log.append(("open_device", device_index))
        return self

    def close_device(self):
        self.log.append("close_device")

    def runtime_ready(self):
        return True

    def get_channel_indices(self, pin_mask, pin_max, pin_mask_override=None, pin_max_override=None):
        return list(self.values.keys())

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
        self.log.append(("digital_read", pin))
        return self.values.get(pin)

    def pin_mode(self, pin, mode):
        self.log.append(("pin_mode", pin, mode))
        return True


def test_read_pin_states_reports_high_low():
    backend = DummyStatusBackend({1: True, 2: False})
    scanner = PinStatusScanner(backend)

    report = scanner.read_pin_states([1, 2], device_index=0)

    assert report.ok is True
    assert report.status == "success"
    assert report.pin_states == {1: "high", 2: "low"}
    assert ("open_device", 0) in backend.log
    assert ("digital_read", 1) in backend.log
    assert ("digital_read", 2) in backend.log
    assert "close_device" in backend.log


def test_read_pin_states_handles_unknown_levels():
    backend = DummyStatusBackend({3: None})
    scanner = PinStatusScanner(backend)

    report = scanner.read_pin_states([3], device_index=0)

    assert report.ok is False
    assert report.pin_states == {3: "unknown"}

