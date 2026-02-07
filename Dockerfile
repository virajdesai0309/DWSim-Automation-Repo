# Use an official Ubuntu LTS base image
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# 1. Install system dependencies and Python/pip
RUN apt-get update && apt-get install -y \
    wget \
    gdebi-core \
    git \
    libgtk2.0-0 \
    libcanberra-gtk-module \
    libcanberra-gtk3-module \
    libgdiplus \
    python3 \
    python3-pip

# 2. Add Microsoft repository for .NET and install .NET runtime
RUN wget https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && apt-get install -y dotnet-sdk-8.0

# Installs dependencies from txt file
    COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt

# Download and install DWSIM v9.0.4 for Debian/Ubuntu
RUN wget https://github.com/DanWBR/dwsim6/releases/download/v9.0.4/dwsim_9.0.4-amd64.deb \
    && gdebi -n dwsim_9.0.4-amd64.deb \
    && rm dwsim_9.0.4-amd64.deb

# Create a non-root user for security
RUN useradd -m -s /bin/bash dwsimuser && \
    usermod -a -G video,dialout dwsimuser

# Fix permission: allow the newly created dwsimuser to write to DWSim's application data directory
RUN mkdir -p /usr/local/lib/dwsim/"DWSIM Application Data" && \
    chown -R dwsimuser:dwsimuser /usr/local/lib/dwsim/"DWSIM Application Data"
    
USER dwsimuser
WORKDIR /home/dwsimuser

# Register the kernel for the dwsimuser (user-level, often better)
RUN python3 -m ipykernel install --user --name dwsim-python --display-name "Python (DWSim)"

# Set environment variables for GUI
ENV DISPLAY=host.docker.internal:0
ENV DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"

# Create a mount point for project files
VOLUME ["/home/dwsimuser/DWSIM_Projects"]

# Default command: Start DWSIM
CMD ["dwsim"]