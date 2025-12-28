import logging
import os
import subprocess
from typing import Optional
import bcrypt

from src.services.database import SessionLocal
from src.model.user import User

# Instancia del logger a nivel de clase/módulo
logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self):
        logger.debug("Inicializando AuthService")

    def autenticar_usuario(self, num_empleado: str, contrasena: str) -> Optional[User]:
        logger.debug(f"Validando credenciales para el usuario: {num_empleado}")

        session = SessionLocal() #Abrimos la sesión con la BBDD
        try:
            user = session.query(User).filter_by(employee_number=num_empleado).first()

            if not user:
                logger.warning(f"Login fallido: Usuario {num_empleado} no encontrado")
                return None
            
            if not user.active or user.blocked:
                logger.warning(f"Login fallido: Usuario {num_empleado} inactivo o bloqueado")
                return None
            
            # Verificamos la contraseña usando bcrypt
            hash_almacenado = user.password.encode('utf-8') if isinstance(user.password, str) else user.password

            if bcrypt.checkpw(contrasena.encode('utf-8'), hash_almacenado):
                logger.info(f"Login exitoso para el usuario: {user.employee_number} ({user.role})")

                # CRUCIAL: "Desconectamos" el objeto de la sesión antes de cerrar la sesión
                # Eso permite usar el objeto fuera del contexto de la sesión
                session.expunge(user)
                return user
            
            # Contraseña incorrecta
            logger.warning(f"Login fallido: Contraseña incorrecta para el usuario {num_empleado}")
            return None
        
        except Exception as e:
            logger.exception(f"Error crítico durante la validación de credenciales para el usuario {num_empleado}: {e}")
            return None
        finally:
            session.close()

    def cerrar_sesion(self, user: User):
        """Método para manejar el cierre de sesión del usuario"""
        if user:
            logger.info(f"Usuario {user.employee_number} ha cerrado sesión.")
            # Aquí podríamos agregar lógica adicional si es necesario
        else:
            logger.warning("Intento de cierre de sesión sin usuario activo.")