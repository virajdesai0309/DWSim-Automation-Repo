"""
01_data_generation.py
=====================
Generates a dataset of Heat Exchanger (HEX) simulation results using
DWSIM automation. Sweeps cold/hot inlet temperatures and mass flow rates
over a defined parameter grid, collects all six target outputs, and saves
the results to a CSV file for ANN training.

Outputs (CSV columns)
---------------------
Inputs  : cold_inlet_temp   [K]
          cold_mass_flow     [kg/s]
          hot_inlet_temp    [K]
          hot_mass_flow      [kg/s]
Targets : thermal_efficiency  [-]
          cold_pressure_drop  [Pa]
          hot_pressure_drop   [Pa]
          global_htc          [W/m²K]
          cold_outlet_temp    [K]
          hot_outlet_temp     [K]
"""

import os
import itertools
import numpy as np
import pandas as pd
import time

# ---------------------------------------------------------------------------
# 1. DWSIM / .NET bootstrap
# ---------------------------------------------------------------------------
os.environ["PYTHONNET_RUNTIME"] = "coreclr"
os.environ["DOTNET_SYSTEM_DRAWING_USE_GDIPLUS"] = "1"

import clr
from pythonnet import load

load("coreclr")

from System.IO import Directory, Path
from System import Environment, Array, String

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

from DWSIM.Interfaces.Enums.GraphicObjects import ObjectType
from DWSIM.Thermodynamics import Streams, PropertyPackages
from DWSIM.UnitOperations import UnitOperations
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

# Grab objects
HEX    = sim.GetObject("HX-1").GetAsObject()
COLD_IN = sim.GetObject("Cold In").GetAsObject()
HOT_IN  = sim.GetObject("Hot In").GetAsObject()
COLD_OUT = sim.GetObject("Cold Out").GetAsObject()
HOT_OUT  = sim.GetObject("Hot Out").GetAsObject() 

Settings.SolverMode = 0

# ---------------------------------------------------------------------------
# 3. Parameter sweep definition
# ---------------------------------------------------------------------------
# Adjust these ranges to match your physical system.
# Keep ranges wide enough for ANN generalisation but physically sensible.

cold_inlet_temps  = np.arange(288.15, 318.15, 5.0)   # 15–45 °C  → K
cold_mass_flows   = np.arange(0.5,    5.5,    0.5)   # kg/s
hot_inlet_temps   = np.arange(333.15, 373.15, 5.0)   # 60–100 °C → K
hot_mass_flows    = np.arange(0.5,    5.5,    0.5)   # kg/s

param_grid = list(itertools.product(
    cold_inlet_temps, cold_mass_flows,
    hot_inlet_temps,  hot_mass_flows
))

total_cases = len(param_grid)
print(f"Total simulation cases: {total_cases}")

# ---------------------------------------------------------------------------
# 4. Run the sweep
# ---------------------------------------------------------------------------
records = []
failed  = 0
t_start = time.time()

for idx, (T_c_in, m_c, T_h_in, m_h) in enumerate(param_grid, start=1):

    # Skip physically impossible combinations
    if T_c_in >= T_h_in:
        continue

    # Set inlet conditions
    COLD_IN.SetTemperature(T_c_in)
    COLD_IN.SetMassFlow(m_c)
    HOT_IN.SetTemperature(T_h_in)
    HOT_IN.SetMassFlow(m_h)

    # Solve the flowsheet
    errors = interf.CalculateFlowsheet2(sim)

    if errors and len(errors) > 0:
        failed += 1
        continue  # skip converge failures

    # Collect outputs
    try:
        rec = {
            # --- inputs ---
            "cold_inlet_temp":   T_c_in,
            "cold_mass_flow":    m_c,
            "hot_inlet_temp":    T_h_in,
            "hot_mass_flow":     m_h,
            # --- targets ---
            "thermal_efficiency": HEX.get_ThermalEfficiency(),
            "cold_pressure_drop": HEX.get_ColdSidePressureDrop(),
            "hot_pressure_drop":  HEX.get_HotSidePressureDrop(),
            "global_htc":         HEX.get_OverallCoefficient(),
            "cold_outlet_temp":   COLD_OUT.GetTemperature(),
            "hot_outlet_temp":    HOT_OUT.GetTemperature(),
        }
        records.append(rec)
    except Exception as e:
        failed += 1
        print(f"  [WARN] Case {idx}: output retrieval failed – {e}")
        continue

    # Progress log every 100 cases
    if idx % 100 == 0:
        elapsed = time.time() - t_start
        eta = elapsed / idx * (total_cases - idx)
        print(f"  [{idx}/{total_cases}] Elapsed: {elapsed:.0f}s  ETA: {eta:.0f}s  "
              f"Records: {len(records)}  Failed: {failed}")

# ---------------------------------------------------------------------------
# 5. Save to CSV
# ---------------------------------------------------------------------------
df = pd.DataFrame(records)
print(f"Raw records: {len(df)}")
print(df.head(10).to_string())
print("\nDescribe:")
print(df.describe())
print("\nNaN counts:")
print(df.isna().sum())
print("\nSample cold_outlet_temp > cold_inlet_temp check:")
print((df["cold_outlet_temp"] > df["cold_inlet_temp"]).value_counts())
print("\nSample hot_outlet_temp < hot_inlet_temp check:")
print((df["hot_outlet_temp"] < df["hot_inlet_temp"]).value_counts())
print("\nThermal eff range:", df["thermal_efficiency"].min(), df["thermal_efficiency"].max())

# Basic sanity filter: drop rows with NaN or physically impossible values
df.dropna(inplace=True)
df = df[(df["thermal_efficiency"] > 0) & (df["thermal_efficiency"] <= 100)]  # percentage
df = df[(df["cold_outlet_temp"] > df["cold_inlet_temp"])]
df = df[(df["hot_outlet_temp"]  < df["hot_inlet_temp"])]

OUTPUT_CSV = "/workspace/10 Surrogate Models/hex_dataset.csv"
df.to_csv(OUTPUT_CSV, index=False)

print(f"\nDone. {len(df)} valid records saved to '{OUTPUT_CSV}'. "
      f"({failed} failed / skipped)")
print(df.describe())