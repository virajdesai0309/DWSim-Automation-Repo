"""
01_data_generation.py
=====================
Generates a dataset of Heat Exchanger (HEX) simulation results using
DWSIM automation. Uses Latin Hypercube Sampling (LHS) to sweep cold/hot
inlet temperatures and mass flow rates, collects all target outputs including
fixed geometry and fluid properties, and saves results to CSV for PINN training.

Columns in output CSV
---------------------
Inputs (vary per run):
    cold_inlet_temp     [K]
    cold_mass_flow      [kg/s]
    hot_inlet_temp      [K]
    hot_mass_flow       [kg/s]

Targets (from DWSim per run):
    thermal_efficiency  [%]
    cold_pressure_drop  [Pa]
    hot_pressure_drop   [Pa]
    global_htc          [W/m²·K]
    cold_outlet_temp    [K]
    hot_outlet_temp     [K]

Fixed geometry (constant, fetched once from DWSim):
    flow_direction      [str]   "CounterCurrent" or "CoCurrent"
    tube_di_mm          [mm]    tube inner diameter — as returned by DWSim API
    tube_di_m           [m]     tube inner diameter — converted to SI for PINN ODE
    tube_length         [m]     effective tube length — DWSim returns in metres
    number_of_tubes     [-]     tubes per shell

Fluid properties (hardcoded constants, water both sides):
    cp_hot              [J/kg·K]   4186.0
    cp_cold             [J/kg·K]   4186.0

Derived (computed here, not from DWSim):
    heat_transfer_area  [m²]    π × tube_di_m × tube_length × number_of_tubes
                                (used directly in PINN ODE as A_total)
"""

import os
import time
import numpy as np
import pandas as pd
import scipy.stats.qmc as qmc

# ---------------------------------------------------------------------------
# 1. DWSIM / .NET bootstrap
# ---------------------------------------------------------------------------
os.environ["PYTHONNET_RUNTIME"] = "coreclr"
os.environ["DOTNET_SYSTEM_DRAWING_USE_GDIPLUS"] = "1"

import clr
from pythonnet import load

load("coreclr")

from System.IO import Directory
from System import Environment

DWSIM_PATH = "/usr/local/lib/dwsim/"
Directory.SetCurrentDirectory(DWSIM_PATH)

for dll in [
    "CapeOpen.dll",
    "DWSIM.Automation.dll",
    "DWSIM.Interfaces.dll",
    "DWSIM.GlobalSettings.dll",
    "DWSIM.SharedClasses.dll",
    "DWSIM.Thermodynamics.dll",
    "DWSIM.UnitOperations.dll",
    "DWSIM.Inspector.dll",
    "System.Buffers.dll",
    "DWSIM.Thermodynamics.ThermoC.dll",
]:
    clr.AddReference(DWSIM_PATH + dll)

from DWSIM.Automation import Automation3
from DWSIM.GlobalSettings import Settings

print("DWSIM imports successful!")

# ---------------------------------------------------------------------------
# 2. Load the flowsheet
# ---------------------------------------------------------------------------
FLOWSHEET_PATH = "/workspace/02 Automation of HEX/02 Automation of HEX.dwxmz"

interf = Automation3()
sim = interf.LoadFlowsheet(FLOWSHEET_PATH)
print("Flowsheet loaded.")

HEX     = sim.GetObject("HX-1").GetAsObject()
COLD_IN  = sim.GetObject("Cold In").GetAsObject()
HOT_IN   = sim.GetObject("Hot In").GetAsObject()
COLD_OUT = sim.GetObject("Cold Out").GetAsObject()
HOT_OUT  = sim.GetObject("Hot Out").GetAsObject()

Settings.SolverMode = 0

# ---------------------------------------------------------------------------
# 3. Fetch fixed geometry ONCE (before the loop — not per iteration)
#    These are properties of the HEX design, not of the operating point.
# ---------------------------------------------------------------------------
st_props       = HEX.get_STProperties()
FLOW_DIRECTION = HEX.get_FlowDir().ToString()       # e.g. "CounterCurrent"
TUBE_DI_MM     = float(st_props.Tube_Di)            # [mm] — DWSim API returns mm
TUBE_DI_M      = TUBE_DI_MM / 1000.0               # [m]  — SI, used in ODE
TUBE_LENGTH    = float(st_props.Tube_Length)        # [m]  — DWSim returns metres
N_TUBES        = int(st_props.Tube_NumberPerShell)

# Derived geometry: total heat transfer area [m²]
# A_total = π × d_i(m) × L × N_tubes
# This is used directly in the PINN ODE as A_total
HEAT_TRANSFER_AREA = np.pi * TUBE_DI_M * TUBE_LENGTH * N_TUBES

# Fluid Cp — both sides water, constant 4186 J/kg·K across 288–373 K range
# (<0.5% variation — negligible for ODE physics loss)
CP_HOT  = 4186.0   # [J/kg·K]
CP_COLD = 4186.0   # [J/kg·K]

