# Contiki-NG instrumentation patches

Applied automatically to the pinned Contiki-NG tree during `docker build`.

Planned (Phase 2):

* `0001-rpl-icmp6-ids-hook.patch` adds a weak hook
  `int ids_rpl_input(uint8_t code, const uip_ipaddr_t *from)` called at the
  top of `dio_input()` and `dis_input()` in `os/net/routing/rpl-lite/rpl-icmp6.c`.
  Returning 0 drops the message, which is how blocking is implemented without
  touching RPL's neighbor table. Guarded by `RPL_IDS_HOOKS`.

Rationale: Contiki-NG registers exactly one ICMPv6 input handler per
(type, code), so a second handler cannot be chained from project code.
