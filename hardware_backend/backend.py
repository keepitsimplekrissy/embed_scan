class HardwareBackend:
    def __init__(self):
        self.error = None

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
