import customtkinter as ctk
from tkinter import messagebox
from typing import Callable, Optional
from core import pipeline as pipe
from shared.criteria import CLIENT_CRITERIA, TEMP_LOGIC
from ui.theme import *
import re as _re


class ResultsPanel(ctk.CTkFrame):
    def __init__(self, parent, on_mv_saved: Callable[[str], None]):
        super().__init__(parent, fg_color="transparent", corner_radius=0)
        self.on_mv_saved = on_mv_saved
        self._result: Optional[dict] = None
        self._on_progress_cb = None
        self._on_done_cb = None
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        self.tabs = ctk.CTkTabview(
            self,
            fg_color=BG_CARD,
            segmented_button_fg_color=BG_SIDEBAR,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            segmented_button_unselected_color=BG_SIDEBAR,
            segmented_button_unselected_hover_color=BG_HOVER,
            text_color=TEXT_SECONDARY,
            text_color_disabled=TEXT_MUTED,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        self.tabs.pack(fill="both", expand=True)

        self._tab_template   = self.tabs.add("  Lead Template  ")
        self._tab_checklist  = self.tabs.add("  Checklist  ")
        self._tab_score      = self.tabs.add("  Score  ")
        self._tab_transcript = self.tabs.add("  Transcript  ")

        self._build_template_tab()
        self._build_checklist_tab()
        self._build_score_tab()
        self._build_transcript_tab()

    # ── Template tab ──────────────────────────────────────────────────────────

    def _build_template_tab(self):
        top = ctk.CTkFrame(self._tab_template, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 6))

        # MV input row
        self.mv_frame = ctk.CTkFrame(top, fg_color="transparent")
        self.mv_frame.pack(side="left")

        ctk.CTkLabel(
            self.mv_frame, text="Zestimate / MV",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 6))

        self.mv_entry = ctk.CTkEntry(
            self.mv_frame, width=130, height=32,
            placeholder_text="e.g. $280,000",
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_PRIMARY, placeholder_text_color=TEXT_MUTED,
            corner_radius=8,
        )
        self.mv_entry.pack(side="left")

        ctk.CTkButton(
            self.mv_frame, text="Save & Recalc",
            width=130, height=32,
            fg_color=ACCENT_DIM, hover_color=ACCENT,
            text_color=ACCENT_LIGHT,
            border_width=1, border_color=ACCENT,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8,
            command=self._save_mv,
        ).pack(side="left", padx=8)

        # Action buttons
        btn_row = ctk.CTkFrame(top, fg_color="transparent")
        btn_row.pack(side="right")

        ctk.CTkButton(
            btn_row, text="Copy", width=80, height=32,
            fg_color=BG_HOVER, hover_color=BORDER,
            text_color=TEXT_SECONDARY,
            border_width=1, border_color=BORDER,
            corner_radius=8,
            command=self._copy_template,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            btn_row, text="Export…", width=90, height=32,
            fg_color=BG_HOVER, hover_color=BORDER,
            text_color=TEXT_SECONDARY,
            border_width=1, border_color=BORDER,
            corner_radius=8,
            command=self._export,
        ).pack(side="left")

        self.template_box = ctk.CTkTextbox(
            self._tab_template,
            font=ctk.CTkFont(family=FONT_MONO, size=12),
            fg_color=BG_INPUT,
            text_color=TEXT_PRIMARY,
            border_color=BORDER,
            border_width=1,
            corner_radius=8,
            wrap="word",
            scrollbar_button_color=BORDER_LIGHT,
            scrollbar_button_hover_color=ACCENT_DIM,
        )
        self.template_box.pack(fill="both", expand=True, padx=12, pady=(4, 12))

    # ── Checklist tab ─────────────────────────────────────────────────────────

    def _build_checklist_tab(self):
        self.checklist_scroll = ctk.CTkScrollableFrame(
            self._tab_checklist,
            fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=ACCENT,
        )
        self.checklist_scroll.pack(fill="both", expand=True, padx=12, pady=10)

    # ── Score tab ─────────────────────────────────────────────────────────────

    def _build_score_tab(self):
        scroll = ctk.CTkScrollableFrame(
            self._tab_score,
            fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=ACCENT,
        )
        scroll.pack(fill="both", expand=True, padx=12, pady=10)
        self.score_container = scroll

    # ── Transcript tab ────────────────────────────────────────────────────────

    def _build_transcript_tab(self):
        top = ctk.CTkFrame(self._tab_transcript, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 6))

        ctk.CTkButton(
            top, text="Copy Transcript",
            width=140, height=32,
            fg_color=BG_HOVER, hover_color=BORDER,
            text_color=TEXT_SECONDARY,
            border_width=1, border_color=BORDER,
            corner_radius=8,
            command=self._copy_transcript,
        ).pack(side="right")

        self.transcript_box = ctk.CTkTextbox(
            self._tab_transcript,
            font=ctk.CTkFont(family=FONT_MONO, size=12),
            fg_color=BG_INPUT,
            text_color=TEXT_PRIMARY,
            border_color=BORDER,
            border_width=1,
            corner_radius=8,
            wrap="word",
            scrollbar_button_color=BORDER_LIGHT,
            scrollbar_button_hover_color=ACCENT_DIM,
        )
        self.transcript_box.pack(fill="both", expand=True, padx=12, pady=(4, 12))

    # ── Public API ────────────────────────────────────────────────────────────

    def start_analysis(self, file_path: str, client_key: str, caller_name: str,
                       call_date: str, on_progress=None, on_done=None):
        self._clear()
        self._on_progress_cb = on_progress
        self._on_done_cb = on_done

        client_type = CLIENT_CRITERIA[client_key]["type"]
        if client_type == "real_estate":
            self.mv_frame.pack(side="left")
        else:
            self.mv_frame.pack_forget()

        pipe.run(
            file_path=file_path,
            client_key=client_key,
            caller_name=caller_name,
            call_date=call_date,
            on_progress=self._on_progress,
            on_complete=self._on_complete,
            on_error=self._on_error,
        )

    def recalculate_temp(self, mv: str):
        if not self._result:
            return

        result = self._result
        result["mv"] = mv

        def _parse(s):
            cleaned = _re.sub(r'[^\d.]', '', str(s))
            return float(cleaned) if cleaned else None

        mv_val  = _parse(mv)
        cd      = result.get("call_data") or {}
        ap      = _parse(cd.get("ap")) if cd.get("ap") else None
        has_motive      = cd.get("has_valid_motive", False)
        timeline        = cd.get("timeline_months")
        open_to_listing = cd.get("open_to_listing", False)
        current_temp    = result.get("preliminary_temp", "").lower()

        if current_temp == "throwaway" or not has_motive:
            new_temp = "Throwaway" if current_temp == "throwaway" else "Cold"
        elif timeline and timeline > 12:
            new_temp = "Nurture"
        elif timeline and timeline >= 9:
            new_temp = "Cold"
        elif mv_val and ap:
            if ap < mv_val:
                new_temp = "Hot"
            elif open_to_listing:
                new_temp = "Warm"
            else:
                new_temp = "Cold"
        else:
            new_temp = result.get("preliminary_temp", "Cold")

        result["preliminary_temp"] = new_temp
        self._render_results(result)

    # ── Pipeline callbacks ────────────────────────────────────────────────────

    def _on_progress(self, pct: int, msg: str):
        if self._on_progress_cb:
            self.after(0, lambda p=pct, m=msg: self._on_progress_cb(p, m))

    def _on_complete(self, result: dict):
        self._result = result
        self.after(0, lambda: self._render_results(result))
        if self._on_done_cb:
            self.after(0, self._on_done_cb)
        try:
            score_val = result.get("score", 0)
            label = f"{result.get('client', '')} — {result.get('call_date', '')}"
            self.winfo_toplevel().add_history_entry(label, score_val)
        except Exception:
            pass

    def _on_error(self, msg: str):
        self.after(0, lambda: messagebox.showerror("Analysis Error", msg))
        if self._on_progress_cb:
            self.after(0, lambda: self._on_progress_cb(0, "Error — see popup"))
        if self._on_done_cb:
            self.after(0, self._on_done_cb)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render_results(self, result: dict):
        self._clear_content()

        # ── Template tab ──────────────────────────────────────────────────────
        template_text = result.get("lead_template", "No template generated.")

        # Fill MV / Zestimate / Market Value field if user provided it
        if result.get("mv"):
            mv_val = result["mv"]
            for label in ("Zestimate:", "MV:", "Market Value:", "Market value:",
                          "Zestimate", "MV", "Market Value", "Market value"):
                # Replace blank lines that contain only the label
                template_text = _re.sub(
                    rf'^({_re.escape(label)})\s*$',
                    f"{label} {mv_val}",
                    template_text, flags=_re.IGNORECASE | _re.MULTILINE
                )
                # Replace label followed by whitespace/colon and nothing
                template_text = template_text.replace(f"{label}\n", f"{label} {mv_val}\n")
                template_text = template_text.replace(f"{label} \n", f"{label} {mv_val}\n")

        # Replace the entire Temp line with the confirmed value
        actual_temp = result.get("preliminary_temp", "")
        if actual_temp:
            template_text = _re.sub(
                r'^((?:Lead\s+)?Temp(?:erature)?:).*$',
                lambda m: f"{m.group(1)} {actual_temp}",
                template_text,
                flags=_re.IGNORECASE | _re.MULTILINE
            )

        self.template_box.configure(state="normal")
        self.template_box.insert("1.0", template_text)
        self.template_box.configure(state="disabled")

        # ── Transcript tab ────────────────────────────────────────────────────
        transcript_text = self._merge_transcript(result)
        self.transcript_box.configure(state="normal")
        self.transcript_box.insert("1.0", transcript_text)
        self.transcript_box.configure(state="disabled")

        # ── Checklist tab ─────────────────────────────────────────────────────
        self._render_checklist(
            result.get("checklist", []),
            result.get("hard_disqualifiers_triggered", [])
        )

        # ── Score tab ─────────────────────────────────────────────────────────
        self._render_score(result)

        self.tabs.set("  Lead Template  ")

    def _render_checklist(self, checklist: list, disqualifiers: list):
        for w in self.checklist_scroll.winfo_children():
            w.destroy()

        ICONS = {
            "yes":     ("✓", SUCCESS,  SUCCESS_BG),
            "no":      ("✗", DANGER,   DANGER_BG),
            "partial": ("◑", WARNING,  WARNING_BG),
            "n/a":     ("—", GRAY,     BG_CARD),
        }

        for item in checklist:
            res = item.get("result", "n/a").lower()
            icon, fg_color, bg_color = ICONS.get(res, ("?", GRAY, BG_CARD))

            row = ctk.CTkFrame(
                self.checklist_scroll,
                fg_color=BG_CARD,
                corner_radius=8,
                border_width=1,
                border_color=BORDER,
            )
            row.pack(fill="x", pady=3)

            # Status badge
            badge = ctk.CTkFrame(row, fg_color=bg_color, corner_radius=6, width=36, height=36)
            badge.pack(side="left", padx=(8, 0), pady=8)
            badge.pack_propagate(False)
            ctk.CTkLabel(
                badge, text=icon,
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=fg_color,
            ).place(relx=0.5, rely=0.5, anchor="center")

            # Item text
            ctk.CTkLabel(
                row,
                text=item.get("item", ""),
                font=ctk.CTkFont(size=12),
                text_color=TEXT_PRIMARY,
                anchor="w", wraplength=480,
            ).pack(side="left", fill="x", expand=True, padx=10, pady=8)

            # Note
            if item.get("note"):
                ctk.CTkLabel(
                    row,
                    text=item["note"],
                    font=ctk.CTkFont(size=11),
                    text_color=TEXT_MUTED,
                    anchor="e",
                ).pack(side="right", padx=12)

        # Hard disqualifiers section
        if disqualifiers:
            # Section header
            hdr = ctk.CTkFrame(self.checklist_scroll, fg_color="transparent")
            hdr.pack(fill="x", pady=(14, 4))
            ctk.CTkFrame(hdr, height=1, fg_color=DANGER).pack(fill="x")
            ctk.CTkLabel(
                hdr,
                text="⚠  Hard Disqualifiers Triggered",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=DANGER,
            ).pack(anchor="w", pady=(6, 0))

            for d in disqualifiers:
                row = ctk.CTkFrame(
                    self.checklist_scroll,
                    fg_color=DANGER_BG,
                    corner_radius=8,
                    border_width=1,
                    border_color=DANGER,
                )
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(
                    row,
                    text=f"  ✗  {d}",
                    font=ctk.CTkFont(size=12),
                    text_color=DANGER,
                    anchor="w",
                ).pack(anchor="w", padx=8, pady=8)

    def _render_score(self, result: dict):
        for w in self.score_container.winfo_children():
            w.destroy()

        score_val = result.get("score", 0)
        if score_val >= 75:
            score_color, score_bg = SUCCESS, SUCCESS_BG
        elif score_val >= 50:
            score_color, score_bg = WARNING, WARNING_BG
        else:
            score_color, score_bg = DANGER, DANGER_BG

        # ── Score hero card ───────────────────────────────────────────────────
        hero = ctk.CTkFrame(
            self.score_container,
            fg_color=BG_CARD,
            corner_radius=12,
            border_width=1,
            border_color=BORDER,
        )
        hero.pack(fill="x", pady=(0, 12))

        # Big number
        num_frame = ctk.CTkFrame(hero, fg_color=score_bg, corner_radius=10)
        num_frame.pack(pady=(18, 8), padx=20)

        ctk.CTkLabel(
            num_frame,
            text=str(score_val),
            font=ctk.CTkFont(size=56, weight="bold"),
            text_color=score_color,
        ).pack(padx=30, pady=(12, 0))

        ctk.CTkLabel(
            num_frame,
            text="out of 100",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
        ).pack(pady=(0, 10))

        # Temperature badge (real estate only)
        temp = result.get("preliminary_temp")
        if temp:
            tc = TEMP_COLORS.get(temp.lower(), GRAY)
            temp_text = temp
            if not result.get("mv"):
                temp_text += "  ·  Preliminary"
            temp_row = ctk.CTkFrame(hero, fg_color="transparent")
            temp_row.pack(pady=(0, 16))
            ctk.CTkLabel(
                temp_row,
                text="Temperature:",
                font=ctk.CTkFont(size=12),
                text_color=TEXT_MUTED,
            ).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                temp_row,
                text=temp_text,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=tc,
            ).pack(side="left")
        else:
            ctk.CTkFrame(hero, height=10, fg_color="transparent").pack()

        # ── Red flags ─────────────────────────────────────────────────────────
        red_flags = result.get("red_flags", [])
        if red_flags:
            self._section_header("🚩  Red Flags", DANGER)
            for rf in red_flags:
                self._detail_row(rf, DANGER, DANGER_BG)

        # ── Coaching notes ────────────────────────────────────────────────────
        coaching = result.get("coaching_notes", [])
        if coaching:
            self._section_header("💬  Coaching Notes", WARNING)
            for note in coaching:
                self._detail_row(note, TEXT_PRIMARY, BG_CARD)

        # ── Strengths ─────────────────────────────────────────────────────────
        strengths = result.get("strengths", [])
        if strengths:
            self._section_header("✅  Strengths", SUCCESS)
            for s in strengths:
                self._detail_row(s, SUCCESS, SUCCESS_BG)

    def _section_header(self, title: str, color: str):
        frame = ctk.CTkFrame(self.score_container, fg_color="transparent")
        frame.pack(fill="x", pady=(16, 6))
        ctk.CTkLabel(
            frame, text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=color,
        ).pack(anchor="w")
        ctk.CTkFrame(frame, height=1, fg_color=BORDER).pack(fill="x", pady=(4, 0))

    def _detail_row(self, text: str, text_color: str, bg: str):
        row = ctk.CTkFrame(
            self.score_container,
            fg_color=bg,
            corner_radius=8,
            border_width=1,
            border_color=BORDER,
        )
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(
            row, text=f"  •  {text}",
            font=ctk.CTkFont(size=12),
            text_color=text_color,
            anchor="w", wraplength=560,
        ).pack(anchor="w", padx=10, pady=8)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _merge_transcript(self, result: dict) -> str:
        """
        Return the transcript with speaker labels.
        Prefers the GPT-diarized version; falls back to the raw stamped transcript.
        """
        labeled = result.get("labeled_transcript")
        if labeled:
            return labeled
        stamped = result.get("stamped_transcript", "")
        if stamped:
            return stamped
        return result.get("transcript", "")

    def _save_mv(self):
        mv = self.mv_entry.get().strip()
        if mv:
            self.on_mv_saved(mv)

    def _copy_template(self):
        text = self.template_box.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)

    def _copy_transcript(self):
        text = self.transcript_box.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)

    def _export(self):
        if not self._result:
            return
        from utils.exporter import export_dialog
        export_dialog(self, self._result)

    def _clear(self):
        self._result = None
        self._clear_content()

    def _clear_content(self):
        self.template_box.configure(state="normal")
        self.template_box.delete("1.0", "end")
        self.template_box.configure(state="disabled")

        self.transcript_box.configure(state="normal")
        self.transcript_box.delete("1.0", "end")
        self.transcript_box.configure(state="disabled")

        for w in self.checklist_scroll.winfo_children():
            w.destroy()
        for w in self.score_container.winfo_children():
            w.destroy()
