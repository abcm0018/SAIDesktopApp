import os
from dotenv import load_dotenv

load_dotenv()

class AppConfig:
    """
    Centraliza la configuración general de la aplicación
    """
    APP_TITLE: str = os.getenv("APP_TITLE", "Sistema de Inventariado Automatizado")
    theme_mode: str = os.getenv("THEME_MODE", "light")