import flet as ft

# ── Gradient backgrounds ──────────────────────────────────────────────────────
BG_GRADIENT_START = "#0F1E33"
BG_GRADIENT_END   = "#1A3050"

# ── Surface hierarchy (darkest → lightest) ────────────────────────────────────
SURFACE_BASE     = "#0D1728"   # page / view background
SURFACE_CARD     = "#111F35"   # panel bodies
SURFACE_ELEVATED = "#1A2F4A"   # header bar, raised cards, state boxes
SURFACE_OVERLAY  = "#1E3A5F"   # badges, hover states

# ── Text ──────────────────────────────────────────────────────────────────────
TEXT_PRIMARY   = ft.Colors.with_opacity(0.92, ft.Colors.WHITE)
TEXT_SECONDARY = "#8BA3C7"
TEXT_MUTED     = "#4A6080"

# ── Semantic accents ──────────────────────────────────────────────────────────
ACCENT_BLUE  = ft.Colors.BLUE_600
ACCENT_GREEN = ft.Colors.GREEN_600
ACCENT_AMBER = "#F59E0B"
ACCENT_RED   = ft.Colors.RED_ACCENT_400

# ── Borders ───────────────────────────────────────────────────────────────────
BORDER_SUBTLE = ft.Colors.with_opacity(0.12, ft.Colors.WHITE)
BORDER_ACCENT = ft.Colors.with_opacity(0.30, ft.Colors.BLUE_300)

# ── Typography scale ──────────────────────────────────────────────────────────
SIZE_DATA_XL = 26   # SSCC barcode value
SIZE_DATA_LG = 16   # secondary data fields
SIZE_LABEL   = 13   # field labels
SIZE_CAPTION = 11   # captions, copyright

# ── Border radius ─────────────────────────────────────────────────────────────
RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 16
RADIUS_XL = 20

# ── Light / dark card overrides — used by login theme toggle ─────────────────
CARD_LIGHT  = ft.Colors.WHITE
CARD_DARK   = SURFACE_CARD
TITLE_LIGHT = ft.Colors.BLUE_GREY_900
TITLE_DARK  = TEXT_PRIMARY
SUB_LIGHT   = ft.Colors.BLUE_GREY_400
SUB_DARK    = TEXT_SECONDARY
DIV_LIGHT   = ft.Colors.BLUE_GREY_100
DIV_DARK    = SURFACE_ELEVATED


# ── Shadow factories ──────────────────────────────────────────────────────────
def card_shadow(opacity: float = 0.25) -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=20,
        color=ft.Colors.with_opacity(opacity, ft.Colors.BLACK),
        offset=ft.Offset(0, 8),
    )


def glow_shadow(color=ft.Colors.BLUE_600, opacity: float = 0.4) -> ft.BoxShadow:
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=16,
        color=ft.Colors.with_opacity(opacity, color),
        offset=ft.Offset(0, 6),
    )
