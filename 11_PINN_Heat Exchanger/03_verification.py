"""
03_verification.py
==================
Head-to-head comparison of the trained PINN against the DWSim digital twin.

For each test case the script:
  1. Runs DWSim to get the "ground truth" outputs
  2. Queries the PINN for the same inputs
  3. Computes per-case and aggregate error metrics
  4. Saves a detailed results CSV and diagnostic plots

Test cases
----------
Two sources of test cases are supported and both are run automatically:

  A) MANUAL cases — defined in MANUAL_CASES below.
     These are hand-picked operating points you want to inspect closely,
     including edge cases, design point, off-design, etc.

  B) RANDOM cases — N_RANDOM fresh LHS points that were never seen during
     training (different seed from the training data).

Outputs
-------
  verification_results.csv   — per-case comparison table (all metrics)
  verification_plots.png     — parity plots, error distributions, profile plots
  verification_summary.txt   — printed summary saved to file

Usage
-----
  python 03_verification.py
  python 03_verification.py --n_random 50 --model_dir /path/to/pinn_outputs_30k
"""

import os
import sys
import time
import argparse
import textwrap
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ── PyTorch (PINN) ────────────────────────────────────────────────────────────
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler

# ── DWSIM bootstrap ───────────────────────────────────────────────────────────
os.environ["PYTHONNET_RUNTIME"] = "coreclr"
os.environ["DOTNET_SYSTEM_DRAWING_USE_GDIPLUS"] = "1"

import clr
from pythonnet import load
load("coreclr")

from System.IO import Directory
DWSIM_PATH = "/usr/local/lib/dwsim/"
Directory.SetCurrentDirectory(DWSIM_PATH)

for dll in [
    "CapeOpen.dll", "DWSIM.Automation.dll", "DWSIM.Interfaces.dll",
    "DWSIM.GlobalSettings.dll", "DWSIM.SharedClasses.dll",
    "DWSIM.Thermodynamics.dll", "DWSIM.UnitOperations.dll",
    "DWSIM.Inspector.dll", "System.Buffers.dll",
    "DWSIM.Thermodynamics.ThermoC.dll",
]:
    clr.AddReference(DWSIM_PATH + dll)

from DWSIM.Automation import Automation3
from DWSIM.GlobalSettings import Settings

# =============================================================================
# 0.  Configuration — edit paths and manual cases here
# =============================================================================
FLOWSHEET_PATH = "/workspace/02 Automation of HEX/02 Automation of HEX.dwxmz"
MODEL_DIR      = "/workspace/11_PINN_Heat Exchanger/pinn_outputs_30k"
OUT_DIR        = "/workspace/11_PINN_Heat Exchanger/verification"

# ── Manual test cases ─────────────────────────────────────────────────────────
# Add / remove rows freely.  Columns: label, cold_inlet_temp [K], cold_mass_flow
# [kg/s], hot_inlet_temp [K], hot_mass_flow [kg/s]
# Rule of thumb: cover design point, low/high flow, near-min ΔT, max ΔT.
MANUAL_CASES = [
    # label                  T_c_in   m_c    T_h_in   m_h
    ("Design point",         303.15,  3.0,   353.15,  3.0 ),
    ("High hot flow",        303.15,  3.0,   353.15,  5.0 ),
    ("Low hot flow",         303.15,  3.0,   353.15,  0.75),
    ("High cold flow",       303.15,  5.0,   353.15,  3.0 ),
    ("Low cold flow",        303.15,  0.75,  353.15,  3.0 ),
    ("Max temperature diff", 288.15,  3.0,   373.15,  3.0 ),
    ("Min temperature diff", 315.15,  3.0,   335.15,  3.0 ),
    ("Cold inlet very low",  288.15,  1.0,   360.00,  2.0 ),
    ("Hot inlet very high",  295.00,  2.0,   373.15,  4.0 ),
    ("Equal mass flows low", 290.00,  1.0,   345.00,  1.0 ),
    ("Equal mass flows high",300.00,  5.0,   365.00,  5.0 ),
    ("Imbalanced flows",     293.15,  0.5,   368.15,  5.5 ),
]

# Number of additional random LHS cases (unseen during training, seed≠42)
N_RANDOM = 30