print("\n--- Fixed HEX Geometry (fetched once) ---")
print(f"  Flow direction     : {FLOW_DIRECTION}")
print(f"  Tube inner diam.   : {TUBE_DI_MM:.3f} mm  →  {TUBE_DI_M:.6f} m (SI)")
print(f"  Tube length        : {TUBE_LENGTH:.4f} m")
print(f"  Number of tubes    : {N_TUBES}")
print(f"  Heat transfer area : {HEAT_TRANSFER_AREA:.4f} m²")
print(f"  Cp (hot/cold)      : {CP_HOT} J/kg·K (water, constant)")
print("-----------------------------------------\n")

# ---------------------------------------------------------------------------
# 4. LHS sampling
# ---------------------------------------------------------------------------
# Bounds for the 4 varying inputs
# [cold_inlet_temp (K), cold_mass_flow (kg/s), hot_inlet_temp (K), hot_mass_flow (kg/s)]
BOUNDS = np.array([
    [288.15, 318.15],   # cold_inlet_temp
    [0.5,    5.5   ],   # cold_mass_flow
    [333.15, 373.15],   # hot_inlet_temp
    [0.5,    5.5   ],   # hot_mass_flow
])

N_SAMPLES = 30000   # ← change to 30000 for production run

sampler    = qmc.LatinHypercube(d=4, seed=42)
lhs_raw    = sampler.random(n=N_SAMPLES)
X_lhs      = qmc.scale(lhs_raw, BOUNDS[:, 0], BOUNDS[:, 1])
cases      = X_lhs.tolist()

# Count and log how many cases will be skipped (T_cold >= T_hot is impossible)
skippable = sum(1 for T_c, _, T_h, _ in cases if T_c >= T_h)
print(f"Total LHS cases     : {N_SAMPLES}")
print(f"Pre-skip (T_c>=T_h) : {skippable}  ({100*skippable/N_SAMPLES:.1f}%)")
print(f"Cases to simulate   : {N_SAMPLES - skippable}\n")

# ---------------------------------------------------------------------------
# 5. Checkpoint setup — prevents total loss if the run crashes mid-way
#    If OUTPUT_CSV already exists AND has the correct schema, resume.
#    If schema doesn't match (e.g. old column names), back up and start fresh.
# ---------------------------------------------------------------------------
OUTPUT_CSV       = "/workspace/11_PINN_Heat Exchanger/hex_dataset_PINN.csv"
CHECKPOINT_EVERY = 500   # flush to disk every N successful records

os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)

# Exact set of columns this script produces — used to validate any existing CSV
EXPECTED_COLUMNS = {
    "cold_inlet_temp", "cold_mass_flow", "hot_inlet_temp", "hot_mass_flow",
    "thermal_efficiency", "cold_pressure_drop", "hot_pressure_drop", "global_htc",
    "cold_outlet_temp", "hot_outlet_temp", "flow_direction",
    "tube_di_mm", "tube_di_m", "tube_length", "number_of_tubes",
    "heat_transfer_area", "cp_hot", "cp_cold",
}

records   = []
completed = 0

if os.path.exists(OUTPUT_CSV):
    df_existing   = pd.read_csv(OUTPUT_CSV)
    existing_cols = set(df_existing.columns.tolist())
    if EXPECTED_COLUMNS.issubset(existing_cols):
        completed = len(df_existing)
        records   = df_existing.to_dict("records")
        print(f"Resuming: {completed} records found with correct schema.\n")
    else:
        missing = EXPECTED_COLUMNS - existing_cols
        backup  = OUTPUT_CSV.replace(".csv", "_old_schema_backup.csv")
        os.rename(OUTPUT_CSV, backup)
        print(f"[WARNING] Existing CSV has incompatible schema.")
        print(f"          Missing columns : {missing}")
        print(f"          Backed up to    : {backup}")
        print(f"          Starting fresh.\n")

# ---------------------------------------------------------------------------
# 6. Simulation loop
# ---------------------------------------------------------------------------
failed  = 0
skipped = 0
t_start = time.time()

