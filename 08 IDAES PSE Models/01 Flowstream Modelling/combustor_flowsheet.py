# Import objects from pyomo package
from pyomo.environ import ConcreteModel, value, TransformationFactory, units as pyunits

# Import the solver
from idaes.core.solvers import get_solver

# Import the main FlowsheetBlock from IDAES. The flowsheet block will contain the unit model
from idaes.core import FlowsheetBlock

# Import the feed unit model
from idaes.models.unit_models import Feed, Product, Mixer, MomentumMixingType, StoichiometricReactor

# Import idaes logger to set output levels
import idaes.logger as idaeslog

# Import the modular property package to create a property block for the flowsheet
from idaes.models.properties.modular_properties.base.generic_property import GenericParameterBlock

# Import the modular reaction package to create a reaction block for the flowsheet
from idaes.models.properties.modular_properties.base.generic_reaction import GenericReactionParameterBlock

# Import the methanol_ethanol property package to create a configuration file for the GenericParameterBlock
from materials import configuration

from combustion_reaction import combustion_reaction_config

# Import the degrees_of_freedom function from the idaes.core.util.model_statistics package
# DOF = Number of Model Variables - Number of Model Constraints
from idaes.core.util.model_statistics import degrees_of_freedom

# Import Arc to connect the unit models
from pyomo.network import Arc

def setup_fuel_air_mixer(
    fuel_stream={
        "flow_mol": 100,            # mol/s
        "mole_frac_methane": 1.0,
        "mole_frac_oxygen": 1e-15,
        "mole_frac_carbon_dioxide": 1e-15,
        "mole_frac_water": 1e-15,
        "mole_frac_nitrogen": 1e-15,
        "pressure": 101325,         # Pa
        "temperature": 298,         # K
    },
    air_stream={
        "flow_mol": 100,            # mol/s
        "mole_frac_methane": 1e-15,
        "mole_frac_oxygen": 0.21,
        "mole_frac_carbon_dioxide": 0.0004,   # optional, approx. 400 ppm
        "mole_frac_water": 0.01,              # humidity, adjust as needed
        "mole_frac_nitrogen": 0.7796,         # remainder
        "pressure": 101325,
        "temperature": 298,
    }
):
    """Create and solve a mixer model for fuel (methane) and air."""
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    m.fs.properties = GenericParameterBlock(**configuration)
    m.fs.reaction_params = GenericReactionParameterBlock(
        property_package=m.fs.properties,
        **combustion_reaction_config,
        )

    # Feed units
    m.fs.fuel_feed = Feed(property_package=m.fs.properties)
    m.fs.air_feed = Feed(property_package=m.fs.properties)

    # Mixer – inlet names must match the component names used in your configuration
    m.fs.mixer = Mixer(
        property_package=m.fs.properties,
        inlet_list=["fuel_inlet", "air_inlet"],
        momentum_mixing_type=MomentumMixingType.minimize,
    )

    # Combustor – using a stoichiometric reactor to directly specify conversion based on the reaction stoichiometry
    m.fs.combustor = StoichiometricReactor(
        property_package=m.fs.properties,
        reaction_package=m.fs.reaction_params,
        has_heat_of_reaction=True,
        has_heat_transfer=False,
        has_pressure_change=False,
    )

    # Product unit
    m.fs.product = Product(property_package=m.fs.properties)

    # Connections
    m.fs.s01 = Arc(source=m.fs.fuel_feed.outlet, destination=m.fs.mixer.fuel_inlet)
    m.fs.s02 = Arc(source=m.fs.air_feed.outlet, destination=m.fs.mixer.air_inlet)
    m.fs.s03 = Arc(source=m.fs.mixer.outlet, destination=m.fs.combustor.inlet)
    m.fs.s04 = Arc(source=m.fs.combustor.outlet, destination=m.fs.product.inlet)

    TransformationFactory("network.expand_arcs").apply_to(m)

    print(f"Degrees of freedom before fixing: {degrees_of_freedom(m)}")

    # Fix fuel feed conditions
    m.fs.fuel_feed.flow_mol.fix(fuel_stream["flow_mol"])
    m.fs.fuel_feed.mole_frac_comp[0, "methane"].fix(fuel_stream["mole_frac_methane"])
    m.fs.fuel_feed.mole_frac_comp[0, "oxygen"].fix(fuel_stream["mole_frac_oxygen"])
    m.fs.fuel_feed.mole_frac_comp[0, "carbon_dioxide"].fix(fuel_stream["mole_frac_carbon_dioxide"])
    m.fs.fuel_feed.mole_frac_comp[0, "water"].fix(fuel_stream["mole_frac_water"])
    m.fs.fuel_feed.mole_frac_comp[0, "nitrogen"].fix(fuel_stream["mole_frac_nitrogen"])
    m.fs.fuel_feed.pressure.fix(fuel_stream["pressure"])
    m.fs.fuel_feed.temperature.fix(fuel_stream["temperature"])

    # Fix air feed conditions
    m.fs.air_feed.flow_mol.fix(air_stream["flow_mol"])
    m.fs.air_feed.mole_frac_comp[0, "methane"].fix(air_stream["mole_frac_methane"])
    m.fs.air_feed.mole_frac_comp[0, "oxygen"].fix(air_stream["mole_frac_oxygen"])
    m.fs.air_feed.mole_frac_comp[0, "carbon_dioxide"].fix(air_stream["mole_frac_carbon_dioxide"])
    m.fs.air_feed.mole_frac_comp[0, "water"].fix(air_stream["mole_frac_water"])
    m.fs.air_feed.mole_frac_comp[0, "nitrogen"].fix(air_stream["mole_frac_nitrogen"])
    m.fs.air_feed.pressure.fix(air_stream["pressure"])
    m.fs.air_feed.temperature.fix(air_stream["temperature"])

    # Set extent based on desired conversion of methane (95%)
    # The methane molar flow into the reactor is exactly the fuel flow (since fuel is pure methane)
    methane_flow_in = fuel_stream["flow_mol"]   # mol/s
    conversion = 0.95
    extent = methane_flow_in * conversion # stoichiometric coefficient of methane is -1, so magnitude = 1
    m.fs.combustor.rate_reaction_extent[0, "combustion"].fix(extent)
    
    print(f"Degrees of freedom after fixing: {degrees_of_freedom(m)}")

    solver = get_solver(options={"tol": 1e-6, "max_iter": 200})
    result = solver.solve(m, tee=True)

    return m, result

