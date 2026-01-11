import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class YoloConfig:
    """DTO que contiene solo la configuración estática"""
    model_path: Path = Path(os.getenv("YOLO_MODEL_PATH", "assets/models/model.pt"))
    repo_path: str = os.getenv("YOLO_REPO_PATH", "assets/yolov5")
    conf_threshold: float = float(os.getenv("YOLO_CONF_THRESHOLD", "0.5"))
    iou_threshold: float = float(os.getenv("YOLO_IOU_THRESHOLD", "0.45"))
    
    # Parámetros de Pre-procesamiento de  ROI
    CLAHE_CLIP_LIMIT: float = 2.0
    CLAHE_GRID_SIZE: tuple = (8, 8)
    
    # Umbrales para estrategias binarias si no se usa Otsu
    BINARY_THRESHOLD: int = 127
    MAX_VAL: int = 255