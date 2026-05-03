# DWSIM Cloud Simulation — System Documentation

> A scaleable, container-native platform for running DWSIM process simulations through a browser-based UI backed by a generic REST API.

---

## Table of Contents

1. [Introduction](#introduction)
2. [System Architecture](#system-architecture)
3. [Folder Structure](#folder-structure)
4. [Component Deep Dive](#component-deep-dive)
5. [Model Plugin System](#model-plugin-system)
6. [API Reference](#api-reference)
7. [Frontend Features](#frontend-features)
8. [Tips & Tricks](#tips--tricks)
9. [Quick Command Reference](#quick-command-reference)
10. [Adding a New Model](#adding-a-new-model)
11. [Cloud Deployment Notes](#cloud-deployment-notes)

---

## Introduction

DWSIM Cloud Simulation wraps DWSIM — a powerful open-source process simulator — inside a web-accessible platform that runs entirely in a Docker container. Instead of operating the DWSIM desktop GUI, engineers interact with simulation models through a clean browser UI: setting stream conditions, running calculations, and reading results — all without touching the underlying Python or .NET code.

**Why this architecture exists:**

- **DWSIM is powerful but desktop-bound.** This platform makes it browser-accessible without changing a single DWSIM file.
- **Teams need shared access.** One container can serve multiple engineers simultaneously once hosted on Azure or AWS.
- **Models grow over time.** The plugin pattern means adding a heat exchanger, distillation column, or reactor simulation tomorrow requires zero changes to the platform code — just a new folder.
- **Container portability.** The entire stack — DWSIM runtime, .NET CLR, Python automation, API, and frontend — ships as one Docker image. What runs locally runs identically in the cloud.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Docker Container                                                   │
│                                                                     │
│  ┌──────────────┐    REST/JSON     ┌──────────────────────────────┐ │
│  │   Browser    │ ◄─────────────► │   FastAPI Backend            │ │
│  │  (React UI)  │                 │   main.py  port 8001         │ │
│  └──────────────┘                 └──────────────┬───────────────┘ │
│                                                  │                 │
│                                                  ▼                 │
│                                   ┌──────────────────────────────┐ │
│                                   │   Model Registry             │ │
│                                   │   registry.py                │ │
│                                   │   Auto-scans /models on boot │ │
│                                   └──────────────┬───────────────┘ │
│                                                  │                 │
│                    ┌─────────────────────────────┼──────────────┐  │
│                    ▼                             ▼              ▼  │
│          ┌──────────────────┐   ┌──────────────────┐   ┌──────┐   │
│          │ 01_water_pump/   │   │ 02_hex/          │   │ .../ │   │
│          │  meta.json       │   │  meta.json       │   │      │   │
│          │  schema.json     │   │  schema.json     │   │      │   │
│          │  runner.py       │   │  runner.py       │   │      │   │
│          │  model.dwxmz     │   │  model.dwxmz     │   │      │   │
│          │  flowsheet.png   │   │  flowsheet.png   │   │      │   │
│          └────────┬─────────┘   └──────────────────┘   └──────┘   │
│                   │                                                 │
│                   ▼                                                 │
│          ┌──────────────────┐                                       │
│          │  DWSIM Engine    │                                       │
│          │  Python + .NET   │                                       │
│          │  CLR via pythonnet│                                      │
│          └──────────────────┘                                       │
└─────────────────────────────────────────────────────────────────────┘
```

**Data flow for a simulation request:**

```
User clicks ▶ Simulate
    │
    ▼
Browser sends POST /run/01_water_pump  { mass_flow: 1.0, ... }
    │
    ▼
main.py validates inputs against schema.json
    │
    ▼
registry.py dynamically imports runner.py for that model
    │
    ▼
runner.py loads model.dwxmz into DWSIM via pythonnet / .NET CLR
    │
    ▼
DWSIM solves the flowsheet
    │
    ▼
runner.py extracts results and returns { mass_flow_out, temp_out, ... }
    │
    ▼
main.py wraps response: { model_id, inputs, outputs, duration_ms }
    │
    ▼
Browser receives JSON → renders results panel + flowchart labels
```

---

## Folder Structure

```
09_Clould_Based_Simulations/
│
├── backend/
│   ├── main.py              # FastAPI app — all API routes (never edit)
│   ├── registry.py          # Model auto-scanner (never edit)
│   └── requirements.txt     # fastapi, uvicorn, python-multipart
│
├── frontend/
│   └── index.html           # Single-file SPA — pan/zoom canvas (never edit)
│
└── models/                  # Drop a new folder here = new model
    ├── 01_water_pump/
    │   ├── meta.json         # Display name, description, tags
    │   ├── schema.json       # Input/output field definitions + flowchart layout
    │   ├── runner.py         # Simulation logic — only file you write per model
    │   ├── model.dwxmz       # DWSIM flowsheet file
    │   └── flowsheet.png     # Flowsheet screenshot (optional)
    │
    ├── 02_heat_exchanger/    # Future model — same structure
    └── 03_distillation/      # Future model — same structure
```

> **The golden rule:** `main.py`, `registry.py`, and `index.html` are written once and never touched again. All new work lives inside a new folder under `models/`.

---

## Component Deep Dive

### `backend/registry.py`

Runs once at server startup. Walks the `models/` directory and builds a registry dict keyed by `model_id`. For each folder it:

1. Checks that `meta.json`, `schema.json`, and `runner.py` are all present
2. Validates `meta.json` has `id`, `name`, `description`
3. Validates `schema.json` has `inputs` and `outputs` arrays
4. Detects whether a `flowsheet.png` exists
5. Logs warnings for skipped/invalid folders rather than crashing

If you add a model while the server is running, hit `POST /admin/reload` to re-scan without restarting.

---

### `backend/main.py`

A FastAPI application with five routes:

| Route | Method | Purpose |
|---|---|---|
| `/health` | GET | Server liveness + model count |
| `/models` | GET | List all registered models |
| `/models/{id}` | GET | Full schema + metadata for a model |
| `/models/{id}/flowsheet` | GET | Serve flowsheet PNG |
| `/run/{id}` | POST | Validate inputs and run simulation |
| `/admin/reload` | POST | Re-scan models directory |

The `/run/{id}` endpoint:
- Validates every required input is present
- Rejects unknown input fields
- Coerces string inputs to the correct type (`float`, `int`, etc.)
- Dynamically imports `runner.py` and calls `run(inputs)`
- Returns `{ model_id, inputs, outputs, duration_ms }`

---

### `models/*/schema.json`

The schema file drives both the API validation and the frontend UI generation. It has three top-level keys:

**`flowchart`** — describes the SVG canvas layout:
```json
{
  "flowchart": {
    "nodes": [
      { "id": "stream_in",  "type": "stream",    "label": "Stream 1" },
      { "id": "pump",       "type": "equipment", "label": "PUMP-1"   },
      { "id": "stream_out", "type": "stream",    "label": "Stream 2" }
    ],
    "connections": [
      { "from": "stream_in", "to": "pump"       },
      { "from": "pump",      "to": "stream_out" }
    ]
  }
}
```

Node types currently supported: `stream` (circle) and `equipment` (hexagon).

**`inputs`** — each field requires `id`, `label`, `type`, `unit`, and `node`:
```json
{
  "id": "mass_flow",
  "label": "Inlet mass flow rate",
  "unit": "kg/s",
  "type": "float",
  "default": 1.0,
  "min": 0.01,
  "max": 1000.0,
  "description": "...",
  "node": "stream_in"
}
```

**`outputs`** — same structure minus `default`/`min`/`max`, with a `node` to attach result labels on the canvas.

---

### `models/*/runner.py`

The only file you write per model. Must expose exactly one function:

```python
def run(inputs: dict) -> dict:
    ...
```

- `inputs` is a flat dict with keys matching schema `inputs[].id`, already type-coerced
- Return a flat dict with keys matching schema `outputs[].id`
- Any exception raised here is caught by the API and returned as a 500 error
- A private key `_solver_errors` can optionally be returned for diagnostics

---

## Model Plugin System

The plugin system means **adding a new DWSIM model to the platform takes roughly 30 minutes** and requires zero changes to any existing file.

**Contract between platform and model:**

```
Platform provides:   Validated, type-coerced inputs dict
Model provides:      run(inputs) function returning outputs dict
Schema provides:     Field definitions that glue both sides together
```

**Category grouping** in the left panel is driven by the first tag in `meta.json`:

```json
{ "tags": ["pump", "fluid mechanics", "water"] }
```

The first tag (`"pump"`) becomes the folder category in the UI. Add `"hex"` as the first tag on a heat exchanger model and it appears under a new **HEX** category automatically.

---

## API Reference

### `GET /health`
```json
{ "status": "ok", "models_loaded": 1 }
```

### `GET /models`
```json
[
  {
    "id": "01_water_pump",
    "name": "Water Pump",
    "description": "...",
    "tags": ["pump", "fluid mechanics", "water"],
    "version": "1.0",
    "has_flowsheet": false
  }
]
```

### `GET /models/{model_id}`
Returns the full `meta` + `schema` object including flowchart layout, all input field definitions, and all output field definitions.

### `POST /run/{model_id}`

**Request body:**
```json
{
  "mass_flow": 1.0,
  "temperature": 300,
  "pressure": 101325,
  "outlet_pressure": 301325
}
```

**Success response `200`:**
```json
{
  "model_id": "01_water_pump",
  "inputs": { "mass_flow": 1.0, "temperature": 300.0, "pressure": 101325.0, "outlet_pressure": 301325.0 },
  "outputs": {
    "mass_flow_out": 1.0,
    "temperature_out": 300.02,
    "pressure_out": 301325.0,
    "power_consumed": 0.2676,
    "_solver_errors": 0
  },
  "duration_ms": 6278.7
}
```

**Validation error `422`:**
```json
{
  "detail": {
    "validation_errors": ["Missing required input: 'pressure'", "Missing required input: 'outlet_pressure'"]
  }
}
```

### `POST /admin/reload`
Re-scans the `models/` directory without server restart.
```json
{ "status": "reloaded", "models_loaded": 2 }
```

---

## Frontend Features

### Canvas navigation

| Action | Control |
|---|---|
| **Zoom in/out** | Mouse wheel (zooms toward cursor position) |
| **Pan** | Click and drag on the canvas background |
| **Fit to view** | `⊡ FIT` button in toolbar, `⊡` zoom button, or press `F` |
| **Zoom in** | `+` button or `+` / `=` key |
| **Zoom out** | `−` button or `−` key |
| **Touch pan** | Single finger drag |

### Flowchart interaction

- **Click a stream node** → popup with that stream's input fields (temperature, pressure, mass flow)
- **Click an equipment node** → popup with that equipment's parameters (outlet pressure, efficiency, etc.)
- **Apply** → values update on the canvas sublabels immediately
- **▶ Simulate** → sends all current input values to the API
- After simulation, **green result labels** appear on the outlet stream and equipment nodes

### Left panel

- Models grouped by first tag as collapsible category folders
- Click any model to load its flowchart on the canvas
- Additional tags shown as small chips under the model name
- Active model highlighted with accent border

---

## Tips & Tricks

### Workflow tips

- **Always start with the lightweight curl tests** (`/health`, `/models`) before running a simulation. This confirms the API is up and the model registered before invoking the heavy DWSIM engine.

- **Use `POST /admin/reload`** while developing a new model. You can add or edit the model folder and reload the registry without restarting uvicorn — much faster iteration.

- **Add `_solver_errors` to your runner return dict.** DWSIM can "succeed" with internal solver errors. Returning `"_solver_errors": errors.Count` lets you spot these in the API response without crashing.

- **Keep `runner.py` stateless.** Each call to `run()` should be independent. Do not store state in module-level variables (other than the DWSIM bootstrap cache) — this makes the runner safe for future async or multi-worker deployments.

- **Take a flowsheet screenshot** and save it as `flowsheet.png` in the model folder. The API serves it at `GET /models/{id}/flowsheet`. The frontend will display it in a future update.

### Schema design tips

- **Use descriptive `label` values.** The label appears verbatim in the popup form and results panel — `"Inlet temperature"` is clearer than `"T_in"`.
- **Always set `default`, `min`, and `max`.** The frontend pre-fills inputs with `default` and the API will gain range validation. Models without defaults force users to know the expected range.
- **Group related inputs on the same node.** All three inlet stream conditions (`mass_flow`, `temperature`, `pressure`) belong on `stream_in` — users click once and see all three together.

### Performance tips

- **DWSIM loads the .NET CLR on the first simulation request** (~5–8 seconds). Subsequent requests are faster. This is expected behaviour with pythonnet.
- **Add a module-level cache to `runner.py`** if you need to run many simulations quickly — load the DWSIM assemblies once and reuse them across calls.
- **The solve time is returned in `duration_ms`** in every API response. Use this to benchmark model complexity and identify slow solvers.

### Debugging tips

- **Check the uvicorn terminal** when a simulation hangs. Any DWSIM solver errors or Python exceptions appear there even if the API returns a 500.
- **Test input validation first.** Send an incomplete body to `POST /run/{id}` — if validation errors come back cleanly, your schema is wired up correctly.
- **Use `--loop asyncio`** when starting uvicorn inside the DWSIM container. The default event loop conflicts with the .NET CLR loaded by pythonnet.

---

## Quick Command Reference

### Starting the server

```bash
# Navigate to backend
cd /workspace/09_Clould_Based_Simulations/backend

# Start the server (always use --loop asyncio in this container)
uvicorn main:app --host 0.0.0.0 --port 8001 --loop asyncio

# With auto-reload during development (slower startup)
uvicorn main:app --host 0.0.0.0 --port 8001 --loop asyncio --reload
```

### Process management

```bash
# Check if uvicorn is running
ps aux | grep uvicorn

# Kill uvicorn
pkill -f uvicorn

# Kill a specific port
kill -9 $(ss -tlnp | grep 8001 | awk '{print $6}' | grep -oP 'pid=\K[0-9]+')
```

### API testing with curl

```bash
# Health check
curl --http1.1 http://localhost:8001/health

# List all models
curl --http1.1 http://localhost:8001/models

# Get model schema
curl --http1.1 http://localhost:8001/models/01_water_pump

# Run a simulation
curl --http1.1 -X POST http://localhost:8001/run/01_water_pump \
  -H "Content-Type: application/json" \
  -d '{"mass_flow": 1.0, "temperature": 300, "pressure": 101325, "outlet_pressure": 301325}'

# Test validation (should return 422)
curl --http1.1 -X POST http://localhost:8001/run/01_water_pump \
  -H "Content-Type: application/json" \
  -d '{"mass_flow": 1.0}'

# Reload model registry without restart
curl --http1.1 -X POST http://localhost:8001/admin/reload
```

### Interactive API docs

```
# Swagger UI (test all endpoints in the browser)
http://localhost:8001/docs

# ReDoc (read-only API reference)
http://localhost:8001/redoc
```

### Install dependencies

```bash
# Backend dependencies
pip install fastapi uvicorn[standard] python-multipart --break-system-packages

# Install process management tools
apt-get install -y psmisc     # gives you fuser, killall, pstree
apt-get install -y lsof       # gives you lsof
```

### Validate JSON files

```bash
# Validate schema.json
python3 -c "import json; json.load(open('models/01_water_pump/schema.json')); print('valid')"

# Validate meta.json
python3 -c "import json; json.load(open('models/01_water_pump/meta.json')); print('valid')"

# Test registry scan manually
cd backend && python3 -c "
from registry import discover_models
r = discover_models()
for mid, e in r.items():
    print(f'{mid}: {e[\"meta\"][\"name\"]} — inputs: {[f[\"id\"] for f in e[\"schema\"][\"inputs\"]]}')
"
```

### Check system resources

```bash
# Memory available (DWSIM needs ~2-3 GB)
free -h

# Disk space
df -h

# Running processes + memory usage
ps aux --sort=-%mem | head -15
```

---

## Adding a New Model

Step-by-step checklist for adding a new DWSIM model to the platform:

```
□ 1. Create the folder
      mkdir models/02_heat_exchanger

□ 2. Write meta.json
      {
        "id": "02_heat_exchanger",
        "name": "Shell & Tube Heat Exchanger",
        "description": "...",
        "tags": ["hex", "heat transfer"],
        "version": "1.0"
      }

□ 3. Write schema.json
      - Define flowchart nodes and connections
      - Assign "node" to every input and output field
      - Set defaults, min, max for all inputs

□ 4. Write runner.py
      - Import DWSIM, load the .dwxmz file
      - def run(inputs: dict) -> dict
      - Push inputs → solve → pull outputs → return dict

□ 5. Copy the .dwxmz file
      cp path/to/model.dwxmz models/02_heat_exchanger/model.dwxmz

□ 6. (Optional) Add a flowsheet screenshot
      cp screenshot.png models/02_heat_exchanger/flowsheet.png

□ 7. Reload the registry
      curl --http1.1 -X POST http://localhost:8001/admin/reload

□ 8. Verify it registered
      curl --http1.1 http://localhost:8001/models

□ 9. Test the schema endpoint
      curl --http1.1 http://localhost:8001/models/02_heat_exchanger

□ 10. Run a test simulation
       curl --http1.1 -X POST http://localhost:8001/run/02_heat_exchanger \
         -H "Content-Type: application/json" \
         -d '{ ...your test inputs... }'
```

---

## Cloud Deployment Notes

The container is already cloud-ready. When you're ready to deploy:

**Azure Container Instances / Azure Container Apps:**
```bash
# Build and tag
docker build -t dwsim-cloud .
docker tag dwsim-cloud <registry>.azurecr.io/dwsim-cloud:latest

# Push
az acr login --name <registry>
docker push <registry>.azurecr.io/dwsim-cloud:latest
```

**AWS ECS / Fargate:**
```bash
aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
docker tag dwsim-cloud <account>.dkr.ecr.<region>.amazonaws.com/dwsim-cloud:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/dwsim-cloud:latest
```

**Things to update for production:**

| Item | Change |
|---|---|
| CORS in `main.py` | Replace `allow_origins=["*"]` with your actual frontend domain |
| Port | Change `8001` to `80` or `443` behind a reverse proxy |
| `API` constant in `index.html` | Change `http://localhost:8001` to your deployed API URL |
| Memory allocation | Set container memory limit to at least 3 GB for DWSIM |
| `/admin/reload` | Add authentication before exposing this in production |

---

*Documentation last updated for DWSIM Cloud Simulation v1.0*
*Stack: DWSIM · Python 3 · pythonnet · FastAPI · uvicorn · vanilla JS*