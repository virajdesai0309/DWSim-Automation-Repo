# Headless image for the DWSIM cloud simulation web app (FastAPI + static frontend).
# Runs on any Docker host (Render free tier via /render.yaml, Koyeb, local).
# Listens on $PORT (default 7860) and runs as an unprivileged UID 1000 user.
# The repo-root Dockerfile is the separate GUI/dev-container image.
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# .NET 8 runtime (Microsoft repo) + DWSIM 9.0.4. The .deb only depends on
# dotnet-runtime-8.0 and coinor-libipopt1v5; libgdiplus covers System.Drawing.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates wget libgdiplus python3 python3-pip \
    && ln -s /usr/lib/libgdiplus.so /usr/lib/gdiplus.dll \
    && wget -q https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -O /tmp/ms.deb \
    && dpkg -i /tmp/ms.deb && rm /tmp/ms.deb \
    && apt-get update \
    && wget -q https://github.com/DanWBR/dwsim6/releases/download/v9.0.4/dwsim_9.0.4-amd64.deb -O /tmp/dwsim.deb \
    && apt-get install -y --no-install-recommends /tmp/dwsim.deb \
    && rm /tmp/dwsim.deb \
    && rm -rf /var/lib/apt/lists/*

ENV DOTNET_SYSTEM_DRAWING_USE_GDIPLUS=1 \
    PYTHONNET_RUNTIME=coreclr \
    PYTHONUNBUFFERED=1

# Free hosts cap the container at 512 MB. Workstation GC, a 16 MB gen0 budget,
# a 200 MB managed-heap ceiling and memory-conserving compaction keep peak RSS
# around 400 MB (measured over 25 solves) instead of ~460 MB with defaults.
ENV DOTNET_gcServer=0 \
    DOTNET_GCgen0size=0x1000000 \
    DOTNET_GCHeapHardLimit=0xC800000 \
    DOTNET_GCConserveMemory=5

COPY backend/requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir "pythonnet==3.1.0" -r /tmp/requirements.txt

# Unprivileged runtime user; DWSIM writes settings to its application data dir
RUN useradd -m -u 1000 user \
    && mkdir -p "/usr/local/lib/dwsim/DWSIM Application Data" \
    && chown -R user:user "/usr/local/lib/dwsim/DWSIM Application Data"

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
