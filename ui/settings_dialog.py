import customtkinter as ctk
from config import settings
from ui.theme import *


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("400x200")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color=BG_CARD)
        self._build()

    def _build(self):
        # Header
        header = ctk.CTkFrame(self, fg_color=BG_SIDEBAR, corner_radius=0, height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="⚙  Settings",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=20, pady=14)

        # Body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)

        # Theme row
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=6)

        ctk.CTkLabel(
            row, text="Theme",
            width=90, anchor="w",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_SECONDARY,
        ).pack(side="left")

        self.theme_var = ctk.StringVar(value=settings.get("theme") or "dark")
        ctk.CTkComboBox(
            row,
            values=["dark", "light", "system"],
            variable=self.theme_var,
            width=150, height=34,
            fg_color=BG_INPUT,
            border_color=BORDER,
            button_color=BORDER,
            button_hover_color=ACCENT,
            dropdown_fg_color=BG_CARD,
            dropdown_text_color=TEXT_PRIMARY,
            text_color=TEXT_PRIMARY,
            corner_radius=8,
            state="readonly",
        ).pack(side="left", padx=10)

        # Save
        ctk.CTkButton(
            body, text="Save",
            width=120, height=36,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8,
            command=self._save,
        ).pack(pady=(16, 0))

    def _save(self):
        settings.set_value("theme", self.theme_var.get())
        ctk.set_appearance_mode(self.theme_var.get())
        self.destroy()
