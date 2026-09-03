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

CONTIKI_PROJECT = rpl-ids-root rpl-ids-node
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

MAKE_ROUTING = MAKE_ROUTING_RPL_LITE
MAKE_MAC = MAKE_MAC_CSMA
MAKE_NET = MAKE_NET_IPV6

include $(CONTIKI)/Makefile.include

# ---- Build-variant tracking -------------------------------------------------
# make does not rebuild objects when only -D flags change, and Cooja reuses
# firmware/build/ across scenarios. Objects that depend on the tunables above
# are made to depend on a stamp file that is rewritten only when the variant
# string changes, so switching window/mode/interval recompiles exactly them.
VARIANT_ID := mode-$(IDS_MODE)_win-$(IDS_WINDOW_SEC)_send-$(APP_SEND_INTERVAL_SEC)
VARIANT_STAMP := $(OBJECTDIR)/variant.stamp
$(VARIANT_STAMP): FORCE
	@mkdir -p $(dir $@)
	@[ "$$(cat $@ 2>/dev/null)" = "$(VARIANT_ID)" ] || { echo "$(VARIANT_ID)" > $@; echo "  VARIANT   $(VARIANT_ID)"; }
FORCE:
$(OBJECTDIR)/ids.o $(OBJECTDIR)/rpl-ids-node.o $(OBJECTDIR)/rpl-ids-root.o: $(VARIANT_STAMP)
