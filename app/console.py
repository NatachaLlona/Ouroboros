"""Conservative terminal color support with native Windows VT detection."""
import copy
import logging
import os


def supports_color(stream):
    if "NO_COLOR" in os.environ or not getattr(stream, "isatty", lambda: False)():
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    if os.name != "nt":
        return bool(os.environ.get("TERM"))
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetConsoleMode.restype = wintypes.BOOL
        kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.SetConsoleMode.restype = wintypes.BOOL
        handle = msvcrt.get_osfhandle(stream.fileno())
        mode = wintypes.DWORD()
        return bool(kernel.GetConsoleMode(handle, ctypes.byref(mode)) and
                    kernel.SetConsoleMode(handle, mode.value | 0x0004))
    except (OSError, ValueError, AttributeError):
        return False


def prepare_console(stream):
    # Windows consoles already use Unicode; redirected text streams also need UTF-8.
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass
    return stream


class LevelColorFormatter(logging.Formatter):
    COLORS = {"DEBUG": "\x1b[90m", "INFO": "\x1b[32m", "WARNING": "\x1b[33m",
              "ERROR": "\x1b[31m", "CRITICAL": "\x1b[1;31m"}

    def __init__(self, plain_formatter, stream):
        super().__init__()
        self.plain_formatter = plain_formatter
        self.stream = stream

    def format(self, record):
        if not supports_color(self.stream):
            return self.plain_formatter.format(record)
        # Replace only the level placeholder; retain visible padding and the shared record.
        cloned = copy.copy(record)
        marker = "\ufdd0" * len(record.level)
        cloned.level = marker
        text = self.plain_formatter.format(cloned)
        return text.replace(marker, self.COLORS[record.level] + record.level + "\x1b[0m", 1)