# =============================================================================
# CLI overrides
# =============================================================================
parser = argparse.ArgumentParser()
parser.add_argument("--model_dir", default=MODEL_DIR)
parser.add_argument("--out_dir",   default=OUT_DIR)
parser.add_argument("--n_random",  type=int, default=N_RANDOM)
parser.add_argument("--flowsheet", default=FLOWSHEET_PATH)
args = parser.parse_args()

os.makedirs(args.out_dir, exist_ok=True)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"\nUsing device : {DEVICE}")
print(f"Model dir    : {args.model_dir}")
print(f"Output dir   : {args.out_dir}\n")

# =============================================================================
# 1.  Load PINN checkpoint
# =============================================================================
CKPT_PATH = os.path.join(args.model_dir, "hex_pinn_30k_best.pt")
if not os.path.exists(CKPT_PATH):
    # Fall back to final checkpoint if best not found
    CKPT_PATH = os.path.join(args.model_dir, "hex_pinn_30k_final.pt")

print(f"Loading checkpoint : {CKPT_PATH}")
_raw = torch.load(CKPT_PATH, map_location=DEVICE)

# Handle two checkpoint formats:
#   Format A (full): dict with 'model_state' + metadata keys
#                    → saved by final save block
#   Format B (bare): OrderedDict of weight tensors only
#                    → saved by best-model tracker (model.state_dict() directly)
# Detect by checking whether the first value is a tensor (Format B) or a dict (Format A)
_first_val = next(iter(_raw.values()))
if isinstance(_first_val, torch.Tensor):
    # Format B — bare state dict, no metadata
    print("  Checkpoint format : bare state_dict (best-epoch snapshot)")
    ckpt = {"model_state": _raw}   # wrap so the rest of the script works uniformly
else:
    # Format A — full metadata dict
    print("  Checkpoint format : full metadata dict")
    ckpt = _raw

# ── Rebuild scaler objects from saved stats ───────────────────────────────────
# Graceful fallback for checkpoints saved before metadata was added
INPUT_COLS  = ckpt.get("input_cols",
              ["cold_inlet_temp", "hot_inlet_temp",
               "cold_mass_flow",  "hot_mass_flow", "global_htc"])
T_MEAN      = ckpt.get("T_mean",  ckpt.get("t_mean",  327.903))
T_STD       = ckpt.get("T_std",   ckpt.get("t_std",    21.115))
A_TOTAL     = ckpt.get("A_TOTAL", ckpt.get("a_total",  39.2699))
CP          = ckpt.get("CP",      ckpt.get("cp",       4186.0))

# Print what was actually loaded so you can verify
print(f"  INPUT_COLS : {INPUT_COLS}")
print(f"  T_MEAN     : {T_MEAN:.3f} K")
print(f"  T_STD      : {T_STD:.4f} K")
print(f"  A_TOTAL    : {A_TOTAL:.4f} m²")
print(f"  CP         : {CP} J/kg·K")

# ── Rebuild scaler from checkpoint or recompute from the training CSV ────────
# x_scaler_mean/std were not saved in early checkpoints — recompute if missing.
x_scaler = StandardScaler()

if "x_scaler_mean" in ckpt and "x_scaler_std" in ckpt:
    x_scaler.mean_  = np.array(ckpt["x_scaler_mean"], dtype=np.float64)
    x_scaler.scale_ = np.array(ckpt["x_scaler_std"],  dtype=np.float64)
    x_scaler.n_features_in_ = len(x_scaler.mean_)
    print("  x_scaler   : loaded from checkpoint")
else:
    # Recompute from the training CSV — must match EXACTLY what training used.
    # INPUT_COLS order: cold_inlet_temp, hot_inlet_temp, cold_mass_flow,
    #                   hot_mass_flow, global_htc
    TRAIN_CSV = "/workspace/11_PINN_Heat Exchanger/hex_dataset_PINN.csv"
    print(f"  x_scaler   : recomputing from {TRAIN_CSV}")
    _df = pd.read_csv(TRAIN_CSV, usecols=INPUT_COLS)
    x_scaler.fit(_df[INPUT_COLS].values.astype(np.float64))
    del _df
    print(f"  x_scaler mean  : {x_scaler.mean_}")
    print(f"  x_scaler scale : {x_scaler.scale_}")

def scale_x(arr_np):
    return ((arr_np - x_scaler.mean_) / x_scaler.scale_).astype(np.float32)

def unscale_T(t_scaled):
    """Works on numpy arrays or torch tensors."""
    return t_scaled * T_STD + T_MEAN

