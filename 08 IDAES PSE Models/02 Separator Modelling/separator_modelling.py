# Import objects from pyomo package
from pyomo.environ import ConcreteModel, SolverFactory, TransformationFactory, value, units

# Import the main FlowsheetBlock from IDAES. The flowsheet block will contain the unit model
from idaes.core import FlowsheetBlock

# Import idaes logger to set output levels
import idaes.logger as idaeslog

# Importing the generic thermo package for the model
from idaes.models.properties.modular_properties.base.generic_property import GenericParameterBlock

# Importing the compounds configuration for the model
from compounds import configuration

# Import the flash unit model from IDAES
from idaes.models.unit_models import Flash

# Importing feed streams for the flash unit model
from idaes.models.unit_models import Feed, Product

# Import the degrees of freedom function to check that the model is well posed
from idaes.core.util.model_statistics import degrees_of_freedom 
    
# Import the Arc and TransformationFactory from pyomo.network
from pyomo.network import Arc 

# Importing diagnostic tools to check that the model is well initialized
from idaes.core.util.model_diagnostics import DiagnosticsToolbox

# Importing the propogate state
from idaes.core.util.initialization import propagate_state

# Create the ConcreteModel and the FlowsheetBlock, and attach the flowsheet block to it.
m = ConcreteModel()

m.fs = FlowsheetBlock(
    dynamic=False
)  # dynamic or ss flowsheet needs to be specified here

# Add properties parameter block to the flowsheet with specifications
m.fs.properties = GenericParameterBlock(**configuration) 

# Creating an instance of mixing unit model and attaching it to the flowsheet
m.fs.flash = Flash(
    property_package=m.fs.properties,
    has_heat_transfer=True,
    has_pressure_change=True,
)

# Creating feed streams for the flash unit model and attaching them to the flowsheet
m.fs.feed1 = Feed(property_package=m.fs.properties)

# Creating product stream for the flash unit model and attaching it to the flowsheet
m.fs.vapor = Product(property_package=m.fs.properties)
m.fs.liquid = Product(property_package=m.fs.properties)

# Connecting the feed and product streams to the flash unit model
m.fs.s01 = Arc(source=m.fs.feed1.outlet, destination=m.fs.flash.inlet)
m.fs.s02 = Arc(source=m.fs.flash.vap_outlet, destination=m.fs.vapor.inlet)
m.fs.s03 = Arc(source=m.fs.flash.liq_outlet, destination=m.fs.liquid.inlet)

# Transforming the arcs to create the necessary constraints for the model
TransformationFactory("network.expand_arcs").apply_to(m)

# Calling the degree of freedom function to check that the model is well posed
print("The degree of freedom for the model is : {}".format(degrees_of_freedom(m)))

# Fixing the feed conditions for the mixer unit model using Pressure and Enthalpy
m.fs.feed1.properties[0].flow_mol.fix(10)
m.fs.feed1.properties[0].temperature.fix(300)
m.fs.feed1.properties[0].pressure.fix(500000)
m.fs.feed1.properties[0].mole_frac_comp["methane"].fix(0.4)
m.fs.feed1.properties[0].mole_frac_comp["ethane"].fix(0.6)

# Fix flash operating conditions (adiabatic, no pressure drop)
m.fs.flash.heat_duty.fix(0)   # W  - adiabatic operation
m.fs.flash.deltaP.fix(0)      # Pa - no pressure drop

# Calling the degree of freedom function again to check that the model is well posed after fixing the feed conditions
print("The degree of freedom for the model is : {}".format(degrees_of_freedom(m)))

# Initialize feed first so all properties (including bubble/dew T) are computed
m.fs.feed1.initialize(outlvl=idaeslog.INFO)

# Initializing the model using the default initialization routine for the mixer unit model
propagate_state(arc=m.fs.s01)   # feed1 → flash
m.fs.flash.initialize(outlvl=idaeslog.INFO)
propagate_state(arc=m.fs.s02)   # flash vap_outlet → vapor
propagate_state(arc=m.fs.s03)   # flash liq_outlet → liquid
m.fs.vapor.initialize(outlvl=idaeslog.INFO)
m.fs.liquid.initialize(outlvl=idaeslog.INFO)

# Creating an instance of the DiagnosticsToolbox to check that the model is well initialized
dt = DiagnosticsToolbox(m)

# Printing any structual issues with the model
print(dt.report_structural_issues())

# Show any variables with None values before numerical analysis
try:
    dt.display_variables_with_none_value_in_activated_constraints()
except Exception as e:
    pass  # No None-valued variables
 
# Printing any numerical issues (requires all variables initialized)
try:
    print(dt.report_numerical_issues())
except RuntimeError as e:
    print(f"Skipping numerical issues report: {e}")
 
# Printing large residuals in the model
try:
    print(dt.display_constraints_with_large_residuals())
except Exception as e:
    print(f"Skipping large residuals: {e}")
 
# Printing variables outside the bounds
try:
    print(dt.display_variables_at_or_outside_bounds())
except Exception as e:
    print(f"Skipping bounds check: {e}")
 
# Solving the model using the ipopt solver
solver = SolverFactory("ipopt")
solver_status = solver.solve(m, tee=True)

# Displaying the results
print(m.fs.feed1.report())
print(m.fs.flash.report())
print(m.fs.vapor.report())
print(m.fs.liquid.report())
