import base64
import logging
import sys
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

class CameraService:
    def __init__(self, camera_id: int = 0, width: int = 1280, height: int = 720, mirror_mode: bool = True):
        self.camera_id = camera_id
        self.request_width = width
        self.request_height = height
        self.cap: Optional[cv2.VideoCapture] = None
        self._is_windows = sys.platform.startswith('win')
        self.mirror_mode = mirror_mode

    def __enter__(self):
        """Permite usar 'with CameraService() as cam:'"""
        self.iniciar_camara()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Asegura el cierre de la cámara al salir del bloque with"""
        self.detener_camara()

    def iniciar_camara(self):
        """Abre la conexión con la cámara aplicando configuraciones óptimas para IA."""
        if self.cap is not None and self.cap.isOpened():
            return

        logger.info(f"Iniciando cámara (ID: {self.camera_id})...")
        try:
            # Selección inteligente del backend
            if self._is_windows:
                # DSHOW es más rápido en Windows iniciando
                self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
            else:
                # V4L2 es el estándar en Linux/Raspi
                self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_V4L2)
                
            if not self.cap or not self.cap.isOpened():
                # Fallback al backend por defecto
                logger.warning("Backend específico falló, intentando backend por defecto...")
                self.cap = cv2.VideoCapture(self.camera_id)

            if not self.cap.isOpened():
                raise ConnectionError(f"No se pudo abrir el dispositivo {self.camera_id}")

            # --- CONFIGURACIÓN CRÍTICA PARA YOLO/TIEMPO REAL ---
            
            # 1. Resolución
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.request_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.request_height)
            
            # 2. Formato: MJPG da más FPS en USB 2.0 que YUYV
            # noinspection PyUnresolvedReferences
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            
            # 3. Buffer Size = 1.
            # VITAL: Evita procesar frames antiguos si la IA es más lenta que la cámara.
            # Asegura que frame leído == realidad instantánea.
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # 4. Autofocus
            self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)

            # Verificación final
            real_w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            real_h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            logger.info(f"Cámara iniciada. {int(real_w)}x{int(real_h)} @ {self.cap.get(cv2.CAP_PROP_FPS)} FPS")

        except Exception as e:
            logger.critical(f"Error fatal iniciando cámara: {e}")
            self.detener_camara()
            raise e

    def detener_camara(self):
        if self.cap:
            logger.info("Liberando recursos de cámara...")
            self.cap.release()
            self.cap = None

    def obtener_frame(self) -> Optional[np.ndarray]:
        """
        Captura el frame más reciente.
        """
        if not self.cap or not self.cap.isOpened():
            return None
        
        # Leemos el frame.
        ret, frame = self.cap.read()
        
        if not ret:
            logger.warning("No se pudo leer el frame (cámara desconectada o frame vacío).")
            return None
        
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

    def __del__(self):
        # Mantenemos esto por seguridad, pero se prefiere usar Context Manager
        self.detener_camara()