# ── Rebuild network (must match training architecture) ────────────────────────
hidden_layers = ckpt.get("hidden_layers", 4)
hidden_dim    = ckpt.get("hidden_dim",    64)

class HexPINN(nn.Module):
    def __init__(self, hidden_layers=4, hidden_dim=64):
        super().__init__()
        layers = [nn.Linear(6, hidden_dim), nn.Tanh()]
        for _ in range(hidden_layers - 1):
            layers += [nn.Linear(hidden_dim, hidden_dim), nn.Tanh()]
        layers.append(nn.Linear(hidden_dim, 2))
        self.net = nn.Sequential(*layers)

    def forward(self, xi, x_op):
        return self.net(torch.cat([xi, x_op], dim=1)).split(1, dim=1)

model = HexPINN(hidden_layers, hidden_dim).to(DEVICE)
model.load_state_dict(ckpt["model_state"])
model.eval()

print(f"Architecture : {hidden_layers} × {hidden_dim}  "
      f"| Parameters : {sum(p.numel() for p in model.parameters()):,}")
if "best_val_mae_K" in ckpt:
    print(f"Best val MAE during training : {ckpt['best_val_mae_K']:.4f} K\n")

# =============================================================================
# 2.  PINN inference helper
# =============================================================================
def pinn_predict(cold_inlet_T, hot_inlet_T, cold_mflow, hot_mflow, U):
    """
    Query the PINN for a single operating point.
    Returns: T_h_out_K, T_c_out_K, T_h_profile [100pts], T_c_profile [100pts]

    Counter-current convention:
        Hot  : enters ξ=0, exits ξ=1  → T_h_out = prediction at ξ=1
        Cold : enters ξ=1, exits ξ=0  → T_c_out = prediction at ξ=0
    """
    x_raw = np.array([[cold_inlet_T, hot_inlet_T,
                        cold_mflow,   hot_mflow,  U]], dtype=np.float32)
    x_s   = scale_x(x_raw)

    N_PROF = 100
    xi_arr = np.linspace(0, 1, N_PROF).astype(np.float32)
    x_rep  = np.repeat(x_s, N_PROF, axis=0)

    xi_t   = torch.tensor(xi_arr.reshape(-1, 1), device=DEVICE)
    x_t    = torch.tensor(x_rep, device=DEVICE)

    with torch.no_grad():
        T_h_s, T_c_s = model(xi_t, x_t)

    T_h_K = unscale_T(T_h_s.cpu().numpy().flatten())
    T_c_K = unscale_T(T_c_s.cpu().numpy().flatten())

    # Outlet values
    T_h_out = T_h_K[-1]   # ξ=1
    T_c_out = T_c_K[0]    # ξ=0

    return T_h_out, T_c_out, T_h_K, T_c_K, xi_arr

# =============================================================================
# 3.  DWSim setup
# =============================================================================
print("Loading DWSim flowsheet...")
interf   = Automation3()
sim      = interf.LoadFlowsheet(args.flowsheet)
HEX      = sim.GetObject("HX-1").GetAsObject()
COLD_IN  = sim.GetObject("Cold In").GetAsObject()
HOT_IN   = sim.GetObject("Hot In").GetAsObject()
COLD_OUT = sim.GetObject("Cold Out").GetAsObject()
HOT_OUT  = sim.GetObject("Hot Out").GetAsObject()
Settings.SolverMode = 0

# Fetch fixed geometry (used to get U for PINN input)
st_props = HEX.get_STProperties()
print(f"Flowsheet loaded.  Flow: {HEX.get_FlowDir().ToString()}\n")

def dwsim_run(T_c_in, m_c, T_h_in, m_h):
    """Run one DWSim case. Returns dict of outputs or None on failure."""
    COLD_IN.SetTemperature(T_c_in)
    COLD_IN.SetMassFlow(m_c)
    HOT_IN.SetTemperature(T_h_in)
    HOT_IN.SetMassFlow(m_h)
    errors = interf.CalculateFlowsheet2(sim)
    if errors and len(errors) > 0:
        return None
    return {
        "hot_outlet_temp":    HOT_OUT.GetTemperature(),
        "cold_outlet_temp":   COLD_OUT.GetTemperature(),
        "thermal_efficiency": HEX.get_ThermalEfficiency(),
        "global_htc":         HEX.get_OverallCoefficient(),
        "cold_pressure_drop": HEX.get_ColdSidePressureDrop(),
        "hot_pressure_drop":  HEX.get_HotSidePressureDrop(),
    }

