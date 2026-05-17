# Auditoría de Diseño Industrial — SAI

**Sistema:** SAI (Sistema de Inventariado Automatizado)
**Fecha:** 2026-05-17
**Versión analizada:** rama `main`, commit `6579153`
**Auditor:** Claude Sonnet 4.6 (claude.ai/code)

---

## Resumen ejecutivo

SAI es un sistema de visión artificial industrial para escáner de palés en almacén. Tras un análisis exhaustivo de las 31 clases Python del proyecto, se han identificado **4 bloqueantes de producción**, **12 problemas de alto riesgo** y **10 puntos de mejora medio**. El sistema también presenta prácticas correctas consolidadas que deben preservarse.

### Tabla de hallazgos por severidad

| Severidad | Cantidad | Descripción |
|-----------|----------|-------------|
| 🔴 CRÍTICO | 4 | Bloqueantes: pérdida de datos, bug runtime, condiciones de carrera |
| 🟠 ALTO | 12 | Riesgos de robustez: resiliencia, thread-safety, observabilidad |
| 🟡 MEDIO | 10 | Mejoras: configuración, validación, seguridad |

---

## Dimensiones evaluadas

1. [Arquitectura y separación de responsabilidades](#1-arquitectura-y-separación-de-responsabilidades)
2. [Concurrencia y thread-safety](#2-concurrencia-y-thread-safety)
3. [Integridad de datos](#3-integridad-de-datos)
4. [Resiliencia y tolerancia a fallos](#4-resiliencia-y-tolerancia-a-fallos)
5. [Observabilidad](#5-observabilidad)
6. [Configuración y operabilidad](#6-configuración-y-operabilidad)
7. [Seguridad](#7-seguridad)
8. [Fortalezas a preservar](#8-fortalezas-a-preservar)
9. [Plan de remediación](#9-plan-de-remediación)

---

## 1. Arquitectura y separación de responsabilidades

### Diagnóstico

El patrón MVC está **correctamente diseñado** en `dashboard_controller.py`, con arquitectura Producer-Consumer, 3 hilos dedicados y cola MQTT separada. Sin embargo, la migración no se completó: `DashboardView` retiene toda la lógica original y `DashboardController` es código muerto.

### Hallazgos

| Severidad | Hallazgo | Archivo | Líneas |
|-----------|----------|---------|--------|
| 🔴 CRÍTICO | `DashboardView` (751 líneas) es un **God Object**: contiene hilos de OS, lógica de negocio de acumulación, estado operacional y componentes UI en la misma clase | `src/ui/views/dashboard_view.py` | 24–751 |
| 🔴 CRÍTICO | `DashboardController` existe con la arquitectura correcta pero **no está conectado a la UI** — es código muerto | `src/controllers/dashboard_controller.py` | 1–244 |
| 🟠 ALTO | Lógica de autenticación, gestión de sesión y navegación mezcladas en `LoginView._handle_login()` | `src/ui/views/login_view.py` | 249–281 |
| 🟠 ALTO | `_fusionar_datos()` implementa lógica de negocio de acumulación de palé directamente en la vista; `PalletProcessingService` ya existe para eso | `src/ui/views/dashboard_view.py` | 661–690 |
| 🟡 MEDIO | La vista accede a `self.mqtt_service.mqtt_manager.disconnect()` — violación de encapsulación de 2 niveles (Law of Demeter) | `src/ui/views/dashboard_view.py` | 325 |

### Impacto industrial

Un God Object es especialmente peligroso en un sistema industrial porque:
- Un fallo de UI puede detener el pipeline de escaneo y viceversa.
- Los hilos no se pueden aislar ni reiniciar sin destruir la vista.
- Cualquier cambio en la lógica de negocio requiere tocar la capa de presentación.

---

## 2. Concurrencia y thread-safety

### Diagnóstico

El sistema arranca 3 hilos concurrentes (cámara, procesamiento, animación) que comparten estado mutable sin sincronización. En un sistema industrial con throughput constante, las condiciones de carrera son reproducibles, no teóricas.

### Hallazgos

| Severidad | Hallazgo | Archivo | Líneas |
|-----------|----------|---------|--------|
| 🔴 CRÍTICO | `is_scanning` flag leído/escrito por 3 hilos sin `Lock` — condición de carrera documentada | `dashboard_view.py` | 567, 596, 352 |
| 🔴 CRÍTICO | `lectura_bloqueada` flag: patrón **TOCTOU** (Time-Of-Check-Time-Of-Use) — entre el check (`if not self.lectura_bloqueada`) y el uso, otro hilo puede cambiar el estado | `dashboard_view.py` | 576, 618 |
| 🟠 ALTO | `cv2.VideoCapture` no está protegido por `Lock` — `_detener_flujo_camara()` puede liberar `self.cap` mientras el hilo de cámara ejecuta `cap.read()` | `src/services/camera_service.py` | — |
| 🟠 ALTO | `_cooldown_event`: si `_detener_flujo_camara()` ejecuta `set()` antes del `clear()` interno de `_finalizar_palet()`, la señal se consume y pierde el efecto de interrupción del cooldown | `dashboard_view.py`, `dashboard_controller.py` | 207–208 |
| 🟠 ALTO | Hilos declarados como `daemon=True` — se matan sin garantía de flush si el proceso principal termina inesperadamente | `dashboard_view.py` | 361–366 |
| 🟡 MEDIO | `AuditService.registrar_incidencia()`: condición de carrera TOCTOU — la query de deduplicación y el insert no son atómicos; dos hilos podrían insertar el mismo SSCC simultáneamente | `src/services/audit_service.py` | 35–56 |

### Impacto industrial

Las condiciones de carrera en sistemas industriales de producción continua son particularmente peligrosas porque se manifiestan bajo carga, no en pruebas. En un almacén con conveyor a 30 palés/hora, un deadlock o estado corrupto puede detener la línea.

---

## 3. Integridad de datos

### Diagnóstico

El sistema tiene dos rutas de pérdida de datos sin recuperación: cola MQTT llena y crash del proceso con hilos daemon activos. Ambas son silenciosas desde el punto de vista del operador.

### Hallazgos

| Severidad | Hallazgo | Archivo | Líneas |
|-----------|----------|---------|--------|
| 🔴 CRÍTICO | **Cola MQTT llena → palé descartado silenciosamente.** Solo se emite `logger.error`; no hay reintento, persistencia local ni Dead Letter Queue (DLQ). En producción, el operador no sabe que el palé no llegó al backend | `dashboard_controller.py` | 195–202 |
| 🔴 CRÍTICO | **Nombre de método incorrecto en runtime:** `mqtt_service` llama a `self.mqtt_manager.publish()` pero el método real se llama `publish_message()`. Falla en runtime con `AttributeError` | `src/services/mqtt_service.py` | 105 |
| 🟠 ALTO | Si el proceso crashea con hilos daemon activos, los mensajes en la cola MQTT en memoria se pierden sin posibilidad de recuperación | Arquitectura general | — |
| 🟡 MEDIO | `PaletScanData` no valida el formato de los campos de fecha (`DD/MM/YYYY`) — datos malformados desde el parser GS1 pueden propagarse directamente al backend | `src/domain/palet.py` | 14–16 |
| 🟡 MEDIO | `scan_start_time` no se resetea en `PalletProcessingService.reset_palet()` — el siguiente palé puede heredar el timer del anterior, disparando un timeout prematuro | `src/services/pallet_processing_service.py` | 61 |

---

## 4. Resiliencia y tolerancia a fallos

### Diagnóstico

Los componentes de infraestructura (MQTT, BD, cámara) no tienen estrategias de recuperación robustas. Un sistema industrial debe asumir que todos los recursos externos fallarán eventualmente.

### Hallazgos

| Severidad | Hallazgo | Archivo | Líneas |
|-----------|----------|---------|--------|
| 🟠 ALTO | **MQTT reconnect sin backoff exponencial** — en fallo persistente del broker, el sistema reintenta inmediatamente en bucle, saturando el broker y la red | `src/core/mqtt_manager.py` | 152–165 |
| 🟠 ALTO | `MqttManager.connect()` usa `time.sleep(0.1)` en bucle de polling para esperar la conexión — debería usar `threading.Event.wait(timeout)` para evitar CPU spinning | `src/core/mqtt_manager.py` | 79–83 |
| 🟠 ALTO | `torch.hub.load()` no tiene timeout — si el archivo `.pt` está corrupto o el disco es lento, la carga puede congelar indefinidamente el splash screen | `src/core/yolo_loader.py` | 33–37 |
| 🟠 ALTO | `DatabaseManager` creado sin `pool_pre_ping=True` — conexiones muertas (p.ej. tras inactividad nocturna) se reutilizan y generan errores en el primer acceso del turno | `src/core/database_manager.py` | 19–24 |
| 🟡 MEDIO | Si BD o MQTT fallan en el arranque, no hay opción de reintento — el operador debe reiniciar toda la aplicación desde cero | `main.py` | 134–189 |
| 🟡 MEDIO | Error en startup no hace cleanup de recursos ya inicializados (la conexión BD queda abierta si MQTT falla a continuación) | `main.py` | 212–221 |
| 🟡 MEDIO | `MqttConfig` y `YoloConfig`: las conversiones `int(os.getenv(...))` y `float(os.getenv(...))` no tienen try/except — un valor inválido en `.env` crashea en inicio con traza críptica | `src/config/mqtt_config.py`, `src/config/yolo_config.py` | 37, 43, 11–12 |

---

## 5. Observabilidad

### Diagnóstico

Un sistema industrial en producción debe ser "legible" sin acceso al código fuente: los logs deben permitir reconstruir qué pasó, cuándo y por qué. El sistema actual tiene logs útiles pero carece de rotación, métricas de pipeline y cobertura de tests.

### Hallazgos

| Severidad | Hallazgo | Archivo | Líneas |
|-----------|----------|---------|--------|
| 🟠 ALTO | **Sin rotación de logs** — `app_inventario.log` crece indefinidamente. En un puesto de almacén activo 8h/día, puede agotar el disco en semanas | `logging_config.yaml` | — |
| 🟠 ALTO | **Frames descartados no se loguean** — si el procesamiento IA no puede seguir el ritmo de la cámara (p.ej. por alta temperatura de GPU), los frames se descartan silenciosamente sin ninguna métrica | `dashboard_view.py`, `dashboard_controller.py` | 577–579, 119–121 |
| 🟠 ALTO | **0 tests en el proyecto** — ni unitarios, ni de integración, ni de UI. Cualquier regresión introducida en mantenimiento es invisible hasta producción | Estructura completa | — |
| 🟡 MEDIO | Logging en texto libre — dificulta el análisis automatizado. Un formato estructurado (JSON) permitiría usar herramientas de centralización de logs | `logging_config.yaml` | — |
| 🟡 MEDIO | `DateTimeFormatter` y `GS1Parser` devuelven `None` silenciosamente en conversiones fallidas — los errores de parsing de etiquetas no quedan registrados | `src/utils/date_time_formatter.py`, `src/utils/gs1parser.py` | 31, 30 |
| 🟡 MEDIO | Cola MQTT llena solo genera `logger.error` — sin alerta activa (sonido, UI, notificación), el operador en almacén no se entera de que un palé no se ha enviado | `dashboard_controller.py` | 200–202 |

---

## 6. Configuración y operabilidad

### Diagnóstico

Los builds no son completamente reproducibles y hay inconsistencias en el patrón de configuración entre módulos.

### Hallazgos

| Severidad | Hallazgo | Archivo |
|-----------|----------|---------|
| 🟠 ALTO | **7 dependencias sin versión fijada** (`zxing-cpp`, `opencv-python>=4.8`, `scipy>=1.4.1`, `pandas>=1.1.4`, `Pillow>=10.3`, `requests>=2.32`, `gitpython>=3.1`) — un `pip install` en nuevo equipo puede traer versiones incompatibles | `requirements.txt` |
| 🟡 MEDIO | `load_dotenv()` se llama dos veces: en `main.py:30` y en `src/config/app_config.py:4` — sin consecuencias prácticas ahora, pero genera confusión sobre cuál es la fuente de verdad | `main.py`, `src/config/app_config.py` |
| 🟡 MEDIO | `AppConfig` no es dataclass ni tiene validación explícita, a diferencia de `MqttConfig` (que sí tiene `@dataclass(frozen=True)` y `validate()`) — inconsistencia del patrón de configuración | `src/config/app_config.py` |
| 🟡 MEDIO | Imports inconsistentes: algunos archivos usan `from services.x` (ruta relativa a raíz), otros `from src.services.x` (ruta absoluta con prefijo) — puede romper en entornos donde el directorio de trabajo no es la raíz del proyecto | Varios archivos |

---

## 7. Seguridad

| Severidad | Hallazgo | Archivo |
|-----------|----------|---------|
| 🟡 MEDIO | `.env` contiene credenciales reales de BD y MQTT. Si se incluye accidentalmente en un commit, queda expuesto en el historial de git. Falta `.env.example` con placeholders como guía | `.env` |
| 🟡 MEDIO | `User.role` es un campo de texto libre sin validación contra un enum — datos inválidos en BD pueden llegar al dominio de la aplicación | `src/domain/user.py` |

---

## 8. Fortalezas a preservar

Las siguientes prácticas son correctas y deben mantenerse como referencia para el resto del código:

| Práctica | Archivo | Por qué es correcta |
|----------|---------|---------------------|
| Carga async de YOLO con `asyncio.to_thread()` | `main.py:153` | Evita congelar la UI durante la carga del modelo (operación de 2–10s) |
| Context manager `DatabaseManager.session()` con rollback automático | `src/core/database_manager.py:49-66` | Garantiza cierre de sesión y reversión incluso ante excepciones |
| `MqttConfig` como `@dataclass(frozen=True)` con `validate()` | `src/config/mqtt_config.py` | Configuración inmutable y validada en el punto de entrada |
| `DateTimeFormatter` con `@lru_cache(maxsize=256)` | `src/utils/date_time_formatter.py` | Correcto para el hot path de parsing GS1 (mismas fechas se repiten en un turno) |
| `AppRoutes` como clase de constantes | `src/config/routes.py` | Elimina magic strings de navegación |
| `design_system.py` centralizado | `src/ui/design_system.py` | Consistencia visual garantizada en toda la aplicación |
| `_obscure_pass_in_url()` en DatabaseManager | `src/core/database_manager.py:42-47` | Protege credenciales en los logs de conexión |
| Fallback visual de error en `main.py` | `main.py:212-221` | El operador ve el error en pantalla en lugar de una ventana que desaparece |
| CLAHE como fallback de contraste en `ScannerService` | `src/services/scanner_service.py` | Estrategia de reintento robusta para etiquetas con baja iluminación |

---

## 9. Plan de remediación

### Fase 1 — Bloqueantes de producción

Estos cinco puntos deben resolverse **antes de cualquier despliegue en almacén**.

| # | Acción | Archivo | Tipo |
|---|--------|---------|------|
| 1 | Corregir `mqtt_manager.publish()` → `mqtt_manager.publish_message()` | `src/services/mqtt_service.py:105` | Bug fix |
| 2 | Cambiar `frame_queue.put_nowait()` a `put(block=True, timeout=5)` o añadir reintento con persistencia local ante cola MQTT llena | `src/controllers/dashboard_controller.py:195` | Integridad de datos |
| 3 | Convertir hilos a `daemon=False` y añadir `join(timeout=5)` en `_stop_system()` para garantizar flush MQTT en shutdown | `src/controllers/dashboard_controller.py:87-105` | Integridad de datos |
| 4 | Añadir `threading.Lock` para `is_scanning` y `lectura_bloqueada` en `DashboardController` | `src/controllers/dashboard_controller.py` | Thread-safety |
| 5 | Añadir `threading.Lock` en `CameraService` para proteger acceso a `cv2.VideoCapture` | `src/services/camera_service.py` | Thread-safety |

### Fase 2 — Resiliencia y observabilidad

| # | Acción | Archivo |
|---|--------|---------|
| 6 | Backoff exponencial en reconexión MQTT (1s → 2s → 4s → 32s máximo) | `src/core/mqtt_manager.py:152-165` |
| 7 | `pool_pre_ping=True` y `pool_recycle=3600` en `DatabaseManager` | `src/core/database_manager.py:19-24` |
| 8 | `RotatingFileHandler` (10 MB, 5 rotaciones) en lugar de `FileHandler` | `logging_config.yaml` |
| 9 | Contador de frames descartados con `logger.warning` cuando supere umbral | `src/controllers/dashboard_controller.py:119-121` |
| 10 | try/except en conversiones de env vars en `AppConfig` y `YoloConfig` | `src/config/app_config.py`, `src/config/yolo_config.py` |
| 11 | Fijar versiones exactas de las 7 dependencias sin pin | `requirements.txt` |

### Fase 3 — Arquitectura y mantenibilidad

| # | Acción | Archivo |
|---|--------|---------|
| 12 | Conectar `DashboardController` a `DashboardView` completando la migración MVC; eliminar lógica de hilos y negocio de la vista | `src/ui/views/dashboard_view.py`, `src/controllers/dashboard_controller.py` |
| 13 | Mover `_fusionar_datos()` de la vista a `PalletProcessingService` | `src/ui/views/dashboard_view.py:661`, `src/services/pallet_processing_service.py` |
| 14 | Tests unitarios básicos para: `AuthService`, `GS1Parser`, `DateTimeFormatter`, `PalletProcessingService` | `tests/` (nuevo) |

---

## Criterios de verificación

| Fase | Cómo verificar |
|------|----------------|
| Fase 1 | Ejecutar la app, activar sistema, desconectar broker MQTT manualmente y reconectar — confirmar que palés en cola llegan al backend; confirmar que no hay `AttributeError` en logs |
| Fase 2 | Saturar la cola de frames artificialmente y verificar `logger.warning` en logs; comprobar que `app_inventario.log` rota al superar 10 MB |
| Fase 3 | `pytest --cov=src` con cobertura ≥ 70% en servicios; verificar que `dashboard_view.py` no contiene imports de `threading` ni `queue` |
