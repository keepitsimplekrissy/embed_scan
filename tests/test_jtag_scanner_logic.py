import pytest

from features.jtag.jtag_scanner import JtagScanner
from hardware_backend import DwfHardwareInterface, HardwareBackend


class DummyBackend(HardwareBackend):
    def __init__(self):
        super().__init__()
        self.log = []

    def open_device(self, device_index=0):
        self.log.append(("open_device", device_index))
        return self

    def close_device(self):
        self.log.append("close_device")

    def get_channel_indices(self, pin_mask, pin_max, pin_mask_override=None, pin_max_override=None):
        self.log.append(("get_channel_indices", pin_mask, pin_max, pin_mask_override, pin_max_override))
        return [2, 3, 4, 5]

    def runtime_ready(self):
        return True

    def get_channel(self, pin):
        self.log.append(("get_channel", pin))
        return None

    def configure_device(self):
        self.log.append("configure_device")
        return True

    def ensure_initialized(self):
        self.log.append("ensure_initialized")
        return True

    def digital_write(self, pin, value):
        self.log.append(("digital_write", pin, value))
        return value

    def digital_read(self, pin):
        self.log.append(("digital_read", pin))
        return False

    def pin_mode(self, pin, mode):
        self.log.append(("pin_mode", pin, mode))
        return True


@pytest.fixture
def scanner_with_dummy_backend():
    return JtagScanner(backend=DummyBackend())


def test_set_log_level_by_name(scanner_with_dummy_backend):
    scanner = scanner_with_dummy_backend
    scanner.set_log_level("DEBUG")
    assert scanner.get_log_level_name() == "DEBUG"


def test_bit_read_and_write():
    assert JtagScanner.bit_read(0b1010, 1) == 1
    assert JtagScanner.bit_read(0b1010, 2) == 0
    assert JtagScanner.bit_write(0b1010, 2, True) == 0b1110
    assert JtagScanner.bit_write(0b1010, 1, False) == 0b1000


def test_run_jtag_scan_with_candidate_channels(scanner_with_dummy_backend):
    scanner = scanner_with_dummy_backend
    result = scanner.run_jtag_scan(candidate_channels=[2, 3, 4, 5], runtime_policy="simulation")
    assert result.ok is True
    assert result.status == "simulation"
    assert result.mapping is not None
    assert len(result.channels) == 4


def test_open_close_runtime_device(scanner_with_dummy_backend):
    scanner = scanner_with_dummy_backend
    assert scanner.open_runtime_device(0) is scanner.backend
    scanner.close_runtime_device()
    assert scanner.backend.runtime_ready()
