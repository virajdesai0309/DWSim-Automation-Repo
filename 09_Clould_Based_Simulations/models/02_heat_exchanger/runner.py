"""
Heat Exchanger runner.
Contract: expose run(inputs: dict) -> dict
The backend calls this; never import this file directly.
"""

import os
from pathlib import Path

# ── DWSIM bootstrap (same pattern as original script) ──────────────────────────

os.environ["PYTHONNET_RUNTIME"] = "coreclr"
os.environ["DOTNET_SYSTEM_DRAWING_USE_GDIPLUS"] = "1"

DWSIM_PATH = "/usr/local/lib/dwsim/"
MODEL_FILE = str(Path(__file__).parent / "model.dwxmz")

_dwsim_cache = None
def _bootstrap_dwsim():
    global _dwsim_cache
    if _dwsim_cache is not None:
        return _dwsim_cache
    """Load DWSIM assemblies. Called once per runner invocation."""
    import clr
    from pythonnet import load as pynet_load

    pynet_load("coreclr")

    try:
        from System.IO import Directory
        Directory.SetCurrentDirectory(DWSIM_PATH)
    except Exception:
        os.chdir(DWSIM_PATH)

    for dll in [
        "CapeOpen", "DWSIM.Automation", "DWSIM.Interfaces",
        "DWSIM.GlobalSettings", "DWSIM.SharedClasses",
        "DWSIM.Thermodynamics", "DWSIM.UnitOperations",
        "DWSIM.Inspector", "System.Buffers",
        "DWSIM.Thermodynamics.ThermoC",
    ]:
        clr.AddReference(f"{DWSIM_PATH}{dll}.dll")

    from DWSIM.Automation import Automation3
    from DWSIM.GlobalSettings import Settings
    from System.IO import Path as DotNetPath
    from System import Environment

    _dwsim_cache = (Automation3, Settings, DotNetPath, Environment)
    return _dwsim_cache


def _solve(interf, sim, Settings):
    """Solve the flowsheet; raise with DWSIM's own messages if it fails."""
    Settings.SolverMode = 0
    errors = interf.CalculateFlowsheet4(sim)
    msgs = [str(getattr(e, "Message", e)) for e in errors] if errors else []
    if msgs:
        raise RuntimeError("; ".join(msgs))


# ── Public contract ─────────────────────────────────────────────────────────────

def run(inputs: dict) -> dict:
    """
    Runs the shell-and-tube heat exchanger (counter-current, rating mode:
    DWSIM solves both outlet temperatures from area and U).

    Hot side:  stream 1 -> 2, water with 1 % methanol
    Cold side: stream 3 -> 4, methanol
    Property package: NRTL
    """
    if inputs["hot_temperature"] <= inputs["cold_temperature"]:
        raise ValueError("Hot inlet must be hotter than the cold inlet.")

    Automation3, Settings, DotNetPath, Environment = _bootstrap_dwsim()

    interf = Automation3()
    sim    = interf.LoadFlowsheet(MODEL_FILE)

    hot_in   = sim.GetObject("1").GetAsObject()
    hot_out  = sim.GetObject("2").GetAsObject()
    cold_in  = sim.GetObject("3").GetAsObject()
    cold_out = sim.GetObject("4").GetAsObject()
    hx       = sim.GetObject("HEX-1").GetAsObject()

    hot_in.SetMassFlow(inputs["hot_mass_flow"])
    hot_in.SetTemperature(inputs["hot_temperature"])
    cold_in.SetMassFlow(inputs["cold_mass_flow"])
    cold_in.SetTemperature(inputs["cold_temperature"])
    hx.Area               = inputs["area"]
    hx.OverallCoefficient = inputs["u_value"]

    _solve(interf, sim, Settings)

    return {
        "hot_out_temperature":  round(float(hot_out.GetTemperature()),  4),
        "cold_out_temperature": round(float(cold_out.GetTemperature()), 4),
        "heat_duty":            round(float(hx.Q),                 4),
        "lmtd":                 round(float(hx.LMTD),              4),
        "effectiveness":        round(float(hx.ThermalEfficiency), 2),
    }
