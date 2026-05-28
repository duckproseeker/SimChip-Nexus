# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

SimChip Nexus (芯境智测平台) generates virtual sensor data from CARLA simulation and injects it into real chips (DUT) for autonomous driving HIL testing.

Core capabilities:
- **Pipeline editor**: visual drag-and-drop sensor topology (cameras, LiDAR, radar)
- **Offline rendering**: CARLA sync-mode frame-by-frame multi-sensor data generation with physics
- **Online playback**: mpv GPU-accelerated fullscreen display for HDMI capture
- **Scenario library**: manage CARLA recorder .log files and rendered datasets

## Commands

### Start API server

```bash
cd /home/du/ros2-humble/src/SimChip-Nexus
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

### Build frontend

```bash
cd /home/du/ros2-humble/src/SimChip-Nexus/frontend
PATH="/home/du/.local/share/simchip-node/node-v22.22.2-linux-x64/bin:$PATH" npx vite build
```

### Run tests

```bash
cd /home/du/ros2-humble/src/SimChip-Nexus
pytest -q
```

## Architecture

### Data Flow

```
Web UI (React SPA)
  → REST API (FastAPI, port 8000)
    → Executor (docker exec ros2-dev python3 -c <script>)
      → CARLA Server (carla-offscreen container, port 2000)
```

### Backend (app/)

```
app/
├── api/
│   ├── main.py                 # FastAPI app entry, mounts routers + static files
│   ├── routes_pipelines.py     # Pipeline CRUD + offline render execution
│   ├── routes_datasets.py      # Dataset list/delete/play/stop
│   └── routes_scenario_assets.py  # Scenario asset CRUD
├── executor/
│   ├── offline_renderer.py     # Builds & runs CARLA render script in container
│   └── online_player.py        # mpv fullscreen playback on host display
├── storage/
│   ├── pipeline_store.py       # Pipeline SQLite store
│   ├── pipeline_execution_store.py  # Execution records
│   ├── dataset_store.py        # Dataset SQLite store
│   └── scenario_asset_store.py # Scenario asset SQLite store
└── core/
    ├── models.py               # Pydantic models (Pipeline, Dataset, Scenario, etc.)
    ├── config.py               # App configuration
    └── logging.py              # Logging setup
```

### Frontend (frontend/src/)

```
frontend/src/
├── app/router.tsx              # Route definitions
├── pages/
│   ├── pipelines/              # Pipeline list + editor + run pages
│   ├── datasets/DatasetsPage   # Dataset management (progress, play, delete)
│   └── scenarios/              # Scenario library
├── components/pipeline/        # Node editor (canvas, library, property panel, forms)
├── features/pipeline/          # Zustand store + validation
└── api/                        # API client modules (pipelines, datasets, scenarioAssets)
```

### Persistence

- SQLite databases in `run_data/` (pipelines, datasets, scenarios, executions)
- Rendered frames on disk: `/home/du/ros2-humble/datasets/<dataset_id>/<sensor_id>/`
- Scenario recordings: `run_data/scenario_recordings/*.log`

## Runtime Environment

- Host IP: `192.168.110.151`
- CARLA 0.9.16 in `carla-offscreen` container (GPU rendering, port 2000)
- `ros2-dev` container: Python 3.10 + carla package, network_mode: host
- Volume mounts: `/home/du/ros2-humble/src` → `/ros2_ws/src`, datasets shared via `/home/du/ros2-humble/datasets` → `/ros2_ws/datasets`
- CARLA recordings mount: host `run_data/scenario_recordings/` → container `/recordings/`
- Node.js: `/home/du/.local/share/simchip-node/node-v22.22.2-linux-x64/bin`
- Online playback: `mpv` installed on host, GPU-accelerated fullscreen

## Key Rendering Flow

1. User configures pipeline (scene_replay + sensors + env_override) in editor
2. Clicks "离线生成" → `POST /pipelines/:id/execute` with mode=offline_render
3. Backend extracts scenario log, sensor configs, weather preset from pipeline nodes
4. Builds a Python script and runs it via `docker exec ros2-dev python3 -c <script>`
5. Script: replay .log → `set_replayer_ignore_hero(True)` → hero gets physics+autopilot → attach sensors → render loop → save frames
6. Dataset status tracked in SQLite, progress shown via file counting on disk

## Key Conventions

- Python 3.10+, no strict linter enforced currently
- Frontend: React 19, Vite, TailwindCSS, Zustand, React Flow (XY Flow)
- API changes: update route → update frontend api module → rebuild frontend
- CARLA paths: host paths must be converted to container paths before passing to CARLA server
- Traffic Manager port: use 8010 (port 8000 is taken by API server)
