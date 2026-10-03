# Headless image for the DWSIM cloud simulation web app (FastAPI + static frontend).
# Runs on any Docker host (Render free tier via /render.yaml, Koyeb, local).
# Listens on $PORT (default 7860) and runs as an unprivileged UID 1000 user.
# The repo-root Dockerfile is the separate GUI/dev-container image.
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# DWSIM 10. The headless automation assemblies (DWSIM.Automation / Automation3)
# ship in the dwsim-mcp package under /opt/dwsim-mcp, not in the GUI package.
# That package bundles its own .NET for the MCP server, but pythonnet can only
# host a shared runtime, so .NET 10 is installed separately via dotnet-install.
# The 10.2.10 dwsim-mcp .deb ships an unquoted DWSIM_MCP_OPTS line that its own
# postinst sources under `set -e` (exit 127), so unpack, quote the value, then configure.
ARG DWSIM_VERSION=10.2.10
ARG DOTNET_CHANNEL=10.0
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl libgdiplus libfontconfig1 libicu70 python3 python3-pip \
    && ln -s /usr/lib/libgdiplus.so /usr/lib/gdiplus.dll \
    && curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && bash /tmp/dotnet-install.sh --channel ${DOTNET_CHANNEL} --runtime dotnet --install-dir /usr/share/dotnet \
    && curl -fsSL https://github.com/DanWBR/dwsim10/releases/download/v${DWSIM_VERSION}/dwsim-mcp_${DWSIM_VERSION}_amd64.deb -o /tmp/dwsim-mcp.deb \
    && dpkg --unpack /tmp/dwsim-mcp.deb \
    && sed -i -E 's/^DWSIM_MCP_OPTS=([^"].*)$/DWSIM_MCP_OPTS="\1"/' /etc/dwsim-mcp/dwsim-mcp.conf* \
    && dpkg --configure dwsim-mcp \
    && rm -f /tmp/dwsim-mcp.deb /tmp/dotnet-install.sh \
    && rm -rf /var/lib/apt/lists/*

ENV DOTNET_SYSTEM_DRAWING_USE_GDIPLUS=1 \
    DOTNET_ROOT=/usr/share/dotnet \
    DWSIM_PATH=/opt/dwsim-mcp/ \
    PYTHONNET_RUNTIME=coreclr \
    PYTHONUNBUFFERED=1

# Free hosts cap the container at 512 MB. Workstation GC, a 16 MB gen0 budget,
# a 200 MB managed-heap ceiling and memory-conserving compaction keep peak RSS
# around 280 MB on DWSIM 10 (20 solves, runners only; ~400 MB on DWSIM 9).
ENV DOTNET_gcServer=0 \
    DOTNET_GCgen0size=0x1000000 \
    DOTNET_GCHeapHardLimit=0xC800000 \
    DOTNET_GCConserveMemory=5

COPY backend/requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir "pythonnet==3.1.0" -r /tmp/requirements.txt

# Unprivileged runtime user (DWSIM 10 no longer writes into its install dir)
RUN useradd -m -u 1000 user

USER user
ENV HOME=/home/user
WORKDIR /home/user/app

COPY --chown=user:user backend/  backend/
COPY --chown=user:user frontend/ frontend/
COPY --chown=user:user models/   models/

WORKDIR /home/user/app/backend
EXPOSE 7860
# --loop asyncio: uvloop conflicts with the .NET runtime
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860} --loop asyncio"]
