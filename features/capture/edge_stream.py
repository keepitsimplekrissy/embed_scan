"""Edge-stream capture: store only signal transitions with timestamps.

An edge stream records (timestamp_ns, level) pairs — one entry per signal
transition — rather than one sample per clock tick.  This is orders of
magnitude smaller for typical UART/JTAG traffic where the line idles for
long periods.

Storage format: BSON (via pymongo's ``bson`` package).

Schema (per-file BSON document):
    {
        "schema":        "edge-stream-v1",
        "capture_kind":  str,          # e.g. "uart", "jtag"
        "backend":       str,
        "device_index":  int,
        "sample_rate_hz": int,         # samples/sec used during acquisition
        "captured_at":   datetime,     # UTC wall-clock time
        "pins": [
            {
                "pin":         int,
                "initial_level": 0 | 1,
                "transitions": [{"t_ns": int, "level": 0|1}, ...]
            },
            ...
        ]
    }

The ``t_ns`` field is nanoseconds from the start of the capture window,
derived from the sample index: t_ns = sample_index * (1_000_000_000 / sample_rate_hz).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PinEdgeStream:
    """Edge-stream for a single pin.

    Attributes:
        pin:           Pin index.
        initial_level: Logic level at sample 0 (0 or 1).
        transitions:   List of (t_ns, level) pairs, one per signal edge,
                       ordered by ascending t_ns.
    """
    pin: int
    initial_level: int
    transitions: list[tuple[int, int]] = field(default_factory=list)

    @property
    def edge_count(self) -> int:
        return len(self.transitions)


@dataclass
class EdgeStreamCapture:
    """Complete edge-stream capture across all pins.

    Attributes:
        capture_kind:   Identifier for the source feature ("uart", "jtag", …).
        backend:        Hardware backend name string.
        device_index:   Backend device index.
        sample_rate_hz: Sample rate at which the raw data was acquired.
        captured_at:    UTC datetime of capture start.
        pins:           One PinEdgeStream per captured pin.
    """
    capture_kind: str
    backend: str
    device_index: int
    sample_rate_hz: int
    captured_at: datetime
    pins: list[PinEdgeStream] = field(default_factory=list)

    @property
    def total_edges(self) -> int:
        return sum(p.edge_count for p in self.pins)


# ---------------------------------------------------------------------------
# Conversion: flat sample list → edge stream
# ---------------------------------------------------------------------------

def samples_to_edge_stream(
    pin: int,
    samples: list[int],
    sample_rate_hz: int,
) -> PinEdgeStream:
    """Convert a flat per-sample list into a compact edge stream.

    Only stores a transition entry when the level changes, giving O(edges)
    storage rather than O(samples).

    Args:
        pin:            Pin index.
        samples:        List of 0/1 integer samples in time order.
        sample_rate_hz: Acquisition sample rate (used to compute t_ns).

    Returns:
        PinEdgeStream with initial_level and sorted transitions list.
    """
    if not samples:
        return PinEdgeStream(pin=pin, initial_level=0, transitions=[])

    ns_per_sample = 1_000_000_000.0 / float(sample_rate_hz)
    initial = int(bool(samples[0]))
    transitions: list[tuple[int, int]] = []
    prev = initial

    for idx in range(1, len(samples)):
        level = int(bool(samples[idx]))
        if level != prev:
            t_ns = int(math.floor(idx * ns_per_sample))
            transitions.append((t_ns, level))
            prev = level

    return PinEdgeStream(pin=pin, initial_level=initial, transitions=transitions)


def edge_stream_to_samples(
    stream: PinEdgeStream,
    sample_rate_hz: int,
    total_samples: int,
) -> list[int]:
    """Reconstruct a flat sample list from an edge stream.

    Useful for verification and replay.

    Args:
        stream:         PinEdgeStream to reconstruct from.
        sample_rate_hz: Sample rate to use for index calculation.
        total_samples:  Length of the output sample list.

    Returns:
        List of 0/1 integers of length total_samples.
    """
    ns_per_sample = 1_000_000_000.0 / float(sample_rate_hz)
    samples = [stream.initial_level] * total_samples

    transitions_sorted = sorted(stream.transitions, key=lambda t: t[0])
    for t_ns, level in transitions_sorted:
        idx = int(round(t_ns / ns_per_sample))
        for i in range(max(0, idx), total_samples):
            samples[i] = level
        # Overwrite up to the next transition
        # (done in a second pass below for efficiency)

    # Rebuild efficiently: fill runs between transitions
    samples = [stream.initial_level] * total_samples
    breakpoints = [(0, stream.initial_level)]
    for t_ns, level in transitions_sorted:
        idx = min(total_samples, int(round(t_ns / ns_per_sample)))
        breakpoints.append((idx, level))
    breakpoints.append((total_samples, None))

    for i in range(len(breakpoints) - 1):
        start_idx, level = breakpoints[i]
        end_idx = breakpoints[i + 1][0]
        if level is not None:
            for j in range(start_idx, end_idx):
                samples[j] = level

    return samples


def pin_samples_to_capture(
    pin_samples: dict[int, list[int]],
    sample_rate_hz: int,
    capture_kind: str,
    backend: str,
    device_index: int,
    captured_at: datetime | None = None,
) -> EdgeStreamCapture:
    """Build an EdgeStreamCapture from a dict of flat per-pin sample lists."""
    if captured_at is None:
        captured_at = datetime.now(timezone.utc)
    streams = [
        samples_to_edge_stream(pin, samples, sample_rate_hz)
        for pin, samples in sorted(pin_samples.items())
    ]
    return EdgeStreamCapture(
        capture_kind=capture_kind,
        backend=backend,
        device_index=device_index,
        sample_rate_hz=sample_rate_hz,
        captured_at=captured_at,
        pins=streams,
    )


# ---------------------------------------------------------------------------
# BSON serialisation helpers
# ---------------------------------------------------------------------------

def _capture_to_bson_doc(capture: EdgeStreamCapture) -> dict:
    """Convert an EdgeStreamCapture to a plain dict suitable for bson.encode."""
    return {
        "schema": "edge-stream-v1",
        "capture_kind": capture.capture_kind,
        "backend": capture.backend,
        "device_index": capture.device_index,
        "sample_rate_hz": capture.sample_rate_hz,
        "captured_at": capture.captured_at,
        "pins": [
            {
                "pin": stream.pin,
                "initial_level": stream.initial_level,
                "transitions": [
                    {"t_ns": t_ns, "level": level}
                    for t_ns, level in stream.transitions
                ],
            }
            for stream in capture.pins
        ],
    }


def _bson_doc_to_capture(doc: dict) -> EdgeStreamCapture:
    """Reconstruct an EdgeStreamCapture from a decoded BSON document."""
    pins = [
        PinEdgeStream(
            pin=p["pin"],
            initial_level=p["initial_level"],
            transitions=[(t["t_ns"], t["level"]) for t in p.get("transitions", [])],
        )
        for p in doc.get("pins", [])
    ]
    captured_at = doc.get("captured_at", datetime.now(timezone.utc))
    if not isinstance(captured_at, datetime):
        captured_at = datetime.now(timezone.utc)
    return EdgeStreamCapture(
        capture_kind=doc.get("capture_kind", ""),
        backend=doc.get("backend", ""),
        device_index=doc.get("device_index", 0),
        sample_rate_hz=doc.get("sample_rate_hz", 0),
        captured_at=captured_at,
        pins=pins,
    )


def write_bson_capture(capture: EdgeStreamCapture, path: str | Path) -> Path:
    """Serialise an EdgeStreamCapture to a BSON file.

    Args:
        capture: The capture to serialise.
        path:    Destination file path (.bson extension recommended).

    Returns:
        The Path that was written.
    """
    try:
        import bson  # pymongo's bson
    except ImportError as exc:
        raise ImportError(
            "pymongo is required for BSON capture storage: pip install pymongo"
        ) from exc

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = _capture_to_bson_doc(capture)
    out.write_bytes(bson.encode(doc))
    return out


def read_bson_capture(path: str | Path) -> EdgeStreamCapture:
    """Deserialise an EdgeStreamCapture from a BSON file.

    Args:
        path: Path to a .bson file written by write_bson_capture.

    Returns:
        Reconstructed EdgeStreamCapture.
    """
    try:
        import bson
    except ImportError as exc:
        raise ImportError(
            "pymongo is required for BSON capture reading: pip install pymongo"
        ) from exc

    raw = Path(path).read_bytes()
    doc = bson.decode(raw)
    return _bson_doc_to_capture(doc)
