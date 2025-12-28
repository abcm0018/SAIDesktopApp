from dataclasses import dataclass

@dataclass(frozen=True)
class PaletScanData:
    """Entidad de dominio pura que representa a un palet escaneado."""
    ean: str
    batch_number: str
    product_use_by_date: str
    packaging_date: str
    production_time: str
    sscc: str
