"""
Auto-updater — checks for a newer version at UPDATE_CHECK_URL on startup.
Runs in a background thread so it never blocks the UI.
"""
import threading
import webbrowser
import urllib.request
import json
import customtkinter as ctk
from shared.version import APP_VERSION, UPDATE_CHECK_URL


def _version_tuple(v: str):
    """Convert '1.2.3' → (1, 2, 3) for comparison."""
    try:
        return tuple(int(x) for x in str(v).split("."))
    except Exception:
        return (0, 0, 0)


def _fetch_latest() -> dict | None:
    """Download version.json from GitHub. Returns None on any failure."""
    try:
        req = urllib.request.Request(
            UPDATE_CHECK_URL,
            headers={"User-Agent": "MyVA-CallAnalyzer-Updater/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, parent, latest_version: str, release_notes: str, download_url: str):
        super().__init__(parent)
        self.download_url = download_url
        self.title("Update Available")
        self.geometry("460x260")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color="#0F1923")
        self._build(latest_version, release_notes)

    def _build(self, latest_version: str, release_notes: str):
        # Header
        ctk.CTkLabel(
            self,
            text="A new version is available!",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#3B82F6",
        ).pack(pady=(28, 4))

        ctk.CTkLabel(
            self,
            text=f"Version {APP_VERSION}  →  {latest_version}",
            font=ctk.CTkFont(size=13),
            text_color="#8FA3BC",
        ).pack(pady=(0, 12))

        # Release notes box
        if release_notes:
            box = ctk.CTkTextbox(
                self, height=80,
                fg_color="#1A2535", text_color="#D0DCE8",
                font=ctk.CTkFont(size=12), corner_radius=8,
            )
            box.pack(fill="x", padx=24, pady=(0, 18))
            box.insert("1.0", release_notes)
            box.configure(state="disabled")

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack()
        ctk.CTkButton(
            btn_row, text="Download Update", width=160,
            fg_color="#3B82F6", hover_color="#2563EB",
            font=ctk.CTkFont(weight="bold"),
            command=self._download,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            btn_row, text="Skip This Version", width=140,
            fg_color="transparent", border_width=1, border_color="#2A3F5C",
            text_color="#8FA3BC", hover_color="#1A2535",
            command=self.destroy,
        ).pack(side="left", padx=8)

    def _download(self):
        webbrowser.open(self.download_url)
        self.destroy()


def check_for_updates(parent_window) -> None:
    """Call this on startup — runs the check in a background thread."""

    def _check():
        data = _fetch_latest()
        if not data:
            return  # No internet or URL not set up yet — silent fail

        latest = data.get("version", "0.0.0")
        if _version_tuple(latest) > _version_tuple(APP_VERSION):
            notes = data.get("release_notes", "")
            url = data.get("download_url", "")
            # Show dialog on the UI thread
            parent_window.after(
                0,
                lambda: UpdateDialog(parent_window, latest, notes, url),
            )

    threading.Thread(target=_check, daemon=True).start()
