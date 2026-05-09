import logging
import torch
import numpy as np
import warnings
from typing import Any, Optional
from src.config.yolo_config import YoloConfig

logger = logging.getLogger(__name__)

class YoloModelLoader:
    """Encapsula la complejidad de cargar PyTorch/YOLO."""
    
    def __init__(self, config: YoloConfig = None):
        # Si no pasan config, creamos una por defecto
        self.config = config or YoloConfig()
        self._model: Optional[Any] = None
        self._device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

    def load(self) -> Any:
        # Patrón Singleton (Lazy Loading)
        if self._model is not None:
            return self._model

        if not self.config.model_path.exists():
            raise FileNotFoundError(f"Modelo no encontrado: {self.config.model_path}")

        try:
            logger.info(f"Cargando YOLO en {self._device}...")
            
            # Suprimir warnings específicos de la carga
            warnings.filterwarnings('ignore', category=FutureWarning)
            
            model = torch.hub.load(
                self.config.repo_path, 
                'custom', 
                path=self.config.model_path, 
                source='local'
            )
            
            model.to(self._device).eval()
            model.conf = self.config.conf_threshold
            model.iou = self.config.iou_threshold
            
            self._warmup(model)
            
            logger.info("Modelo YOLO cargado.")
            self._model = model
            return self._model

        except Exception as e:
            logger.exception(f"Error cargando modelo: {e}")
            raise

    def _warmup(self, model):
        """Precalentamiento para evitar lag en la primera detección."""
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        model(dummy)

# Instancia global lista para usar (Singleton)
yolo_loader = YoloModelLoader()