for idx, (T_c_in, m_c, T_h_in, m_h) in enumerate(cases, start=1):

    # Skip physically impossible combinations (cold hotter than hot)
    if T_c_in >= T_h_in:
        skipped += 1
        continue

    # If resuming, skip cases we already have
    # (assumes LHS order is deterministic, which it is with seed=42)
    simulated_so_far = len(records)
    if simulated_so_far >= completed and completed > 0:
        completed = 0   # reset flag once we've caught up
    elif completed > 0:
        completed -= 1
        continue

    # --- Set inlet conditions ---
    COLD_IN.SetTemperature(T_c_in)
    COLD_IN.SetMassFlow(m_c)
    HOT_IN.SetTemperature(T_h_in)
    HOT_IN.SetMassFlow(m_h)

    # --- Solve ---
    errors = interf.CalculateFlowsheet2(sim)
    if errors and len(errors) > 0:
        failed += 1
        continue

    # --- Collect outputs ---
    try:
        rec = {
            # Inputs (varying)
            "cold_inlet_temp":    T_c_in,
            "cold_mass_flow":     m_c,
            "hot_inlet_temp":     T_h_in,
            "hot_mass_flow":      m_h,

            # Targets from DWSim
            "thermal_efficiency": HEX.get_ThermalEfficiency(),
            "cold_pressure_drop": HEX.get_ColdSidePressureDrop(),
            "hot_pressure_drop":  HEX.get_HotSidePressureDrop(),
            "global_htc":         HEX.get_OverallCoefficient(),
            "cold_outlet_temp":   COLD_OUT.GetTemperature(),
            "hot_outlet_temp":    HOT_OUT.GetTemperature(),

            # Fixed geometry (same for every row — needed by PINN ODE)
            "flow_direction":     FLOW_DIRECTION,
            "tube_di_mm":         TUBE_DI_MM,          # [mm] — as returned by DWSim
            "tube_di_m":          TUBE_DI_M,           # [m]  — SI, use this in PINN ODE
            "tube_length":        TUBE_LENGTH,          # [m]
            "number_of_tubes":    N_TUBES,
            "heat_transfer_area": HEAT_TRANSFER_AREA,   # [m²] — derived: π×d_m×L×N

            # Fluid properties (constant, water)
            "cp_hot":             CP_HOT,              # [J/kg·K]
            "cp_cold":            CP_COLD,             # [J/kg·K]
        }
        records.append(rec)
    except Exception as e:
        failed += 1
        print(f"  [WARN] Case {idx}: output retrieval failed — {e}")
        continue

    # --- Progress log every 100 simulated records ---
    n_done = len(records)
    if n_done % 100 == 0:
        elapsed = time.time() - t_start
        rate    = n_done / elapsed if elapsed > 0 else 0
        remaining = (N_SAMPLES - skipped - failed - n_done)
        eta     = remaining / rate if rate > 0 else 0
        print(f"  [{n_done} records | case {idx}/{N_SAMPLES}] "
              f"Elapsed: {elapsed:.0f}s  ETA: {eta:.0f}s  "
              f"Skipped: {skipped}  Failed: {failed}")

    # --- Periodic checkpoint to disk ---
    if n_done % CHECKPOINT_EVERY == 0:
        pd.DataFrame(records).to_csv(OUTPUT_CSV, index=False)
        print(f"  [CHECKPOINT] {n_done} records saved to disk.")

# ---------------------------------------------------------------------------
# 7. Final save + sanity checks
# ---------------------------------------------------------------------------
df = pd.DataFrame(records)

print(f"\n--- Raw records collected: {len(df)} ---")
print(f"    Skipped (T_c >= T_h): {skipped}")
print(f"    Failed (DWSim error): {failed}")

# Sanity checks
print("\nNaN counts per column:")
print(df.isna().sum())

print("\nPhysical direction check (cold_out > cold_in):")
print((df["cold_outlet_temp"] > df["cold_inlet_temp"]).value_counts())

print("\nPhysical direction check (hot_out < hot_in):")
print((df["hot_outlet_temp"] < df["hot_inlet_temp"]).value_counts())

print(f"\nThermal efficiency range: "
      f"{df['thermal_efficiency'].min():.2f} – {df['thermal_efficiency'].max():.2f} %")

print(f"\nGlobal HTC range: "
      f"{df['global_htc'].min():.2f} – {df['global_htc'].max():.2f} W/m²·K")

# Verify geometry columns are constant (sanity check)
print(f"\nGeometry column unique values (should each be 1):")
for col in ["flow_direction", "tube_di_mm", "tube_di_m", "tube_length", "number_of_tubes", "heat_transfer_area"]:
    print(f"  {col}: {df[col].nunique()} unique value(s) → {df[col].iloc[0]}")

# Energy balance check: Q_hot ≈ Q_cold (same Cp, water both sides)
df["Q_hot"]  = df["hot_mass_flow"]  * CP_HOT  * (df["hot_inlet_temp"]  - df["hot_outlet_temp"])
df["Q_cold"] = df["cold_mass_flow"] * CP_COLD * (df["cold_outlet_temp"] - df["cold_inlet_temp"])
df["Q_balance_error_%"] = 100 * abs(df["Q_hot"] - df["Q_cold"]) / df["Q_hot"]
print(f"\nEnergy balance error — mean: {df['Q_balance_error_%'].mean():.3f}%  "
      f"max: {df['Q_balance_error_%'].max():.3f}%")

# Drop the diagnostic columns before saving
df.drop(columns=["Q_hot", "Q_cold", "Q_balance_error_%"], inplace=True)

# Final physics filter
df.dropna(inplace=True)
df = df[(df["thermal_efficiency"] > 0)  & (df["thermal_efficiency"] <= 100)]
df = df[(df["cold_outlet_temp"]   > df["cold_inlet_temp"])]
df = df[(df["hot_outlet_temp"]    < df["hot_inlet_temp"])]

df.to_csv(OUTPUT_CSV, index=False)
print(f"\n✓ Done. {len(df)} valid records saved to '{OUTPUT_CSV}'.")
print("\nFinal column summary:")
print(df.describe())