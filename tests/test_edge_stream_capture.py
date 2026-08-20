"""Tests for the BSON edge-stream capture module."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from features.capture import (
    EdgeStreamCapture,
    PinEdgeStream,
    edge_stream_to_samples,
    pin_samples_to_capture,
    read_bson_capture,
    samples_to_edge_stream,
    write_bson_capture,
)


# ---------------------------------------------------------------------------
# samples_to_edge_stream
# ---------------------------------------------------------------------------

def test_samples_to_edge_stream_idle_high_no_transitions():
    """Constant-HIGH signal produces no transitions."""
    samples = [1] * 1000
    stream = samples_to_edge_stream(pin=3, samples=samples, sample_rate_hz=8_000_000)

    assert stream.pin == 3
    assert stream.initial_level == 1
    assert stream.transitions == []
    assert stream.edge_count == 0


def test_samples_to_edge_stream_single_edge():
    """One falling edge produces one transition entry."""
    samples = [1] * 100 + [0] * 100
    stream = samples_to_edge_stream(pin=0, samples=samples, sample_rate_hz=1_000_000)

    assert stream.initial_level == 1
    assert len(stream.transitions) == 1
    t_ns, level = stream.transitions[0]
    assert level == 0
    # sample 100 at 1 MHz → 100 000 ns
    assert t_ns == 100_000


def test_samples_to_edge_stream_multiple_edges():
    """Multiple edges captured correctly and in order."""
    samples = [1, 0, 0, 1, 1, 0, 1]
    stream = samples_to_edge_stream(pin=1, samples=samples, sample_rate_hz=1_000_000)

    assert stream.initial_level == 1
    levels = [l for _, l in stream.transitions]
    assert levels == [0, 1, 0, 1]


def test_samples_to_edge_stream_empty():
    """Empty sample list gives empty stream with initial_level 0."""
    stream = samples_to_edge_stream(pin=5, samples=[], sample_rate_hz=8_000_000)
    assert stream.initial_level == 0
    assert stream.transitions == []


def test_samples_to_edge_stream_compresses_well():
    """Edge stream should be much smaller than original for mostly-idle signals."""
    # Idle HIGH, one short LOW pulse, then idle again
    samples = [1] * 10_000 + [0] * 70 + [1] * 10_000
    stream = samples_to_edge_stream(pin=6, samples=samples, sample_rate_hz=8_000_000)

    assert stream.edge_count == 2  # one falling + one rising edge
    # storage ratio: 2 entries vs 20_070 samples
    assert stream.edge_count < len(samples) // 100


# ---------------------------------------------------------------------------
# edge_stream_to_samples (round-trip)
# ---------------------------------------------------------------------------

def _round_trip(samples, sample_rate_hz=1_000_000):
    stream = samples_to_edge_stream(pin=0, samples=samples, sample_rate_hz=sample_rate_hz)
    return edge_stream_to_samples(stream, sample_rate_hz=sample_rate_hz,
                                  total_samples=len(samples))


def test_round_trip_idle_high():
    samples = [1] * 50
    assert _round_trip(samples) == samples


def test_round_trip_single_pulse():
    samples = [1] * 20 + [0] * 10 + [1] * 20
    assert _round_trip(samples) == samples


def test_round_trip_alternating():
    samples = [1, 0] * 25
    assert _round_trip(samples) == samples


# ---------------------------------------------------------------------------
# pin_samples_to_capture
# ---------------------------------------------------------------------------

def test_pin_samples_to_capture_builds_correct_structure():
    pin_samples = {
        3: [1] * 100 + [0] * 50 + [1] * 100,
        5: [1] * 250,
    }
    capture = pin_samples_to_capture(
        pin_samples=pin_samples,
        sample_rate_hz=8_000_000,
        capture_kind="uart",
        backend="DWF",
        device_index=0,
    )

    assert capture.capture_kind == "uart"
    assert capture.backend == "DWF"
    assert capture.device_index == 0
    assert capture.sample_rate_hz == 8_000_000
    assert isinstance(capture.captured_at, datetime)
    assert len(capture.pins) == 2
    pins_seen = {p.pin for p in capture.pins}
    assert pins_seen == {3, 5}


def test_pin_samples_to_capture_edge_counts():
    pin_samples = {0: [1, 0, 1, 0, 1]}
    capture = pin_samples_to_capture(
        pin_samples=pin_samples,
        sample_rate_hz=1_000_000,
        capture_kind="test",
        backend="sim",
        device_index=0,
    )
    assert capture.total_edges == 4


# ---------------------------------------------------------------------------
# BSON write / read round-trip
# ---------------------------------------------------------------------------

def _make_capture() -> EdgeStreamCapture:
    pin_samples = {
        2: [1] * 200 + [0] * 69 + [1] * 200,
        3: [1] * 500,
    }
    return pin_samples_to_capture(
        pin_samples=pin_samples,
        sample_rate_hz=8_000_000,
        capture_kind="uart",
        backend="DWF",
        device_index=0,
        captured_at=datetime(2026, 8, 20, 14, 0, 0, tzinfo=timezone.utc),
    )


def test_bson_write_creates_file():
    capture = _make_capture()
    with tempfile.NamedTemporaryFile(suffix=".bson", delete=False) as f:
        path = Path(f.name)

    try:
        write_bson_capture(capture, path)
        assert path.exists()
        assert path.stat().st_size > 0
    finally:
        path.unlink(missing_ok=True)


def test_bson_round_trip_preserves_metadata():
    capture = _make_capture()
    with tempfile.NamedTemporaryFile(suffix=".bson", delete=False) as f:
        path = Path(f.name)

    try:
        write_bson_capture(capture, path)
        loaded = read_bson_capture(path)

        assert loaded.capture_kind == capture.capture_kind
        assert loaded.backend == capture.backend
        assert loaded.device_index == capture.device_index
        assert loaded.sample_rate_hz == capture.sample_rate_hz
        # datetime UTC round-trip (bson stores UTC ms precision)
        assert abs((loaded.captured_at.replace(tzinfo=timezone.utc)
                    - capture.captured_at).total_seconds()) < 1.0
    finally:
        path.unlink(missing_ok=True)


def test_bson_round_trip_preserves_transitions():
    capture = _make_capture()
    with tempfile.NamedTemporaryFile(suffix=".bson", delete=False) as f:
        path = Path(f.name)

    try:
        write_bson_capture(capture, path)
        loaded = read_bson_capture(path)

        assert len(loaded.pins) == len(capture.pins)
        for orig, loaded_pin in zip(
            sorted(capture.pins, key=lambda p: p.pin),
            sorted(loaded.pins, key=lambda p: p.pin),
        ):
            assert loaded_pin.pin == orig.pin
            assert loaded_pin.initial_level == orig.initial_level
            assert loaded_pin.transitions == orig.transitions
    finally:
        path.unlink(missing_ok=True)


def test_bson_file_smaller_than_json_for_idle_signal():
    """BSON edge-stream must be significantly smaller than a flat JSON sample array."""
    import json

    pin_samples = {6: [1] * 10_000 + [0] * 70 + [1] * 10_000}
    capture = pin_samples_to_capture(
        pin_samples=pin_samples,
        sample_rate_hz=8_000_000,
        capture_kind="uart",
        backend="DWF",
        device_index=0,
    )

    with tempfile.NamedTemporaryFile(suffix=".bson", delete=False) as f:
        bson_path = Path(f.name)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json_path = Path(f.name)
        json.dump({"pin_samples": {"6": pin_samples[6]}}, f)

    try:
        write_bson_capture(capture, bson_path)
        bson_size = bson_path.stat().st_size
        json_size = json_path.stat().st_size
        # BSON edge-stream should be at least 50× smaller for mostly-idle signal
        assert bson_size * 50 < json_size, (
            f"Expected BSON ({bson_size}B) << JSON ({json_size}B)"
        )
    finally:
        bson_path.unlink(missing_ok=True)
        json_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# backend.store_capture_data writes BSON alongside JSON
# ---------------------------------------------------------------------------

def test_backend_store_writes_bson_file():
    from hardware_backend.backend import HardwareBackend

    class StubBackend(HardwareBackend):
        def __init__(self):
            super().__init__()
            self.backend_name = "test"
        def open_device(self, d=0): return self
        def close_device(self): pass
        def runtime_ready(self): return True
        def get_channel_indices(self,*a,**kw): return []
        def resolve_device(self, d): return self
        def get_channel(self, p): return None
        def configure_device(self): return True
        def ensure_initialized(self): return True
        def pin_mode(self, p, m): return True
        def digital_write(self, p, v): return v
        def digital_read(self, p): return 0

    backend = StubBackend()
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path_str = backend.store_capture_data(
            capture_kind="uart_capture",
            payload={
                "backend": "test",
                "device_index": 0,
                "pins": [3],
                "sample_rate_hz": 1_000_000,
                "duration_seconds": 0.001,
                "pin_samples": {3: [1] * 100 + [0] * 50 + [1] * 100},
            },
            capture_path=tmpdir,
        )
        json_path = Path(json_path_str)
        bson_path = json_path.with_suffix(".bson")

        assert json_path.exists(), "JSON file must be written"
        assert bson_path.exists(), "BSON edge-stream file must be written alongside JSON"

        loaded = read_bson_capture(bson_path)
        assert loaded.capture_kind == "uart_capture"
        assert loaded.sample_rate_hz == 1_000_000
        assert len(loaded.pins) == 1
        assert loaded.pins[0].pin == 3
        # 2 transitions: falling at 100, rising at 150
        assert loaded.pins[0].edge_count == 2


def test_backend_store_no_bson_without_pin_samples():
    """When payload has no pin_samples, only the JSON file is written."""
    from hardware_backend.backend import HardwareBackend

    class StubBackend(HardwareBackend):
        def __init__(self):
            super().__init__()
            self.backend_name = "test"
        def open_device(self, d=0): return self
        def close_device(self): pass
        def runtime_ready(self): return True
        def get_channel_indices(self,*a,**kw): return []
        def resolve_device(self, d): return self
        def get_channel(self, p): return None
        def configure_device(self): return True
        def ensure_initialized(self): return True
        def pin_mode(self, p, m): return True
        def digital_write(self, p, v): return v
        def digital_read(self, p): return 0

    backend = StubBackend()
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path_str = backend.store_capture_data(
            capture_kind="status_scan",
            payload={"backend": "test", "pins": [1, 2]},
            capture_path=tmpdir,
        )
        json_path = Path(json_path_str)
        bson_path = json_path.with_suffix(".bson")

        assert json_path.exists()
        assert not bson_path.exists(), "BSON should not be written without pin_samples"
