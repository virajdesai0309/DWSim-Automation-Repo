#################################################################################
# This file demonstrates the creation of a property package
# using the IDAES Generic Property Package Framework.
#
# The property package includes thermodynamic properties
# and phase equilibrium calculations for pure methane, oxygen, carbon dioxide, water, and nitrogen.
#################################################################################
"""
Property package for methane-oxygen-carbon dioxide-water-nitrogen using ideal liquid and vapor.

Example property package using the Generic Property Package Framework.
This example shows how to set up a property package to do phase equilibrium
in the generic framework using ideal liquid and vapor assumptions along with
methods drawn from the pre-built IDAES property libraries.
"""

__author__ = "Viraj Desai"
__date__ = "2024-06-01"

# Import Pyomo units
from pyomo.environ import units as pyunits

# Import IDAES cores
from idaes.core import LiquidPhase, VaporPhase, Component
import idaes.logger as idaeslog

from idaes.models.properties.modular_properties.state_definitions import FTPx
from idaes.models.properties.modular_properties.eos.ideal import Ideal
from idaes.models.properties.modular_properties.phase_equil import SmoothVLE
from idaes.models.properties.modular_properties.phase_equil.bubble_dew import (
    IdealBubbleDew,
)
from idaes.models.properties.modular_properties.phase_equil.forms import fugacity
from idaes.models.properties.modular_properties.pure import Perrys
from idaes.models.properties.modular_properties.pure import RPP5
from idaes.core import PhaseType as PT

# Import the Chemicals
import chemicals
from chemicals.critical import Pc, Tc
from chemicals.heat_capacity import Cp_data_Poling
from chemicals.identifiers import MW
from chemicals.vapor_pressure import Psat_data_AntoinePoling
from chemicals.volume import rho_data_Perry_8E_105_l

# Import DIPPR vapor pressure correlation
from perry import Dippr101
R_value = 8.31446261815324  # J/(mol*K)

# Set up logger
_log = idaeslog.getLogger(__name__)

'''
# Data Sources:
# Values are obtained from the chemicals library which uses data from NIST, Perry's Handbook, etc.
# The chemicals library provides a convenient interface to access chemical properties using CAS numbers.
'''

