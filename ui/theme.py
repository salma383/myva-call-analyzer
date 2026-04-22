"""
MyVA brand color palette — used across all UI files.
Centralised here so a single edit changes the whole app.
"""

# ── Backgrounds ──────────────────────────────────────────────────────────────
BG_MAIN    = "#0D1520"   # Deepest navy — window fill
BG_SIDEBAR = "#090F1A"   # Even darker sidebar strip
BG_CARD    = "#111D2E"   # Card / panel surfaces
BG_INPUT   = "#0F1A2A"   # Entry fields
BG_HOVER   = "#1C2D44"   # Hover state for rows / buttons
BG_TAB     = "#0D1520"   # Tab body background (matches BG_MAIN)

# ── Borders ───────────────────────────────────────────────────────────────────
BORDER       = "#1E3150"  # Subtle card borders
BORDER_LIGHT = "#2A4570"  # Slightly visible dividers

# ── Text ──────────────────────────────────────────────────────────────────────
TEXT_PRIMARY   = "#EBF1F8"  # Near-white body text
TEXT_SECONDARY = "#7A9BBF"  # Muted blue-gray labels
TEXT_MUTED     = "#3D5A7A"  # Very muted / placeholder

# ── Accent — MyVA blue ───────────────────────────────────────────────────────
ACCENT         = "#2F78E4"  # Primary brand blue
ACCENT_HOVER   = "#1D5FC8"  # Darker on hover
ACCENT_LIGHT   = "#3B90FF"  # Slightly lighter accent
ACCENT_DIM     = "#1A3A6A"  # Very dim blue (backgrounds behind accent elements)

# ── Semantic colours ─────────────────────────────────────────────────────────
SUCCESS      = "#10B981"   # Green — "yes" checklist, high score
SUCCESS_BG   = "#071F15"
WARNING      = "#F59E0B"   # Amber — "partial" checklist, mid score
WARNING_BG   = "#1F1507"
DANGER       = "#EF4444"   # Red — "no" checklist, disqualifiers, low score
DANGER_BG    = "#1F0707"
PURPLE       = "#A78BFA"   # Nurture temperature
GRAY         = "#4A6A8A"   # n/a checklist items, neutral

# ── Temperature badge colours ─────────────────────────────────────────────────
TEMP_COLORS = {
    "hot":       "#EF4444",
    "warm":      "#F59E0B",
    "cold":      "#3B90FF",
    "nurture":   "#A78BFA",
    "throwaway": "#4A6A8A",
}

# ── Typography ────────────────────────────────────────────────────────────────
FONT_MONO = "Consolas"
FONT_UI   = "Segoe UI"      # Falls back gracefully on non-Windows