# =============================================================================
# 4.  Build full test case list
# =============================================================================
test_cases = []

# A) Manual cases
for label, T_c, m_c, T_h, m_h in MANUAL_CASES:
    test_cases.append({"label": label, "source": "manual",
                        "cold_inlet_temp": T_c, "cold_mass_flow": m_c,
                        "hot_inlet_temp":  T_h, "hot_mass_flow":  m_h})

# B) Random LHS cases (seed=99 — never seen by the model trained with seed=42)
if args.n_random > 0:
    import scipy.stats.qmc as qmc
    BOUNDS = np.array([[288.15, 318.15], [0.5, 5.5],
                       [333.15, 373.15], [0.5, 5.5]])
    sampler  = qmc.LatinHypercube(d=4, seed=99)
    X_rand   = qmc.scale(sampler.random(n=args.n_random), BOUNDS[:,0], BOUNDS[:,1])
    for i, (T_c, m_c, T_h, m_h) in enumerate(X_rand):
        if T_c < T_h:   # physical constraint
            test_cases.append({"label": f"random_{i+1:03d}", "source": "random",
                                "cold_inlet_temp": T_c, "cold_mass_flow": m_c,
                                "hot_inlet_temp":  T_h, "hot_mass_flow":  m_h})

print(f"Test cases : {len(test_cases)}  "
      f"({len(MANUAL_CASES)} manual + {args.n_random} random LHS)\n")
print(f"{'─'*90}")
print(f"{'#':>3}  {'Label':<28} {'T_c_in':>7} {'m_c':>5} {'T_h_in':>7} {'m_h':>5}  "
      f"{'Th_out DWSim':>12} {'Th_out PINN':>11} {'Err_h':>8}  "
      f"{'Tc_out DWSim':>12} {'Tc_out PINN':>11} {'Err_c':>8}")
print(f"{'─'*90}")

# =============================================================================
# 5.  Run verification loop
# =============================================================================
results = []
profile_store = {}   # save profiles for a few manual cases to plot

