# RPL IDS firmware build. Lives next to the sources because Cooja runs the
# mote type's build command in the source file's directory.
#
# Usage (inside the container, from rpl-ids/):
#   make -C firmware TARGET=cooja                 # native Cooja motes (fast)
#   make -C firmware TARGET=sky                   # Tmote Sky, for ROM/RAM numbers
#   make -C firmware TARGET=cooja IDS_MODE=SLIDING
#   make -C firmware TARGET=cooja IDS_WINDOW_SEC=60
#
# Cooja clears the environment before invoking make, so CONTIKI must resolve
# without relying on the shell: prefer the image's CONTIKI_NG, else Cooja's
# own CONTIKI variable, else fail loudly.
CONTIKI ?= $(CONTIKI_NG)
ifeq ($(CONTIKI),)
  CONTIKI := /home/user/contiki-ng
endif
ifeq ($(wildcard $(CONTIKI)/Makefile.include),)
  $(error Contiki-NG not found at '$(CONTIKI)'; run inside the rpl-ids container)
endif

CONTIKI_PROJECT = rpl-ids-root rpl-ids-node neighbor-attacker dis-attacker
all: $(CONTIKI_PROJECT)

PROJECTDIRS += ../include
PROJECT_SOURCEFILES += ids.c

# Detector mode: PAPER (fixed window) or SLIDING (ring buffer, section 6).
IDS_MODE ?= PAPER
CFLAGS += -DIDS_MODE_$(IDS_MODE)=1

# Optional overrides of project-conf.h tunables from the command line.
ifdef IDS_WINDOW_SEC
  CFLAGS += -DIDS_WINDOW_SEC=$(IDS_WINDOW_SEC)
endif
ifdef APP_SEND_INTERVAL_SEC
  CFLAGS += -DAPP_SEND_INTERVAL_SEC=$(APP_SEND_INTERVAL_SEC)
endif
ifdef IDS_DIS_THRESHOLD
  CFLAGS += -DIDS_DIS_THRESHOLD=$(IDS_DIS_THRESHOLD)
endif
ifdef IDS_WARMUP_WINDOWS
  CFLAGS += -DIDS_WARMUP_WINDOWS=$(IDS_WARMUP_WINDOWS)
endif
# Per-message EV logging. Without this clause the IDS_LOG_EVENTS=0 that
# gen_scenario.py puts on the make command line was silently ignored, because a
# make variable is not a preprocessor define; project-conf.h's default of 1
# always won. The analysis now counts control-plane overhead from EV records,
# so leave it enabled for scenarios whose traffic figures are reported.
ifdef IDS_LOG_EVENTS
  CFLAGS += -DIDS_LOG_EVENTS=$(IDS_LOG_EVENTS)
endif
ifdef ATTACK_START_SEC
  CFLAGS += -DATTACK_START_SEC=$(ATTACK_START_SEC)
endif
ifdef ATTACK_DURATION_SEC
  CFLAGS += -DATTACK_DURATION_SEC=$(ATTACK_DURATION_SEC)
endif
ifdef ATTACK_PERIOD_MS
  CFLAGS += -DATTACK_PERIOD_MS=$(ATTACK_PERIOD_MS)
endif
ifdef ATTACK_REBROADCAST
  CFLAGS += -DATTACK_REBROADCAST=$(ATTACK_REBROADCAST)
endif

# Sky-fit build (ROM/RAM overhead measurement): shrink tables and silence the
# per-message event log so the experimental node fits the Tmote Sky's 48 KB
# ROM / 10 KB RAM. Enable with `make TARGET=sky SKY_FIT=1`.
ifdef SKY_FIT
  CFLAGS += -DNBR_TABLE_CONF_MAX_NEIGHBORS=12 -DNETSTACK_MAX_ROUTE_ENTRIES=8
  CFLAGS += -DUIP_CONF_MAX_ROUTES=8 -DIDS_MAX_NEIGHBORS=12 -DIDS_LOG_EVENTS=0
  CFLAGS += -DLOG_CONF_LEVEL_MAIN=LOG_LEVEL_NONE
endif

MAKE_ROUTING = MAKE_ROUTING_RPL_LITE
MAKE_MAC = MAKE_MAC_CSMA
MAKE_NET = MAKE_NET_IPV6

include $(CONTIKI)/Makefile.include

# ---- Build-variant tracking -------------------------------------------------
# make does not rebuild objects when only -D flags change, and Cooja reuses
# firmware/build/ across scenarios. Objects that depend on the tunables above
# are made to depend on a stamp file that is rewritten only when the variant
# string changes, so switching window/mode/interval recompiles exactly them.
VARIANT_ID := mode-$(IDS_MODE)_win-$(IDS_WINDOW_SEC)_send-$(APP_SEND_INTERVAL_SEC)_dis-$(IDS_DIS_THRESHOLD)_warm-$(IDS_WARMUP_WINDOWS)_ev-$(IDS_LOG_EVENTS)_atk-$(ATTACK_START_SEC)-$(ATTACK_DURATION_SEC)-$(ATTACK_PERIOD_MS)-rb$(ATTACK_REBROADCAST)
VARIANT_STAMP := $(OBJECTDIR)/variant.stamp
$(VARIANT_STAMP): FORCE
	@mkdir -p $(dir $@)
	@[ "$$(cat $@ 2>/dev/null)" = "$(VARIANT_ID)" ] || { echo "$(VARIANT_ID)" > $@; echo "  VARIANT   $(VARIANT_ID)"; }
FORCE:
$(OBJECTDIR)/ids.o $(OBJECTDIR)/rpl-ids-node.o $(OBJECTDIR)/rpl-ids-root.o \
$(OBJECTDIR)/neighbor-attacker.o $(OBJECTDIR)/dis-attacker.o: $(VARIANT_STAMP)
