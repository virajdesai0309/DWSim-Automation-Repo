"""
Water Pump runner.
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


# ── Public contract ─────────────────────────────────────────────────────────────

def run(inputs: dict) -> dict:
    """
    Runs the water pump DWSIM simulation.

    inputs:
        mass_flow       — kg/s
        temperature     — K
        pressure        — Pa
        outlet_pressure — Pa

    returns:
        mass_flow_out   — kg/s
        temperature_out — K
        pressure_out    — Pa
        power_consumed  — W
    """
    Automation3, Settings, DotNetPath, Environment = _bootstrap_dwsim()

    interf = Automation3()
    sim    = interf.LoadFlowsheet(MODEL_FILE)

    # Get stream and unit operation objects
    one  = sim.GetObject("1").GetAsObject()
    two  = sim.GetObject("2").GetAsObject()
    pump = sim.GetObject("PUMP-1").GetAsObject()

    # Push inputs into the model
    one.SetMassFlow(inputs["mass_flow"])
    one.SetTemperature(inputs["temperature"])
    one.SetPressure(inputs["pressure"])
    pump.set_Pout(inputs["outlet_pressure"])

    # Solve
    Settings.SolverMode = 0
    errors = interf.CalculateFlowsheet4(sim)

    error_count = 0
    try:
        error_count = errors.Count if hasattr(errors, "Count") else int(str(errors) != "")
    except Exception:
        pass

    return {
        "mass_flow_out":   round(float(two.GetMassFlow()),    6),
        "temperature_out": round(float(two.GetTemperature()), 4),
        "pressure_out":    round(float(two.GetPressure()),    2),
        "power_consumed":  round(float(pump.get_DeltaQ()),    4),
        "_solver_errors":  error_count,
    }