t0 = time.time()
for i, case in enumerate(test_cases):
    T_c_in = case["cold_inlet_temp"]
    m_c    = case["cold_mass_flow"]
    T_h_in = case["hot_inlet_temp"]
    m_h    = case["hot_mass_flow"]
    label  = case["label"]

    # ── DWSim ─────────────────────────────────────────────────────────────────
    dws = dwsim_run(T_c_in, m_c, T_h_in, m_h)
    if dws is None:
        print(f"  [SKIP] Case {i+1} '{label}' — DWSim failed to converge")
        continue

    U = dws["global_htc"]

    # ── PINN ──────────────────────────────────────────────────────────────────
    Th_pinn, Tc_pinn, Th_prof, Tc_prof, xi_arr = pinn_predict(
        T_c_in, T_h_in, m_c, m_h, U
    )

    # ── Error metrics ─────────────────────────────────────────────────────────
    err_h   = Th_pinn - dws["hot_outlet_temp"]
    err_c   = Tc_pinn - dws["cold_outlet_temp"]
    abs_h   = abs(err_h)
    abs_c   = abs(err_c)

    # Derived metrics from DWSim (ground truth)
    Q_dws   = m_h * CP * (T_h_in - dws["hot_outlet_temp"])   # [W]
    eff_dws = dws["thermal_efficiency"]

    # Derived from PINN
    Q_pinn    = m_h * CP * (T_h_in - Th_pinn)
    eff_pinn  = 100 * (T_h_in - Th_pinn) / (T_h_in - T_c_in) \
                if (T_h_in - T_c_in) > 0 else 0.0

    rec = {
        "label":              label,
        "source":             case["source"],
        "cold_inlet_temp":    T_c_in,
        "cold_mass_flow":     m_c,
        "hot_inlet_temp":     T_h_in,
        "hot_mass_flow":      m_h,
        # DWSim ground truth
        "Th_out_DWSim":       dws["hot_outlet_temp"],
        "Tc_out_DWSim":       dws["cold_outlet_temp"],
        "efficiency_DWSim":   eff_dws,
        "U_DWSim":            U,
        "Q_hot_DWSim_W":      Q_dws,
        "cold_dp_DWSim_Pa":   dws["cold_pressure_drop"],
        "hot_dp_DWSim_Pa":    dws["hot_pressure_drop"],
        # PINN predictions
        "Th_out_PINN":        Th_pinn,
        "Tc_out_PINN":        Tc_pinn,
        "efficiency_PINN":    eff_pinn,
        "Q_hot_PINN_W":       Q_pinn,
        # Errors
        "err_Th_K":           err_h,          # signed: PINN − DWSim
        "err_Tc_K":           err_c,
        "abs_err_Th_K":       abs_h,
        "abs_err_Tc_K":       abs_c,
        "pct_err_Th":         100 * err_h / dws["hot_outlet_temp"],
        "pct_err_Tc":         100 * err_c / dws["cold_outlet_temp"],
        "abs_pct_err_Th":     100 * abs_h / dws["hot_outlet_temp"],
        "abs_pct_err_Tc":     100 * abs_c / dws["cold_outlet_temp"],
        "err_efficiency_ppt": eff_pinn - eff_dws,   # percentage points
        "err_Q_W":            Q_pinn - Q_dws,
    }
    results.append(rec)

    # Save profiles for first 6 manual cases (for profile plot)
    if case["source"] == "manual" and len(profile_store) < 6:
        profile_store[label] = {
            "xi": xi_arr, "Th": Th_prof, "Tc": Tc_prof,
            "Th_in": T_h_in, "Tc_in": T_c_in,
            "Th_out_dws": dws["hot_outlet_temp"],
            "Tc_out_dws": dws["cold_outlet_temp"],
        }

    # Terminal print
    flag = "  ✓" if abs_h < 1.0 and abs_c < 1.0 else " ⚠ " if abs_h < 2.0 and abs_c < 2.0 else " ✗ "
    print(f"{i+1:>3}{flag} {label:<28} "
          f"{T_c_in:>7.2f} {m_c:>5.2f} {T_h_in:>7.2f} {m_h:>5.2f}  "
          f"{dws['hot_outlet_temp']:>12.3f} {Th_pinn:>11.3f} {err_h:>+8.3f}K  "
          f"{dws['cold_outlet_temp']:>12.3f} {Tc_pinn:>11.3f} {err_c:>+8.3f}K")

elapsed = time.time() - t0
print(f"{'─'*90}")
print(f"Completed {len(results)} cases in {elapsed:.1f}s\n")

# =============================================================================
# 6.  Aggregate statistics
# =============================================================================
df = pd.DataFrame(results)

def stats_block(col, label):
    s = df[col]
    return (f"  {label:<30}  mean={s.mean():>8.4f}  "
            f"std={s.std():>8.4f}  "
            f"p50={s.median():>8.4f}  "
            f"p95={s.quantile(0.95):>8.4f}  "
            f"max={s.max():>8.4f}")

summary_lines = [
    "",
    "=" * 70,
    "  VERIFICATION SUMMARY — PINN vs DWSim Digital Twin",
    "=" * 70,
    f"  Total cases          : {len(df)}",
    f"  Manual cases         : {(df['source']=='manual').sum()}",
    f"  Random LHS cases     : {(df['source']=='random').sum()}",
    "",
    "── Hot outlet temperature (T_h_out) ──────────────────────────────────",
    stats_block("abs_err_Th_K",  "Abs error [K]"),
    stats_block("abs_pct_err_Th","Abs % error [%]"),
    "",
    "── Cold outlet temperature (T_c_out) ─────────────────────────────────",
    stats_block("abs_err_Tc_K",  "Abs error [K]"),
    stats_block("abs_pct_err_Tc","Abs % error [%]"),
    "",
    "── Thermal efficiency ────────────────────────────────────────────────",
    stats_block("err_efficiency_ppt", "Error [%-points]"),
    "",
    "── Heat duty Q ───────────────────────────────────────────────────────",
    stats_block("err_Q_W", "Error [W]"),
    "",
    "── Cases within tolerance ────────────────────────────────────────────",
    f"  |err_Th| < 0.5 K     : {(df['abs_err_Th_K'] < 0.5).sum():>4} / {len(df)}  "
    f"({100*(df['abs_err_Th_K']<0.5).mean():.1f}%)",
    f"  |err_Th| < 1.0 K     : {(df['abs_err_Th_K'] < 1.0).sum():>4} / {len(df)}  "
    f"({100*(df['abs_err_Th_K']<1.0).mean():.1f}%)",
    f"  |err_Tc| < 0.5 K     : {(df['abs_err_Tc_K'] < 0.5).sum():>4} / {len(df)}  "
    f"({100*(df['abs_err_Tc_K']<0.5).mean():.1f}%)",
    f"  |err_Tc| < 1.0 K     : {(df['abs_err_Tc_K'] < 1.0).sum():>4} / {len(df)}  "
    f"({100*(df['abs_err_Tc_K']<1.0).mean():.1f}%)",
    "=" * 70,
    "",
]

