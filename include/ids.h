/*
 * ids.h - lightweight distributed anomaly IDS for RPL (Farzaneh et al. 2019)
 *
 * Section 2 scope: per-neighbour DIO/DIS counters, observation windows,
 * parent-change tracking and CSV logging. Detection (section 3) and
 * blocking (section 3) plug into the same state.
 *
 * Log record formats (all tab separated, printed with printf; Cooja's
 * control script prepends "<time_us>\t<mote_id>\t"):
 *   EV   <DIO|DIS> <nbr_id>                       one per received message
 *   NBR  <win> <nbr_id> <dio> <dis>               per neighbour at window end
 *   WIN  <win> <n_heard> <n_rpl> <dio_sum> <dis_sum>  window summary
 *   PAR  <old_id> <new_id> <changes>              preferred-parent switch
 */
#ifndef IDS_H_
#define IDS_H_

#include "contiki.h"
#include "net/ipv6/uip.h"
#include "net/routing/rpl-lite/rpl.h"

typedef struct {
  uint16_t id;        /* neighbour node id (last 16 bits of its IPv6 address) */
  uint16_t dio;       /* DIOs received in the current window */
  uint16_t dis;       /* DISs received in the current window */
  uint8_t used;
} ids_nbr_t;

/* Start the observation-window timer. Call once from the node process. */
void ids_init(void);

/* Called by the patched rpl-icmp6.c for every DIS/DIO before RPL handles it.
 * code is RPL_CODE_DIS or RPL_CODE_DIO. Returns 0 to drop, 1 to accept. */
int ids_rpl_input(uint8_t code, const uip_ipaddr_t *from);

/* Bound to RPL_CALLBACK_PARENT_SWITCH in project-conf.h. */
void ids_parent_switch(rpl_nbr_t *old, rpl_nbr_t *new);

/* Helpers shared with the node firmware. */
uint16_t ids_node_id(const uip_ipaddr_t *addr);   /* 0 when addr is NULL */
uint16_t ids_parent_changes(void);
uint16_t ids_window(void);                        /* windows completed so far */
const ids_nbr_t *ids_neighbors(uint8_t *count);   /* current table */

#endif /* IDS_H_ */
