import sys
import time

from typing import Callable


class ScannerUI:
    """Shared interactive CLI helpers for scanner-specific UIs."""

    def __init__(self, prompt: str = "> ", wait_hook: Callable[[], None] | None = None):
        self.run_loop = True
        self._prompt = prompt
        self._wait_hook = wait_hook

    def _idle_wait(self):
        if self._wait_hook is not None:
            self._wait_hook()
            return
        time.sleep(0.1)

    def read_cli_byte(self):
        while True:
            if sys.stdin is not None and not sys.stdin.closed:
                try:
                    input_value = sys.stdin.buffer.read(1)
                    if input_value:
                        return input_value[0]
                except Exception:
                    pass
            self._idle_wait()

    def read_cli_line(self) -> str:
        try:
            line = sys.stdin.buffer.readline()
        except Exception:
            return ""
        if not line:
            return ""
        return line.decode("utf-8", errors="ignore").strip()

    def read_cli_nonempty_line(self, max_attempts: int = 2) -> str:
        text = ""
        for _ in range(max_attempts):
            text = self.read_cli_line()
            if text:
                return text
        return text

    def read_cli_unsigned_int(self):
        buffer = ""
        idx = 0
        while True:
            if sys.stdin is not None and not sys.stdin.closed:
                try:
                    input_value = sys.stdin.buffer.read(1)
                    if input_value:
                        byte = input_value[0]
                        sys.stdout.write(chr(byte if 0x20 <= byte <= 0x7e else 0x20))
                        sys.stdout.flush()
                        if idx < 20 - 1 and byte not in (0x0d, 0x0a):
                            if 0x30 <= byte <= 0x7a:
                                buffer = buffer + chr(byte)
                                idx += 1
                        else:
                            sys.stdout.write("\n")
                            sys.stdout.flush()
                            return int(buffer, 0) if buffer else 0
                except Exception:
                    pass
            self._idle_wait()

    @staticmethod
    def parse_pin_spec(pin_spec: str) -> list[int]:
        pins: list[int] = []
        for token in pin_spec.replace(",", " ").split():
            if "-" in token:
                parts = token.split("-")
                if len(parts) != 2:
                    continue
                try:
                    start = int(parts[0])
                    end = int(parts[1])
                except (TypeError, ValueError):
                    continue
                if start < 0 or end < 0:
                    continue
                step = 1 if end >= start else -1
                pins.extend(range(start, end + step, step))
                continue
            try:
                pin = int(token)
            except (TypeError, ValueError):
                continue
            if pin >= 0:
                pins.append(pin)

        deduped: list[int] = []
        seen = set()
        for pin in pins:
            if pin not in seen:
                seen.add(pin)
                deduped.append(pin)
        return deduped

    def read_cli_pin_list(self):
        text = ""
        for _ in range(2):
            try:
                line = sys.stdin.buffer.readline()
            except Exception:
                return []

            if not line:
                return []

            text = line.decode("utf-8", errors="ignore").strip()
            if text:
                break
        if not text:
            return []
        return self.parse_pin_spec(text)

    def print_prompt(self):
        sys.stdout.write(self._prompt)
        sys.stdout.flush()

    def command_line_interface(self):
        raise NotImplementedError

    def loop(self):
        self.print_prompt()
        self.command_line_interface()
