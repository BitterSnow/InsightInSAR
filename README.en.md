**Language / 语言:** [简体中文](README.md) | **English**

## Insight InSAR

**Website:** [https://www.insightinsar.com/](https://www.insightinsar.com/)

An all-in-one deformation monitoring system on **Windows desktop + WSL InSAR processing**: the local desktop client (PySide6) and backend (FastAPI + Celery + Redis) run on Windows with **no web frontend**; all InSAR computation (ISCE2 / MintPy) runs only inside WSL—no need to install or build ISCE2 on Windows.

### Key Features

- **Local desktop app**: PySide6 UI for task management, ROI selection, product browsing, and parameter configuration.
- **Non-web frontend**: The desktop client is the entry point (not a browser); the backend is a local API and async job scheduler.
- **Backend job scheduling**: FastAPI REST API, Celery for long-running tasks, Redis as broker/backend.
- **InSAR via WSL only**: S1 import, topsStack, MintPy, etc. are invoked in WSL through `wsl`; desktop and backend only bridge parameters and progress.
- **Packaged deployment**: Single-machine Windows delivery with the “InSAR WSL Deploy Wizard” to import WSL images and config; runs without Docker.
- **Logging & monitoring**: Task progress and logs on disk; view status and errors in the desktop app.

### Tech Stack

- **Desktop (`desktop/`)**
  - PySide6 (Qt for Python)
  - Qt Widgets / QGraphicsView for map and image visualization
  - Embedded Matplotlib / charts for time series and profiles

- **Backend**
  - FastAPI: local REST API for the desktop (submit tasks, query status, fetch results)
  - Celery: async queue (dispatches InSAR steps to WSL)
  - Redis: Celery broker / backend

- **InSAR engine (WSL only)**
  - ISCE2: Python API inside WSL (Ubuntu, etc.)
  - MintPy: time-series deformation analysis and products in WSL
  - Bridge: `backend.services.wsl_runner` runs `wsl` and `backend.scripts.run_*_wsl` entry points

### Directory Layout (brief)

```
InsightInSAR/
├── desktop/              # PySide6 desktop source
├── config/               # Backend and pipeline config
├── scripts/              # Dev / deploy / ops scripts
├── packaging/            # Windows packaging and install scripts
├── build/                # Build intermediates (safe to clean)
├── dist/                 # Packaged outputs (installers, binaries)
├── manual/               # Operation manual (PDF)
├── logs/                 # Runtime logs
├── .venv/                # Local Python virtualenv
└── README.md             # Chinese readme (default on GitHub)
```

Install and offline delivery: `packaging/README.md`. Operation manual: `manual/Insight_InSAR_Operation_Manual.pdf`.

### Quick Start (development)

1. **Requirements**
   - Windows 10/11 with WSL 2 enabled
   - Python 3.10+ on Windows for desktop and backend (**no** ISCE2 on Windows)
   - ISCE2 and MintPy configured in WSL with `INSAR_USE_WSL=1`, `INSAR_WSL_PROJECT_ROOT`, etc. (see `packaging/README.md`; use the WSL deploy wizard or `scripts/start_desktop_wsl.bat`)

2. **Create and activate environment**

   ```bash
   conda create -n insight-insar python=3.10
   conda activate insight-insar
   git clone https://github.com/BitterSnow/InsightInSAR.git
   cd InsightInSAR
   ```

3. **Install dependencies**

   ```bash
   pip install -r packaging/requirements.txt
   ```

4. **Run (WSL mode)**

   - Recommended: `scripts/start_desktop_wsl.bat` (loads WSL config and starts the desktop), or set `INSAR_USE_WSL=1` and `INSAR_WSL_PROJECT_ROOT` before starting backend and desktop.
   - FastAPI: `uvicorn backend.app.main:app --reload`
   - Celery worker: `celery -A backend.app.celery_app worker -l info`
   - Desktop: `python -m desktop`

### Architecture

- Desktop talks to local FastAPI over HTTP: submit jobs, poll status, get result paths and metadata.
- FastAPI hands InSAR work to Celery; Celery uses **wsl_runner** in WSL for `run_s1_extract_wsl`, `run_stack_wsl`, `run_mintpy_wsl`, etc.—**no direct ISCE2/MintPy on Windows**.
- Data and work dirs may use Windows paths; the backend converts paths for WSL before invocation; results remain accessible from Windows.

### Community

Test & discussion QQ group: **678738326**

### License

MIT
