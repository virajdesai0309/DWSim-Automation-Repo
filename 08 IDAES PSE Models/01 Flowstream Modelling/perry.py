# dippr.py
from pyomo.environ import Param, exp, log, units as pyunits
from idaes.core.util.misc import set_param_from_config

class Dippr101:
    """
    Vapor pressure correlation using DIPPR Equation 101:
        P_sat = exp(A + B/T + C*ln(T) + D * T**E)
    """
    @staticmethod
    def build_parameters(cobj):
        """Create Pyomo parameters on the component object for the coefficients."""
        # Coefficient parameters
        cobj.pressure_sat_comp_coeff_A = Param(mutable=True, doc="Coefficient A")
        cobj.pressure_sat_comp_coeff_B = Param(mutable=True, doc="Coefficient B")
        cobj.pressure_sat_comp_coeff_C = Param(mutable=True, doc="Coefficient C")
        cobj.pressure_sat_comp_coeff_D = Param(mutable=True, doc="Coefficient D")
        cobj.pressure_sat_comp_coeff_E = Param(mutable=True, doc="Coefficient E")

        # Read the values from the component's parameter_data
        set_param_from_config(cobj, param="pressure_sat_comp_coeff", index="A")
        set_param_from_config(cobj, param="pressure_sat_comp_coeff", index="B")
        set_param_from_config(cobj, param="pressure_sat_comp_coeff", index="C")
        set_param_from_config(cobj, param="pressure_sat_comp_coeff", index="D")
        set_param_from_config(cobj, param="pressure_sat_comp_coeff", index="E")

    @staticmethod
    def return_expression(b, cobj, T):
        """
        Return a Pyomo expression for the vapor pressure.

        b   : property block
        cobj: component object (contains the coefficient parameters)
        T   : temperature expression (from the property block)
        """
        A = cobj.pressure_sat_comp_coeff_A
        B = cobj.pressure_sat_comp_coeff_B
        C = cobj.pressure_sat_comp_coeff_C
        D = cobj.pressure_sat_comp_coeff_D
        E = cobj.pressure_sat_comp_coeff_E

        # Expression for P_sat
        return exp(A + B / T + C * log(T) + D * (T ** E))