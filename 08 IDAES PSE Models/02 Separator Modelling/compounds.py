"""
Hydrocarbon processing phase equilibrium package using Peng-Robinson EoS.

Example property package using the Generic Property Package Framework.
This example shows how to set up a property package to do hydrocarbon
processing phase equilibrium in the generic framework using Peng-Robinson
equation along with methods drawn from the pre-built IDAES property libraries.

The example includes the dictionary named configuration contains parameters
for calculating VLE phase equilibrium and properties for hydrocarbon processing.
"""

# Import Python libraries
import logging

# Import Pyomo units
from pyomo.environ import units as pyunits
from pyomo.environ import Var, log

# Import IDAES cores
from idaes.core import LiquidPhase, VaporPhase, Component, PhaseType as PT
from idaes.models.properties.modular_properties.state_definitions import FTPx
from idaes.models.properties.modular_properties.eos.ceos import Cubic, CubicType
from idaes.models.properties.modular_properties.phase_equil import SmoothVLE
from idaes.models.properties.modular_properties.phase_equil.bubble_dew import (
    LogBubbleDew,
)
from idaes.models.properties.modular_properties.phase_equil.forms import log_fugacity

from idaes.models.properties.modular_properties.pure import Perrys
from idaes.models.properties.modular_properties.pure import RPP4
from idaes.models.properties.modular_properties.pure import RPP5

from idaes.core.util.misc import set_param_from_config

# Set up logger
_log = logging.getLogger(__name__)

# Import chemicals
from chemicals import heat_capacity
from chemicals import volume
from chemicals import vapor_pressure
from chemicals import critical
from chemicals import identifiers
from chemicals import acentric
from chemicals import reaction

