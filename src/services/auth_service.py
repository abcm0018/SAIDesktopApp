import logging
from typing import Optional
import bcrypt

from src.core.database_manager import DatabaseManager 
from src.domain.user import User

logger = logging.getLogger(__name__)

class AuthService:
    """
    Servicio encargado de la autenticación de usuarios.
    Sigue el principio de Inversión de Dependencias (DIP) al recibir el gestor de BD.
    """

    def __init__(self, db_manager: DatabaseManager):
        """
        Args:
            db_manager (DatabaseManager): Instancia inyectada del gestor de base de datos.
        """
        self.db = db_manager
        logger.debug("Inicializando AuthService con DatabaseManager inyectado")

    def autenticar_usuario(self, num_empleado: str, contrasena: str) -> Optional[User]:
        logger.debug(f"Validando credenciales para el usuario: {num_empleado}")

        try:
            with self.db.session() as session:
                user = session.query(User).filter_by(employee_number=num_empleado).first()

                if not self._validar_estado_usuario(user, num_empleado):
                    return None
                
                if not self._verificar_password(user, contrasena):
                    logger.warning(f"Login fallido: Contraseña incorrecta para el usuario {num_empleado}")
                    return None

                logger.info(f"Login exitoso para el usuario: {user.employee_number} ({user.role})")
                
                # Desvinculamos el objeto de la sesión para usarlo fuera
                session.expunge(user)
                return user

        except Exception as e:
            logger.exception(f"Error crítico validando usuario {num_empleado}: {e}")
            return None

    def _validar_estado_usuario(self, user: Optional[User], num_empleado: str) -> bool:
        """Método helper privado para validar existencia y estado (Single Responsibility)."""
        if not user:
            logger.warning(f"Login fallido: Usuario {num_empleado} no encontrado")
            return False
        
        if not user.active or user.blocked:
            logger.warning(f"Login fallido: Usuario {num_empleado} inactivo o bloqueado")
            return False
            
        return True

    def _verificar_password(self, user: User, contrasena_input: str) -> bool:
        """Método helper para encapsular la lógica de bcrypt."""
        # Manejo defensivo por si la password en BD no es string (legacy data)
        hash_almacenado = user.password.encode('utf-8') if isinstance(user.password, str) else user.password
        return bcrypt.checkpw(contrasena_input.encode('utf-8'), hash_almacenado)

    def cerrar_sesion(self, user: User):
        if user:
            logger.info(f"Usuario {user.employee_number} ha cerrado sesión.")
        else:
            logger.warning("Intento de cierre de sesión sin usuario activo.")