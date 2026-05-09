import logging
import cv2
import numpy as np
from typing import Dict, Any, Optional, List, Tuple

from src.config.yolo_config import YoloConfig


logger = logging.getLogger(__name__)

class YoloService:
    """
    Servicio de Dominio encargado EXCLUSIVAMENTE de la detección visual.
    Responsabilidad: Recibir imagen -> Devolver coordenadas de códigos (Bounding Boxes)
    No lee el código, NOgestiona el estado del palet.
    """
    def __init__(self, model: Any, conf_threshold: float = 0.5):
        """
        Args:
            model: Objeto del modelo YOLOv5 ya cargado y en memoria (GPU/CPU)
            conf_threshold: Umbral de confianza para filtrar detecciones manualmente.
        """
        self.model = model
        self.conf_threshold = conf_threshold
        
        if self.model is None:
            logger.warning("YoloService inicializado con el modelo None. No habrá detección inteligente de códigos")
        else:
            logger.info(f"YoloService inicializado. Umbral de corte: {self.conf_threshold}")
            
    def detectar(self, frame: np.array) -> List[Tuple[int, int, int, int]] :
        """
        Realiza la inferencia sobre un frame y devuelve las cajas detectadas.
        Returns: [(x, y, w, h), ...]
        """
        if self.model is None or frame is None:
            return []
        
        try:
            # 1. Procesamiento: OpenCV (BGR) -> YOLO (RGB)
            img_rgb = frame[..., ::-1]

            # 2. Inferencia
            results = self.model(img_rgb, size=640)

            # 3. Post-procesamiento con numpy — evita la costosa conversión a pandas
            # Tensor shape: (N, 6) → [x1, y1, x2, y2, conf, cls]
            det = results.xyxy[0].cpu().numpy()

            detecciones = []
            for row in det:
                if row[4] < self.conf_threshold:
                    continue
                x1, y1, x2, y2 = int(row[0]), int(row[1]), int(row[2]), int(row[3])
                w, h = x2 - x1, y2 - y1
                if w > 0 and h > 0:
                    detecciones.append((x1, y1, w, h))

            return detecciones
        except Exception as e:
            logger.error(f"Error en iferencia YOLO: {e}")
            return []

    def detectar_v2(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        MÉTODO 2 (Portado de Scan Service):
        Estrategia robusta. Aplica PADDING (zona quieta) alrededor de la detección
        y asegura que las coordenadas no se salgan de la imagen.
        Returns: [(x, y, w, h), ...]
        """
        resultados = []
        
        if self.model is None or frame is None or frame.size == 0:
            return resultados

        try:
            # 1. Inferencia
            results = self.model(frame)

            h_img, w_img = frame.shape[:2]
            PADDING = 15

            # 2. Post-procesamiento con numpy — evita la costosa conversión a pandas
            det = results.xyxy[0].cpu().numpy()

            for row in det:
                if row[4] < self.conf_threshold:
                    continue

                x1 = max(0, int(row[0]) - PADDING)
                y1 = max(0, int(row[1]) - PADDING)
                x2 = min(w_img, int(row[2]) + PADDING)
                y2 = min(h_img, int(row[3]) + PADDING)

                w, h = x2 - x1, y2 - y1
                if w > 0 and h > 0:
                    resultados.append((x1, y1, w, h))

            return resultados

        except Exception as e:
            logger.error(f"Error en detección YOLO (detectar_v2): {e}")
            return []