import logging
import flet as ft
from src.services.auth_service import AuthService
from src.services.camera_service import CameraService
from src.ui.router import Router
from src.utils.logger_config import setup_logging

# Configuración global del Logger
setup_logging()
logger = logging.getLogger(__name__)

# CONFIGURACIÓN GLOBAL
RUTA_EXE = r"C:\Ruta\Falsa\scanner.exe"

def main(page: ft.Page):
    logger.info("Iniciando la aplicación de login")
   
    # 1. Configuración de la Ventana (Look & Feel global)
    page.title = "Sistema Automatizado de Inventariado"
    page.window_width = 400
    page.window_height = 500
    page.theme_mode = ft.ThemeMode.LIGHT

    # 2. Inyección de Dependencias (Core Services)
    auth_service = AuthService()
    camera_service = CameraService()

    # 3. Incialización del Router
    # Le pasamos la página y los servicios para que él orqueste
    my_router = Router(page, auth_service=auth_service, camera_service=camera_service)
    page.on_route_change = my_router.route_change

    # 4. Bindings
    # Conectamos el evento de cambio de ruta al router
    page.on_route_change = my_router.route_change

    # 5. Navegamos  a la ruta inicial
    # Forzamos la navegación inicial a /login
    page.go("/login")

if __name__ == "__main__":
    ft.app(target=main)