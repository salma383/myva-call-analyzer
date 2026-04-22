import os
import customtkinter as ctk
from tkinterdnd2 import DND_FILES
from tkinter import filedialog
from typing import Callable
from ui.theme import *

SUPPORTED = {".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".flac", ".webm"}


class UploadPanel(ctk.CTkFrame):
    def __init__(self, parent, on_analyze: Callable[[str], None]):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=12,
                         border_width=1, border_color=BORDER)
        self.on_analyze = on_analyze
        self._file_path = None
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # Drop zone
        self.drop_zone = ctk.CTkFrame(
            self,
            fg_color=BG_INPUT,
            corner_radius=10,
            border_width=2,
            border_color=BORDER,
        )
        self.drop_zone.pack(fill="x", padx=16, pady=(16, 10))

        # Inner content of drop zone
        inner = ctk.CTkFrame(self.drop_zone, fg_color="transparent")
        inner.pack(pady=20, padx=20)

        ctk.CTkLabel(
            inner, text="⬆",
            font=ctk.CTkFont(size=28),
            text_color=ACCENT,
        ).pack()

        self.drop_label = ctk.CTkLabel(
            inner,
            text="Drop your call recording here",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT_PRIMARY,
        )
        self.drop_label.pack(pady=(4, 2))

        ctk.CTkLabel(
            inner,
            text="MP3 · WAV · M4A · MP4 · OGG · FLAC · WEBM",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
        ).pack()

        # Register DnD
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self._on_drop)
        inner.drop_target_register(DND_FILES)
        inner.dnd_bind("<<Drop>>", self._on_drop)
        self.drop_label.drop_target_register(DND_FILES)
        self.drop_label.dnd_bind("<<Drop>>", self._on_drop)

        # Controls row
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=16, pady=(0, 4))

        self.browse_btn = ctk.CTkButton(
            controls,
            text="Browse Files",
            width=130, height=34,
            fg_color=BG_HOVER,
            hover_color=BORDER,
            border_width=1, border_color=BORDER_LIGHT,
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(size=12),
            corner_radius=8,
            command=self._browse,
        )
        self.browse_btn.pack(side="left")

        self.analyze_btn = ctk.CTkButton(
            controls,
            text="▶  Analyze",
            width=130, height=34,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8,
            state="disabled",
            command=self._analyze,
        )
        self.analyze_btn.pack(side="left", padx=10)

        self.file_label = ctk.CTkLabel(
            controls,
            text="No file selected",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        self.file_label.pack(side="left", padx=8)

        # Progress row
        prog_row = ctk.CTkFrame(self, fg_color="transparent")
        prog_row.pack(fill="x", padx=16, pady=(4, 14))

        self.progress = ctk.CTkProgressBar(
            prog_row,
            height=6,
            corner_radius=3,
            fg_color=BG_HOVER,
            progress_color=ACCENT,
        )
        self.progress.set(0)
        self.progress.pack(fill="x", side="left", expand=True)

        self.status_label = ctk.CTkLabel(
            prog_row,
            text="Ready",
            width=190,
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
            anchor="e",
        )
        self.status_label.pack(side="right", padx=(12, 0))

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_drop(self, event):
        paths = self.tk.splitlist(event.data)
        if paths:
            self._set_file(paths[0].strip("{}"))

    def _browse(self):
        path = filedialog.askopenfilename(
            filetypes=[("Audio files", "*.mp3 *.wav *.m4a *.mp4 *.ogg *.flac *.webm")]
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED:
            self.status_label.configure(text="Unsupported format", text_color=DANGER)
            return

        self._file_path = path
        name = os.path.basename(path)
        self.file_label.configure(text=name, text_color=TEXT_PRIMARY)
        self.drop_label.configure(text=f"📎  {name}")
        self.drop_zone.configure(border_color=ACCENT)
        self.analyze_btn.configure(state="normal")
        self.set_status(0, "Ready to analyze")

    def _analyze(self):
        if self._file_path:
            self.analyze_btn.configure(state="disabled")
            self.browse_btn.configure(state="disabled")
            self.on_analyze(self._file_path)

    # ── Public ────────────────────────────────────────────────────────────────

    def set_status(self, pct: int, message: str):
        """Called from pipeline thread via after()."""
        self.progress.set(pct / 100)
        color = SUCCESS if pct >= 100 else ACCENT
        self.progress.configure(progress_color=color)
        self.status_label.configure(text=message, text_color=TEXT_SECONDARY)
        if pct >= 100:
            self.analyze_btn.configure(state="normal")
            self.browse_btn.configure(state="normal")

    def reset(self):
        self._file_path = None
        self.file_label.configure(text="No file selected", text_color=TEXT_MUTED)
        self.drop_label.configure(text="Drop your call recording here")
        self.drop_zone.configure(border_color=BORDER)
        self.analyze_btn.configure(state="disabled")
        self.progress.set(0)
        self.progress.configure(progress_color=ACCENT)
        self.status_label.configure(text="Ready", text_color=TEXT_MUTED)
