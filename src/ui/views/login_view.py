import logging
from datetime import date

import flet as ft

from src.config.app_config import AppConfig
from src.services.auth_service import AuthService
from src.config.routes import AppRoutes
from src.utils.ui_helpers import UiHelper
from src.ui import design_system as ds

logger = logging.getLogger(__name__)

_CARD_W  = 400
_VERSION = "1.0.0"

# Colors per theme — derived from design system
_BG_START   = ds.BG_GRADIENT_START
_BG_END     = ds.BG_GRADIENT_END
_CARD_LIGHT = ds.CARD_LIGHT
_CARD_DARK  = ds.CARD_DARK
_TITLE_LIGHT = ds.TITLE_LIGHT
_TITLE_DARK  = ds.TITLE_DARK
_SUB_LIGHT  = ds.SUB_LIGHT
_SUB_DARK   = ds.SUB_DARK
_DIV_LIGHT  = ds.DIV_LIGHT
_DIV_DARK   = ds.DIV_DARK


class LoginView(ft.Stack):
    def __init__(self, page: ft.Page, auth_service: AuthService):
        super().__init__()
        self.page         = page
        self.auth_service = auth_service
        self.station_code = self.page.session.get("station_code")
        self.expand       = True
        self.is_dark      = page.theme_mode == ft.ThemeMode.DARK
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        # --- Form fields ---
        self.txt_user = ft.TextField(
            label="Número de empleado",
            prefix_icon=ft.Icons.BADGE_OUTLINED,
            border_radius=10,
            border_color=ft.Colors.BLUE_100,
            focused_border_color=ft.Colors.BLUE_600,
            on_submit=self._handle_login,
        )
        self.txt_pass = ft.TextField(
            label="Contraseña",
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.LOCK_OUTLINE,
            border_radius=10,
            border_color=ft.Colors.BLUE_100,
            focused_border_color=ft.Colors.BLUE_600,
            on_submit=self._handle_login,
        )
        self.txt_station = ft.TextField(
            label="Puesto de trabajo asignado",
            value=self.station_code,
            prefix_icon=ft.Icons.FACTORY_OUTLINED,
            border_radius=10,
            disabled=True,
            color=ft.Colors.GREY_600,
            border_color=ft.Colors.GREY_200,
        )

        # --- Button + loading ---
        self.btn_login = ft.ElevatedButton(
            text="INGRESAR",
            width=_CARD_W - 72,
            height=48,
            on_click=self._handle_login,
            style=ft.ButtonStyle(
                bgcolor={
                    ft.ControlState.DEFAULT:  ft.Colors.BLUE_700,
                    ft.ControlState.HOVERED:  ft.Colors.BLUE_600,
                    ft.ControlState.DISABLED: ft.Colors.GREY_300,
                },
                color={
                    ft.ControlState.DEFAULT:  ft.Colors.WHITE,
                    ft.ControlState.DISABLED: ft.Colors.GREY_500,
                },
                shape=ft.RoundedRectangleBorder(radius=10),
                elevation={
                    ft.ControlState.DEFAULT: 2,
                    ft.ControlState.HOVERED: 5,
                },
                animation_duration=180,
            ),
        )
        self.loading = ft.ProgressRing(
            visible=False,
            width=22,
            height=22,
            stroke_width=2.5,
            color=ft.Colors.BLUE_600,
        )

        # --- Header (stored refs for theme updates) ---
        self._header_title    = ft.Text("SAI", size=30, weight=ft.FontWeight.BOLD,  color=_TITLE_DARK if self.is_dark else _TITLE_LIGHT)
        self._header_subtitle = ft.Text(AppConfig.APP_TITLE, size=11, text_align=ft.TextAlign.CENTER, color=_SUB_DARK if self.is_dark else _SUB_LIGHT)
        self._divider         = ft.Divider(height=1, color=_DIV_DARK if self.is_dark else _DIV_LIGHT)

        # --- Theme toggle ---
        self._theme_btn = ft.IconButton(
            icon=ft.Icons.LIGHT_MODE if self.is_dark else ft.Icons.DARK_MODE,
            icon_color=ft.Colors.with_opacity(0.55, ft.Colors.WHITE),
            icon_size=18,
            tooltip="Cambiar tema",
            on_click=self._toggle_theme,
        )

        # --- Card ---
        self._card = ft.Container(
            content=ft.Column(
                controls=[
                    self._build_header(),
                    ft.Container(height=8),
                    self._divider,
                    ft.Container(height=8),
                    self.txt_user,
                    self.txt_pass,
                    self.txt_station,
                    ft.Container(height=2),
                    ft.Row([self.loading], alignment=ft.MainAxisAlignment.CENTER),
                    self.btn_login,
                ],
                spacing=10,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                tight=True,
            ),
            width=_CARD_W,
            padding=ft.padding.symmetric(horizontal=36, vertical=40),
            border_radius=20,
            bgcolor=_CARD_DARK if self.is_dark else _CARD_LIGHT,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=60,
                color=ft.Colors.with_opacity(0.22, ft.Colors.BLACK),
                offset=ft.Offset(0, 20),
            ),
        )

        # --- Copyright ---
        copyright_label = ft.Text(
            f"© {date.today().year}  SAI v{_VERSION}",
            size=10,
            color=ft.Colors.with_opacity(0.4, ft.Colors.WHITE),
        )

        # --- Bottom bar: copyright left, theme toggle right ---
        bottom_bar = ft.Row(
            controls=[copyright_label, self._theme_btn],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # --- Stack layers ---
        self.controls = [
            # Gradient background
            ft.Container(
                expand=True,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_left,
                    end=ft.alignment.bottom_right,
                    colors=[_BG_START, _BG_END],
                ),
            ),
            # Decorative circles
            ft.Container(width=360, height=360, border_radius=180, bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE), right=-100, top=-100),
            ft.Container(width=220, height=220, border_radius=110, bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.WHITE), left=-60,  bottom=-60),
            ft.Container(width=120, height=120, border_radius=60,  bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.BLUE_300),  right=80,   bottom=120),
            # Main layout column: card (centered, expands) + bottom bar
            ft.Container(
                expand=True,
                padding=ft.padding.symmetric(horizontal=24, vertical=16),
                content=ft.Column(
                    controls=[
                        ft.Container(
                            content=self._card,
                            alignment=ft.alignment.center,
                            expand=True,
                        ),
                        bottom_bar,
                    ],
                    spacing=8,
                    expand=True,
                ),
            ),
        ]

    def _build_header(self) -> ft.Column:
        logo = ft.Container(
            content=ft.Icon(ft.Icons.INVENTORY_2_ROUNDED, size=36, color=ft.Colors.WHITE),
            width=72,
            height=72,
            border_radius=20,
            bgcolor=ft.Colors.BLUE_700,
            alignment=ft.alignment.center,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=20,
                color=ft.Colors.with_opacity(0.4, ft.Colors.BLUE_700),
                offset=ft.Offset(0, 8),
            ),
        )
        return ft.Column(
            controls=[logo, self._header_title, self._header_subtitle],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
        )

    # ------------------------------------------------------------------
    # Theme toggle
    # ------------------------------------------------------------------

    def _toggle_theme(self, e):
        self.is_dark = not self.is_dark
        self.page.theme_mode = ft.ThemeMode.DARK if self.is_dark else ft.ThemeMode.LIGHT
        self._card.bgcolor          = _CARD_DARK  if self.is_dark else _CARD_LIGHT
        self._header_title.color    = _TITLE_DARK if self.is_dark else _TITLE_LIGHT
        self._header_subtitle.color = _SUB_DARK   if self.is_dark else _SUB_LIGHT
        self._divider.color         = _DIV_DARK   if self.is_dark else _DIV_LIGHT
        self._theme_btn.icon        = ft.Icons.LIGHT_MODE if self.is_dark else ft.Icons.DARK_MODE
        self.page.update()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _set_loading(self, is_loading: bool):
        self.loading.visible    = is_loading
        self.btn_login.disabled = is_loading
        self.txt_user.disabled  = is_loading
        self.txt_pass.disabled  = is_loading
        self.update()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_login(self, e):
        user_val     = self.txt_user.value
        password_val = self.txt_pass.value

        if not user_val or not password_val:
            UiHelper.show_alert(self.page, "Campos vacíos", "Por favor, introduce usuario y contraseña.")
            return

        self._set_loading(True)

        if self.station_code == "PUEST_NO_CONFIGURADO":
            UiHelper.show_alert(
                self.page,
                "Error en la configuración",
                "Contacte con mantenimiento para configurar el puesto de trabajo.",
            )
            return

        try:
            user = self.auth_service.autenticar_usuario(user_val, password_val)

            if user:
                logger.debug(f"Sesión iniciada: {user.employee_number}")
                self.page.session.set("user", user)
                self.page.session.set("station_code", self.station_code)
                self.page.go(AppRoutes.DASHBOARD)
            else:
                self._set_loading(False)
                UiHelper.show_alert(
                    self.page,
                    "Error de Acceso",
                    "Credenciales incorrectas o usuario bloqueado.",
                )

        except Exception as ex:
            self._set_loading(False)
            logger.error(f"Excepción en login: {ex}")
            UiHelper.show_alert(self.page, "Error del Sistema", "Ocurrió un error inesperado al intentar ingresar.")