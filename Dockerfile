# syntax=docker/dockerfile:1.7
#
# Build environment for the RPL IDS experiment.
#
# Base image: the official Contiki-NG toolchain image. It ships msp430-gcc,
# arm-none-eabi-gcc, Java 17 and the Cooja build dependencies, but it does
# NOT ship a Contiki-NG source tree; the tree is normally bind-mounted.
# We instead clone a pinned tag into the image so every build is reproducible
# and record the exact commit in /opt/VERSION.txt.

ARG CONTIKI_NG_TAG=release/v5.2

FROM contiker/contiki-ng:latest

ARG CONTIKI_NG_TAG
ENV CONTIKI_NG_TAG=${CONTIKI_NG_TAG} \
    DEBIAN_FRONTEND=noninteractive

USER root
WORKDIR /home/user

# Pinned Contiki-NG checkout with Cooja submodule.
RUN rm -rf "${CONTIKI_NG}" \
    && git clone --branch "${CONTIKI_NG_TAG}" --depth 1 \
        https://github.com/contiki-ng/contiki-ng.git "${CONTIKI_NG}" \
    && cd "${CONTIKI_NG}" \
    && git submodule update --init --depth 1 tools/cooja \
    && chown -R user:user "${CONTIKI_NG}"

# Apply our instrumentation patches to the pinned tree (Phase 2).
COPY patches/ /opt/patches/
RUN cd "${CONTIKI_NG}" \
    && for p in /opt/patches/*.patch; do \
         [ -e "$p" ] || continue; \
         echo "Applying $p"; git apply --whitespace=nowarn "$p" || exit 1; \
       done

# Pre-build Cooja so headless runs do not pay the Gradle cost every time.
USER user
RUN cd "${CONTIKI_NG}/tools/cooja" && ./gradlew --no-daemon -q jar

# Version record for the report (Phase 0 checkpoint).
USER root
RUN { echo "date=$(date -u +%FT%TZ)"; \
      echo "contiki_ng_tag=${CONTIKI_NG_TAG}"; \
      echo "contiki_ng_commit=$(git -C ${CONTIKI_NG} rev-parse HEAD)"; \
      echo "cooja_commit=$(git -C ${CONTIKI_NG}/tools/cooja rev-parse HEAD)"; \
      echo "java=$(java -version 2>&1 | head -1)"; \
      echo "msp430_gcc=$(msp430-gcc --version 2>&1 | head -1)"; \
      echo "arm_gcc=$(arm-none-eabi-gcc --version 2>&1 | head -1)"; \
      echo "host_gcc=$(gcc --version 2>&1 | head -1)"; \
      echo "os=$(. /etc/os-release && echo $PRETTY_NAME)"; \
    } > /opt/VERSION.txt && cat /opt/VERSION.txt

# Host-side analysis dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir pandas matplotlib numpy pytest

ENV PATH=/opt/venv/bin:$PATH \
    MPLBACKEND=Agg \
    PYTHONUNBUFFERED=1

USER user
WORKDIR /home/user/rpl-ids
CMD ["/bin/bash"]
