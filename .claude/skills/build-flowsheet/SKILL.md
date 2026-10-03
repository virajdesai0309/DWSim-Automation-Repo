---
name: build-flowsheet
description: Build, solve and report a DWSIM process flowsheet from a plain-language description using the dwsim MCP server. Use when the user asks to build, simulate, model or size a process flowsheet, unit operation or stream ("mix two water streams and pump them to a heat exchanger", "simulate a methane compressor", "what duty does this heater need").
---

# Build a DWSIM flowsheet

You are acting as a careful process engineer driving DWSIM 10 through the
`dwsim` MCP server (tools named `dwsim_*`). The server's own instructions give
the basic tool order; this skill adds the engineering workflow and the gotchas
verified against DWSIM 10.2.10.

## 1. Plan before touching the simulator

Turn the request into a block list and show it to the user in a few lines:

- streams (feeds, intermediates, products, utilities), each with a tag
- unit operations with their `dwsim_unitop_add` type (`dwsim_unitop_list_types`)
- connections: which stream enters/leaves which unit on which port
- compounds and property package

Property package defaults (state the choice and why):

| System | Package |
|---|---|
| Water / steam only | `Steam Tables (IAPWS-IF97)` |
| Hydrocarbons, light gases | `Peng-Robinson (PR)` |
| Polar or non-ideal liquids (alcohols, water + organics) | `NRTL` |

Check exact names with `dwsim_thermo_list_property_packages` and
`dwsim_thermo_list_compounds`. Do not guess them.

## 2. Ask for what you do not know, before building

Never invent a process spec silently. For anything the user did not give,
ask in one batch with AskUserQuestion, offering a sensible default as the
first option. Typical gaps:

- each feed: temperature, pressure, flow (mass or molar), composition
- pump / compressor: outlet pressure (or pressure rise) and efficiency
- heater / cooler: outlet temperature or duty
- heat exchanger: what the other side is (utility stream T, P, flow) and the
  spec: outlet temperature, duty, or area + U (rating)
- columns: key components, recoveries or purities, reflux ratio, pressure

Units the server expects: K, Pa, kg/s, mol/s. Convert from the user's units
and echo both back.

## 3. Build

1. `dwsim_flowsheet_create`
2. `dwsim_thermo_add_compounds`, then `dwsim_thermo_set_property_package`.
   Both must come before any stream.
3. Feeds:
   - Call `dwsim_stream_add_material` with T, P and `composition`
     ({compound: **mass** fraction}).
   - **Then** set the flow in a *separate* `dwsim_stream_set_conditions`
     call with only `mass_flow_kg_s` or `molar_flow_mol_s`.
   - Known server bug: when `composition` is passed in the same call as a
     flow, the flow is silently reset to 1 kg/s.
4. Products and intermediates: `dwsim_stream_add_material` with just a name.
5. `dwsim_unitop_add` for each unit; `dwsim_stream_add_energy` for duties.
6. `dwsim_unitop_connect`:
   - Mixer feeds use `feed_port` 0, 1, 2, …
   - Heat exchanger:
     - port 0 = cold side in and out (`feed_port`/`product_port` 0);
     - port 1 = hot side in and out (`feed_port`/`product_port` 1).
   - Energy **into** a unit (Pump, Heater, Compressor, column reboiler):
     `energy_feed` with `energy_feed_port: 1`. Port 0 fails with
     "This connection is not allowed."
   - Energy **out of** a unit (Cooler, Expander, Pipe, column condenser):
     `energy_product` (port 0).
7. `dwsim_unitop_set` for the specs, e.g.:
   - Pump: `{"CalcMode": "OutletPressure", "Pout": <Pa>, "Eficiencia": <percent>}`
   - Compressor: `{"CalcMode": "OutletPressure", "POut": <Pa>, "AdiabaticEfficiency": <percent>}`
   - Heat exchanger rating: `{"CalcMode": "CalcBothTemp_UA", "Area": <m2>, "OverallCoefficient": <W/m2.K>}`
   - Efficiencies are **percent** (75, not 0.75).
   - If a name is wrong the tool lists valid ones. Use that rather than
     guessing again.

## 4. Check, then solve

1. `dwsim_flowsheet_check`: fix every blocker (dangling streams, unconnected
   ports, feeds with no flow, unsolved loops need a Recycle).
2. `dwsim_flowsheet_degrees_of_freedom`: if anything is still open, ask the
   user rather than picking a value.
3. `dwsim_solve_run`. On failure call `dwsim_solve_diagnostics`
   (and `dwsim_explain_finding` for codes). Fix the cause or ask, then
   re-solve. Don't loop more than three times without telling the user.

## 5. Verify and report

- Pull `dwsim_stream_get_results` for every stream and
  `dwsim_unitop_get_results` for every unit.
- Sanity-check before reporting:
  - mass balance closes on every unit (sum in = sum out);
  - temperatures are physically plausible (mixer outlet between its feeds;
    exchanger has no temperature cross unless expected);
  - vapor fraction is what the user expects (e.g. a pump feed is liquid).
  - If something looks off, say so. Don't bury it.
- Report:
  1. a short narrative of what was built and the property package;
  2. a markdown stream table: tag, T (°C), P (bar), mass flow (kg/s), vapor
     fraction, plus composition if multicomponent;
  3. key unit results: pump/compressor power, heater/cooler/HX duty, HX
     LMTD, column stages/reflux/duties;
  4. assumptions you made (with the user's agreement) and anything suspicious.
- Save, using absolute paths, to `/workspace/flowsheets/<snake_case_name>.dwxmz`
  with `dwsim_flowsheet_save` (compressed: true), and render the diagram with
  `dwsim_graphic_screenshot_to_file` to `/workspace/flowsheets/<name>.png`.
  Give the user both paths; the `.dwxmz` opens in the DWSIM 10 GUI (`dwsim`).

## Follow-ups

- "What if" questions: `dwsim_scenario_snapshot`, change one spec,
  re-solve, snapshot again, then `dwsim_scenario_compare`.
- "Why is X this value": `dwsim_explain_result`.
- Transients and control loops: follow the server's DYNAMICS workflow
  (`dwsim_dynamics_*`).

## Known limitations (DWSIM 10.2.10)

- The Solar Panel can't be connected to an energy stream in headless mode
  (`Index was out of range`). Tell the user rather than retrying.
- Python Script unit operations do not run headless (upstream issue #71).
