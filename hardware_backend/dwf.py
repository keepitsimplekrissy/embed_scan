import logging

from .backend import HardwareBackend
from . import dwfpy, Device

LOW = 0
HIGH = 1


class DwfHardwareInterface(HardwareBackend):
    def __init__(self):
        super().__init__()
        self.backend_name = "DWF"
        self._dwf_device = None
        self._dwf_handle = None
        self._dwf_connected = False

    def open_device(self, device_index=0):
        if self._dwf_connected and self._dwf_device is not None:
            return self._dwf_device

        if dwfpy is None or Device is None:
            self.error = RuntimeError("dwfpy module is not importable")
            return None

        try:
            devices = Device.enumerate()
            if not devices:
                self.error = RuntimeError("No Digilent DWF devices found")
                return None

            candidate = devices[device_index] if 0 <= device_index < len(devices) else devices[0]
            candidate.open()
            self._dwf_device = candidate
            self._dwf_handle = self._dwf_device.handle
            self._dwf_connected = self._dwf_device.is_open
            return self._dwf_device
        except Exception as exc:
            self.error = exc
            self._close_internal()
            return None

    def _close_internal(self):
        try:
            if self._dwf_device is not None and getattr(self._dwf_device, "is_open", False):
                self._dwf_device.close()
        except Exception:
            pass
        finally:
            self._dwf_connected = False
            self._dwf_device = None
            self._dwf_handle = None

    def close_device(self):
        self._close_internal()

    def get_channel_indices(self, pin_mask, pin_max, pin_mask_override=None, pin_max_override=None):
        if not self.ensure_initialized() or self._dwf_device is None:
            return []

        digital_io = getattr(self._dwf_device, "digital_io", None)
        if digital_io is None:
            return []

        channels = getattr(digital_io, "channels", None)
        if channels is None:
            return []

        channel_count = len(channels)
        effective_pin_mask = pin_mask if pin_mask_override is None else int(pin_mask_override)

        if pin_max_override is not None:
            effective_pin_max = int(pin_max_override)
        elif pin_max:
            effective_pin_max = int(pin_max)
        else:
            effective_pin_max = channel_count

        capable = []
        for idx, channel in enumerate(channels):
            can_read = bool(getattr(channel, "can_read", False))
            can_write = bool(getattr(channel, "can_write", False))
            if (can_read or can_write) and idx < effective_pin_max:
                if effective_pin_mask:
                    if (effective_pin_mask >> idx) & 1:
                        capable.append(idx)
                else:
                    capable.append(idx)

        return capable

    def runtime_ready(self):
        return self._dwf_connected and self._dwf_device is not None and getattr(self._dwf_device, "is_open", False)

    def get_channel(self, pin):
        if not self.ensure_initialized() or self._dwf_device is None:
            return None

        digital_io = getattr(self._dwf_device, "digital_io", None)
        if digital_io is None:
            return None

        channels = getattr(digital_io, "channels", None)
        if channels is None:
            return None

        if 0 <= pin < len(channels):
            return channels[pin]
        return None

    def configure_device(self):
        if self.ensure_initialized() and self._dwf_device is not None:
            digital_io = getattr(self._dwf_device, "digital_io", None)
            if digital_io is not None:
                try:
                    digital_io.read_status()
                    return True
                except Exception as exc:
                    self.error = exc
                    return False
        return False

    def ensure_initialized(self):
        if self._dwf_connected:
            return True
        if dwfpy is None or Device is None:
            return False

        try:
            devices = Device.enumerate()
            if not devices:
                self.error = RuntimeError("No Digilent DWF devices found")
                self._dwf_connected = False
                return False

            self._dwf_device = devices[0]
            self._dwf_device.open()
            self._dwf_handle = self._dwf_device.handle
            self._dwf_connected = self._dwf_device.is_open
            return self._dwf_connected
        except Exception as exc:
            self.error = exc
            self._dwf_connected = False
            self._dwf_device = None
            self._dwf_handle = None
            return False

    def digital_write(self, pin, value):
        if self.ensure_initialized() and self._dwf_device is not None:
            try:
                channel = self.get_channel(pin)
                if channel is not None:
                    channel.enabled = True
                    channel.output_state = value
                    channel.module.configure()
                    return value
            except Exception:
                pass
        return bool(value)

    def digital_read(self, pin):
        if self.ensure_initialized() and self._dwf_device is not None:
            try:
                channel = self.get_channel(pin)
                if channel is not None:
                    channel.module.read_status()
                    return bool(channel.input_state)
            except Exception:
                pass
        return None

    def pin_mode(self, pin, mode):
        if self.ensure_initialized() and self._dwf_device is not None:
            try:
                channel = self.get_channel(pin)
                if channel is not None:
                    mode_value = str(mode).upper()
                    if mode_value in {"OUTPUT", "OUT"}:
                        channel.enabled = True
                        channel.output_state = LOW
                    elif mode_value in {"INPUT", "INPUT_PULLUP", "IN"}:
                        channel.enabled = False
                    else:
                        channel.enabled = False
                    channel.module.configure()
                    return True
            except Exception:
                pass
        return False
