"""
Record live API responses into frontend/demo/ so the static frontend can
show real results when the backend is asleep or offline.

Usage (backend running locally):
    python scripts/export_demo.py                 # uses http://localhost:8001
    python scripts/export_demo.py http://host:port

Re-run whenever a model is added or changed.
"""

import json
import sys
import urllib.request
from pathlib import Path

API = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001").rstrip("/")
OUT = Path(__file__).resolve().parent.parent / "frontend" / "demo"


def call(path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def write(rel: str, obj):
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")
    print(f"  wrote {path.relative_to(OUT.parent.parent)}")


def main():
    models = call("/models")
    write("models.json", models)
    for m in models:
        model_id = m["id"]
        detail = call(f"/models/{model_id}")
        write(f"models/{model_id}.json", detail)
        defaults = {f["id"]: f.get("default") for f in detail["schema"]["inputs"]}
        print(f"  running {model_id} with defaults…")
        run = call(f"/run/{model_id}", defaults)
        errors = run["outputs"].get("_solver_errors", 0)
        if errors:
            print(f"  WARNING: {model_id} reported {errors} solver error(s)")
        write(f"runs/{model_id}.json", run)


if __name__ == "__main__":
    main()
