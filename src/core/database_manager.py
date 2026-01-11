import logging
import os
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Clase responsable de gestionar la conexión a la base de datos y la fábrica de sesiones.
    Aplica el patrón Singleton implícito o Inyección de Dependencias según se use.
    """

    def __init__(self, db_url: str = None, echo: bool = False):
        self.db_url = db_url or self._get_default_db_url()
        self.engine = create_engine(self.db_url, echo=echo)
        self.session_factory = sessionmaker(
            autocommit=False, 
            autoflush=False, 
            bind=self.engine
        )
        logger.debug(f"DatabaseManager inicializado con URL: {self._obscure_pass_in_url(self.db_url)}")

    def _get_default_db_url(self) -> str:
        """Construye la URL de conexión desde variables de entorno."""
        load_dotenv()
        
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        host = os.getenv("DB_HOST")
        port = os.getenv("DB_PORT")
        db_name = os.getenv("DB_NAME")

        if not all([user, password, host, port, db_name]):
            error_msg = "Faltan variables de entorno para la configuración de la base de datos."
            logger.critical(error_msg)
            raise ValueError(error_msg)

        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}"

    @staticmethod
    def _obscure_pass_in_url(url: str) -> str:
        """Método auxiliar para no loguear la contraseña real."""
        if "@" in url:
            return url.split("@")[1] # Retorna solo host/db para el log
        return "InMemory/SQLite"

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """
        Context Manager para manejar el ciclo de vida de la sesión.
        Asegura que la sesión se cierre incluso si ocurre un error.
        Uso:
            with db.session() as session:
                session.query(...)
        """
        session: Session = self.session_factory()
        try:
            yield session
        except Exception:
            logger.error("Error durante la sesión de base de datos. Realizando rollback.")
            session.rollback()
            raise
        finally:
            session.close()

# Instancia global por defecto (para compatibilidad hacia atrás o uso simple)
# Pero ahora podemos instanciar otro DatabaseManager en los tests con SQLite.
try:
    # Intentamos inicializar, pero si fallan las env vars, no rompemos el import,
    # solo fallará si se intenta usar esta instancia específica.
    db = DatabaseManager()
except ValueError:
    logger.warning("No se pudo inicializar la instancia por defecto de DatabaseManager (faltan env vars).")
    db = None