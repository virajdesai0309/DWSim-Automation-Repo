"""
03_verification.py
==================
Cross-checks ANN predictions against live DWSIM simulations.

Workflow
--------
1.  Loads the trained ANN and scalers from ann_artefacts/.
2.  Loads the DWSIM flowsheet and runs a fresh set of verification cases
    (either a random sub-sample of the training grid, or custom points you
    supply in CUSTOM_CASES below).
3.  Compares ANN predictions vs. DWSIM output for all six target variables.
4.  Prints a detailed error table and saves a parity-plot figure.

Run after 01_data_generation.py and 02_ann_model.py have completed.
"""

import os
import pickle
import itertools
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import torch
import torch.nn as nn

# ---------------------------------------------------------------------------
# 0.  Config
# ---------------------------------------------------------------------------
ARTEFACT_DIR   = "/workspace/10 Surrogate Models/ann_artefacts"
MODEL_PATH    = os.path.join(ARTEFACT_DIR, "hex_ann_model.pt")
SCALER_X_PATH = os.path.join(ARTEFACT_DIR, "scaler_X.pkl")
SCALER_Y_PATH = os.path.join(ARTEFACT_DIR, "scaler_y.pkl")
FLOWSHEET_PATH = "/workspace/02 Automation of HEX/02 Automation of HEX.dwxmz"
OUTPUT_DIR     = "/workspace/10 Surrogate Models/verification_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Custom verification cases ─────────────────────────────────────────────
# Each row: [cold_inlet_temp (K), cold_mass_flow (kg/s),
#            hot_inlet_temp (K),  hot_mass_flow  (kg/s)]
# Set to None to auto-generate a random grid.
CUSTOM_CASES = None
N_RANDOM_CASES = 40   # used only when CUSTOM_CASES is None

# ---------------------------------------------------------------------------
# 1.  Load ANN model
# ---------------------------------------------------------------------------
class HEXANN(nn.Module):
    def __init__(self, n_in, n_out, hidden, dropout):
        super().__init__()
        layers = []
        prev = n_in
        for h in hidden:
            layers += [nn.Linear(prev, h), nn.BatchNorm1d(h),
                       nn.SiLU(), nn.Dropout(dropout)]
            prev = h
        layers.append(nn.Linear(prev, n_out))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


checkpoint = torch.load(MODEL_PATH, map_location="cpu")
cfg        = checkpoint["model_config"]
INPUT_COLS  = checkpoint["input_cols"]
OUTPUT_COLS = checkpoint["output_cols"]

model = HEXANN(**cfg)
model.load_state_dict(checkpoint["model_state"])
model.eval()
print("ANN model loaded.")

with open(SCALER_X_PATH, "rb") as f:
    scaler_X = pickle.load(f)
with open(SCALER_Y_PATH, "rb") as f:
    scaler_y = pickle.load(f)

def ann_predict(X_phys: np.ndarray) -> np.ndarray:
    """X_phys shape: (N, 4). Returns (N, 6) in physical units."""
    X_s = scaler_X.transform(X_phys.astype(np.float32))
    with torch.no_grad():
        y_s = model(torch.tensor(X_s)).numpy()
    return scaler_y.inverse_transform(y_s)

# ---------------------------------------------------------------------------
# 2.  Boot DWSIM
# ---------------------------------------------------------------------------
import os as _os
_os.environ["PYTHONNET_RUNTIME"] = "coreclr"
_os.environ["DOTNET_SYSTEM_DRAWING_USE_GDIPLUS"] = "1"

import clr
from pythonnet import load as _load
_load("coreclr")

from System.IO import Directory
DWSIM_PATH = "/usr/local/lib/dwsim/"
Directory.SetCurrentDirectory(DWSIM_PATH)

for dll in ["CapeOpen.dll", "DWSIM.Automation.dll", "DWSIM.Interfaces.dll",
            "DWSIM.GlobalSettings.dll", "DWSIM.SharedClasses.dll",
            "DWSIM.Thermodynamics.dll", "DWSIM.UnitOperations.dll",
            "DWSIM.Inspector.dll", "System.Buffers.dll",
            "DWSIM.Thermodynamics.ThermoC.dll"]:
    clr.AddReference(DWSIM_PATH + dll)

