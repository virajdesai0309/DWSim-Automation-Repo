"""
Heat Exchanger runner.
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
    Runs the shell-and-tube heat exchanger (counter-current, rating mode:
    DWSIM solves both outlet temperatures from area and U).

    Hot side:  stream 1 -> 2, water with 1 % methanol
    Cold side: stream 3 -> 4, methanol
    Property package: NRTL
    """
    if inputs["hot_temperature"] <= inputs["cold_temperature"]:
        raise ValueError("Hot inlet must be hotter than the cold inlet.")

    Automation3, Settings = bootstrap()

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

    solve(interf, sim, Settings)

    return {
        "hot_out_temperature":  round(float(hot_out.GetTemperature()),  4),
        "cold_out_temperature": round(float(cold_out.GetTemperature()), 4),
        "heat_duty":            round(float(hx.Q),                 4),
        "lmtd":                 round(float(hx.LMTD),              4),
        "effectiveness":        round(float(hx.ThermalEfficiency), 2),
    }
