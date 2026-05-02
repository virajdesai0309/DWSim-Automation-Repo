import os
os.environ["PYTHONNET_RUNTIME"] = "coreclr"
os.environ["DOTNET_SYSTEM_DRAWING_USE_GDIPLUS"] = "1"

import clr
import numpy as np
import time
from datetime import timedelta
from pythonnet import load
from System import Environment, Array, String

# Load .NET Core runtime
load("coreclr")

# Try to import System.IO; fallback to os.chdir if it fails
try:
    from System.IO import Directory, Path, File
    use_dotnet_dir = True
except Exception as e:
    print(f"Note: System.IO import failed ({e}), using os.chdir instead")
    import os
    use_dotnet_dir = False

# Define DWSIM path
dwsimpath = "/usr/local/lib/dwsim/"

# Set working directory
if use_dotnet_dir:
    Directory.SetCurrentDirectory(dwsimpath)
else:
    os.chdir(dwsimpath)

# Add DWSIM assemblies
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

# Now import DWSIM types
from DWSIM.Interfaces.Enums.GraphicObjects import ObjectType
from DWSIM.Thermodynamics import Streams, PropertyPackages
from DWSIM.UnitOperations import UnitOperations
from DWSIM.Automation import Automation3
from DWSIM.GlobalSettings import Settings

print("DWSIM imports successful!")

# Create an instance of the Automation3 class from the DWSIM.Automation module
# This class provides methods for automating tasks in DWSIM, such as creating and manipulating flowsheets
interf = Automation3()

# Set the file path of an existing DWSIM flowsheet to be loaded using the Path.Combine method from the System.IO module
# The flowsheet file path is constructed using the Environment.GetFolderPath method to obtain the path to the desktop folder and the relative path to the flowsheet file
fileNameToLoad = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Desktop), "/workspace/09_Clould_Based_Simulations/dwsim_model_files/01_Water_Pump_Model.dwxmz")

# Load the DWSIM flowsheet using the LoadFlowsheet method of the Automation3 class
# The method takes a single argument, which is the file path of the flowsheet to be loaded
# The method returns a Simulation object that represents the loaded flowsheet
sim = interf.LoadFlowsheet(fileNameToLoad)

one = sim.GetObject("1")
two = sim.GetObject("2")
pump = sim.GetObject("PUMP-1")

one = one.GetAsObject()
two = two.GetAsObject()
pump = pump.GetAsObject()

one_massflow = float(input("Enter the mass flow rate of the inlet stream (kg/s): "))
one_temperature = float(input("Enter the temperature of the inlet stream (K): "))
one_pressure = float(input("Enter the pressure of the inlet stream (Pa): "))

pump_outlet_pressure = float(input("Enter the desired outlet pressure of the pump (Pa): "))

one.SetMassFlow(one_massflow)
one.SetTemperature(one_temperature)
one.SetPressure(one_pressure)

pump.set_Pout(pump_outlet_pressure)

Settings.SolverMode = 0
errors = interf.CalculateFlowsheet4(sim)

print(f"Calculation completed with {errors} errors.")

# Retrieve and print the results
two_massflow = two.GetMassFlow()
two_temperature = two.GetTemperature()
two_pressure = two.GetPressure()

print(f"Outlet Stream Mass Flow Rate: {two_massflow:.2f} kg/s")
print(f"Outlet Stream Temperature: {two_temperature:.2f} K")
print(f"Outlet Stream Pressure: {two_pressure:.2f} Pa")

power_consumed = pump.get_DeltaQ()
print(f"Power Consumed by the Pump: {power_consumed:.2f} W")