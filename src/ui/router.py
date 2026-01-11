import logging
import flet as ft
from typing import Callable, Dict

from src.services.mqtt_service import MqttService
from src.services.yolo_service import YoloService
from src.config.routes import AppRoutes
from src.services.auth_service import AuthService
from src.services.camera_service import CameraService
from src.services.scanner_service import ScannerService
from src.ui.views.dashboard_view import DashboardView
from src.ui.views.login_view import LoginView

logger = logging.getLogger(__name__)

class Router:
    """
    Gestor de navegación centralizado.
    Se encarga de mapear URLs a Vistas y proteger rutas privadas.
    """

    def __init__(
        self,
        page: ft.Page,
        auth_service: AuthService,
        camera_service: CameraService,
        scanner_service: ScannerService,
        mqtt_service: MqttService,
        yolo_service: YoloService
    ):
        self.page = page
        self.auth_service = auth_service
        self.camera_service = camera_service
        self.scanner_service = scanner_service
        self.yolo_service = yolo_service
        self.mqtt_service = mqtt_service

        # Definición de rutas y sus manejadores
        self.routes: Dict[str, Callable[[], ft.View]] = {
            AppRoutes.LOGIN: self._login_view,
            AppRoutes.DASHBOARD: self._dashboard_view,
        }

    def route_change(self, route):
        """Callback principal cuando cambia la URL (page.go)."""
        troute = ft.TemplateRoute(self.page.route)
        
        # 1. Protección de rutas (Middleware de Auth)
        if self._requires_auth(troute.route) and not self._is_user_authenticated():
            logger.warning(f"Intento de acceso no autorizado a {troute.route}. Redirigiendo a Login.")
            self.page.go(AppRoutes.LOGIN)
            return

        # 2. Selección de Vista
        self.page.views.clear()
        
        # Buscamos el constructor de la vista en el mapa
        view_builder = self.routes.get(troute.route)
        
        if view_builder:
            self.page.views.append(view_builder())
        else:
            logger.warning(f"Ruta no encontrada: {troute.route}. Redirigiendo a Login.")
            self.page.go(AppRoutes.LOGIN)

        self.page.update()

    def view_pop(self, view):
        """
        NUEVO MÉTODO: Maneja el evento de navegación 'Atrás'.
        Elimina la última vista de la pila y navega a la anterior.
        """
        if len(self.page.views) > 1:
            self.page.views.pop()
            top_view = self.page.views[-1]
            self.page.go(top_view.route)
        else:
            # Si no hay historial, quizás salir de la app o ir al login
            logger.info("No hay vistas previas en el historial para volver atrás.")

    def _requires_auth(self, route: str) -> bool:
        """Define qué rutas son privadas."""
        # Por defecto todas son privadas excepto Login. 
        return route != AppRoutes.LOGIN

    def _is_user_authenticated(self) -> bool:
        """Verifica si existe una sesión válida."""
        return self.page.session.get("user") is not None

    # --- Constructores de Vistas ---

    def _login_view(self) -> ft.View:
        return ft.View(
            route=AppRoutes.LOGIN,
            controls=[
                LoginView(self.page, auth_service=self.auth_service)
            ],
            vertical_alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )

    def _dashboard_view(self) -> ft.View:
        return ft.View(
            route=AppRoutes.DASHBOARD,
            controls=[
                DashboardView(
                    page=self.page,
                    auth_service=self.auth_service, 
                    camera_service=self.camera_service, 
                    scanner_service=self.scanner_service,
                    yolo_service=self.yolo_service,
                    mqtt_service=self.mqtt_service
                )
            ],
            vertical_alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            padding=0
        )