for line in summary_lines:
    print(line)

# Save summary to file
summary_path = os.path.join(args.out_dir, "verification_summary.txt")
with open(summary_path, "w") as f:
    f.write("\n".join(summary_lines))
print(f"Summary saved → {summary_path}")

# Save results CSV
csv_path = os.path.join(args.out_dir, "verification_results.csv")
df.to_csv(csv_path, index=False)
print(f"Results CSV  → {csv_path}")

# =============================================================================
# 7.  Diagnostic plots
# =============================================================================
fig = plt.figure(figsize=(20, 16))
gs  = gridspec.GridSpec(3, 3, figure=fig, hspace=0.42, wspace=0.35)

# Colour by source
colors = ["tomato" if s == "manual" else "steelblue" for s in df["source"]]

# ── (a) Parity — T_h_out ──────────────────────────────────────────────────────
ax = fig.add_subplot(gs[0, 0])
ax.scatter(df["Th_out_DWSim"], df["Th_out_PINN"], c=colors, s=35, alpha=0.7)
lims = [df["Th_out_DWSim"].min()-1, df["Th_out_DWSim"].max()+1]
ax.plot(lims, lims, "k--", lw=1)
ax.fill_between(lims, [l-1 for l in lims], [l+1 for l in lims],
                alpha=0.08, color="green", label="±1 K band")
ax.set_xlabel("DWSim T_h_out [K]"); ax.set_ylabel("PINN T_h_out [K]")
ax.set_title("Parity — Hot outlet"); ax.legend(fontsize=7); ax.grid(alpha=0.3)

# ── (b) Parity — T_c_out ──────────────────────────────────────────────────────
ax = fig.add_subplot(gs[0, 1])
ax.scatter(df["Tc_out_DWSim"], df["Tc_out_PINN"], c=colors, s=35, alpha=0.7)
lims = [df["Tc_out_DWSim"].min()-1, df["Tc_out_DWSim"].max()+1]
ax.plot(lims, lims, "k--", lw=1)
ax.fill_between(lims, [l-1 for l in lims], [l+1 for l in lims],
                alpha=0.08, color="green", label="±1 K band")
ax.set_xlabel("DWSim T_c_out [K]"); ax.set_ylabel("PINN T_c_out [K]")
ax.set_title("Parity — Cold outlet"); ax.legend(fontsize=7); ax.grid(alpha=0.3)

# ── (c) Parity — Thermal efficiency ──────────────────────────────────────────
ax = fig.add_subplot(gs[0, 2])
ax.scatter(df["efficiency_DWSim"], df["efficiency_PINN"], c=colors, s=35, alpha=0.7)
lims = [df["efficiency_DWSim"].min()-2, df["efficiency_DWSim"].max()+2]
ax.plot(lims, lims, "k--", lw=1)
ax.set_xlabel("DWSim Efficiency [%]"); ax.set_ylabel("PINN Efficiency [%]")
ax.set_title("Parity — Thermal Efficiency"); ax.grid(alpha=0.3)

# ── (d) Error distribution — T_h ─────────────────────────────────────────────
ax = fig.add_subplot(gs[1, 0])
ax.hist(df["err_Th_K"], bins=20, color="tomato", edgecolor="white", alpha=0.8)
ax.axvline(0, color="k", lw=1, ls="--")
ax.axvline( 1, color="green", lw=1, ls=":", label="±1 K")
ax.axvline(-1, color="green", lw=1, ls=":")
ax.set_xlabel("Error [K]  (PINN − DWSim)")
ax.set_ylabel("Count")
ax.set_title(f"Hot outlet error  (mean={df['err_Th_K'].mean():+.3f} K)")
ax.legend(fontsize=7); ax.grid(alpha=0.3)

