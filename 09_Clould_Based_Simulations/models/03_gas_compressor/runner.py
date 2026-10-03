"""
Gas Compressor runner.
Contract: expose run(inputs: dict) -> dict
The backend calls this; never import this file directly.
"""

import sys
from pathlib import Path

# Shared bootstrap lives in backend/; make it importable however this file is loaded
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from dwsim_runtime import bootstrap, solve  # noqa: E402

MODEL_FILE = str(Path(__file__).parent / "model.dwxmz")


# ── Public contract ─────────────────────────────────────────────────────────────

def run(inputs: dict) -> dict:
    """
    Runs the adiabatic methane compressor (Peng-Robinson).

    Note: DWSIM takes AdiabaticEfficiency in percent (default 75.0), not as a
    fraction. Passing 0.85 means 0.85 % and gives a ~2000 K outlet.
    """
    if inputs["outlet_pressure"] <= inputs["pressure"]:
        raise ValueError("Outlet pressure must be higher than the inlet pressure.")

    Automation3, Settings = bootstrap()
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

    solve(interf, sim, Settings)

    return {
        "temperature_out":  round(float(two.GetTemperature()), 4),
        "pressure_out":     round(float(two.GetPressure()),    2),
        "power":            round(float(comp.DeltaQ),          4),
        "temperature_rise": round(float(comp.DeltaT),          4),
    }
