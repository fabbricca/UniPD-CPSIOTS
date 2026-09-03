# RPL IDS firmware build.
#
# Usage (inside the container):
#   make TARGET=cooja            # fast native Cooja mote, no memory limit
#   make TARGET=sky              # Tmote Sky, for the ROM/RAM overhead report
#   make TARGET=cooja IDS_MODE=SLIDING
#
# Four firmware images are produced, one per Cooja mote type.

CONTIKI = $(CNG_PATH)

CONTIKI_PROJECT = rpl-ids-root rpl-ids-node neighbor-attacker dis-attacker
all: $(CONTIKI_PROJECT)

PROJECTDIRS += firmware include
PROJECT_SOURCEFILES += ids.c

# Detector mode: PAPER (fixed window) or SLIDING (ring buffer).
IDS_MODE ?= PAPER
CFLAGS += -DIDS_MODE_$(IDS_MODE)=1

# Contiki-NG configuration.
MAKE_ROUTING = MAKE_ROUTING_RPL_LITE
MAKE_MAC = MAKE_MAC_CSMA
MAKE_NET = MAKE_NET_IPV6

include $(CONTIKI)/Makefile.include
