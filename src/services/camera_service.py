import base64
import logging
import sys
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

class CameraService:
    def __init__(
            self,
            camera_id: int = 0,
            backup_id: Optional[int] = None,
            width: int = 1280,
            height: int = 720,
            mirror_mode: bool = True):
        """
        Inicializa el servicio de cámara con configuraciones predeterminadas.

        Args:
            camera_id (int): ID de la cámara a utilizar (por defecto, 0).
            backup_id (Optional[int]): ID de la cámara de respaldo en caso de error (por defecto, None).
            width (int): Ancho deseado de la imagen capturada (por defecto, 1280).
            height (int): Alto deseado de la imagen capturada (por defecto, 720).
            mirror_mode (bool): Si True, activa el modo espejo para imágenes capturadas (por defecto, True).
        """
        # Configuración de Hardware
        self.master_id = camera_id
        self.slave_id = backup_id

        self.camera_id = camera_id
        self.request_width = width
        self.request_height = height
        self._is_windows = sys.platform.startswith('win')
        self.mirror_mode = mirror_mode

        # Estado interno
        self.cap: Optional[cv2.VideoCapture] = None
        self.current_id = self.master_id # ID que estamos usando actualmente
        self.using_backup = False

        # Configuración de Failover (Patrón Circuit Breaker)
        self.error_count = 0
        self.MAX_ERRORS = 5 # Número de frames fallidos antes de conmutar

    def __enter__(self):
        """Permite usar 'with CameraService() as cam:'"""
        self.iniciar_camara()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Asegura el cierre de la cámara al salir del bloque with"""
        self.detener_camara()

    def __del__(self):
        # Mantenemos esto por seguridad, pero se prefiere usar Context Manager
        self.detener_camara()

    def iniciar_camara(self):
        """
        Intenta iniciar la cámara.
        Lógica Master-Slave: Intenta Master primero, si falla y existe Slave, intenta Slave.
        """
        if self.cap is not None and self.cap.isOpened():
            return

        logger.info(f"Iniciando sistema de cámaras. Maestro: {self.master_id}, Esclavo: {self.slave_id}")

        # Intentamos conectar la cámara MAESTRA
        if self._conectar_driver(self.master_id):
            self.current_id = self.master_id
            self.using_backup = False
            logger.info(f"Conexión exitosa con la cámara maestra {self.master_id}")
            return

        # Si falla la maestra, verificamos si tenemos ESCLAVA configurada
        if self.slave_id is not None:
            logger.warning(f"Conexión fallida con la cámara maestra {self.master_id}, intentando con la cámara esclava {self.slave_id}")
            if self._conectar_driver(self.slave_id):
                self.current_id = self.slave_id
                self.using_backup = True
                logger.info(f"Conexión exitosa con la cámara esclava {self.slave_id}")
                return

        logger.error("No se pudo iniciar ninguna cámara.")


        # try:
        #     # Selección inteligente del backend
        #     if self._is_windows:
        #         # DSHOW es más rápido en Windows iniciando
        #         self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
        #     else:
        #         # V4L2 es el estándar en Linux/Raspi
        #         self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_V4L2)
        #
        #     if not self.cap or not self.cap.isOpened():
        #         # Fallback al backend por defecto
        #         logger.warning("Backend específico falló, intentando backend por defecto...")
        #         self.cap = cv2.VideoCapture(self.camera_id)
        #
        #     if not self.cap.isOpened():
        #         raise ConnectionError(f"No se pudo abrir el dispositivo {self.camera_id}")
        #
        #     # --- CONFIGURACIÓN CRÍTICA PARA YOLO/TIEMPO REAL ---
        #
        #     # 1. Resolución
        #     self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.request_width)
        #     self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.request_height)
        #
        #     # 2. Formato: MJPG da más FPS en USB 2.0 que YUYV
        #     # noinspection PyUnresolvedReferences
        #     self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        #
        #     # 3. Buffer Size = 1.
        #     # VITAL: Evita procesar frames antiguos si la IA es más lenta que la cámara.
        #     # Asegura que frame leído == realidad instantánea.
        #     self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        #
        #     # 4. Autofocus
        #     self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
        #
        #     # Verificación final
        #     real_w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        #     real_h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        #     logger.info(f"Cámara iniciada. {int(real_w)}x{int(real_h)} @ {self.cap.get(cv2.CAP_PROP_FPS)} FPS")
        #
        # except Exception as e:
        #     logger.critical(f"Error fatal iniciando cámara: {e}")
        #     self.detener_camara()
        #     raise e

    def detener_camara(self):
        if self.cap:
            logger.info("Liberando recursos de cámara...")
            self.cap.release()
            self.cap = None

    def obtener_frame(self) -> Optional[np.ndarray]:
        """
        Captura un frame.
        Incluye lógica de 'Self-Healing': Si falla X veces, intenta cambiar de cámara automáticamente.
        """
        if not self.cap or not self.cap.isOpened():
            return None
        
        # Leemos el frame.
        ret, frame = self.cap.read()
        
        if not ret:
            self.error_count += 1
            logger.warning(f"Fallo de lectura ({self.error_count}/{self.MAX_ERRORS})")

            if self.error_count >= self.MAX_ERRORS:
                self._ejecutar_failover()

            return None

        # Si leemos bien, reseteamos el contador de errores
        self.error_count = 0

        # Aplicamos el efecto espejo si es necesario.
        if self.mirror_mode:
            frame = cv2.flip(frame, 1)
            
        return frame

    @staticmethod
    def convertir_numpy_a_base64(frame: np.ndarray, quality: int = 60, width_resize: int = 640) -> Optional[str]:
        """
        Prepara el frame para enviarlo a la UI de Flet.
        """
        if frame is None or frame.size == 0:
            return None

        try:
            # Optimización visual para Flet
            h, w = frame.shape[:2]

            # Solo redimensionamos si la imagen es más grande que el target
            if w > width_resize:
                scale = width_resize / w
                new_dim = (width_resize, int(h * scale))
                # INTER_LINEAR es más suave que NEAREST y casi igual de rápido hoy en día
                frame_view = cv2.resize(frame, new_dim, interpolation=cv2.INTER_LINEAR)
            else:
                frame_view = frame

            # Codificación JPG
            params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            success, buffer = cv2.imencode('.jpg', frame_view, params)

            if not success:
                return None

            return base64.b64encode(buffer).decode('utf-8')
        except Exception as e:
            logger.error(f"Error en conversión Base64: {e}")
            return None

    def _conectar_driver(self, dev_id):
        """
        Función privada para conectar al driver de la cámara. (Low Level)
        Aplica SRP: solo se preocupa de hablar con OpenCV
        """
        try:
            if self._is_windows:
                cap = cv2.VideoCapture(dev_id, cv2.CAP_DSHOW)
                # Fallback si DSHOW falla
                if not cap.isOpened():
                    cap = cv2.VideoCapture(dev_id)
            else:
                cap = cv2.VideoCapture(dev_id)

            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.request_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.request_height)

                # Liberamos la anterior si existía
                if self.cap:
                    self.cap.release()

                self.cap = cap
                return True

        except cv2.error as cv2_error:
            logger.error(f"Error al conectar con la cámara: {cv2_error}")
            raise
        except Exception as e:
            logger.error(f"Error desconocido al conectar con la cámara: {e}")
            raise
        return False

    def _ejecutar_failover(self):
        """
        Intentar cambiar la cámara alternariva si está disponible
        """
        self.error_count = 0 # Reseteamos para dar oportunidad a la nueva cámara

        # Caso 1: Estamos en Master y tenemos Slave -> vamos a Slave
        if not self.using_backup and self.slave_id is not None:
            logger.warning("Iniciando failover: Maestro -> Esclavo")
            if self._conectar_driver(self.slave_id):
                self.using_backup = True
                self.current_id = self.slave_id
            else:
                logger.error("Falló el cambio a ESCLAVA.")

        # Caso 2: Estamos en Slave y falla -> Intentamos recuperar Master (Retry Strategy)
        elif self.using_backup:
            logger.warning("La Esclava está fallando. Intentando recuperar MAESTRO.")
            if self._conectar_driver(self.master_id):
                self.using_backup = False
                self.current_id = self.master_id
            else:
                logger.error("Falló la recuperación del MAESTRO. Sistema sin video.")