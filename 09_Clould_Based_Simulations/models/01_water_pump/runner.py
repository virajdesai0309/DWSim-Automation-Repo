"""
Water Pump runner.
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
        power_consumed  — kW (DWSIM DeltaQ)
    """
    if inputs["outlet_pressure"] <= inputs["pressure"]:
        raise ValueError("Outlet pressure must be higher than the inlet pressure.")

    Automation3, Settings = bootstrap()

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

    # Solve; surface DWSIM's own messages instead of returning stale numbers
    solve(interf, sim, Settings)

    return {
        "mass_flow_out":   round(float(two.GetMassFlow()),    6),
        "temperature_out": round(float(two.GetTemperature()), 4),
        "pressure_out":    round(float(two.GetPressure()),    2),
        "power_consumed":  round(float(pump.get_DeltaQ()),    4),
    }