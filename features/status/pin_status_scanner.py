from dataclasses import dataclass

from hardware_backend import DwfHardwareInterface, HardwareBackend


@dataclass
class PinStatusReport:
    ok: bool
    status: str
    pin_states: dict[int, str]
    reason: str


class PinStatusScanner:
    """Read instantaneous high/low states for a list of pins."""

    def __init__(self, backend: HardwareBackend):
        self.backend = backend or DwfHardwareInterface()

    def read_pin_states(self, pins: list[int], device_index: int = 0) -> PinStatusReport:
        selected_pins = self._normalize_pins(pins)
        if not selected_pins:
            return PinStatusReport(
                ok=False,
                status="failed",
                pin_states={},
                reason="no valid pins were provided",
            )

        device = self.backend.open_device(device_index)
        if device is None:
            return PinStatusReport(
                ok=False,
                status="failed",
                pin_states={},
                reason="backend could not open a device",
            )

        pin_states: dict[int, str] = {}
        try:
            for pin in selected_pins:
                try:
                    self.backend.pin_mode(pin, "INPUT")
                except Exception:
                    pass
                value = self.backend.digital_read(pin)
                if value is None:
                    pin_states[pin] = "unknown"
                else:
                    pin_states[pin] = "high" if bool(value) else "low"
        finally:
            self.backend.close_device()

        known_states = [state for state in pin_states.values() if state in {"high", "low"}]
        if known_states:
            return PinStatusReport(
                ok=True,
                status="success",
                pin_states=pin_states,
                reason="pin levels read from backend",
            )
        return PinStatusReport(
            ok=False,
            status="failed",
            pin_states=pin_states,
            reason="backend did not return readable pin states",
        )

    @staticmethod
    def _normalize_pins(pins: list[int]) -> list[int]:
        normalized: list[int] = []
        seen = set()
        for pin in pins:
            try:
                value = int(pin)
            except (TypeError, ValueError):
                continue
            if value < 0 or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

