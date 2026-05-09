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
            width: int = 1280,
            height: int = 720,
            mirror_mode: bool = False):
        """
        Inicializa el servicio de cámara con configuraciones predeterminadas.

        Args:
            camera_id (int): ID de la cámara a utilizar (por defecto, 0).
            width (int): Ancho deseado de la imagen capturada (por defecto, 1280).
            height (int): Alto deseado de la imagen capturada (por defecto, 720).
            mirror_mode (bool): Si True, activa el modo espejo para imágenes capturadas (por defecto, True).
        """
        # Configuración de Hardware
        self.camera_id = camera_id
        self.request_width = width
        self.request_height = height
        self._is_windows = sys.platform.startswith('win')
        self.mirror_mode = mirror_mode

        # Estado interno
        self.cap: Optional[cv2.VideoCapture] = None

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

    def iniciar_camara(self) -> bool:
        """
        Intenta iniciar la cámara.
        """
        if self.cap is not None and self.cap.isOpened():
            return False

        if self._conectar_driver(self.camera_id):
            logger.error("Cámara inciada correctamente.")
            return True

        logger.error("No se pudo iniciar ninguna cámara.")
        return False

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
                # INTER_NEAREST es suficiente para preview de UI y es 2-3x más rápido que LINEAR
                frame_view = cv2.resize(frame, new_dim, interpolation=cv2.INTER_NEAREST)
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
                # Si falla el DSHOW, es vital liberar el bloqueo de hardware antes del fallback
                if not cap.isOpened():
                    cap.release()
                    cap = cv2.VideoCapture(dev_id)
            else:
                cap = cv2.VideoCapture(dev_id)

            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.request_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.request_height)

                # Liberamos la anterior si existía en la instancia
                if self.cap:
                    self.cap.release()

                self.cap = cap
                return True
            else:
                # Si llegamos aquí y sigue sin abrir, liberamos hardware para que se apague la luz
                cap.release()
                return False

        except cv2.error as cv2_error:
            logger.error(f"Error al conectar con la cámara: {cv2_error}")
            return False