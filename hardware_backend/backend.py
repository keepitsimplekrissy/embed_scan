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

    def store_capture_data(self, capture_kind: str, payload: dict, capture_path: str | None = None) -> str:
        """Persist capture payload in backend-specific storage and return its path."""
        if capture_path:
            storage_dir = Path(capture_path)
        else:
            backend_folder = (self.backend_name or "generic").strip().lower().replace(" ", "_")
            storage_dir = Path.cwd() / "captures" / backend_folder
        storage_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output_path = storage_dir / f"{capture_kind}_{timestamp}.json"
        with output_path.open("w", encoding="utf-8") as output_file:
            json.dump(payload, output_file, indent=2, sort_keys=True)
            output_file.write("\n")
        return str(output_path)
