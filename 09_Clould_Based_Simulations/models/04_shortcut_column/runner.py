"""
Shortcut Distillation Column runner.
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
    Runs the benzene/toluene shortcut column (Fenske-Underwood-Gilliland,
    Peng-Robinson, total condenser). Benzene is the light key, toluene the
    heavy key.
    """
    Automation3, Settings = bootstrap()
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

    solve(interf, sim, Settings)

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