from DWSIM.Automation import Automation3
from DWSIM.GlobalSettings import Settings

interf   = Automation3()
sim      = interf.LoadFlowsheet(FLOWSHEET_PATH)
HEX      = sim.GetObject("HX-1").GetAsObject()
COLD_IN  = sim.GetObject("Cold In").GetAsObject()
HOT_IN   = sim.GetObject("Hot In").GetAsObject()
COLD_OUT = sim.GetObject("Cold Out").GetAsObject()
HOT_OUT  = sim.GetObject("Hot Out").GetAsObject()
Settings.SolverMode = 0
print("DWSIM flowsheet loaded.")

# ---------------------------------------------------------------------------
# 3.  Build verification cases
# ---------------------------------------------------------------------------
if CUSTOM_CASES is not None:
    cases = np.array(CUSTOM_CASES, dtype=np.float32)
else:
    rng = np.random.default_rng(seed=99)
    T_c = rng.uniform(288.15, 313.15, N_RANDOM_CASES)
    m_c = rng.uniform(0.5,    5.0,    N_RANDOM_CASES)
    T_h = rng.uniform(338.15, 368.15, N_RANDOM_CASES)
    m_h = rng.uniform(0.5,    5.0,    N_RANDOM_CASES)
    cases = np.column_stack([T_c, m_c, T_h, m_h]).astype(np.float32)
    # Ensure hot side is always hotter
    cases = cases[cases[:, 0] < cases[:, 2]]

print(f"Running {len(cases)} verification cases in DWSIM …")

# ---------------------------------------------------------------------------
# 4.  Run DWSIM for each case & collect results
# ---------------------------------------------------------------------------
dwsim_results = []
ann_results   = []
valid_cases   = []

for i, (T_c, m_c, T_h, m_h) in enumerate(cases):
    COLD_IN.SetTemperature(float(T_c))
    COLD_IN.SetMassFlow(float(m_c))
    HOT_IN.SetTemperature(float(T_h))
    HOT_IN.SetMassFlow(float(m_h))

    errors = interf.CalculateFlowsheet2(sim)
    if errors and len(errors) > 0:
        print(f"  [WARN] Case {i+1}: solver did not converge – skipped.")
        continue

    try:
        sim_row = [
            HEX.get_ThermalEfficiency(),
            HEX.get_ColdSidePressureDrop(),
            HEX.get_HotSidePressureDrop(),
            HEX.get_OverallCoefficient(),
            COLD_OUT.GetTemperature(),
            HOT_OUT.GetTemperature(),
        ]
    except Exception as e:
        print(f"  [WARN] Case {i+1}: output retrieval error – {e}")
        continue

    dwsim_results.append(sim_row)
    ann_results.append(ann_predict(np.array([[T_c, m_c, T_h, m_h]]))[0])
    valid_cases.append([T_c, m_c, T_h, m_h])

    if (i + 1) % 10 == 0:
        print(f"  Completed {i+1}/{len(cases)}")

dwsim_arr = np.array(dwsim_results)
ann_arr   = np.array(ann_results)
cases_arr = np.array(valid_cases)
print(f"\n{len(dwsim_arr)} cases converged successfully.")

# ---------------------------------------------------------------------------
# 5.  Compute error metrics
# ---------------------------------------------------------------------------
abs_err  = np.abs(ann_arr - dwsim_arr)
rel_err  = abs_err / (np.abs(dwsim_arr) + 1e-10) * 100  # percent
mae      = abs_err.mean(axis=0)
rmse     = np.sqrt(((ann_arr - dwsim_arr)**2).mean(axis=0))
mape     = rel_err.mean(axis=0)
max_err  = abs_err.max(axis=0)

print("\n" + "=" * 72)
print(" ANN vs DWSIM Verification Summary")
print("=" * 72)
header = f"{'Output':<25} {'MAE':>10} {'RMSE':>10} {'MAPE%':>8} {'MaxErr':>10}"
print(header)
print("-" * 72)
for col, m, r, p, mx in zip(OUTPUT_COLS, mae, rmse, mape, max_err):
    print(f"{col:<25} {m:10.4f} {r:10.4f} {p:8.2f} {mx:10.4f}")