class RPP5_Safe(object):
    class cp_mol_ig_comp:
        @staticmethod
        def build_parameters(cobj):
            cobj.cp_mol_ig_comp_coeff_a0 = Var(
                doc = "Coefficient a0 for ideal gas heat capacity",
                units = pyunits.J / pyunits.mol / pyunits.K,
            )
            set_param_from_config(cobj, param = "cp_mol_ig_comp_coeff", index = "a0")

            cobj.cp_mol_ig_comp_coeff_a1 = Var(
                doc = "Coefficient a1 for ideal gas heat capacity",
                units = pyunits.J / pyunits.mol / pyunits.K**2,
            )
            set_param_from_config(cobj, param = "cp_mol_ig_comp_coeff", index = "a1")

            cobj.cp_mol_ig_comp_coeff_a2 = Var(
                doc = "Coefficient a2 for ideal gas heat capacity",
                units = pyunits.J / pyunits.mol / pyunits.K**3,
            )
            set_param_from_config(cobj, param = "cp_mol_ig_comp_coeff", index = "a2")

            cobj.cp_mol_ig_comp_coeff_a3 = Var(
                doc = "Coefficient a3 for ideal gas heat capacity",
                units = pyunits.J / pyunits.mol / pyunits.K**4,
            )
            set_param_from_config(cobj, param = "cp_mol_ig_comp_coeff", index = "a3")

            cobj.cp_mol_ig_comp_coeff_a4 = Var(
                doc = "Coefficient a4 for ideal gas heat capacity",
                units = pyunits.J / pyunits.mol / pyunits.K**5,
            )
            set_param_from_config(cobj, param = "cp_mol_ig_comp_coeff", index = "a4")

        @staticmethod
        def return_expression(b, cobj, T):
            # Specific heat capacity
            T = pyunits.convert(T, to_units=pyunits.K)

            cp = (
                cobj.cp_mol_ig_comp_coeff_a4 * T**4
                + cobj.cp_mol_ig_comp_coeff_a3 * T**3
                + cobj.cp_mol_ig_comp_coeff_a2 * T**2
                + cobj.cp_mol_ig_comp_coeff_a1 * T
                + cobj.cp_mol_ig_comp_coeff_a0
            )

            units = b.params.get_metadata().derived_units
            return pyunits.convert(cp, to_units=units.HEAT_CAPACITY_MOLE)

    class enth_mol_ig_comp:
        @staticmethod
        def build_parameters(cobj):
            if not hasattr(cobj, "cp_mol_ig_comp_coeff_a0"):
                RPP5_Safe.cp_mol_ig_comp.build_parameters(cobj)
            
            if hasattr(cobj.parent_block().config, "include_enthalpy_of_formation") and cobj.parent_block().config.include_enthalpy_of_formation:
                units = cobj.parent_block().get_metadata().derived_units

                cobj.enth_mol_form_vap_comp_ref = Var(
                    doc = "Vapor phase molar heat of formation @ Tref",
                    units = units.ENERGY_MOLE,
                )
                set_param_from_config(cobj, param = "enth_mol_form_vap_comp_ref")

        @staticmethod
        def return_expression(b, cobj, T):
            # Specific enthalpy
            T = pyunits.convert(T, to_units=pyunits.K)
            Tr = pyunits.convert(b.params.temperature_ref, to_units=pyunits.K)

            units = b.params.get_metadata().derived_units
            
            h_form = (
                cobj.enth_mol_form_vap_comp_ref
                if hasattr(b.params, "include_enthalpy_of_formation") and b.params.include_enthalpy_of_formation
                else 0 * units.ENERGY_MOLE
            )

            h = (
                pyunits.convert(
                    (cobj.cp_mol_ig_comp_coeff_a4 / 5) * (T**5 - Tr**5)
                    + (cobj.cp_mol_ig_comp_coeff_a3 / 4) * (T**4 - Tr**4)
                    + (cobj.cp_mol_ig_comp_coeff_a2 / 3) * (T**3 - Tr**3)
                    + (cobj.cp_mol_ig_comp_coeff_a1 / 2) * (T**2 - Tr**2)
                    + cobj.cp_mol_ig_comp_coeff_a0 * (T - Tr),
                    to_units=units.ENERGY_MOLE,
                )
                + h_form
            )
            return h
    
    class entr_mol_ig_comp:
        @staticmethod
        def build_parameters(cobj):
            if not hasattr(cobj, "cp_mol_ig_comp_coeff_a0"):
                RPP5_Safe.cp_mol_ig_comp.build_parameters(cobj)
            
            units = cobj.parent_block().get_metadata().derived_units

            cobj.entr_mol_form_vap_comp_ref = Var(
                doc = "Vapor phase molar entropy of formation @ Tref",
                units = units.ENTROPY_MOLE,
            )

            set_param_from_config(cobj, param = "entr_mol_form_vap_comp_ref")

        @staticmethod
        def return_expression(b, cobj, T):
            # Specific entropy
            T = pyunits.convert(T, to_units=pyunits.K)
            Tr = pyunits.convert(b.params.temperature_ref, to_units=pyunits.K)

            units = b.params.get_metadata().derived_units

            s = (
                pyunits.convert(
                    (cobj.cp_mol_ig_comp_coeff_a4 / 4) * (T**4 - Tr**4)
                    + (cobj.cp_mol_ig_comp_coeff_a3 / 3) * (T**3 - Tr**3)
                    + (cobj.cp_mol_ig_comp_coeff_a2 / 2) * (T**2 - Tr**2)
                    + cobj.cp_mol_ig_comp_coeff_a1 * (T - Tr)
                    + cobj.cp_mol_ig_comp_coeff_a0 * log(T / Tr),
                    to_units=units.ENTROPY_MOLE,
                )
            )
            return s

