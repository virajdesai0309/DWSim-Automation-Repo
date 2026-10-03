"""
Shared DWSIM runtime for every model runner.

DWSIM 10 ships its headless automation assemblies (DWSIM.Automation,
Automation3) in the dwsim-mcp package under /opt/dwsim-mcp/, built for
.NET 10. pythonnet needs a shared .NET 10 runtime to host them; the bundled
runtime inside /opt/dwsim-mcp is self-contained and cannot be borrowed.

Environment overrides:
    DWSIM_PATH   folder holding DWSIM.Automation.dll   (default /opt/dwsim-mcp/)
    DOTNET_ROOT  folder holding shared/Microsoft.NETCore.App/10.x
"""

import json
import os
import tempfile

os.environ.setdefault("PYTHONNET_RUNTIME", "coreclr")
os.environ.setdefault("DOTNET_SYSTEM_DRAWING_USE_GDIPLUS", "1")

DWSIM_PATH = os.path.join(os.environ.get("DWSIM_PATH", "/opt/dwsim-mcp/"), "")
DOTNET_ROOT = os.environ.get("DOTNET_ROOT", "/usr/share/dotnet")
DOTNET_TFM = "net10.0"

ASSEMBLIES = [
    "CapeOpen", "DWSIM.Automation", "DWSIM.Interfaces",
    "DWSIM.GlobalSettings", "DWSIM.SharedClasses",
    "DWSIM.Thermodynamics", "DWSIM.UnitOperations",
    "DWSIM.Inspector", "System.Buffers",
]
OPTIONAL_ASSEMBLIES = ["DWSIM.Thermodynamics.ThermoC"]  # gone in DWSIM 10

_cache = None


def _load_clr():
    """Host .NET 10 in-process. pythonnet's default probe picks the newest
    runtime it can find, which may be .NET 8, so pin it via a runtimeconfig."""
    from clr_loader import get_coreclr
    from pythonnet import set_runtime

    cfg = os.path.join(tempfile.mkdtemp(prefix="dwsim-rc-"), "runtimeconfig.json")
    with open(cfg, "w") as f:
        json.dump({"runtimeOptions": {
            "tfm": DOTNET_TFM,
            "framework": {"name": "Microsoft.NETCore.App", "version": "10.0.0"},
        }}, f)
    set_runtime(get_coreclr(runtime_config=cfg, dotnet_root=DOTNET_ROOT))


def bootstrap():
    """Load DWSIM once per process; returns (Automation3, Settings)."""
    global _cache
    if _cache is not None:
        return _cache

    _load_clr()
    import clr
    from System.IO import Directory
    Directory.SetCurrentDirectory(DWSIM_PATH)

    for dll in ASSEMBLIES:
        clr.AddReference(f"{DWSIM_PATH}{dll}.dll")
    for dll in OPTIONAL_ASSEMBLIES:
        if os.path.exists(f"{DWSIM_PATH}{dll}.dll"):
            clr.AddReference(f"{DWSIM_PATH}{dll}.dll")

    from DWSIM.Automation import Automation3
    from DWSIM.GlobalSettings import Settings

    _cache = (Automation3, Settings)
    return _cache


def solve(interf, sim, Settings):
    """Solve the flowsheet; raise with DWSIM's own messages if it fails."""
    Settings.SolverMode = 0
    errors = interf.CalculateFlowsheet4(sim)
    msgs = [str(getattr(e, "Message", e)) for e in errors] if errors else []
    if msgs:
        raise RuntimeError("; ".join(msgs))
