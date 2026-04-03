# perry.py
from pyomo.environ import Var, exp, log, units as pyunits
from idaes.core.util.misc import set_param_from_config

class Dippr101:
    """
    Vapor pressure correlation using DIPPR Equation 101:
        P_sat = exp(A + B/T + C*ln(T) + D * T**E)
    All coefficients are treated as dimensionless; the expression returns pressure in Pa
    when T is in Kelvin (using DIPPR tabulated coefficients).
    """

    class pressure_sat_comp:
        @staticmethod
        def build_parameters(cobj):
            # Define coefficients as Var with units=None (dimensionless)
            cobj.pressure_sat_comp_coeff_A = Var(
                doc="Coefficient A for DIPPR vapor pressure equation",
                units=None,
            )
            set_param_from_config(cobj, param="pressure_sat_comp_coeff", index="A")

            cobj.pressure_sat_comp_coeff_B = Var(
                doc="Coefficient B for DIPPR vapor pressure equation",
                units=None,
            )
            set_param_from_config(cobj, param="pressure_sat_comp_coeff", index="B")

            cobj.pressure_sat_comp_coeff_C = Var(
                doc="Coefficient C for DIPPR vapor pressure equation",
                units=None,
            )
            set_param_from_config(cobj, param="pressure_sat_comp_coeff", index="C")

            cobj.pressure_sat_comp_coeff_D = Var(
                doc="Coefficient D for DIPPR vapor pressure equation",
                units=None,
            )
            set_param_from_config(cobj, param="pressure_sat_comp_coeff", index="D")

            cobj.pressure_sat_comp_coeff_E = Var(
                doc="Coefficient E for DIPPR vapor pressure equation",
                units=None,
            )
            set_param_from_config(cobj, param="pressure_sat_comp_coeff", index="E")

        @staticmethod
        def return_expression(b, cobj, T):
            """
            Return a Pyomo expression for the vapor pressure (Pa).
            T is a temperature expression (expected in Kelvin).
            """
            # Ensure T is in Kelvin (convert if units are attached, else assume K)
            T_K = pyunits.convert(T, to_units=pyunits.K)

            A = cobj.pressure_sat_comp_coeff_A
            B = cobj.pressure_sat_comp_coeff_B
            C = cobj.pressure_sat_comp_coeff_C
            D = cobj.pressure_sat_comp_coeff_D
            E = cobj.pressure_sat_comp_coeff_E

            # DIPPR equation: ln(P_sat) = A + B/T + C*ln(T) + D*T^E
            ln_Psat = A + B / T_K + C * log(T_K) + D * (T_K ** E)
            P_sat = exp(ln_Psat)

            # The result is in Pa because the coefficients are fitted for that unit.
            return P_sat