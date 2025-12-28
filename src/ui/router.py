import logging
import flet as ft
from src.services.auth_service import AuthService
from src.services.camera_service import CameraService
from src.ui.views.dashboard_view import DashboardView
from src.ui.views.login_view import LoginView


logger = logging.getLogger(__name__)

class Router:
    def __init__(self, page: ft.Page, auth_service: AuthService, camera_service: CameraService):
        self.page = page
        self.auth_service = auth_service
        self.camera_service = camera_service

        # Mapa de rutas: String -> Función que retorna una vista (ft.View)
        self.routes = {
            "/login": self._login_view,
            "/dashboard": self._dashboard_view
        }

    def route_change(self, route_event):
        """Manejador de eventos cuando cambia la ruta"""
        troute = ft.TemplateRoute(self.page.route)
        logger.info(f"Cambiando de ruta a: {troute.route}")

        self.page.views.clear()  # Limpiamos las vistas actuales

        # Buscamos la vista correspondiente en el mapa de rutas
        if troute.route == "/login":
            self.page.views.append(self._login_view())
        elif troute.route == "/dashboard":
            self.page.views.append(self._dashboard_view())
        else:
            # Fallback a login si la ruta no existe
            logger.warning(f"Ruta no encontrada: {troute.route}. Redirigiendo a /login")
            self.page.go("/login")

        self.page.update()

    
    def _login_view(self):
        """Construye la página de Login inyectando dependecias"""
        return ft.View(
            "/login",
            controls=[
                LoginView(self.page, auth_service=self.auth_service)
            ],
            vertical_alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )


    def _dashboard_view(self):
        """Construye la página del Dashboard (Vista protegida)"""
        return ft.View(
            "/dashboard",
            controls=[
                # Inyectamos dependencias igual que en el Login
                DashboardView(self.page, self.auth_service, self.camera_service)
            ],
            padding=0, 
            bgcolor=ft.Colors.WHITE
        )
