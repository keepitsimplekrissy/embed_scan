import logging

from .backend import HardwareBackend
from . import saleae


class SaleaeHardwareInterface(HardwareBackend):
    def __init__(self):
        super().__init__()
        self.backend_name = "Saleae"
        self._saleae_device = None
        self._saleae_connected = False

    def open_device(self, device_index=0):
        if self._saleae_connected and self._saleae_device is not None:
            return self._saleae_device

        if saleae is None:
            self.error = RuntimeError("python-saleae module is not importable")
            return None

        try:
            device = saleae.Saleae()
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
