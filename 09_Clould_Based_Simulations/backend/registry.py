"""
Model registry — scans the /models directory on startup.
Never needs to be edited when new models are added.
"""

import json
import importlib.util
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent.parent / "models"

REQUIRED_FILES = {"meta.json", "schema.json", "runner.py"}


def _validate_meta(meta: dict, folder: Path) -> list[str]:
    errors = []
    for field in ("id", "name", "description"):
        if field not in meta:
            errors.append(f"meta.json missing required field: '{field}'")
    return errors


def _validate_schema(schema: dict, folder: Path) -> list[str]:
    errors = []
    if "inputs" not in schema or not isinstance(schema["inputs"], list):
        errors.append("schema.json must have an 'inputs' list")
    if "outputs" not in schema or not isinstance(schema["outputs"], list):
        errors.append("schema.json must have an 'outputs' list")
    for inp in schema.get("inputs", []):
        for f in ("id", "label", "type"):
            if f not in inp:
                errors.append(f"Input field missing '{f}': {inp}")
    return errors


def discover_models() -> dict:
    """
    Walk MODELS_DIR, load every valid model folder, return a registry dict.
    Registry shape: { model_id: { meta, schema, folder } }
    """
    if not MODELS_DIR.exists():
        logger.warning(f"Models directory not found: {MODELS_DIR}")
        return {}

    registry = {}

    for folder in sorted(MODELS_DIR.iterdir()):
        if not folder.is_dir():
            continue

        present = {f.name for f in folder.iterdir()}
        missing = REQUIRED_FILES - present
        if missing:
            logger.warning(f"Skipping '{folder.name}': missing {missing}")
            continue

        try:
            meta   = json.loads((folder / "meta.json").read_text())
            schema = json.loads((folder / "schema.json").read_text())
        except json.JSONDecodeError as e:
            logger.error(f"Skipping '{folder.name}': JSON parse error — {e}")
            continue

        meta_errors   = _validate_meta(meta, folder)
        schema_errors = _validate_schema(schema, folder)
        all_errors    = meta_errors + schema_errors

        if all_errors:
            logger.error(f"Skipping '{folder.name}': validation errors:")
            for err in all_errors:
                logger.error(f"  • {err}")
            continue

        model_id = meta["id"]

        if model_id in registry:
            logger.error(
                f"Duplicate model id '{model_id}' in '{folder.name}', "
                f"already registered from '{registry[model_id]['folder'].name}'. Skipping."
            )
            continue

        # Optional assets
        has_flowsheet = (folder / "flowsheet.png").exists()

        registry[model_id] = {
            "meta":          meta,
            "schema":        schema,
            "folder":        folder,
            "has_flowsheet": has_flowsheet,
        }

        logger.info(f"Registered model: '{model_id}' ({meta['name']})")

    logger.info(f"Registry ready — {len(registry)} model(s) loaded.")
    return registry


def load_runner(model_id: str, registry: dict):
    """
    Dynamically import runner.py for the given model_id and return its run() function.
    Raises ValueError if the runner doesn't expose run().
    """
    folder = registry[model_id]["folder"]
    runner_path = folder / "runner.py"

    spec = importlib.util.spec_from_file_location(f"runner_{model_id}", runner_path)
    mod  = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        raise RuntimeError(f"Failed to load runner for '{model_id}': {e}") from e

    if not hasattr(mod, "run") or not callable(mod.run):
        raise ValueError(
            f"runner.py for '{model_id}' must expose a callable named 'run(inputs: dict) -> dict'"
        )

    return mod.run