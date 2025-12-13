"""
This script automates the creation and configuration of a DWSIM flowsheet using Python and pythonnet.
It performs the following tasks:
- Sets up the .NET runtime environment for DWSIM automation.
- Loads required DWSIM assemblies and modules.
- Initializes the DWSIM Automation interface and loads a template flowsheet.
- Adds chemical compounds (Methane, Ethane, Propane, Water, Carbon Dioxide, Nitrogen) to the simulation.
- Adds a material stream to the flowsheet and retrieves it as an object.
- Creates and assigns the Peng-Robinson (PR) property package to the stream.
- Sets initial conditions for the stream (temperature, pressure, mass flow, and composition).
- Specifies the flash calculation mode for the stream.
- Solves the flowsheet and prints any errors encountered.
- Saves the updated flowsheet to a specified file path.
"""

__author__ = "Viraj Parikh"
__date__ = "2024-06-10"

# Importing the necessary modules and setting up the .NET runtime environment
import os
os.environ["PYTHONNET_RUNTIME"] = "coreclr"
import clr
import numpy as np
import time
from datetime import timedelta

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

file_path = "/home/viraj/Documents/Github/DWSim-Automation-Repo/00 Template.dwxmz"

sim = interf.LoadFlowsheet(file_path)

# Adding compounds to the simulation
methane = sim.AddCompound("Methane")
ethane = sim.AddCompound("Ethane")
propane = sim.AddCompound("Propane")
water = sim.AddCompound("Water")
carbon_dioxide = sim.AddCompound("CarbonDioxide")
nitrogen = sim.AddCompound("Nitrogen")

# Adding streams to the simulation
stream1 = sim.AddFlowsheetObject("Material Stream", "Stream1")

# Getting them as objects
Stream1 = stream1.GetAsObject()

print("Compounds and Streams added successfully.")

# Configuring the property package
PR = sim.CreateAndAddPropertyPackage("Peng-Robinson (PR)")
print("Property Packages created successfully.")

# Assigning property packages to streams
Stream1.SetPropertyPackage(PR)
print("Property Packages assigned to streams successfully.")

# Setting initial conditions for Stream1
Stream1.SetTemperature(300)  # K
Stream1.SetPressure(101325)  # Pa
Stream1.SetMassFlow(10)      # kg/s
Stream1.SetOverallComposition(Array[float]([0.5, 0.2, 0.1, 0.1, 0.05, 0.05]))
print("Initial conditions for Stream1 set successfully.")

# Calculation modes for streams
Stream1.SetFlashSpec("PT")
print("Flash specifications set successfully.")

# Solving
errors = interf.CalculateFlowsheet4(sim)
print("Flowsheet calculated successfully.")
print("Errors (if any):", list(errors))

# Saving the file
fileNameToSave = "/home/viraj/Documents/Github/DWSim-Automation-Repo/00 FlowSheet Automation/00 Streams/00 Material Streams.dwxmz"
interf.SaveFlowsheet(sim, fileNameToSave, True)