print("=" * 72)

# ---------------------------------------------------------------------------
# 6.  Save detailed results table
# ---------------------------------------------------------------------------
cols_in  = INPUT_COLS
cols_sim = [f"sim_{c}" for c in OUTPUT_COLS]
cols_ann = [f"ann_{c}" for c in OUTPUT_COLS]
cols_err = [f"err_{c}" for c in OUTPUT_COLS]

results_df = pd.DataFrame(
    np.hstack([cases_arr, dwsim_arr, ann_arr, abs_err]),
    columns=cols_in + cols_sim + cols_ann + cols_err
)
results_csv = os.path.join(OUTPUT_DIR, "verification_results.csv")
results_df.to_csv(results_csv, index=False)
print(f"\nDetailed results saved → {results_csv}")

# ---------------------------------------------------------------------------
# 7.  Parity plots  (DWSIM vs ANN for each output)
# ---------------------------------------------------------------------------
n_out = len(OUTPUT_COLS)
ncols = 3
nrows = (n_out + ncols - 1) // ncols

fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4 * nrows))
axes = axes.flatten()

for k, col in enumerate(OUTPUT_COLS):
    ax  = axes[k]
    sim_vals = dwsim_arr[:, k]
    ann_vals = ann_arr[:, k]

    mn = min(sim_vals.min(), ann_vals.min())
    mx = max(sim_vals.max(), ann_vals.max())

    ax.scatter(sim_vals, ann_vals, s=18, alpha=0.6, edgecolors="none",
               color="steelblue")
    ax.plot([mn, mx], [mn, mx], "r--", linewidth=1.2, label="Ideal (y = x)")
    ax.set_xlabel(f"DWSIM  [{col}]", fontsize=8)
    ax.set_ylabel(f"ANN    [{col}]", fontsize=8)
    ax.set_title(col, fontsize=9, fontweight="bold")
    ax.legend(fontsize=7)
    ax.grid(True, linestyle="--", alpha=0.4)

    # Annotate with R²
    ss_res = ((sim_vals - ann_vals) ** 2).sum()
    ss_tot = ((sim_vals - sim_vals.mean()) ** 2).sum()
    r2 = 1 - ss_res / (ss_tot + 1e-12)
    ax.text(0.05, 0.92, f"R² = {r2:.4f}", transform=ax.transAxes,
            fontsize=8, color="darkred",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7))

# Hide unused subplots
for k in range(n_out, len(axes)):
    axes[k].set_visible(False)

plt.suptitle("ANN Predictions vs DWSIM Simulations  —  Parity Plots",
             fontsize=12, fontweight="bold", y=1.01)
plt.tight_layout()
parity_png = os.path.join(OUTPUT_DIR, "parity_plots.png")
plt.savefig(parity_png, dpi=150, bbox_inches="tight")
print(f"Parity plots saved   → {parity_png}")

# ---------------------------------------------------------------------------
# 8.  Interactive single-point prediction demo
# ---------------------------------------------------------------------------
print("\n" + "=" * 50)
print("  Single-Point Prediction Demo")
print("=" * 50)

demo_points = [
    [298.15, 2.0, 353.15, 2.0],   # moderate flows
    [293.15, 1.0, 363.15, 4.0],   # low cold / high hot
    [308.15, 4.5, 343.15, 1.5],   # high cold / low hot
]

for pt in demo_points:
    T_c, m_c, T_h, m_h = pt
    pred = ann_predict(np.array([pt]))[0]
    print(f"\n  Inputs: T_c={T_c-273.15:.1f}°C  ṁ_c={m_c} kg/s  "
          f"T_h={T_h-273.15:.1f}°C  ṁ_h={m_h} kg/s")
    for col, val in zip(OUTPUT_COLS, pred):
        unit = ("%" if "efficiency" in col
        else "Pa" if "pressure" in col
        else "W/m²K" if "htc" in col
        else "K")
        print(f"    {col:<25} → {val:10.3f}  {unit}")

print("\nVerification complete.")