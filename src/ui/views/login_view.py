import logging
import flet as ft

from src.config.app_config import AppConfig
from src.services.auth_service import AuthService
from src.config.routes import AppRoutes
from src.utils.ui_helpers import UiHelper

logger = logging.getLogger(__name__)

class LoginView(ft.Column):
    def __init__(self, page: ft.Page, auth_service: AuthService):
        super().__init__()
        self.page = page
        self.auth_service = auth_service
        
        self.alignment = ft.MainAxisAlignment.CENTER
        self.horizontal_alignment = ft.CrossAxisAlignment.CENTER
        self.spacing = 20

        # --- Componentes UI ---
        self.txt_user = ft.TextField(
            label="Número de Empleado", 
            width=300, 
            prefix_icon=ft.Icons.PERSON,
            border_radius=10,
            on_submit=self._handle_login 
        )

        self.txt_pass = ft.TextField(
            label="Contraseña", 
            password=True, 
            can_reveal_password=True, 
            width=300, 
            prefix_icon=ft.Icons.LOCK,
            border_radius=10,
            on_submit=self._handle_login 
        )

        self.btn_login = ft.ElevatedButton(
            text="INGRESAR",
            width=300,
            height=45,
            on_click=self._handle_login,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_700,
                color=ft.Colors.WHITE,
                shape=ft.RoundedRectangleBorder(radius=8)
            )
        )

        self.loading = ft.ProgressRing(visible=False)

        # Estructura visual
        self.controls = [
            ft.Icon(ft.Icons.SECURITY, size=80, color=ft.Colors.BLUE_700),
            ft.Text(AppConfig.APP_TITLE, size=24, weight=ft.FontWeight.BOLD),
            # ft.Text("de Inventariado", size=24, weight=ft.FontWeight.BOLD),
            ft.Container(height=20),
            self.txt_user,
            self.txt_pass,
            ft.Container(height=10),
            self.loading,
            self.btn_login
        ]

    def _set_loading(self, is_loading: bool):
        """Helper para gestionar estado de carga visual"""
        self.loading.visible = is_loading
        self.btn_login.disabled = is_loading
        self.txt_user.disabled = is_loading
        self.txt_pass.disabled = is_loading
        self.update() # Actualizamos solo este componente (Column)

    def _handle_login(self, e):
        user_val = self.txt_user.value
        password_val = self.txt_pass.value

        if not user_val or not password_val:
            UiHelper.show_alert(self.page, "Campos vacíos", "Por favor, introduce usuario y contraseña.")
            return

        self._set_loading(True)

        try:
            # 3. Llamada al Servicio
            user = self.auth_service.autenticar_usuario(user_val, password_val)

            if user:
                logger.debug(f"Sesión iniciada: {user.employee_number}")
                self.page.session.set("user", user)
                self.page.go(AppRoutes.DASHBOARD)
            else:
                self._set_loading(False)
                UiHelper.show_alert(
                    self.page, 
                    "Error de Acceso", 
                    "Credenciales incorrectas o usuario bloqueado."
                )

        except Exception as ex:
            self._set_loading(False)
            logger.error(f"Excepción en login: {ex}")
            UiHelper.show_alert(self.page, "Error del Sistema", "Ocurrió un error inesperado al intentar ingresar.")