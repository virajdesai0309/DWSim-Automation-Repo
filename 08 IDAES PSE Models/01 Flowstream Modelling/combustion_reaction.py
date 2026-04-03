# combustion_reaction.py
from pyomo.environ import units as pyunits
from idaes.models.properties.modular_properties.base.generic_reaction import (
    ConcentrationForm,
)
from idaes.models.properties.modular_properties.reactions.dh_rxn import constant_dh_rxn
from idaes.models.properties.modular_properties.reactions.rate_constant import arrhenius
from idaes.models.properties.modular_properties.reactions.rate_forms import (
    power_law_rate,
)

# Configuration dictionary for the generic reaction package
combustion_reaction_config = {
    "base_units": {
        "time": pyunits.s,
        "length": pyunits.m,
        "mass": pyunits.kg,
        "amount": pyunits.mol,
        "temperature": pyunits.K,
    },
    "rate_reactions": {
        "combustion": {
            "stoichiometry": {
                ("Vap", "methane"): -1,
                ("Vap", "oxygen"): -2,
                ("Vap", "carbon_dioxide"): 1,
                ("Vap", "water"): 2,
                ("Vap", "nitrogen"): 0,      # inert
            },
            "heat_of_reaction": constant_dh_rxn,
            "rate_constant": arrhenius,
            "rate_form": power_law_rate,
            "concentration_form": ConcentrationForm.molarity,  # mol/m³
            "parameter_data": {
                # Reaction order – only methane appears (power law)
                "reaction_order": {("Vap", "methane"): 1},
                # Standard heat of combustion of methane (J/mol)
                "dh_rxn_ref": (-409108, pyunits.J / pyunits.mol),
                # Dummy Arrhenius parameters – not used because we will fix conversion directly.
                # The stoichiometric reactor does not use the rate constant, but the framework requires them.
                "arrhenius_const": (1e-6, pyunits.s**-1),
                "energy_activation": (1e4, pyunits.J / pyunits.mol),
            },
        }
    },
}