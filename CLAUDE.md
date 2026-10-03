# DWSim-Automation-Repo

DWSIM process-simulation automation: per-unit-op notebooks (`00 FlowSheet Automation/`),
a FastAPI cloud app (`09_Clould_Based_Simulations/`), surrogate/PINN experiments.

## DWSIM 10 environment

- GUI: `dwsim` (`/opt/dwsim`). Headless automation DLLs and the MCP server: `/opt/dwsim-mcp`.
- Python loads DWSIM via pythonnet on the shared .NET 10 runtime (`/usr/share/dotnet`).
  The cloud runners do this through `09_Clould_Based_Simulations/backend/dwsim_runtime.py`.
- Start uvicorn with `--loop asyncio` (uvloop conflicts with the .NET runtime).

## Building flowsheets on request

When asked to build, simulate or size a process, use the `dwsim` MCP server
(`.mcp.json`) and follow the `build-flowsheet` skill: plan the blocks, ask for missing
specs, build, check degrees of freedom, solve, verify, report. Save results under
`flowsheets/`.

## Careful

- Many notebooks save `.dwxmz` files to absolute `/workspace/...` paths, so running one
  overwrites the committed reference model next to it.
