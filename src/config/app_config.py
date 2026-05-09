import os
from dotenv import load_dotenv

load_dotenv()

class AppConfig:
    """
    Centraliza la configuración general de la aplicación
    """
    APP_TITLE: str = os.getenv("APP_TITLE", "Sistema de Inventariado Automatizado")
    theme_mode: str = os.getenv("THEME_MODE", "light")
    
    READ_TIMEOUT_SEC = float(os.getenv("READ_TIMEOUT_SEC", "5"))
    QUEUE_MAX_SIZE = int(os.getenv("QUEUE_MAX_SIZE", "1000"))
    POST_SEND_DELAY_SEC = float(os.getenv("POST_SEND_DELAY_SEC", "2.0"))
    VIDEO_PREVIEW_WIDTH = int(os.getenv("VIDEO_PREVIEW_WIDTH", "640"))