"""
Crash logger — captures every uncaught exception (main thread, worker threads,
Tk callbacks) into %LocalAppData%\\MyVA\\logs\\errors.log with a full traceback.

Why: intermittent runtime errors are impossible to diagnose without a stack trace.
A windowed PyInstaller build has no console, so prints go nowhere. This routes
every crash through a single file Salma can send back when reporting bugs.

MUST be installed early in main.py — before the Tk root is created and before
any worker thread is spawned, so all exception hooks are in place when code
starts running.
"""

from __future__ import annotations

import os
import sys
import traceback
import threading
from datetime import datetime


def _log_dir() -> str:
    base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    d = os.path.join(base, "MyVA", "logs")
    os.makedirs(d, exist_ok=True)
    return d


def _log_path() -> str:
    return os.path.join(_log_dir(), "errors.log")


_lock = threading.Lock()


def _write_entry(source: str, exc_type, exc_value, exc_tb) -> None:
    """Append one timestamped entry. Thread-safe."""
    try:
        from shared.version import APP_VERSION
        version = APP_VERSION
    except Exception:
        version = "unknown"

    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    when = datetime.now().isoformat(timespec="seconds")
    entry = (
        f"\n{'=' * 70}\n"
        f"[{when}] v{version} | source={source} | thread={threading.current_thread().name}\n"
        f"{tb_text}"
    )
    try:
        with _lock:
            with open(_log_path(), "a", encoding="utf-8") as f:
                f.write(entry)
    except Exception:
        # Last-resort: don't let the logger itself crash the app
        pass


def _excepthook(exc_type, exc_value, exc_tb):
    _write_entry("main", exc_type, exc_value, exc_tb)
    # Also print to stderr (visible in console builds, ignored in windowed)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _thread_excepthook(args):
    _write_entry("thread", args.exc_type, args.exc_value, args.exc_traceback)


def install() -> None:
    """Wire up all three exception hooks. Idempotent."""
    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook

    # Tk callback exceptions need to be patched per-root after Tk is imported.
    # We monkey-patch the class method so every Tk root instance picks it up.
    try:
        import tkinter

        def _tk_report_callback_exception(self, exc, val, tb):
            _write_entry("tk_callback", exc, val, tb)

        tkinter.Tk.report_callback_exception = _tk_report_callback_exception
    except Exception:
        pass


def log_exception(source: str = "manual") -> None:
    """Manually log the current exception from inside an except block."""
    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_type is not None:
        _write_entry(source, exc_type, exc_value, exc_tb)


def errors_log_path() -> str:
    """Public accessor — UI can show this path so Salma knows where to find logs."""
    return _log_path()
