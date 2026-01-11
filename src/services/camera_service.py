import logging
import cv2
import base64
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

class CameraService:
    def __init__(self, camera_id: int = 0, width: int = 1280, height: int = 720):
        self.camera_id = camera_id
        self.cap: Optional[cv2.VideoCapture] = None
        self.request_width = width
        self.request_height = height

    def iniciar_camara(self):
        """Abre la conexión con la cámara."""
        if self.cap is not None and self.cap.isOpened():
            return

        logger.info(f"Iniciando cámara (ID: {self.camera_id})...")
        try:
            # CAP_DSHOW es vital en Windows para inicio rápido
            self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
            
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.camera_id)

            if not self.cap.isOpened():
                raise Exception(f"No se pudo abrir el dispositivo {self.camera_id}")

            # Configuración
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.request_width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.request_height)
            
            # CAMBIO IMPORTANTE: Autofocus activado (1) para asegurar nitidez
            # en distintas distancias de palets.
            self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 1) 
            
            # Forzar MJPG suele dar más FPS en cámaras USB 2.0
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

            real_w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            real_h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            logger.info(f"Cámara iniciada. Resolución: {int(real_w)}x{int(real_h)}")

        except Exception as e:
            logger.critical(f"Error fatal cámara: {e}")
            self.cap = None

    def detener_camara(self):
        if self.cap:
            self.cap.release()
            self.cap = None

    def obtener_frame(self) -> Optional[np.ndarray]:
        """
        Captura el frame crudo. 
        Este es el que pasaremos al ScannerService directamente.
        """
        if not self.cap or not self.cap.isOpened():
            return None
        
        ret, frame = self.cap.read()
        return frame if ret else None

    def convertir_numpy_a_base64(self, frame: np.ndarray, quality: int = 50, width_resize: int = 640) -> Optional[str]:
        """
        Optimizado para Flet:
        1. Baja la calidad del JPG (50% es suficiente para preview).
        2. Redimensiona visualmente la imagen antes de codificar (Menos bytes = UI más fluida).
        NO afecta a la lectura del código de barras (que usa el frame original).
        """
        if frame is None or frame.size == 0:
            return None
        
        try:
            # Reducimos tamaño SOLO para la visualización en UI (mejora rendimiento Flet brutalmente)
            h, w = frame.shape[:2]
            if w > width_resize:
                scale = width_resize / w
                new_dim = (width_resize, int(h * scale))
                frame_view = cv2.resize(frame, new_dim, interpolation=cv2.INTER_NEAREST)
            else:
                frame_view = frame

            # Codificamos con calidad media para no saturar el hilo
            success, buffer = cv2.imencode('.jpg', frame_view, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if not success: return None
            
            return base64.b64encode(buffer).decode('utf-8')
        except Exception:
            return None

    def __del__(self):
        self.detener_camara()