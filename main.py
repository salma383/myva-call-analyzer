import sys
import os

# Make sure shared/ and project root are importable when frozen by PyInstaller
if getattr(sys, "frozen", False):
    base = sys._MEIPASS
else:
    base = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, base)


def _suppress_subprocess_windows():
    """
    Stop ffmpeg/ffprobe (invoked by pydub) from flashing a console window on
    every call. MUST run before any pydub import so our patched Popen wraps
    every subsequent subprocess.Popen call.

    Without this: each ffmpeg invocation during prepare_audio / silence
    detection / audio duration probe / format transcode opens a black
    terminal window that immediately closes. Annoying during analysis.
    """
    if sys.platform != "win32":
        return
    import subprocess
    # Flags: CREATE_NO_WINDOW = 0x08000000
    _NO_WINDOW = 0x08000000
    _original_popen = subprocess.Popen

    class _QuietPopen(_original_popen):
        def __init__(self, *args, **kwargs):
            # Only silence when caller didn't already pass creationflags —
            # don't override intentional behavior.
            if "creationflags" not in kwargs:
                kwargs["creationflags"] = _NO_WINDOW
            # Same for startupinfo
            if "startupinfo" not in kwargs:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0  # SW_HIDE
                kwargs["startupinfo"] = si
            super().__init__(*args, **kwargs)

    subprocess.Popen = _QuietPopen


_suppress_subprocess_windows()


def _set_windows_app_id():
    """
    Tell Windows this is a distinct app, not 'python.exe', so the taskbar
    uses our embedded icon instead of the generic Python feather.
    MUST be called before any Tk window is created.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # Arbitrary but unique app id — groups all MyVA windows under one icon
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "MyVA.CallAnalysis.Desktop.1"
        )
    except Exception:
        pass


_set_windows_app_id()

from config import api_manager, settings
from ui.main_window import MainWindow


def main():
    app = MainWindow()

    # Check for updates in the background — silent if no internet / URL not set
    try:
        from utils.updater import check_for_updates
        check_for_updates(app)
    except Exception:
        pass

    app.mainloop()


if __name__ == "__main__":
    main()
