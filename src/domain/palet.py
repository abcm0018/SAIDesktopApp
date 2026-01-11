from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime

@dataclass
class PaletScanData:
    """
    DTO que representa la información de un palet.
    Responsabilidad: Mantener el estado de los datos y validar completitud.
    """
    sscc: Optional[str] = None
    ean: Optional[str] = None
    batch_number: Optional[str] = None
    product_use_by_date: Optional[str] = None  # Formato: DD/MM/20AA
    packaging_date: Optional[str] = None       # Formato: DD/MM/20AA
    production_time: Optional[str] = None      # Formato: HH:MM
    
    # Metadatos de control
    ultimo_update: datetime = field(default_factory=datetime.now)

    def is_complete(self) -> bool:
        """
        Define si el palet tiene la información mínima necesaria.
        """
        campos_obligatorios = [
            self.sscc, 
            self.ean, 
            self.batch_number, 
            self.product_use_by_date
            # self.production_time # Descomentar si la hora es crítica
        ]
        # Verificamos que ninguno sea None
        return all(v is not None for v in campos_obligatorios)

    def actualizar_datos(self, datos_parser: Dict[str, Any]):
        """
        Ingesta datos provenientes del GS1Parser y actualiza los campos.
        """
        self.ultimo_update = datetime.now()

        # MAPA DE TRADUCCIÓN: { "Clave_Parser": "Atributo_Clase" }
        mapping = {
            "sscc": "sscc",
            "gtin": "ean",
            "batch": "batch_number",
            "best_before_date": "product_use_by_date",
            "production_date": "packaging_date", 
            "production_time": "production_time"
        }

        for key_parser, attr_class in mapping.items():
            valor_nuevo = datos_parser.get(key_parser)
            
            # Solo actualizamos si el valor existe y el atributo actual es None
            # (o si quisieras lógica de sobrescritura, quitarías la condición 'is None')
            if valor_nuevo and getattr(self, attr_class) is None:
                setattr(self, attr_class, valor_nuevo)

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializa el objeto para devolverlo a la UI, API o imprimirlo.
        """
        return {
            "sscc": self.sscc,
            "ean": self.ean,
            "batch_number": self.batch_number,
            "product_use_by_date": self.product_use_by_date,
            "packaging_date": self.packaging_date,
            "production_time": self.production_time,
            "is_complete": self.is_complete(),
            "ultimo_update": self.ultimo_update.isoformat() if self.ultimo_update else None
        }