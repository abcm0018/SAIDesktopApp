# Funciones de conversión de fecha y hora GS1 a formato SQL
def formatear_fecha_gs1_a_java(fecha_gs1):
    if fecha_gs1 and len(fecha_gs1) == 6:
        year = int(fecha_gs1[0:2])
        year += 2000 if year < 50 else 1900
        month = int(fecha_gs1[2:4])
        day = int(fecha_gs1[4:6])
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year}-{month:02d}-{day:02d}"
    return None

def formatear_hora_gs1_a_java(hora_gs1):
    if hora_gs1 and len(hora_gs1) == 4:
        hour = int(hora_gs1[0:2])
        minute = int(hora_gs1[2:4])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    return None
