import json
from datetime import datetime, timezone
from pathlib import Path


class HardwareBackend:
    def __init__(self):
        self.error = None
        self.backend_name = ""

    def open_device(self, device_index=0):
        raise NotImplementedError

    def close_device(self):
        raise NotImplementedError

    def get_channel_indices(self, pin_mask, pin_max, pin_mask_override=None, pin_max_override=None):
        raise NotImplementedError

    def runtime_ready(self):
        raise NotImplementedError

    def resolve_device(self, device_or_index):
        if device_or_index is None:
            return None
        if isinstance(device_or_index, int):
            return self.open_device(device_or_index)
        if hasattr(device_or_index, "open") and hasattr(device_or_index, "close"):
            return device_or_index
        if hasattr(device_or_index, "is_open") or hasattr(device_or_index, "is_connected"):
            return device_or_index
        return None

    def get_channel(self, pin):
        raise NotImplementedError

    def configure_device(self):
        raise NotImplementedError

    def ensure_initialized(self):
        raise NotImplementedError

    def digital_write(self, pin, value):
        raise NotImplementedError

    def digital_read(self, pin):
        raise NotImplementedError

    def pin_mode(self, pin, mode):
        raise NotImplementedError

    def store_capture_data(
        self,
        capture_kind: str,
        payload: dict,
        capture_path: str | None = None,
    ) -> str:
        """Persist capture payload and return the primary storage path.

        Two files are written when the payload contains a ``pin_samples`` key:

        1. **JSON** — the full flat sample arrays (``<capture_kind>_<ts>.json``),
           for human inspection and backward compatibility.
        2. **BSON** edge-stream — only the signal-transition timestamps
           (``<capture_kind>_<ts>.bson``), compact and ready for analysis.

        When ``pin_samples`` is absent only the JSON file is written.

        The JSON path is returned so existing callers are unaffected.
        """
        if capture_path:
            storage_dir = Path(capture_path)
        else:
            backend_folder = (self.backend_name or "generic").strip().lower().replace(" ", "_")
            storage_dir = Path.cwd() / "captures" / backend_folder
        storage_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        stem = f"{capture_kind}_{timestamp}"

        # --- JSON (flat samples, full payload) ---
        json_path = storage_dir / f"{stem}.json"
        with json_path.open("w", encoding="utf-8") as json_file:
            json.dump(payload, json_file, indent=2, sort_keys=True)
            json_file.write("\n")

        # --- BSON edge-stream (transitions only) ---
        pin_samples_raw = payload.get("pin_samples")
        if pin_samples_raw:
            try:
                from features.capture.edge_stream import (
                    pin_samples_to_capture,
                    write_bson_capture,
                )
                # pin_samples keys may be strings (from JSON round-trip) or ints
                pin_samples = {int(k): list(v) for k, v in pin_samples_raw.items()}
                sample_rate_hz = int(payload.get("sample_rate_hz", 0))
                device_index = int(payload.get("device_index", 0))
                captured_at = datetime.now(timezone.utc)

                capture = pin_samples_to_capture(
                    pin_samples=pin_samples,
                    sample_rate_hz=sample_rate_hz,
                    capture_kind=capture_kind,
                    backend=self.backend_name,
                    device_index=device_index,
                    captured_at=captured_at,
                )
                bson_path = storage_dir / f"{stem}.bson"
                write_bson_capture(capture, bson_path)
            except Exception:
                pass  # BSON write is best-effort; never break the caller

        return str(json_path)
