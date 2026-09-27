"""
Shortcut Distillation Column runner.
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
    Runs the benzene/toluene shortcut column (Fenske-Underwood-Gilliland,
    Peng-Robinson, total condenser). Benzene is the light key, toluene the
    heavy key.
    """
    Automation3, Settings, DotNetPath, Environment = _bootstrap_dwsim()
    from System import Array

    interf = Automation3()
    sim    = interf.LoadFlowsheet(MODEL_FILE)

    feed       = sim.GetObject("feed").GetAsObject()
    distillate = sim.GetObject("distillate").GetAsObject()
    residue    = sim.GetObject("residue").GetAsObject()
    sc         = sim.GetObject("SC").GetAsObject()

    x = inputs["benzene_fraction"]
    feed.SetOverallComposition(Array[float]([x, 1.0 - x]))
    feed.SetMassFlow(inputs["feed_mass_flow"])
    feed.SetTemperature(inputs["feed_temperature"])
    feed.SetPressure(inputs["pressure"])

    sc.m_refluxratio         = inputs["reflux_ratio"]
    sc.m_lightkeymolarfrac   = inputs["lk_in_bottoms"]
    sc.m_heavykeymolarfrac   = inputs["hk_in_distillate"]
    sc.m_condenserpressure   = inputs["pressure"]
    sc.m_boilerpressure      = inputs["pressure"]

    _solve(interf, sim, Settings)

    return {
        "min_reflux":             round(float(sc.m_Rmin), 4),
        "min_stages":             round(float(sc.m_Nmin), 2),
        "stages":                 round(float(sc.m_N),    2),
        "feed_stage":             round(float(sc.ofs),    2),
        "condenser_duty":         round(float(sc.m_Qc),   2),
        "reboiler_duty":          round(float(sc.m_Qb),   2),
        "distillate_flow":        round(float(distillate.GetMassFlow()),   4),
        "distillate_temperature": round(float(distillate.GetTemperature()), 2),
        "distillate_benzene":     round(float(distillate.GetOverallComposition()[0]), 4),
        "residue_flow":           round(float(residue.GetMassFlow()),   4),
        "residue_temperature":    round(float(residue.GetTemperature()), 2),
    }
