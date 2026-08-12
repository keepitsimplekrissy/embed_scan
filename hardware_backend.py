import logging

try:
    import dwfpy
    from dwfpy import Device
    _dwf_error = None
except ImportError as exc:
    dwfpy = None
    Device = None
    _dwf_error = exc

try:
    import saleae
    from saleae import Saleae
    _saleae_error = None
except ImportError as exc:
    saleae = None
    Saleae = None
    _saleae_error = exc

LOW = 0
HIGH = 1


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


class DwfHardwareInterface(HardwareBackend):
    def __init__(self):
        super().__init__()
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


class SaleaeHardwareInterface(HardwareBackend):
    def __init__(self):
        super().__init__()
        self._saleae_device = None
        self._saleae_connected = False

    def open_device(self, device_index=0):
        if self._saleae_connected and self._saleae_device is not None:
            return self._saleae_device

        if saleae is None or Saleae is None:
            self.error = RuntimeError("python-saleae module is not importable")
            return None

        try:
            device = Saleae()
            if hasattr(device, "connect"):
                device.connect()
            elif hasattr(device, "connect_to_device"):
                device.connect_to_device()
            else:
                raise RuntimeError("Saleae backend requires a connect method")

            self._saleae_device = device
            self._saleae_connected = True
            return self._saleae_device
        except Exception as exc:
            self.error = exc
            self._close_internal()
            return None

    def _close_internal(self):
        try:
            if self._saleae_device is not None:
                if hasattr(self._saleae_device, "disconnect"):
                    self._saleae_device.disconnect()
                elif hasattr(self._saleae_device, "close"):
                    self._saleae_device.close()
        except Exception:
            pass
        finally:
            self._saleae_connected = False
            self._saleae_device = None

    def close_device(self):
        self._close_internal()

    def get_channel_indices(self, pin_mask, pin_max, pin_mask_override=None, pin_max_override=None):
        if not self.runtime_ready() or self._saleae_device is None:
            return []

        channels = None
        if hasattr(self._saleae_device, "available_channels"):
            channels = self._saleae_device.available_channels()
        elif hasattr(self._saleae_device, "get_available_channels"):
            channels = self._saleae_device.get_available_channels()
        elif hasattr(self._saleae_device, "digital_input_channels"):
            channels = self._saleae_device.digital_input_channels
        elif hasattr(self._saleae_device, "channels"):
            channels = self._saleae_device.channels

        if channels is None:
            return []

        if isinstance(channels, (list, tuple)):
            count = len(channels)
        else:
            try:
                count = int(channels)
            except Exception:
                return []

        effective_pin_mask = pin_mask if pin_mask_override is None else int(pin_mask_override)
        if pin_max_override is not None:
            effective_pin_max = int(pin_max_override)
        elif pin_max:
            effective_pin_max = int(pin_max)
        else:
            effective_pin_max = count

        capable = []
        for idx in range(count):
            if idx < effective_pin_max:
                if effective_pin_mask:
                    if (effective_pin_mask >> idx) & 1:
                        capable.append(idx)
                else:
                    capable.append(idx)

        return capable

    def runtime_ready(self):
        return self._saleae_connected and self._saleae_device is not None

    def get_channel(self, pin):
        if not self.runtime_ready() or self._saleae_device is None:
            return None

        channels = None
        if hasattr(self._saleae_device, "available_channels"):
            channels = self._saleae_device.available_channels()
        elif hasattr(self._saleae_device, "get_available_channels"):
            channels = self._saleae_device.get_available_channels()
        elif hasattr(self._saleae_device, "digital_input_channels"):
            channels = self._saleae_device.digital_input_channels
        elif hasattr(self._saleae_device, "channels"):
            channels = self._saleae_device.channels

        if isinstance(channels, (list, tuple)) and 0 <= pin < len(channels):
            return channels[pin]
        return None

    def configure_device(self):
        return self.runtime_ready()

    def ensure_initialized(self):
        if self.runtime_ready():
            return True
        self.open_device(0)
        return self.runtime_ready()

    def digital_write(self, pin, value):
        if not self.runtime_ready() or self._saleae_device is None:
            return False

        if hasattr(self._saleae_device, "digital_write"):
            try:
                self._saleae_device.digital_write(pin, value)
                return True
            except Exception:
                pass
        elif hasattr(self._saleae_device, "set_digital_output"):
            try:
                self._saleae_device.set_digital_output(pin, value)
                return True
            except Exception:
                pass

        logging.getLogger(__name__).warning("Saleae backend does not support digital_write for pin %s", pin)
        return False

    def digital_read(self, pin):
        if not self.runtime_ready() or self._saleae_device is None:
            return None

        if hasattr(self._saleae_device, "digital_read"):
            try:
                return bool(self._saleae_device.digital_read(pin))
            except Exception:
                pass

        logging.getLogger(__name__).warning("Saleae backend does not support digital_read for pin %s", pin)
        return None

    def pin_mode(self, pin, mode):
        if not self.runtime_ready() or self._saleae_device is None:
            return False

        if hasattr(self._saleae_device, "set_pin_mode"):
            try:
                self._saleae_device.set_pin_mode(pin, mode)
                return True
            except Exception:
                pass

        logging.getLogger(__name__).warning("Saleae backend does not support pin_mode for pin %s", pin)
        return False
