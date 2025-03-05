import os
os.environ["PYTHONNET_RUNTIME"] = "coreclr"
import clr
import numpy as np
import time
from datetime import timedelta
from joblib import Parallel, delayed

from pythonnet import load
load("coreclr")

from System.IO import Directory, Path, File
from System import String, Environment
from System import Array

dwsimpath = "/usr/local/lib/dwsim/"

clr.AddReference(dwsimpath + "CapeOpen.dll")
clr.AddReference(dwsimpath + "DWSIM.Automation.dll")
clr.AddReference(dwsimpath + "DWSIM.Interfaces.dll")
clr.AddReference(dwsimpath + "DWSIM.GlobalSettings.dll")
clr.AddReference(dwsimpath + "DWSIM.SharedClasses.dll")
clr.AddReference(dwsimpath + "DWSIM.Thermodynamics.dll")
clr.AddReference(dwsimpath + "DWSIM.UnitOperations.dll")
clr.AddReference(dwsimpath + "DWSIM.Inspector.dll")
clr.AddReference(dwsimpath + "System.Buffers.dll")
clr.AddReference(dwsimpath + "DWSIM.Thermodynamics.ThermoC.dll")

from DWSIM.Interfaces.Enums.GraphicObjects import ObjectType
from DWSIM.Thermodynamics import Streams, PropertyPackages
from DWSIM.UnitOperations import UnitOperations
from DWSIM.Automation import Automation3
from DWSIM.GlobalSettings import Settings

Directory.SetCurrentDirectory(dwsimpath)

interf = Automation3()

file_path = "/home/viraj/Documents/Github/DWSim Automation Parallel Processing/Parallel Processing Test.dwxmz"

sim = interf.LoadFlowsheet(file_path)

# Get necessary objects
one = sim.GetObject("1").GetAsObject()
pump_1 = sim.GetObject("PUMP-1").GetAsObject()
HT_1 = sim.GetObject("HT-1").GetAsObject()

# Define ranges using numpy linspace (start, stop, num_points)
mass_flows = np.linspace(5, 15, 5)          # 5 evenly spaced points between 5 and 15
pressures = np.linspace(100000, 300000, 5)  # 5 evenly spaced points
temperatures = np.linspace(300, 323.15, 5)      # 5 evenly spaced points
delta_qs = np.linspace(2, 8, 5)             # 5 evenly spaced points
efficiencies = np.linspace(65, 85, 5)       # 5 evenly spaced points

# Run simulations


start_time = time.time()

def run_simulation(params):
    mass_flow, pressure, temperature, delta_q, efficiency = params
    
    # Set parameters
    one.SetMassFlow(mass_flow)
    one.SetPressure(pressure)
    one.SetTemperature(temperature)
    pump_1.set_DeltaQ(delta_q)
    pump_1.set_Eficiencia(efficiency)

    # Run calculation
    Settings.SolverMode = 0
    errors = interf.CalculateFlowsheet2(sim)

# Create parameter combinations
param_combinations = [
    (mass_flow, pressure, temperature, delta_q, efficiency)
    for mass_flow in mass_flows
    for pressure in pressures
    for temperature in temperatures
    for delta_q in delta_qs
    for efficiency in efficiencies
]

# Run parallel simulations
# Using 'threading' backend since we're working with COM objects
n_jobs = -1  # Use all available CPU cores
Parallel(n_jobs=n_jobs, backend='threading')(
    delayed(run_simulation)(params) for params in param_combinations
)

end_time = time.time()
total_time = end_time - start_time

print(f"\nTotal execution time: {timedelta(seconds=int(total_time))}")
