import os
import customtkinter as ctk
from tkinterdnd2 import TkinterDnD

from ui.upload_panel import UploadPanel
from ui.results_panel import ResultsPanel
from ui.settings_dialog import SettingsDialog
from ui.theme import *
from shared.criteria import CLIENT_CRITERIA
from config import settings


# ─── Icon helper ─────────────────────────────────────────────────────────────

def _get_icon_path() -> str | None:
    """Return path to app.ico if it exists (works both dev and frozen exe)."""
    import sys
    base = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    ico = os.path.join(base, "assets", "icons", "app.ico")
    return ico if os.path.exists(ico) else None


class MainWindow(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("MyVA Call Analysis")
        self.geometry("1340x840")
        self.minsize(960, 640)
        self.configure(bg=BG_MAIN)

        # Set window icon — triple-layer so Windows taskbar + window both update
        self._apply_icon()

        self._build_ui()

    def _apply_icon(self):
        ico = _get_icon_path()
        if not ico:
            return

        # 1. iconbitmap(default=...) applies to EVERY Tk window (including dialogs)
        #    and is what Windows usually reads for the taskbar.
        try:
            self.iconbitmap(default=ico)
        except Exception:
            pass

        # 2. Direct iconbitmap on this window (belt-and-suspenders).
        try:
            self.iconbitmap(ico)
        except Exception:
            pass

        # 3. iconphoto fallback — reads the PNG-ish image through PIL and sets
        #    it as the WM icon. This covers cases where Tk's ICO parser fails.
        try:
            from PIL import Image, ImageTk
            img = Image.open(ico)
            photo = ImageTk.PhotoImage(img)
            self.iconphoto(True, photo)
            self._icon_ref = photo  # keep a ref so Tk doesn't GC it
        except Exception:
            pass

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, height=54, fg_color=BG_SIDEBAR, corner_radius=0)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)

        # Logo / brand area
        brand = ctk.CTkFrame(top, fg_color="transparent")
        brand.pack(side="left", padx=20, pady=8)

        # Try to show logo image; fall back to text if not found
        logo_path = self._get_logo_path()
        if logo_path:
            try:
                from PIL import Image
                img = Image.open(logo_path).convert("RGBA")
                img.thumbnail((120, 38), Image.LANCZOS)
                logo_img = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
                ctk.CTkLabel(brand, image=logo_img, text="").pack(side="left")
            except Exception:
                self._build_text_brand(brand)
        else:
            self._build_text_brand(brand)

        # Version badge
        try:
            from shared.version import APP_VERSION
            ctk.CTkLabel(
                top, text=f"v{APP_VERSION}",
                font=ctk.CTkFont(size=10),
                text_color=TEXT_MUTED,
            ).pack(side="left", padx=(0, 16))
        except ImportError:
            pass

        # Settings button
        ctk.CTkButton(
            top, text="⚙  Settings",
            width=110, height=34,
            fg_color=BG_CARD, hover_color=BG_HOVER,
            border_width=1, border_color=BORDER,
            text_color=TEXT_SECONDARY,
            font=ctk.CTkFont(size=12),
            corner_radius=8,
            command=self._open_settings,
        ).pack(side="right", padx=16, pady=10)

        # ── Body ──────────────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color=BG_MAIN, corner_radius=0)
        body.pack(fill="both", expand=True)

        # Sidebar
        sidebar = ctk.CTkFrame(body, width=230, fg_color=BG_SIDEBAR, corner_radius=0)
        sidebar.pack(fill="y", side="left")
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        # Thin separator line
        ctk.CTkFrame(body, width=1, fg_color=BORDER, corner_radius=0).pack(
            fill="y", side="left"
        )

        # Main content area
        main = ctk.CTkFrame(body, fg_color=BG_MAIN, corner_radius=0)
        main.pack(fill="both", expand=True, side="left")

        self.results = ResultsPanel(main, on_mv_saved=self._on_mv_saved)
        self.upload  = UploadPanel(main, on_analyze=self._on_analyze)

        self.upload.pack(fill="x", padx=18, pady=(18, 10))
        self.results.pack(fill="both", expand=True, padx=18, pady=(0, 18))

    def _build_text_brand(self, parent):
        """Fallback: text logo when image not available."""
        ctk.CTkLabel(
            parent,
            text="MyVA",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=ACCENT,
        ).pack(side="left")
        ctk.CTkLabel(
            parent,
            text=" Call Analysis",
            font=ctk.CTkFont(size=15),
            text_color=TEXT_SECONDARY,
        ).pack(side="left")

    def _get_logo_path(self) -> str | None:
        import sys
        base = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        for name in ("logo.png", "logo.jpg", "logo.jpeg", "logo.webp"):
            p = os.path.join(base, "assets", "icons", name)
            if os.path.exists(p):
                return p
        return None

    def _build_sidebar(self, parent):
        # ── Section: Analysis Settings ────────────────────────────────────────
        self._sidebar_section(parent, "Analysis Settings")

        # Client
        self._sidebar_label(parent, "Client")
        self.client_var = ctk.StringVar(value=list(CLIENT_CRITERIA.keys())[0])
        self.client_menu = ctk.CTkComboBox(
            parent,
            values=list(CLIENT_CRITERIA.keys()),
            variable=self.client_var,
            width=200, height=34,
            fg_color=BG_INPUT,
            border_color=BORDER,
            button_color=BORDER,
            button_hover_color=ACCENT,
            dropdown_fg_color=BG_CARD,
            dropdown_hover_color=BG_HOVER,
            dropdown_text_color=TEXT_PRIMARY,
            text_color=TEXT_PRIMARY,
            font=ctk.CTkFont(size=12),
            corner_radius=8,
            state="readonly",
        )
        self.client_menu.pack(padx=15, pady=(0, 12))

        # Caller Name
        self._sidebar_label(parent, "Caller Name")
        saved_name = settings.get("caller_name") or ""
        self.caller_var = ctk.StringVar(value=saved_name)
        ctk.CTkEntry(
            parent,
            textvariable=self.caller_var,
            placeholder_text="Your name",
            width=200, height=34,
            fg_color=BG_INPUT,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_MUTED,
            corner_radius=8,
        ).pack(padx=15, pady=(0, 12))

        # Call Date
        self._sidebar_label(parent, "Call Date")
        from datetime import date
        self.date_var = ctk.StringVar(value=date.today().strftime("%m/%d/%Y"))
        ctk.CTkEntry(
            parent,
            textvariable=self.date_var,
            placeholder_text="MM/DD/YYYY",
            width=200, height=34,
            fg_color=BG_INPUT,
            border_color=BORDER,
            text_color=TEXT_PRIMARY,
            placeholder_text_color=TEXT_MUTED,
            corner_radius=8,
        ).pack(padx=15, pady=(0, 16))

        # Divider
        ctk.CTkFrame(parent, height=1, fg_color=BORDER).pack(fill="x", padx=12)

        # ── Section: Recent Calls ─────────────────────────────────────────────
        self._sidebar_section(parent, "Recent Calls")

        self.history_frame = ctk.CTkScrollableFrame(
            parent,
            fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=ACCENT,
            corner_radius=0,
        )
        self.history_frame.pack(fill="both", expand=True, padx=8, pady=(0, 10))

    def _sidebar_section(self, parent, title: str):
        ctk.CTkLabel(
            parent, text=title,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=ACCENT,
        ).pack(anchor="w", padx=16, pady=(16, 6))

    def _sidebar_label(self, parent, text: str):
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=11),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", padx=16, pady=(0, 4))

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_analyze(self, file_path: str):
        caller = self.caller_var.get().strip() or "Agent"
        settings.set_value("caller_name", caller)
        self.results.start_analysis(
            file_path=file_path,
            client_key=self.client_var.get(),
            caller_name=caller,
            call_date=self.date_var.get(),
            on_progress=self.upload.set_status,
            on_done=self.upload.reset,
        )

    def _on_mv_saved(self, mv: str):
        self.results.recalculate_temp(mv)

    def _open_settings(self):
        SettingsDialog(self)

    def add_history_entry(self, label: str, score: int):
        if score >= 75:
            score_color, bg = SUCCESS, SUCCESS_BG
        elif score >= 50:
            score_color, bg = WARNING, WARNING_BG
        else:
            score_color, bg = DANGER, DANGER_BG

        row = ctk.CTkFrame(
            self.history_frame,
            fg_color=BG_CARD,
            corner_radius=8,
            border_width=1,
            border_color=BORDER,
        )
        row.pack(fill="x", pady=3, padx=3)

        ctk.CTkLabel(
            row, text=label,
            font=ctk.CTkFont(size=10),
            text_color=TEXT_SECONDARY,
            anchor="w",
            wraplength=150,
        ).pack(side="left", padx=8, pady=6)

        badge = ctk.CTkFrame(row, fg_color=bg, corner_radius=6, width=34, height=24)
        badge.pack(side="right", padx=8, pady=6)
        badge.pack_propagate(False)
        ctk.CTkLabel(
            badge, text=str(score),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=score_color,
        ).place(relx=0.5, rely=0.5, anchor="center")
