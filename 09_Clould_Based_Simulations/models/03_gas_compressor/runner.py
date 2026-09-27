"""
Gas Compressor runner.
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
    Runs the adiabatic methane compressor (Peng-Robinson).

    Note: DWSIM takes AdiabaticEfficiency in percent (default 75.0), not as a
    fraction. Passing 0.85 means 0.85 % and gives a ~2000 K outlet.
    """
    if inputs["outlet_pressure"] <= inputs["pressure"]:
        raise ValueError("Outlet pressure must be higher than the inlet pressure.")

    Automation3, Settings, DotNetPath, Environment = _bootstrap_dwsim()
    from System import Enum

    interf = Automation3()
    sim    = interf.LoadFlowsheet(MODEL_FILE)

    one  = sim.GetObject("1").GetAsObject()
    two  = sim.GetObject("2").GetAsObject()
    comp = sim.GetObject("C-1").GetAsObject()

    one.SetMassFlow(inputs["mass_flow"])
    one.SetTemperature(inputs["temperature"])
    one.SetPressure(inputs["pressure"])
    comp.CalcMode = Enum.Parse(comp.CalcMode.GetType(), "OutletPressure")
    comp.POut = inputs["outlet_pressure"]
    comp.AdiabaticEfficiency = inputs["efficiency"]

    _solve(interf, sim, Settings)

    return {
        "temperature_out":  round(float(two.GetTemperature()), 4),
        "pressure_out":     round(float(two.GetPressure()),    2),
        "power":            round(float(comp.DeltaQ),          4),
        "temperature_rise": round(float(comp.DeltaT),          4),
    }
