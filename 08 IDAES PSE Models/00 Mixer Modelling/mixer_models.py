# Import objects from pyomo package
from pyomo.environ import ConcreteModel, SolverFactory, TransformationFactory, value, units

# Import the main FlowsheetBlock from IDAES. The flowsheet block will contain the unit model
from idaes.core import FlowsheetBlock

# Import idaes logger to set output levels
import idaes.logger as idaeslog

# Import the IAPWS property package to create a properties block for the flowsheet
from idaes.models.properties import iapws95
from idaes.models.properties.helmholtz.helmholtz import PhaseType

# Import the mixer unit model from IDAES
from idaes.models.unit_models import Mixer, MomentumMixingType

# Importing feed streams for the mixer unit model
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
m.fs.properties = iapws95.Iapws95ParameterBlock(
    phase_presentation=PhaseType.LG,
    state_vars = iapws95.StateVars.PH)

# Creating an instance of mixing unit model and attaching it to the flowsheet
m.fs.mixer = Mixer(
    property_package=m.fs.properties,
    num_inlets=2,
    momentum_mixing_type=MomentumMixingType.minimize,
)

# Creating feed streams for the mixer unit model and attaching them to the flowsheet
m.fs.feed1 = Feed(property_package=m.fs.properties)
m.fs.feed2 = Feed(property_package=m.fs.properties)

# Creating product stream for the mixer unit model and attaching it to the flowsheet
m.fs.product = Product(property_package=m.fs.properties)

# Connecting the feed and product streams to the mixer unit model
m.fs.s01 = Arc(source=m.fs.feed1.outlet, destination=m.fs.mixer.inlet_1)
m.fs.s02 = Arc(source=m.fs.feed2.outlet, destination=m.fs.mixer.inlet_2)
m.fs.s03 = Arc(source=m.fs.mixer.outlet, destination=m.fs.product.inlet)

# Transforming the arcs to create the necessary constraints for the model
TransformationFactory("network.expand_arcs").apply_to(m)

# Calling the degree of freedom function to check that the model is well posed
print("The degree of freedom for the model is : {}".format(degrees_of_freedom(m)))

# Fixing the feed conditions for the mixer unit model using Pressure and Enthalpy
# Stream 1: 300 K, 101325 Pa, 1 mol/s
enth_1 = iapws95.htpx(T=350 * units.K, P=101325 * units.Pa)  # Calculate enthalpy
m.fs.feed1.properties[0].flow_mol.fix(55.5084)
m.fs.feed1.properties[0].enth_mol.fix(enth_1)
m.fs.feed1.properties[0].pressure.fix(101325)

# Stream 2: 350 K, 101325 Pa, 1 mol/s
enth_2 = iapws95.htpx(T=450 * units.K, P=501325 * units.Pa)  # Calculate enthalpy
m.fs.feed2.properties[0].flow_mol.fix(55.5084)
m.fs.feed2.properties[0].enth_mol.fix(enth_2)
m.fs.feed2.properties[0].pressure.fix(501325)

# Calling the degree of freedom function again to check that the model is well posed after fixing the feed conditions
print("The degree of freedom for the model is : {}".format(degrees_of_freedom(m)))

# Initializing the model using the default initialization routine for the mixer unit model
m.fs.feed1.initialize(outlvl=idaeslog.INFO, state_args={})
m.fs.feed2.initialize(outlvl=idaeslog.INFO, state_args={})

# Propogating the state from the feed streams to the mixer unit model
propagate_state(arc=m.fs.s01, direction="forward") 
propagate_state(arc=m.fs.s02, direction="forward") 

# Initializing the mixer unit model using the default initialization routine for the mixer unit model
m.fs.mixer.initialize(outlvl=idaeslog.DEBUG)

# Propogating the state from the mixer unit model to the product stream
propagate_state(arc=m.fs.s03, direction="forward")

# Creating an instance of the DiagnosticsToolbox to check that the model is well initialized
dt = DiagnosticsToolbox(m)

# Printing any structual issues with the model
print(dt.report_structural_issues())

# Printing any numerical issues with the model
print(dt.report_numerical_issues())

# Printing large residuals in the model
print(dt.display_constraints_with_large_residuals())

# Wrapping and Printing any infeasibilities with the model
try:
    print(dt.compute_infeasibility_explanation())
except Exception as e:
    print("Model is feasible - no infeasibility explanation needed.")

# Printing variables inside or outside the bounds
print(dt.display_variables_at_or_outside_bounds())

# Solving the model using the ipopt solver
solver = SolverFactory("ipopt")
solver_status = solver.solve(m, tee=True)

# Displaying the results
print(m.fs.feed1.report())
print(m.fs.feed2.report())
print(m.fs.mixer.report())
