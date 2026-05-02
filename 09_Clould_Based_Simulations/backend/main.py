"""
DWSIM Cloud Simulation — FastAPI backend
All routes are generic. Adding a new model never requires editing this file.
"""

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from registry import discover_models, load_runner

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── App lifecycle ───────────────────────────────────────────────────────────────

REGISTRY: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global REGISTRY
    logger.info("Scanning models directory…")
    REGISTRY = discover_models()
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="DWSIM Cloud Simulation API",
    description="Generic simulation runner — drop a model folder in /models to add a new simulation.",
    version="1.0.0",
    lifespan=lifespan,
)


# ── CORS (allow all origins for local dev; restrict in production) ──────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request timing middleware ───────────────────────────────────────────────────

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed:.1f}"
    return response


# ── Health check ────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health():
    return {
        "status": "ok",
        "models_loaded": len(REGISTRY),
    }


# ── Model registry endpoints ────────────────────────────────────────────────────

@app.get("/models", tags=["models"])
def list_models():
    """
    Returns all registered models — name, description, tags, id.
    Used by the frontend to populate the left panel.
    """
    return [
        {**entry["meta"], "has_flowsheet": entry["has_flowsheet"]}
        for entry in REGISTRY.values()
    ]


@app.get("/models/{model_id}", tags=["models"])
def get_model_schema(model_id: str):
    """
    Returns the full input/output schema for a model.
    The frontend uses this to dynamically build the input form.
    """
    _require_model(model_id)
    return {
        "meta":   REGISTRY[model_id]["meta"],
        "schema": REGISTRY[model_id]["schema"],
    }


@app.get("/models/{model_id}/flowsheet", tags=["models"])
def get_flowsheet(model_id: str):
    """
    Serves the flowsheet PNG for a model.
    Returns 404 if the model has no flowsheet image.
    """
    _require_model(model_id)
    folder = REGISTRY[model_id]["folder"]
    img_path: Path = folder / "flowsheet.png"
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="No flowsheet image for this model.")
    return FileResponse(img_path, media_type="image/png")


# ── Simulation runner ───────────────────────────────────────────────────────────

@app.post("/run/{model_id}", tags=["simulation"])
def run_simulation(model_id: str, inputs: dict[str, Any]):
    """
    Runs a simulation for the given model_id.

    Body: flat JSON object matching the model's schema inputs.
    Example: { "mass_flow": 1.0, "temperature": 300, "pressure": 101325, "outlet_pressure": 301325 }

    Returns: flat JSON object with output values defined in schema.
    """
    _require_model(model_id)
    schema = REGISTRY[model_id]["schema"]

    # Validate inputs against schema
    errors = _validate_inputs(inputs, schema["inputs"])
    if errors:
        raise HTTPException(status_code=422, detail={"validation_errors": errors})

    # Coerce types according to schema
    coerced = _coerce_inputs(inputs, schema["inputs"])

    # Load and call the runner
    try:
        runner = load_runner(model_id, REGISTRY)
    except (RuntimeError, ValueError) as e:
        logger.error(f"Runner load failed for '{model_id}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"Running simulation: {model_id} | inputs={coerced}")
    start = time.perf_counter()

    try:
        result = runner(coerced)
    except Exception as e:
        logger.exception(f"Simulation failed: {model_id}")
        raise HTTPException(status_code=500, detail=f"Simulation error: {str(e)}")

    elapsed = (time.perf_counter() - start) * 1000
    logger.info(f"Simulation complete: {model_id} | {elapsed:.0f}ms")

    return {
        "model_id":     model_id,
        "inputs":       coerced,
        "outputs":      result,
        "duration_ms":  round(elapsed, 1),
    }


# ── Reload registry without restart (dev convenience) ──────────────────────────

@app.post("/admin/reload", tags=["system"])
def reload_registry():
    """
    Re-scans the /models directory and refreshes the registry.
    Useful during development when adding new models without restarting.
    """
    global REGISTRY
    REGISTRY = discover_models()
    return {"status": "reloaded", "models_loaded": len(REGISTRY)}


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _require_model(model_id: str):
    if model_id not in REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found. Available: {list(REGISTRY.keys())}",
        )


def _validate_inputs(inputs: dict, schema_inputs: list) -> list[str]:
    errors = []
    required_ids = {f["id"] for f in schema_inputs}
    for field_id in required_ids:
        if field_id not in inputs:
            errors.append(f"Missing required input: '{field_id}'")
    for key in inputs:
        if key not in required_ids:
            errors.append(f"Unknown input field: '{key}'")
    return errors


TYPE_MAP = {"float": float, "int": int, "str": str, "bool": bool}

def _coerce_inputs(inputs: dict, schema_inputs: list) -> dict:
    coerced = {}
    for field in schema_inputs:
        fid   = field["id"]
        ftype = TYPE_MAP.get(field.get("type", "float"), float)
        try:
            coerced[fid] = ftype(inputs[fid])
        except (ValueError, TypeError):
            coerced[fid] = inputs[fid]  # leave as-is, runner will surface the error
    return coerced


# ── Serve frontend (must be last — catches all unmatched routes) ────────────────

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")