# ── (e) Error distribution — T_c ─────────────────────────────────────────────
ax = fig.add_subplot(gs[1, 1])
ax.hist(df["err_Tc_K"], bins=20, color="steelblue", edgecolor="white", alpha=0.8)
ax.axvline(0, color="k", lw=1, ls="--")
ax.axvline( 1, color="green", lw=1, ls=":", label="±1 K")
ax.axvline(-1, color="green", lw=1, ls=":")
ax.set_xlabel("Error [K]  (PINN − DWSim)")
ax.set_ylabel("Count")
ax.set_title(f"Cold outlet error  (mean={df['err_Tc_K'].mean():+.3f} K)")
ax.legend(fontsize=7); ax.grid(alpha=0.3)

# ── (f) Absolute error vs hot inlet temperature ───────────────────────────────
ax = fig.add_subplot(gs[1, 2])
ax.scatter(df["hot_inlet_temp"], df["abs_err_Th_K"],
           c="tomato", s=25, alpha=0.7, label="T_h_out")
ax.scatter(df["hot_inlet_temp"], df["abs_err_Tc_K"],
           c="steelblue", s=25, alpha=0.7, label="T_c_out")
ax.axhline(1.0, color="green", lw=1, ls="--", label="1 K threshold")
ax.set_xlabel("Hot inlet temp [K]"); ax.set_ylabel("Abs error [K]")
ax.set_title("Error vs Hot inlet temp"); ax.legend(fontsize=7); ax.grid(alpha=0.3)

# ── (g–i) Temperature profiles for first 6 manual cases ──────────────────────
profile_labels = list(profile_store.keys())[:6]
for pi, plabel in enumerate(profile_labels):
    row = pi // 3 + 2 if pi < 3 else 2
    col = pi % 3
    if pi == 3:
        row = 2
    ax = fig.add_subplot(gs[2, pi % 3])
    p  = profile_store[plabel]
    ax.plot(p["xi"], p["Th"], color="tomato",    lw=2.0, label="T_hot (PINN)")
    ax.plot(p["xi"], p["Tc"], color="steelblue", lw=2.0, label="T_cold (PINN)")
    # DWSim endpoint markers
    ax.scatter([0], [p["Th_in"]], color="tomato", s=60, zorder=5)
    ax.scatter([1], [p["Th_out_dws"]], color="tomato", s=60, marker="D",
               zorder=5, label=f"DWSim Th_out={p['Th_out_dws']:.1f}K")
    ax.scatter([1], [p["Tc_in"]], color="steelblue", s=60, zorder=5)
    ax.scatter([0], [p["Tc_out_dws"]], color="steelblue", s=60, marker="D",
               zorder=5, label=f"DWSim Tc_out={p['Tc_out_dws']:.1f}K")
    ax.set_xlabel("ξ = x/L"); ax.set_ylabel("T [K]")
    ax.set_title(plabel, fontsize=8)
    ax.legend(fontsize=6); ax.grid(alpha=0.3)

# Legend for source colours
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0],[0], marker='o', color='w', markerfacecolor='tomato',    ms=8, label='Manual'),
    Line2D([0],[0], marker='o', color='w', markerfacecolor='steelblue', ms=8, label='Random LHS'),
]
fig.legend(handles=legend_elements, loc="upper center",
           ncol=2, fontsize=9, bbox_to_anchor=(0.5, 1.01))

plot_path = os.path.join(args.out_dir, "verification_plots.png")
plt.savefig(plot_path, dpi=150, bbox_inches="tight")
print(f"Plots saved  → {plot_path}")

# =============================================================================
# 8.  Per-case table printed at the end for easy reading
# =============================================================================
print("\n── Per-case results (" + "sorted by |err_Th|) ─────────────────────────────")
df_sorted = df.sort_values("abs_err_Th_K", ascending=False)
pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 140)
print(df_sorted[["label","cold_inlet_temp","hot_inlet_temp",
                 "cold_mass_flow","hot_mass_flow",
                 "Th_out_DWSim","Th_out_PINN","abs_err_Th_K",
                 "Tc_out_DWSim","Tc_out_PINN","abs_err_Tc_K",
                 "efficiency_DWSim","efficiency_PINN"]].to_string(index=False))

print(f"\n✓  Verification complete — all outputs in: {args.out_dir}/")