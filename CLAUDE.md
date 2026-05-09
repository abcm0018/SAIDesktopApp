# CLAUDE.md

### Agent Role and Expertise

When working with this repository, you must act as an **expert in intelligent vision application development**, with:

- **Strong experience in Python**, including:
  - Computer vision pipelines
  - Asynchronous and multithreaded processing
  - Integration with external systems (MQTT, databases, hardware devices)
- **Advanced knowledge of intelligent vision and AI**, especially:
  - Object detection and localization (e.g. YOLO-based models)
  - Image preprocessing and enhancement
  - Barcode and label recognition in industrial environments
- **Deep domain experience in logistics and warehouse management**, including:
  - Automated inventory systems
  - Pallet identification and traceability
  - Industrial scanning workflows
  - Reliability and robustness requirements in production environments

All code suggestions, refactors, and architectural decisions must take into account:

- Industrial constraints (performance, robustness, fault tolerance)
- Real-world warehouse conditions (lighting, camera positioning, label quality)
- Maintainability and clarity for long-term evolution of the system

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**SAI (Sistema de Inventariado Automatizado)** - a Windows desktop application for automated pallet scanning at warehouse workstations. A camera captures pallet labels, YOLOv5 locates barcode regions, zxing-cpp decodes GS1-128/ITF/DataMatrix barcodes, and the parsed data is published over MQTT to a backend Java system.

## Running the app

```bash
python main.py
```

Requires a `.env` file (see `.env` for the full template). Key variables:

| Variable | Purpose |
|---|---|
| `DB_HOST/PORT/USER/PASSWORD/NAME` | MySQL connection |
| `MQTT_BROKER/PORT/TOPIC/TOPIC_ERRORS` | MQTT broker |
| `YOLO_MODEL_PATH` | Path to `.pt` weights file |
| `YOLO_REPO_PATH` | Path to local YOLOv5 repo (`assets/yolov5`) |
| `DEVICE_CAMERA_ID` | OpenCV camera index |
| `STATION_CODE / STATION_CAMERA_ID` | Per-workstation identifiers, stored in `page.session` |

## Installing dependencies

```bash
pip install -r requirements.txt
# PyTorch must be installed separately based on hardware:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
# For CUDA: use the appropriate CUDA wheel URL from pytorch.org
```

## Architecture

### Startup sequence (`main.py`)

`main.py` is an `async` Flet entry point. On launch it shows a splash screen while sequentially initialising (in order): `DatabaseManager` -> `YoloModelLoader` (blocking, run via `asyncio.to_thread`) -> `MqttManager` -> all services. Once ready it hands off to `Router`.

### Layer responsibilities

```
src/config/       - Config dataclasses loaded from .env (AppConfig, MqttConfig, YoloConfig)
src/core/         - Infrastructure: DatabaseManager (SQLAlchemy/MySQL), MqttManager (paho-mqtt), YoloModelLoader (torch.hub)
src/domain/       - Domain models: PaletScanData (DTO), User, AuditScanIncidents
src/services/     - Application services (one responsibility each)
src/controllers/  - DashboardController: orchestrates the scanning loop
src/ui/           - Router + Views (Flet components only, no logic)
src/utils/        - GS1Parser, DateTimeFormatter, UI helpers, logging config
```

### Scanning pipeline (producer/consumer with two threads)

`DashboardController` owns two daemon threads started by `_start_system()`:

1. **Camera thread** (`_camera_capture_loop`): reads frames from `CameraService`, converts to base64 for the live video preview, and puts raw numpy frames on a `queue.Queue`.

2. **Processing thread** (`_processing_loop`): consumes frames and runs the pipeline:
   - `YoloService.detectar()` -> bounding boxes (ROIs) for barcode regions
   - `ScannerService.procesar_zonas()` -> decodes barcodes from ROIs using zxing-cpp with CLAHE contrast enhancement fallback; falls back to a central-crop strategy when YOLO finds nothing
   - `GS1Parser.parse()` -> maps GS1 Application Identifiers to `PaletScanData` fields
   - `PalletProcessingService.procesar_nuevos_datos()` -> accumulates data across frames (fill-the-gaps merge, never overwrites an already-set field)

Resolution triggers (either condition ends the read cycle):
- **Success** (`_finalizar_palet`): pallet has SSCC -> publish via `MqttService.enviar_datos_palet()` -> log via `AuditService` -> reset
- **Timeout** (`_handle_scan_timeout`): watchdog timer (`READ_TIMEOUT_SEC`, default 5 s) fires without SSCC -> log via `AuditService` -> reset

### MQTT split

`MqttManager` (in `src/core/`) is pure infrastructure: it maintains the paho client, handles reconnects, and publishes raw strings. `MqttService` (in `src/services/`) is the application layer: it builds the JSON payload, converts date formats via `DateTimeFormatter`, and delegates to `MqttManager`. Incidents are published to `MQTT_TOPIC_ERRORS`.

### Routing and auth

`Router` maps `AppRoutes` constants to view builders and enforces a simple auth guard: any route except `/login` requires `page.session.get("user") is not None`. Navigation is done via `page.go(route)`.

### Date formatting

GS1 dates arrive as `YYMMDD`; they are converted to UI format `DD/MM/20YY` by `DateTimeFormatter.gs1_to_ui_date()` at parse time, and then back to ISO `YYYY-MM-DD` by `DateTimeFormatter.ui_date_to_iso()` when building the MQTT payload.

## Import paths

The project uses `src.*` absolute imports (e.g. `from src.services.auth_service import AuthService`). Some older files still use root-relative imports (e.g. `from services.audit_service import AuditService`) - this is inconsistent; the `src.*` form is preferred.

## Assets

- `assets/models/model.pt` - YOLOv5 custom weights (not in repo, must be provided)
- `assets/yolov5/` - local YOLOv5 repo used as the `torch.hub` source
- `assets/logo.png` - splash screen logo