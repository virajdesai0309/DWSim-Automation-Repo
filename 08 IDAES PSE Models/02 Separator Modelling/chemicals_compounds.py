from chemicals import heat_capacity
from chemicals import volume
from chemicals import vapor_pressure
from chemicals import critical
from chemicals import identifiers
from chemicals import acentric
from chemicals import reaction

methane = "74-82-8"
ethane = "74-84-0"

'''
gas_molar_entropy_ethane = reaction.S0g("74-84-0") or 0
print(gas_molar_entropy_ethane)
liquid_molar_entropy_ethane = reaction.S0l("74-84-0") or 0
print(liquid_molar_entropy_ethane)
gas_heat_of_formation_ethane = reaction.Hfg("74-84-0") or 0
print(gas_heat_of_formation_ethane)
liquid_heat_of_formation_ethane = reaction.Hfl("74-84-0") or 0
print(liquid_heat_of_formation_ethane)

omega_ethane = acentric.omega("74-84-0")
print(omega_ethane)
Mw_ethane = identifiers.MW("74-84-0")
print(Mw_ethane)
Pc = critical.Pc(ethane)
print(Pc)
Tc_ethane = critical.Tc(ethane)
print(Tc_ethane)
ethane_cp = heat_capacity.Cp_data_Perry_Table_153_114.loc[ethane]
print(ethane_cp)

ethane_density = volume.rho_data_Perry_8E_105_l.loc[ethane]
print(ethane_density)
'''

'''
ethane_ideal_gas_heat_capacity = heat_capacity.Cp_data_Poling.loc[ethane]
print(ethane_ideal_gas_heat_capacity)

'''
ethane_vapor_pressure = vapor_pressure.Psat_data_AntoinePoling.loc[ethane].iloc[3]
print(ethane_vapor_pressure)
