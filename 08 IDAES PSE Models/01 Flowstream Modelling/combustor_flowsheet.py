# Import objects from pyomo package
from pyomo.environ import ConcreteModel, value, TransformationFactory, units as pyunits

# Import the solver
from idaes.core.solvers import get_solver

# Import the main FlowsheetBlock from IDAES. The flowsheet block will contain the unit model
from idaes.core import FlowsheetBlock

# Import the feed unit model
from idaes.models.unit_models import Feed, Product, Mixer, MomentumMixingType

# Import idaes logger to set output levels
import idaes.logger as idaeslog

# Import the modular property package to create a property block for the flowsheet
from idaes.models.properties.modular_properties.base.generic_property import GenericParameterBlock

# Import the methanol_ethanol property package to create a configuration file for the GenericParameterBlock
from materials import configuration

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

    # Feed units
    m.fs.fuel_feed = Feed(property_package=m.fs.properties)
    m.fs.air_feed = Feed(property_package=m.fs.properties)

    # Mixer – inlet names must match the component names used in your configuration
    m.fs.mixer = Mixer(
        property_package=m.fs.properties,
        inlet_list=["fuel_inlet", "air_inlet"],
        momentum_mixing_type=MomentumMixingType.minimize,
    )

    # Product unit
    m.fs.product = Product(property_package=m.fs.properties)

    # Connections
    m.fs.s01 = Arc(source=m.fs.fuel_feed.outlet, destination=m.fs.mixer.fuel_inlet)
    m.fs.s02 = Arc(source=m.fs.air_feed.outlet, destination=m.fs.mixer.air_inlet)
    m.fs.s03 = Arc(source=m.fs.mixer.outlet, destination=m.fs.product.inlet)

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

    print(f"Degrees of freedom after fixing: {degrees_of_freedom(m)}")

    solver = get_solver()
    result = solver.solve(m, tee=True)

    return m, result

def report_mixer_properties(model):
    """Print key properties of the mixed stream."""
    fuel = model.fs.fuel_feed
    air = model.fs.air_feed
    mix = model.fs.mixer
    prod = model.fs.product

    print("\n--- Fuel Feed ---")
    fuel.report()

    print("\n--- Air Feed ---")
    air.report()

    print("\n--- Mixer Outlet ---")
    mix.report()

    print("\n--- Product (same as mixer outlet) ---")
    prod.report()

