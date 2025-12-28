import logging
import cv2
import base64

logger = logging.getLogger(__name__)

class CameraService:
    def __init__(self):
        self.cap = None # Variable para mantener la cámara abierta

    def verificar_disponibilidad(self) -> bool:
        """Verifica si hay cámara sin dejarla abierta."""
        try:
            temp_cap = cv2.VideoCapture(0)
            if temp_cap is None or not temp_cap.isOpened():
                return False
            temp_cap.release()
            return True
        except:
            return False

    def iniciar_camara(self):
        """Abre la conexión con la cámara."""
        if self.cap is None:
            self.cap = cv2.VideoCapture(0)
            # Opcional: Bajar resolución para ganar velocidad en Flet
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    def detener_camara(self):
        """Libera la cámara."""
        if self.cap:
            self.cap.release()
            self.cap = None

    def obtener_frame_base64(self):
        """
        Captura un frame, lo convierte a JPG y luego a string Base64 
        para que Flet pueda renderizarlo.
        Retorna: String Base64 o None si falla.
        """
        if not self.cap or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        if not ret:
            return None

        # 1. OpenCV usa BGR, a veces es bueno pasar a RGB, 
        # pero para Base64/JPG directo suele dar igual.
        
        # 2. Codificar la imagen a formato JPG en memoria
        # (quality=70 para que pese menos y vaya más rápido)
        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        
        # 3. Convertir bytes a Base64 string
        jpg_as_text = base64.b64encode(buffer).decode('utf-8')
        
        return jpg_as_text