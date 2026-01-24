import asyncio  # Necesario para la carga asíncrona
import logging

import flet as ft

from src.config.app_config import AppConfig
from src.config.mqtt_config import MqttConfig
from src.config.routes import AppRoutes
from src.config.yolo_config import YoloConfig
from src.core.database_manager import DatabaseManager
from src.core.mqtt_manager import MqttManager
from src.core.yolo_loader import YoloModelLoader
from src.services.auth_service import AuthService
from src.services.camera_service import CameraService
from src.services.mqtt_service import MqttService
from src.services.scanner_service import ScannerService
from src.services.yolo_service import YoloService
from src.ui.router import Router
from src.utils.logger_config import setup_logging

# Configuración global del Logger
setup_logging()
logger = logging.getLogger(__name__)

async def main(page: ft.Page):
    logger.info("Iniciando aplicación (SAI)...")
   
    # 1. Configuración de la Ventana (Inmediata)
    page.title = AppConfig.APP_TITLE
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window.full_screen = False
    page.window.maximized = True
    page.padding = 0
    
    # 2. PANTALLA DE CARGA (Splash Screen)
    # Creamos componentes visuales para feedback inmediato
    loading_text = ft.Text("Iniciando servicios del sistema...", size=16, color=ft.Colors.GREY_700)
    loading_bar = ft.ProgressBar(width=400, color=ft.Colors.BLUE_700, bgcolor=ft.Colors.BLUE_100)
    
    splash_content = ft.Container(
        content=ft.Column(
            controls=[
                ft.Image(src="assets/logo.png", width=150, error_content=ft.Icon(ft.Icons.APPS_ROUNDED, size=100)),
                ft.Container(height=20),
                ft.ProgressRing(width=50, height=50, stroke_width=4),
                ft.Container(height=20),
                loading_text,
                ft.Container(height=10),
                loading_bar
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        ),
        alignment=ft.alignment.center,
        expand=True,
        bgcolor=ft.Colors.WHITE
    )

    # Añadimos y actualizamos YA para que el usuario vea algo
    page.add(splash_content)
    page.update()

    # 3. Carga Pesada en Segundo Plano
    # Usamos try/except para capturar fallos sin cerrar la ventana de golpe
    try:
        # --- A. Base de Datos ---
        loading_text.value = "Conectando con Base de Datos..."
        page.update()
        
        # Simulamos un pequeño delay async si es necesario, o usamos to_thread si la db bloquea mucho
        db_manager = DatabaseManager() 
        # Si db_manager.connect() tarda mucho, deberías envolverlo en asyncio.to_thread
        
        # --- B. Inteligencia Artificial (El paso lento) ---
        loading_text.value = "Cargando Modelos de IA (YOLOv5)..."
        page.update()
        
        yolo_config = YoloConfig()
        yolo_loader = YoloModelLoader(config=yolo_config)
        
        # TRUCO DE OPTIMIZACIÓN:
        # asyncio.to_thread ejecuta la función bloqueante en un hilo separado
        # Esto permite que la interfaz (el spinner) siga girando fluidamente.
        modelo_yolo = await asyncio.to_thread(yolo_loader.load)
        
        # --- C. MQTT y Red ---
        loading_text.value = "Configurando Comunicaciones MQTT..."
        page.update()
        
        mqtt_config = MqttConfig.from_env()
        
        # Instanciamos Manager
        mqtt_manager = MqttManager(config=mqtt_config)
        # Conectamos (Idealmente también async si el broker tarda en responder)
        mqtt_manager.connect()

        # --- D. Inicialización de Servicios ---
        loading_text.value = "Finalizando configuración..."
        page.update()

        auth_service = AuthService(db_manager=db_manager)
        camera_service = CameraService()
        scanner_service = ScannerService()
        
        # Inyectamos el manager en el servicio (según tu refactorización)
        mqtt_service = MqttService(mqtt_manager=mqtt_manager)
        
        yolo_service = YoloService(model=modelo_yolo, conf_threshold=yolo_config.conf_threshold)

        logger.info("✅ Servicios del Core inicializados correctamente.")
        
        # Pequeña pausa estética para que el usuario vea "Completado"
        loading_bar.value = 1
        loading_text.value = "¡Sistema listo!"
        page.update()
        await asyncio.sleep(0.5) 

        # 4. Inicialización del Router y Navegación
        
        # Limpiamos la pantalla de carga
        page.clean()
        
        my_router = Router(
            page, 
            auth_service=auth_service, 
            camera_service=camera_service, 
            scanner_service=scanner_service,
            yolo_service=yolo_service,
            mqtt_service=mqtt_service
        )
        
        page.on_route_change = my_router.route_change
        page.on_view_pop = my_router.view_pop
        
        # Forzamos la navegación al Login
        page.go(AppRoutes.LOGIN)
                
    except Exception as e:
        logger.critical(f"Error crítico en el arranque: {e}", exc_info=True)
        # En caso de error, actualizamos la UI de carga para mostrar el fallo
        loading_text.value = f"Error Crítico: {str(e)}"
        loading_text.color = ft.Colors.RED
        loading_bar.bgcolor = ft.Colors.RED_100
        loading_bar.color = ft.Colors.RED
        page.update()
        # No hacemos return para dejar que el usuario lea el error
        # Podrías añadir un botón de "Reintentar" o "Salir"

if __name__ == "__main__":
    # Importante: Flet maneja el loop asíncrono internamente cuando el target es async
    ft.app(target=main)