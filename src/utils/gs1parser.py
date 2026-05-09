import re
from typing import Dict, Optional
# Importamos la nueva utilidad
from src.utils.date_time_formatter import DateTimeFormatter

class GS1Parser:
    """
    Clase responsable de interpretar cadenas crudas GS1-128.
    Delega el formateo de valores a DateTimeFormatter.
    """
    
    _GS1_PATTERN = re.compile(r'\((\d+)\)\s*([^\(\)]+)')

    @staticmethod
    def parse(raw_text: str) -> Dict[str, str]:
        matches = GS1Parser._GS1_PATTERN.findall(raw_text)
        parsed_data = {}

        for ai, value in matches:
            value = value.strip()
            
            if ai == '00':
                parsed_data['sscc'] = value
            elif ai == '01':
                parsed_data['gtin'] = value
            elif ai == '10':
                parsed_data['batch'] = value
            elif ai == '15': # Best Before Date (YYMMDD)
                # Delegamos a la utilidad
                parsed_data['best_before_date'] = DateTimeFormatter.gs1_to_ui_date(value)
            elif ai == '8008': # Production Data
                prod_data = GS1Parser._parse_production_ai_8008(value)
                parsed_data.update(prod_data)
        
        return parsed_data

    @staticmethod
    def _parse_production_ai_8008(value: str) -> Dict[str, str]:
        """
        Maneja la lógica específica del AI 8008 (YYMMDDHHMM).
        Divide el string y delega el formateo.
        """
        result = {}
        if len(value) >= 10:
            date_part = value[:6]
            time_part = value[6:10]
            
            # Usamos la utilidad para convertir cada parte
            formatted_date = DateTimeFormatter.gs1_to_ui_date(date_part)
            formatted_time = DateTimeFormatter.gs1_to_ui_time(time_part)
            
            if formatted_date:
                result['production_date'] = formatted_date
            if formatted_time:
                result['production_time'] = formatted_time
                
        return result