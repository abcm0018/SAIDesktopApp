import base64
import logging
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class FramePacket:
    """
    Representa un fotograma capturado por la cámara.

    Attributes:
        frame_id: identificador secuencial del fotograma.
        captured_at: instante de captura expresado como timestamp.
        frame: imagen capturada en formato BGR de OpenCV.
    """

    frame_id: int
    captured_at: float
    frame: np.ndarray

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

        # Acceso al dispositivo físico de captura
        self.cap: Optional[cv2.VideoCapture] = None
        self._cap_lock = threading.Lock()

        # Último fotograma capturado
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_frame_id = 0
        self._latest_frame_at = 0.0

        # Hilo único encargado de leer la cámara
        self._capture_stop = threading.Event()
        self._capture_thread: Optional[threading.Thread] = None

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
            Abre la cámara e inicia el hilo único de adquisición de imágenes.

            Returns:
                True si la cámara queda disponible; False en caso contrario.
            """
        if self.cap is not None and self.cap.isOpened():
            logger.info("La cámara ya estaba iniciada.")
            return True

        if not self._conectar_driver(self.camera_id):
            logger.error("No se pudo iniciar la cámara.")
            return False

        # Reiniciar el estado del último fotograma.
        with self._frame_lock:
            self._latest_frame = None
            self._latest_frame_id = 0
            self._latest_frame_at = 0.0

        self._capture_stop.clear()
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=False,
            name="sai-camera-reader",
        )
        self._capture_thread.start()

        logger.info("Cámara iniciada correctamente.")
        return True

    def _capture_loop(self) -> None:
        """
            Lee continuamente la cámara y conserva únicamente el fotograma más reciente.

            Este es el único método de la aplicación que debe ejecutar cap.read().
            """
        logger.info("Hilo único de captura iniciado.")

        frames_capturados = 0
        inicio_medicion = time.monotonic()

        while not self._capture_stop.is_set():
            with self._cap_lock:
                cap = self.cap

                if cap is None or not cap.isOpened():
                    break

                ret, frame = cap.read()

            if not ret or frame is None:
                logger.warning("No se pudo obtener un fotograma de la cámara.")
                time.sleep(0.02)
                continue

            frames_capturados += 1

            ahora = time.monotonic()
            tiempo_transcurrido = ahora - inicio_medicion

            if tiempo_transcurrido >= 5.0:
                fps_efectivos = frames_capturados / tiempo_transcurrido

                logger.info(
                    "Rendimiento real de captura: %.2f FPS "
                    "(%d fotogramas en %.2f segundos).",
                    fps_efectivos,
                    frames_capturados,
                    tiempo_transcurrido,
                )

                frames_capturados = 0
                inicio_medicion = ahora

            if self.mirror_mode:
                frame = cv2.flip(frame, 1)

            with self._frame_lock:
                self._latest_frame = frame
                self._latest_frame_id += 1
                self._latest_frame_at = time.time()

        logger.info("Hilo único de captura finalizado.")

    def detener_camara(self) -> None:
        """
        Detiene primero el hilo de adquisición y después libera la cámara.

        Este orden evita liberar VideoCapture mientras otro hilo se encuentra
        ejecutando cap.read(), especialmente importante en macOS.
        """
        self._capture_stop.set()

        capture_thread = self._capture_thread

        if (
                capture_thread is not None
                and capture_thread.is_alive()
                and capture_thread is not threading.current_thread()
        ):
            capture_thread.join()

        self._capture_thread = None

        with self._cap_lock:
            if self.cap is not None:
                logger.info("Liberando recursos de cámara...")
                self.cap.release()
                self.cap = None

        with self._frame_lock:
            self._latest_frame = None
            self._latest_frame_id = 0
            self._latest_frame_at = 0.0

    def obtener_ultimo_frame(self) -> Optional[FramePacket]:
        """
        Devuelve una copia del último fotograma disponible.

        No realiza una nueva lectura sobre el dispositivo físico.
        """
        with self._frame_lock:
            if self._latest_frame is None:
                return None

            return FramePacket(
                frame_id=self._latest_frame_id,
                captured_at=self._latest_frame_at,
                frame=self._latest_frame.copy(),
            )

    def obtener_frame(self) -> Optional[np.ndarray]:
        """
        Mantiene compatibilidad con el código existente.

        Devuelve únicamente la imagen del último fotograma capturado.
        """
        packet = self.obtener_ultimo_frame()

        if packet is None:
            return None

        return packet.frame

    def capturar_foto_hd(self, n_flush: int = 3) -> Optional[np.ndarray]:
        """
        Devuelve en escala de grises el último fotograma capturado.

        El parámetro n_flush se conserva temporalmente por compatibilidad,
        pero ya no se descartan fotogramas directamente desde el driver.
        """
        packet = self.obtener_ultimo_frame()

        if packet is None:
            return None

        return cv2.cvtColor(packet.frame, cv2.COLOR_BGR2GRAY)

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

    def _registrar_configuracion_real(self, cap: cv2.VideoCapture) -> None:
        """
        Registra las propiedades que OpenCV puede consultar de la cámara.

        Los valores obtenidos mediante cap.get() representan lo que el backend
        comunica realmente, que puede diferir de los valores solicitados mediante
        cap.set().
        """

        try:
            backend = cap.getBackendName()
        except (cv2.error, AttributeError):
            backend = "desconocido"

        propiedades = {
            "width": cap.get(cv2.CAP_PROP_FRAME_WIDTH),
            "height": cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
            "fps": cap.get(cv2.CAP_PROP_FPS),
            "exposure": cap.get(cv2.CAP_PROP_EXPOSURE),
            "gain": cap.get(cv2.CAP_PROP_GAIN),
            "focus": cap.get(cv2.CAP_PROP_FOCUS),
            "autofocus": cap.get(cv2.CAP_PROP_AUTOFOCUS),
            "auto_exposure": cap.get(cv2.CAP_PROP_AUTO_EXPOSURE),
            "buffer_size": cap.get(cv2.CAP_PROP_BUFFERSIZE),
        }

        logger.info("Backend de cámara: %s", backend)

        logger.info(
            "Configuración real de cámara: "
            "resolución=%.0fx%.0f, "
            "fps=%.2f, "
            "exposición=%.2f, "
            "ganancia=%.2f, "
            "enfoque=%.2f, "
            "autoenfoque=%.2f, "
            "autoexposición=%.2f, "
            "buffer=%.2f",
            propiedades["width"],
            propiedades["height"],
            propiedades["fps"],
            propiedades["exposure"],
            propiedades["gain"],
            propiedades["focus"],
            propiedades["autofocus"],
            propiedades["auto_exposure"],
            propiedades["buffer_size"],
        )

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
                width_aplicado = cap.set(
                    cv2.CAP_PROP_FRAME_WIDTH,
                    self.request_width,
                )
                height_aplicado = cap.set(
                    cv2.CAP_PROP_FRAME_HEIGHT,
                    self.request_height,
                )
                buffer_aplicado = cap.set(
                    cv2.CAP_PROP_BUFFERSIZE,
                    1,
                )

                logger.info(
                    "Configuración solicitada: "
                    "resolución=%dx%d, buffer=1; "
                    "aplicación width=%s, height=%s, buffer=%s",
                    self.request_width,
                    self.request_height,
                    width_aplicado,
                    height_aplicado,
                    buffer_aplicado,
                )

                self._registrar_configuracion_real(cap)

                with self._cap_lock:
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