configuration = {
    # Specifying components
    "components": {
        "methane": {
            "type": Component,
            "valid_phase_types": PT.vaporPhase,
            "elemental_composition": {"C": 1, "H": 4},
            "dens_mol_liq_comp": Perrys,
            "enth_mol_liq_comp": Perrys,
            "enth_mol_ig_comp": RPP5,
            "entr_mol_ig_comp": RPP5,
            "pressure_sat_comp": RPP5,
            # "phase_equilibrium_form": {("Vap", "Liq"): fugacity},
            "parameter_data": {
                "mw": (chemicals.identifiers.MW(ID="74-82-8") / 1000, pyunits.kg / pyunits.mol),
                "pressure_crit": (chemicals.critical.Pc(CASRN="74-82-8"), pyunits.Pa),
                "temperature_crit": (chemicals.critical.Tc(CASRN="74-82-8"), pyunits.K),
                "dens_mol_liq_comp_coeff": {
                    "eqn_type": 1,
                    "1": (chemicals.volume.rho_data_Perry_8E_105_l.loc["74-82-8"][1] / 1000, pyunits.kmol * pyunits.m**-3),
                    "2": (chemicals.volume.rho_data_Perry_8E_105_l.loc["74-82-8"][2], None),
                    "3": (chemicals.volume.rho_data_Perry_8E_105_l.loc["74-82-8"][3], pyunits.K),
                    "4": (chemicals.volume.rho_data_Perry_8E_105_l.loc["74-82-8"][4], None),
                },
                "cp_mol_ig_comp_coeff": {
                    "a0": (Cp_data_Poling.loc["74-82-8"][3]/R_value, None),
                    "a1": (Cp_data_Poling.loc["74-82-8"][4]/R_value, pyunits.K**-1),
                    "a2": (Cp_data_Poling.loc["74-82-8"][5]/R_value, pyunits.K**-2),
                    "a3": (Cp_data_Poling.loc["74-82-8"][6]/R_value, pyunits.K**-3),
                    "a4": (Cp_data_Poling.loc["74-82-8"][7]/R_value, pyunits.K**-4),
                },
                "cp_mol_liq_comp_coeff": {
                    "1": (chemicals.heat_capacity.Cp_data_Perry_Table_153_114.loc["74-82-8"][1], pyunits.J / pyunits.kmol / pyunits.K),
                    "2": (chemicals.heat_capacity.Cp_data_Perry_Table_153_114.loc["74-82-8"][2], pyunits.J / pyunits.kmol / pyunits.K**2),
                    "3": (chemicals.heat_capacity.Cp_data_Perry_Table_153_114.loc["74-82-8"][3], pyunits.J / pyunits.kmol / pyunits.K**3),
                    "4": (chemicals.heat_capacity.Cp_data_Perry_Table_153_114.loc["74-82-8"][4], pyunits.J / pyunits.kmol / pyunits.K**4),
                    "5": (chemicals.heat_capacity.Cp_data_Perry_Table_153_114.loc["74-82-8"][5], pyunits.J / pyunits.kmol / pyunits.K**5),
                },
                "enth_mol_form_liq_comp_ref": (0, pyunits.J / pyunits.mol),
                "enth_mol_form_vap_comp_ref": (chemicals.reaction.Hfg(CASRN="74-82-8"), pyunits.J / pyunits.mol),
                "entr_mol_form_liq_comp_ref": (0, pyunits.J / pyunits.mol / pyunits.K),
                "entr_mol_form_vap_comp_ref": (chemicals.reaction.S0g(CASRN="74-82-8"), pyunits.J / pyunits.mol / pyunits.K),
                "pressure_sat_comp_coeff": {
                    "A": (chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["74-82-8"][1], None),
                    "B": (chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["74-82-8"][2], pyunits.K),
                    "C": (chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["74-82-8"][3], pyunits.K),
                },
            },
        },
        "oxygen": {
            "type": Component,
            "valid_phase_types": PT.vaporPhase,
            "elemental_composition": {"O": 2},
            "dens_mol_liq_comp": Perrys,
            "enth_mol_liq_comp": Perrys,
            "enth_mol_ig_comp": RPP5,
            "entr_mol_ig_comp": RPP5,
            "pressure_sat_comp": RPP5,
            # "phase_equilibrium_form": {("Vap", "Liq"): fugacity},
            "parameter_data": {
                "mw": (chemicals.identifiers.MW(ID="7782-44-7") / 1000, pyunits.kg / pyunits.mol),
                "pressure_crit": (chemicals.critical.Pc(CASRN="7782-44-7"), pyunits.Pa),
                "temperature_crit": (chemicals.critical.Tc(CASRN="7782-44-7"), pyunits.K),
                "dens_mol_liq_comp_coeff": {
                    "eqn_type": 1,
                    "1": (chemicals.volume.rho_data_Perry_8E_105_l.loc["7782-44-7"][1] / 1000, pyunits.kmol * pyunits.m**-3),
                    "2": (chemicals.volume.rho_data_Perry_8E_105_l.loc["7782-44-7"][2], None),
                    "3": (chemicals.volume.rho_data_Perry_8E_105_l.loc["7782-44-7"][3], pyunits.K),
                    "4": (chemicals.volume.rho_data_Perry_8E_105_l.loc["7782-44-7"][4], None),
                },
                "cp_mol_ig_comp_coeff": {
                    "a0": (Cp_data_Poling.loc["7782-44-7"][3]/R_value, None),
                    "a1": (Cp_data_Poling.loc["7782-44-7"][4]/R_value, pyunits.K**-1),
                    "a2": (Cp_data_Poling.loc["7782-44-7"][5]/R_value, pyunits.K**-2),
                    "a3": (Cp_data_Poling.loc["7782-44-7"][6]/R_value, pyunits.K**-3),
                    "a4": (Cp_data_Poling.loc["7782-44-7"][7]/R_value, pyunits.K**-4),
                },
                "cp_mol_liq_comp_coeff": {
                    "1": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7782-44-7"][1], pyunits.J / pyunits.kmol / pyunits.K),
                    "2": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7782-44-7"][2], pyunits.J / pyunits.kmol / pyunits.K**2),
                    "3": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7782-44-7"][3], pyunits.J / pyunits.kmol / pyunits.K**3),
                    "4": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7782-44-7"][4], pyunits.J / pyunits.kmol / pyunits.K**4),
                    "5": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7782-44-7"][5], pyunits.J / pyunits.kmol / pyunits.K**5),
                },
                "enth_mol_form_liq_comp_ref": (0, pyunits.J / pyunits.mol),
                "enth_mol_form_vap_comp_ref": (chemicals.reaction.Hfg(CASRN="7782-44-7"), pyunits.J / pyunits.mol),
                "entr_mol_form_liq_comp_ref": (0, pyunits.J / pyunits.mol / pyunits.K),
                "entr_mol_form_vap_comp_ref": (chemicals.reaction.S0g(CASRN="7782-44-7"), pyunits.J / pyunits.mol / pyunits.K),
                "pressure_sat_comp_coeff": {
                    "A": (chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["7782-44-7"][1], None),
                    "B": (chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["7782-44-7"][2], pyunits.K),
                    "C": (chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["7782-44-7"][3], pyunits.K),
                },
            },
        },
        "carbon_dioxide": {
            "type": Component,
            "valid_phase_types": PT.vaporPhase,
            "elemental_composition": {"C": 1, "O": 2},
            "dens_mol_liq_comp": Perrys,
            "enth_mol_liq_comp": Perrys,
            "enth_mol_ig_comp": RPP5,
            "entr_mol_ig_comp": RPP5,
            "pressure_sat_comp": Dippr101,
            # "phase_equilibrium_form": {("Vap", "Liq"): fugacity},
            "parameter_data": {
                "mw": (chemicals.identifiers.MW(ID="124-38-9") / 1000, pyunits.kg / pyunits.mol),
                "pressure_crit": (chemicals.critical.Pc(CASRN="124-38-9"), pyunits.Pa),
                "temperature_crit": (chemicals.critical.Tc(CASRN="124-38-9"), pyunits.K),
                "dens_mol_liq_comp_coeff": {
                    "eqn_type": 1,
                    "1": (chemicals.volume.rho_data_Perry_8E_105_l.loc["124-38-9"][1] / 1000, pyunits.kmol * pyunits.m**-3),
                    "2": (chemicals.volume.rho_data_Perry_8E_105_l.loc["124-38-9"][2], None),
                    "3": (chemicals.volume.rho_data_Perry_8E_105_l.loc["124-38-9"][3], pyunits.K),
                    "4": (chemicals.volume.rho_data_Perry_8E_105_l.loc["124-38-9"][4], None),
                },
                "cp_mol_ig_comp_coeff": {
                    "a0": (Cp_data_Poling.loc["124-38-9"][3]/R_value, None),
                    "a1": (Cp_data_Poling.loc["124-38-9"][4]/R_value, pyunits.K**-1),
                    "a2": (Cp_data_Poling.loc["124-38-9"][5]/R_value, pyunits.K**-2),
                    "a3": (Cp_data_Poling.loc["124-38-9"][6]/R_value, pyunits.K**-3),
                    "a4": (Cp_data_Poling.loc["124-38-9"][7]/R_value, pyunits.K**-4),
                },
                "cp_mol_liq_comp_coeff": {
                    "1": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["124-38-9"][1], pyunits.J / pyunits.kmol / pyunits.K),
                    "2": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["124-38-9"][2], pyunits.J / pyunits.kmol / pyunits.K**2),
                    "3": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["124-38-9"][3], pyunits.J / pyunits.kmol / pyunits.K**3),
                    "4": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["124-38-9"][4], pyunits.J / pyunits.kmol / pyunits.K**4),
                    "5": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["124-38-9"][5], pyunits.J / pyunits.kmol / pyunits.K**5),
                },
                "enth_mol_form_liq_comp_ref": (0, pyunits.J / pyunits.mol),
                "enth_mol_form_vap_comp_ref": (chemicals.reaction.Hfg(CASRN="124-38-9"), pyunits.J / pyunits.mol),
                "entr_mol_form_liq_comp_ref": (0, pyunits.J / pyunits.mol / pyunits.K),
                "entr_mol_form_vap_comp_ref": (chemicals.reaction.S0g(CASRN="124-38-9"), pyunits.J / pyunits.mol / pyunits.K),
                "pressure_sat_comp_coeff": {
                    "A": (chemicals.vapor_pressure.Psat_data_Perrys2_8.loc["124-38-9"][1], None),
                    "B": (chemicals.vapor_pressure.Psat_data_Perrys2_8.loc["124-38-9"][2], None),
                    "C": (chemicals.vapor_pressure.Psat_data_Perrys2_8.loc["124-38-9"][3], None),
                    "D": (chemicals.vapor_pressure.Psat_data_Perrys2_8.loc["124-38-9"][4], None),
                    "E": (chemicals.vapor_pressure.Psat_data_Perrys2_8.loc["124-38-9"][5], None),
                },
            },
        },
        "water": {
            "type": Component,
            "valid_phase_types": PT.vaporPhase,
            "elemental_composition": {"H": 2, "O": 1},
            "dens_mol_liq_comp": Perrys,
            "enth_mol_liq_comp": Perrys,
            "enth_mol_ig_comp": RPP5,
            "entr_mol_ig_comp": RPP5,
            "pressure_sat_comp": RPP5,
            # "phase_equilibrium_form": {("Vap", "Liq"): fugacity},
            "parameter_data": {
                "mw": (chemicals.identifiers.MW(ID="7732-18-5") / 1000, pyunits.kg / pyunits.mol),
                "pressure_crit": (chemicals.critical.Pc(CASRN="7732-18-5"), pyunits.Pa),
                "temperature_crit": (chemicals.critical.Tc(CASRN="7732-18-5"), pyunits.K),
                "dens_mol_liq_comp_coeff": {
                    "eqn_type": 1,
                    "1": (5.459, pyunits.kmol * pyunits.m**-3),
                    "2": (0.30542, None),
                    "3": (647.13, pyunits.K),
                    "4": (0.081, None),
                },
                "cp_mol_ig_comp_coeff": {
                    "a0": (Cp_data_Poling.loc["7732-18-5"][3]/R_value, None),
                    "a1": (Cp_data_Poling.loc["7732-18-5"][4]/R_value, pyunits.K**-1),
                    "a2": (Cp_data_Poling.loc["7732-18-5"][5]/R_value, pyunits.K**-2),
                    "a3": (Cp_data_Poling.loc["7732-18-5"][6]/R_value, pyunits.K**-3),
                    "a4": (Cp_data_Poling.loc["7732-18-5"][7]/R_value, pyunits.K**-4),
                },
                "cp_mol_liq_comp_coeff": {
                    "1": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7732-18-5"][1], pyunits.J / pyunits.kmol / pyunits.K),
                    "2": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7732-18-5"][2], pyunits.J / pyunits.kmol / pyunits.K**2),
                    "3": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7732-18-5"][3], pyunits.J / pyunits.kmol / pyunits.K**3),
                    "4": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7732-18-5"][4], pyunits.J / pyunits.kmol / pyunits.K**4),
                    "5": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7732-18-5"][5], pyunits.J / pyunits.kmol / pyunits.K**5),
                },
                "enth_mol_form_liq_comp_ref": (0, pyunits.J / pyunits.mol),
                "enth_mol_form_vap_comp_ref": (chemicals.reaction.Hfg(CASRN="7732-18-5"), pyunits.J / pyunits.mol),
                "entr_mol_form_liq_comp_ref": (0, pyunits.J / pyunits.mol / pyunits.K),
                "entr_mol_form_vap_comp_ref": (chemicals.reaction.S0g(CASRN="7732-18-5"), pyunits.J / pyunits.mol / pyunits.K),
                "pressure_sat_comp_coeff": {
                    "A": (chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["7732-18-5"][1], None),
                    "B": (chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["7732-18-5"][2], pyunits.K),
                    "C": (chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["7732-18-5"][3], pyunits.K),
                },
            },
        },
        "nitrogen": {
            "type": Component,
            "valid_phase_types": PT.vaporPhase,
            "elemental_composition": {"N": 2},
            "dens_mol_liq_comp": Perrys,
            "enth_mol_liq_comp": Perrys,
            "enth_mol_ig_comp": RPP5,
            "entr_mol_ig_comp": RPP5,
            "pressure_sat_comp": RPP5,
            # "phase_equilibrium_form": {("Vap", "Liq"): fugacity},
            "parameter_data": {
                "mw": (chemicals.identifiers.MW(ID="7727-37-9") / 1000, pyunits.kg / pyunits.mol),
                "pressure_crit": (chemicals.critical.Pc(CASRN="7727-37-9"), pyunits.Pa),
                "temperature_crit": (chemicals.critical.Tc(CASRN="7727-37-9"), pyunits.K),
                "dens_mol_liq_comp_coeff": {
                    "eqn_type": 1,
                    "1": (chemicals.volume.rho_data_Perry_8E_105_l.loc["7727-37-9"][1] / 1000, pyunits.kmol * pyunits.m**-3),
                    "2": (chemicals.volume.rho_data_Perry_8E_105_l.loc["7727-37-9"][2], None),
                    "3": (chemicals.volume.rho_data_Perry_8E_105_l.loc["7727-37-9"][3], pyunits.K),
                    "4": (chemicals.volume.rho_data_Perry_8E_105_l.loc["7727-37-9"][4], None),
                },
                "cp_mol_ig_comp_coeff": {
                    "a0": (Cp_data_Poling.loc["7727-37-9"][3]/R_value, None),
                    "a1": (Cp_data_Poling.loc["7727-37-9"][4]/R_value, pyunits.K**-1),
                    "a2": (Cp_data_Poling.loc["7727-37-9"][5]/R_value, pyunits.K**-2),
                    "a3": (Cp_data_Poling.loc["7727-37-9"][6]/R_value, pyunits.K**-3),
                    "a4": (Cp_data_Poling.loc["7727-37-9"][7]/R_value, pyunits.K**-4),
                },
                "cp_mol_liq_comp_coeff": {
                    "1": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7727-37-9"][1], pyunits.J / pyunits.kmol / pyunits.K),
                    "2": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7727-37-9"][2], pyunits.J / pyunits.kmol / pyunits.K**2),
                    "3": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7727-37-9"][3], pyunits.J / pyunits.kmol / pyunits.K**3),
                    "4": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7727-37-9"][4], pyunits.J / pyunits.kmol / pyunits.K**4),
                    "5": (chemicals.heat_capacity.Cp_data_Perry_Table_153_100.loc["7727-37-9"][5], pyunits.J / pyunits.kmol / pyunits.K**5),
                },
                "enth_mol_form_liq_comp_ref": (0, pyunits.J / pyunits.mol),
                "enth_mol_form_vap_comp_ref": (chemicals.reaction.Hfg(CASRN="7727-37-9"), pyunits.J / pyunits.mol),
                "entr_mol_form_liq_comp_ref": (0, pyunits.J / pyunits.mol / pyunits.K),
                "entr_mol_form_vap_comp_ref": (chemicals.reaction.S0g(CASRN="7727-37-9"), pyunits.J / pyunits.mol / pyunits.K),
                "pressure_sat_comp_coeff": {
                    "A": (chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["7727-37-9"][1], None),
                    "B": (chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["7727-37-9"][2], pyunits.K),
                    "C": (chemicals.vapor_pressure.Psat_data_AntoinePoling.loc["7727-37-9"][3], pyunits.K),
                },
            },
        },
    },
    # Specifying phases
    "phases": {
        #"Liq": {"type": LiquidPhase, "equation_of_state": Ideal},
        "Vap": {"type": VaporPhase, "equation_of_state": Ideal},
    },
    # Set base units of measurement
    "base_units": {
        "time": pyunits.s,
        "length": pyunits.m,
        "mass": pyunits.kg,
        "amount": pyunits.mol,
        "temperature": pyunits.K,
    },
    # Specifying state definition
    "state_definition": FTPx,
    "state_bounds": {
        "flow_mol": (0, 100, 1000, pyunits.mol / pyunits.s),
        "temperature": (273.15, 300, 2500, pyunits.K),
        "pressure": (5e4, 1e5, 1e6, pyunits.Pa),
    },
    "pressure_ref": (1e5, pyunits.Pa),
    "temperature_ref": (300, pyunits.K),
    # Defining phase equilibria
    #"phases_in_equilibrium": [("Vap", "Liq")],
    #"phase_equilibrium_state": {("Vap", "Liq"): SmoothVLE},
    #"bubble_dew_method": IdealBubbleDew,
}
