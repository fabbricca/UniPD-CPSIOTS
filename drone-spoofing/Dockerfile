# syntax=docker/dockerfile:1.7

ARG ARDUPILOT_TAG=Copter-4.6.3

# ---------------------------------------------------------------------------
# Stage 1: build ArduPilot SITL with clang.
# Base on ArduPilot's official dev-clang image: clang, gcc, all libs, ccache,
# python build tooling already installed -> no apt step needed in this layer.
# ---------------------------------------------------------------------------
FROM ardupilot/ardupilot-dev-clang:latest AS builder

ARG ARDUPILOT_TAG
ENV CC=clang \
    CXX=clang++ \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /opt
RUN git clone --depth 1 --branch "${ARDUPILOT_TAG}" \
        https://github.com/ArduPilot/ardupilot.git ardupilot \
    && cd ardupilot \
    && git submodule update --init --recursive --depth 1

WORKDIR /opt/ardupilot
RUN ./waf configure --board sitl \
    && ./waf copter

# ---------------------------------------------------------------------------
# Stage 2: runtime image (slim).
# ---------------------------------------------------------------------------
FROM ubuntu:24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        python3 \
        python3-pip \
        python3-venv \
        python3-tk \
        procps \
        tini \
        rsync \
        gawk \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# ArduPilot tree (with built binary) from builder.
COPY --from=builder /opt/ardupilot /opt/ardupilot

# Runtime python deps.
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir \
        pymavlink \
        mavproxy \
        matplotlib \
        pyserial \
        empy==3.3.4 \
        pexpect \
        future

ENV PATH=/opt/venv/bin:/opt/ardupilot/Tools/autotest:$PATH \
    ARDUPILOT_ROOT=/opt/ardupilot \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg

WORKDIR /work

# Project sources (overlaid by bind-mount in docker-compose for live edits).
COPY scripts/   /work/scripts/
COPY analysis/  /work/analysis/
COPY missions/  /work/missions/

RUN mkdir -p /work/logs /work/plots

ENTRYPOINT ["tini", "--"]
CMD ["python", "/work/scripts/run_scenarios.py", "--help"]
