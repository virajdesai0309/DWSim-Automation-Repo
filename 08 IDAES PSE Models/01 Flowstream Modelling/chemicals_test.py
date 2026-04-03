import chemicals
from chemicals.critical import Pc, Tc
from chemicals.heat_capacity import Cp_data_Poling
from chemicals.identifiers import MW
from chemicals.reaction import Hfl, Hfg, S0l, S0g
from chemicals.vapor_pressure import Psat_data_AntoinePoling
from pyomo.environ import units as pyunits
'''
print("Methane MW:", chemicals.identifiers.MW(ID="74-82-8"))
print("Methane Pc:", chemicals.critical.Pc(CASRN="74-82-8"))
print("Methane Tc:", chemicals.critical.Tc(CASRN="74-82-8"))
print("Methane Cp data (Poling):", chemicals.heat_capacity.Cp_data_Poling.loc["74-82-8"])
print("Methane Psat data (Antoine Poling):", chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["74-82-8"])
print("Methane Hfl:", chemicals.reaction.Hfl(CASRN="74-82-8"))
print("Methane Hfg:", chemicals.reaction.Hfg(CASRN="74-82-8"))
print("Methane S0l:", chemicals.reaction.S0l(CASRN="74-82-8"))
print("Methane S0g:", chemicals.reaction.S0g(CASRN="74-82-8"))
'''
print("Value of R", pyunits.R, "J/mol-K")
print("Nitrogen MW:", chemicals.identifiers.MW(ID="7727-37-9"))
print("Nitrogen Pc:", chemicals.critical.Pc(CASRN="7727-37-9"))
print("Nitrogen Tc:", chemicals.critical.Tc(CASRN="7727-37-9"))
print("Nitrogen Cp data (Poling):", chemicals.heat_capacity.Cp_data_Poling.loc["7727-37-9"])
print("Nitrogen Hfl:", chemicals.reaction.Hfl(CASRN="7727-37-9"))
print("Nitrogen Hfg:", chemicals.reaction.Hfg(CASRN="7727-37-9"))
print("Nitrogen S0l:", chemicals.reaction.S0l(CASRN="7727-37-9"))
print("Nitrogen S0g:", chemicals.reaction.S0g(CASRN="7727-37-9"))
print("Nitrogen liquid heat capacity data (Perry's):", chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7727-37-9"])
print("Nitrogen Psat data (Antoine Extended):", chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["7727-37-9"])
print("Nitrogen density data (Perry's):", chemicals.volume.rho_data_Perry_8E_105_l.loc["7727-37-9"])