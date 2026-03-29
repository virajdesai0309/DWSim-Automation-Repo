import chemicals
from chemicals.critical import Pc, Tc
from chemicals.heat_capacity import Cp_data_Poling
from chemicals.identifiers import MW
from chemicals.reaction import Hfl, Hfg, S0l, S0g
from chemicals.vapor_pressure import Psat_data_AntoinePoling

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

print("Ethane MW:", chemicals.identifiers.MW(ID="124-38-9"))
print("Ethane Pc:", chemicals.critical.Pc(CASRN="124-38-9"))
print("Ethane Tc:", chemicals.critical.Tc(CASRN="124-38-9"))
print("Ethane Cp data (Poling):", chemicals.heat_capacity.Cp_data_Poling.loc["124-38-9"])
print("Ethane Hfl:", chemicals.reaction.Hfl(CASRN="124-38-9"))
print("Ethane Hfg:", chemicals.reaction.Hfg(CASRN="124-38-9"))
print("Ethane S0l:", chemicals.reaction.S0l(CASRN="124-38-9"))
print("Ethane S0g:", chemicals.reaction.S0g(CASRN="124-38-9"))
print("Ethane density data (Perry's):", chemicals.volume.rho_data_Perry_8E_105_l.loc["124-38-9"])
print("Ethane liquid heat capacity data (Perry's):", chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["124-38-9"])
print("Ethane Psat data (Antoine Extended):", chemicals.vapor_pressure.Psat_data_Perrys2_8.loc["124-38-9"])