configuration = {
    # Specifying components
    "components": {
        "methane": {
            "type": Component,
            "elemental_composition": {"H": 4, "C": 1},
            "dens_mol_liq_comp": Perrys,
            "enth_mol_liq_comp": Perrys,
            "enth_mol_ig_comp": RPP5_Safe,
            "entr_mol_ig_comp": RPP5_Safe,
            "pressure_sat_comp": RPP5,
            "phase_equilibrium_form": {("Vap", "Liq"): log_fugacity},
            "parameter_data": {
                "mw": (identifiers.MW("74-82-8") / 1000, pyunits.kg / pyunits.mol),
                "pressure_crit": (critical.Pc("74-82-8"), pyunits.Pa),
                "temperature_crit": (critical.Tc("74-82-8"), pyunits.K), 
                "omega": acentric.omega("74-82-8"),
                "dens_mol_liq_comp_coeff": {
                    "eqn_type": 1,
                    "1": (volume.rho_data_Perry_8E_105_l.loc["74-82-8"].iloc[1] / 1000, pyunits.kmol * pyunits.m**-3),
                    "2": (volume.rho_data_Perry_8E_105_l.loc["74-82-8"].iloc[2], None),
                    "3": (volume.rho_data_Perry_8E_105_l.loc["74-82-8"].iloc[3], pyunits.K),
                    "4": (volume.rho_data_Perry_8E_105_l.loc["74-82-8"].iloc[4], None),
                },
                "cp_mol_ig_comp_coeff": {
                    "a0": (heat_capacity.Cp_data_Poling.loc["74-82-8"].iloc[3], pyunits.J / pyunits.mol / pyunits.K),
                    "a1": (heat_capacity.Cp_data_Poling.loc["74-82-8"].iloc[4], pyunits.J / pyunits.mol / pyunits.K**2),
                    "a2": (heat_capacity.Cp_data_Poling.loc["74-82-8"].iloc[5], pyunits.J / pyunits.mol / pyunits.K**3),
                    "a3": (heat_capacity.Cp_data_Poling.loc["74-82-8"].iloc[6], pyunits.J / pyunits.mol / pyunits.K**4),
                    "a4": (heat_capacity.Cp_data_Poling.loc["74-82-8"].iloc[7], pyunits.J / pyunits.mol / pyunits.K**5),
                },
                "cp_mol_liq_comp_coeff": {
                    "1": (heat_capacity.Cp_data_Perry_Table_153_114.loc["74-82-8"].iloc[1], pyunits.J * pyunits.kmol**-1 * pyunits.K**-1),
                    "2": (heat_capacity.Cp_data_Perry_Table_153_114.loc["74-82-8"].iloc[2], pyunits.J * pyunits.kmol**-1 * pyunits.K**-2),
                    "3": (heat_capacity.Cp_data_Perry_Table_153_114.loc["74-82-8"].iloc[3], pyunits.J * pyunits.kmol**-1 * pyunits.K**-3),
                    "4": (heat_capacity.Cp_data_Perry_Table_153_114.loc["74-82-8"].iloc[4], pyunits.J * pyunits.kmol**-1 * pyunits.K**-4),
                    "5": (heat_capacity.Cp_data_Perry_Table_153_114.loc["74-82-8"].iloc[5], pyunits.J * pyunits.kmol**-1 * pyunits.K**-5),
                },
                "enth_mol_form_liq_comp_ref": (reaction.Hfl("74-82-8") or 0, pyunits.J / pyunits.mol),
                "entr_mol_form_vap_comp_ref": (reaction.S0g("74-82-8") or 0, pyunits.J / pyunits.mol / pyunits.K),
                "enth_mol_form_vap_comp_ref": (reaction.Hfg("74-82-8") or 0, pyunits.J / pyunits.mol),
                "pressure_sat_comp_coeff": {
                    "A" : (vapor_pressure.Psat_data_AntoinePoling.loc["74-82-8"].iloc[1] + 5, None),
                    "B" : (vapor_pressure.Psat_data_AntoinePoling.loc["74-82-8"].iloc[2], pyunits.K),
                    "C" : (vapor_pressure.Psat_data_AntoinePoling.loc["74-82-8"].iloc[3] + 273.15, pyunits.K),
                },
            },
        },
        "ethane": {
            "type": Component,
            "elemental_composition": {"H": 6, "C": 2},
            "dens_mol_liq_comp": Perrys,
            "enth_mol_liq_comp": Perrys,
            "enth_mol_ig_comp": RPP5_Safe,
            "entr_mol_ig_comp": RPP5_Safe,
            "pressure_sat_comp": RPP5,
            "phase_equilibrium_form": {("Vap", "Liq"): log_fugacity},
            "parameter_data": {
                "mw": (identifiers.MW("74-84-0") / 1000, pyunits.kg / pyunits.mol),
                "pressure_crit": (critical.Pc("74-84-0"), pyunits.Pa),
                "temperature_crit": (critical.Tc("74-84-0"), pyunits.K),
                "omega": acentric.omega("74-84-0"),
                "dens_mol_liq_comp_coeff": {
                    "eqn_type": 1,
                    "1": (volume.rho_data_Perry_8E_105_l.loc["74-84-0"].iloc[1] / 1000, pyunits.kmol * pyunits.m**-3),
                    "2": (volume.rho_data_Perry_8E_105_l.loc["74-84-0"].iloc[2], None),
                    "3": (volume.rho_data_Perry_8E_105_l.loc["74-84-0"].iloc[3], pyunits.K),
                    "4": (volume.rho_data_Perry_8E_105_l.loc["74-84-0"].iloc[4], None),
                },
                "cp_mol_ig_comp_coeff": {
                    "a0": (heat_capacity.Cp_data_Poling.loc["74-84-0"].iloc[3], pyunits.J / pyunits.mol / pyunits.K),
                    "a1": (heat_capacity.Cp_data_Poling.loc["74-84-0"].iloc[4], pyunits.J / pyunits.mol / pyunits.K**2),
                    "a2": (heat_capacity.Cp_data_Poling.loc["74-84-0"].iloc[5], pyunits.J / pyunits.mol / pyunits.K**3),
                    "a3": (heat_capacity.Cp_data_Poling.loc["74-84-0"].iloc[6], pyunits.J / pyunits.mol / pyunits.K**4),
                    "a4": (heat_capacity.Cp_data_Poling.loc["74-84-0"].iloc[7], pyunits.J / pyunits.mol / pyunits.K**5),
                },
                "cp_mol_liq_comp_coeff": {
                    "1": (heat_capacity.Cp_data_Perry_Table_153_114.loc["74-84-0"].iloc[1], pyunits.J * pyunits.kmol**-1 * pyunits.K**-1),
                    "2": (heat_capacity.Cp_data_Perry_Table_153_114.loc["74-84-0"].iloc[2], pyunits.J * pyunits.kmol**-1 * pyunits.K**-2),
                    "3": (heat_capacity.Cp_data_Perry_Table_153_114.loc["74-84-0"].iloc[3], pyunits.J * pyunits.kmol**-1 * pyunits.K**-3),
                    "4": (heat_capacity.Cp_data_Perry_Table_153_114.loc["74-84-0"].iloc[4], pyunits.J * pyunits.kmol**-1 * pyunits.K**-4),
                    "5": (heat_capacity.Cp_data_Perry_Table_153_114.loc["74-84-0"].iloc[5], pyunits.J * pyunits.kmol**-1 * pyunits.K**-5),
                },
                "enth_mol_form_liq_comp_ref": (reaction.Hfl("74-84-0") or 0, pyunits.J / pyunits.mol),
                "entr_mol_form_vap_comp_ref": (reaction.S0g("74-84-0") or 0, pyunits.J / pyunits.mol / pyunits.K),
                "enth_mol_form_vap_comp_ref": (reaction.Hfg("74-84-0") or 0, pyunits.J / pyunits.mol),
                "pressure_sat_comp_coeff": {
                    "A": (vapor_pressure.Psat_data_AntoinePoling.loc["74-84-0"].iloc[1] + 5, None),
                    "B": (vapor_pressure.Psat_data_AntoinePoling.loc["74-84-0"].iloc[2], pyunits.K),
                    "C": (vapor_pressure.Psat_data_AntoinePoling.loc["74-84-0"].iloc[3] + 273.15, pyunits.K),
                },
            },
        },
    },
    # Specifying phases
    "phases": {
        "Liq": {
            "type": LiquidPhase,
            "equation_of_state": Cubic,
            "equation_of_state_options": {"type": CubicType.PR},
        },
        "Vap": {
            "type": VaporPhase,
            "equation_of_state": Cubic,
            "equation_of_state_options": {"type": CubicType.PR},
        },
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
        "temperature": (273.15, 300, 1500, pyunits.K),
        "pressure": (5e4, 1e5, 1e7, pyunits.Pa),
    },
    "pressure_ref": (101325, pyunits.Pa),
    "temperature_ref": (298.15, pyunits.K),
    # Defining phase equilibria
    "phases_in_equilibrium": [("Vap", "Liq")],
    "phase_equilibrium_state": {("Vap", "Liq"): SmoothVLE},
    "bubble_dew_method": LogBubbleDew,
    "parameter_data": {
        "PR_kappa": {
                ("methane", "methane"): 0.0,
                ("methane", "ethane"): -0.0033, # From DWSim Interaction parameter
                ("ethane", "methane"): -0.0033, # From DWSim Interaction parameter
                ("ethane", "ethane"): 0.0,
        }
    },
}