def report_mixer_properties(model):
    """Print key properties of all streams: fuel, air, mixer (reactor inlet), combustor, product."""
    fuel = model.fs.fuel_feed
    air = model.fs.air_feed
    mixer = model.fs.mixer
    combustor = model.fs.combustor
    product = model.fs.product

    print("\n" + "="*80)
    print("FUEL FEED")
    print("="*80)
    fuel.report()

    print("\n" + "="*80)
    print("AIR FEED")
    print("="*80)
    air.report()

    print("\n" + "="*80)
    print("MIXER OUTLET (REACTOR INLET)")
    print("="*80)
    mixer.report()

    print("\n" + "="*80)
    print("COMBUSTOR OUTLET")
    print("="*80)
    combustor.report()

    print("\n" + "="*80)
    print("PRODUCT (same as combustor outlet)")
    print("="*80)
    product.report()

    # Additional reactor performance metrics
    print("\n" + "="*80)
    print("REACTOR PERFORMANCE")
    print("="*80)
    # Conversion (if fixed)
    if hasattr(combustor, "conversion"):
        conv = combustor.conversion["combustion"].value
        print(f"Methane conversion (fixed): {conv:.4f} ({conv*100:.2f}%)")
    # Extent of reaction
    if hasattr(combustor, "extent"):
        ext = combustor.extent["combustion"].value
        print(f"Extent of reaction: {ext:.6e} mol/s")
    # Temperature change
    T_inlet = mixer.outlet.temperature[0].value
    T_outlet = combustor.outlet.temperature[0].value
    print(f"Inlet temperature: {T_inlet:.2f} K")
    print(f"Outlet temperature: {T_outlet:.2f} K")
    print(f"Temperature rise: {T_outlet - T_inlet:.2f} K")
    # Pressure
    print(f"Pressure (inlet/outlet): {mixer.outlet.pressure[0].value:.1f} Pa / {combustor.outlet.pressure[0].value:.1f} Pa")
    # Heat duty (if any)
    if hasattr(combustor, "heat_duty"):
        Q = combustor.heat_duty[0].value
        print(f"Heat duty: {Q:.2f} W")

