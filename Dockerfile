# Use an official Ubuntu LTS base image
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# 1. Install system dependencies and Python/pip
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gdebi-core \
    git \
    libgtk2.0-0 \
    libcanberra-gtk-module \
    libcanberra-gtk3-module \
    libgdiplus \
    libc6-dev \
    libx11-dev \
    libxext-dev \
    libxrandr-dev \
    libxrender-dev \
    libfontconfig1-dev \
    libfreetype6-dev \
    python3 \
    python3-pip \
    build-essential \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    cmake \
    && ln -s /usr/lib/libgdiplus.so /usr/lib/gdiplus.dll

# 2. .NET 10 SDK (includes the runtime). DWSIM 10 targets net10.0, and pythonnet
#    needs a shared .NET 10 runtime to host its assemblies.
RUN apt-get install -y libicu70 \
    && curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && bash /tmp/dotnet-install.sh --channel 10.0 --install-dir /usr/share/dotnet \
    && ln -s /usr/share/dotnet/dotnet /usr/bin/dotnet \
    && rm /tmp/dotnet-install.sh
ENV DOTNET_ROOT=/usr/share/dotnet

# Set environment variables for .NET
ENV DOTNET_SYSTEM_DRAWING_USE_GDIPLUS=1
ENV DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=0

# Install dependencies from txt file
COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt

# Install IDAES extensions (solvers, etc.)
# This will place the extensions in /root/.idaes
RUN idaes get-extensions

# DWSIM 10: the GUI (/opt/dwsim, `dwsim` command) and the headless MCP server
# (/opt/dwsim-mcp, `dwsim-mcp` command). /opt/dwsim-mcp also holds the
# automation assemblies (Automation3) that the Python scripts load.
# Both packages bundle their own .NET runtime.
ARG DWSIM_VERSION=10.2.10
RUN wget -q https://github.com/DanWBR/dwsim10/releases/download/v${DWSIM_VERSION}/dwsim_${DWSIM_VERSION}_amd64.deb -O /tmp/dwsim.deb \
    && gdebi -n /tmp/dwsim.deb && rm /tmp/dwsim.deb

# The 10.2.10 dwsim-mcp .deb ships an unquoted DWSIM_MCP_OPTS line that its own
# postinst sources under `set -e` (exit 127), so unpack, quote the value, then configure.
RUN wget -q https://github.com/DanWBR/dwsim10/releases/download/v${DWSIM_VERSION}/dwsim-mcp_${DWSIM_VERSION}_amd64.deb -O /tmp/dwsim-mcp.deb \
    && dpkg --unpack /tmp/dwsim-mcp.deb \
    && sed -i -E 's/^DWSIM_MCP_OPTS=([^"].*)$/DWSIM_MCP_OPTS="\1"/' /etc/dwsim-mcp/dwsim-mcp.conf* \
    && dpkg --configure dwsim-mcp \
    && rm /tmp/dwsim-mcp.deb
ENV DWSIM_PATH=/opt/dwsim-mcp/

# Create a non-root user for security
RUN useradd -m -s /bin/bash dwsimuser && \
    usermod -a -G video,dialout dwsimuser

# Copy IDAES extensions from root's home to the user's home and set ownership
RUN mkdir -p /home/dwsimuser/.idaes && \
    cp -r /root/.idaes/* /home/dwsimuser/.idaes/ && \
    chown -R dwsimuser:dwsimuser /home/dwsimuser/.idaes

USER dwsimuser
WORKDIR /home/dwsimuser

# Adds Claude code into the container
RUN curl -fsSL https://claude.ai/install.sh | bash

# Register the kernel for the dwsimuser (user-level, often better)
RUN python3 -m ipykernel install --user --name dwsim-python --display-name "Python (DWSim)"

# Set environment variables for GUI
ENV DISPLAY=host.docker.internal:0
ENV DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"

# Create a mount point for project files
VOLUME ["/home/dwsimuser/DWSIM_Projects"]

# Default command: Start DWSIM
CMD ["dwsim"]