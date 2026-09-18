/* Distributed anomaly IDS for RPL (Farzaneh et al., ICWR 2019).
 * Per-neighbour DIO/DIS counters, threshold mean+k*sigma, temporary and
 * permanent blocking. Log record formats are documented in the report. */
#ifndef IDS_H_
#define IDS_H_

#include "contiki.h"
#include "net/ipv6/uip.h"
#include "net/routing/rpl-lite/rpl.h"

typedef struct {
  uint16_t id;          /* neighbour node id (last 16 bits of its IPv6 address) */
  uint16_t dio;         /* DIOs heard in the current window (incl. dropped) */
  uint16_t dis;         /* DISs heard in the current window (incl. dropped) */
  uint16_t dropped;     /* messages dropped while blocked, current window */
  uint8_t block_count;  /* detections so far (paper: block_count) */
  uint8_t permanent;    /* permanently blocked */
  unsigned long block_until;  /* clock_seconds() at which a temp block ends, 0 = none */
#if IDS_MODE_SLIDING
  uint8_t dio_buckets[IDS_SLIDE_BUCKETS];  /* rolling per-bucket DIO counts */
  uint8_t dis_buckets[IDS_SLIDE_BUCKETS];  /* rolling per-bucket DIS counts */
#endif
} ids_nbr_t;

/* Start the observation-window timer. Call once from the node process. */
void ids_init(void);

/* Called by the patched rpl-icmp6.c for every DIS/DIO before RPL handles it.
 * code is RPL_CODE_DIS or RPL_CODE_DIO. Returns 0 to drop, 1 to accept. */
int ids_rpl_input(uint8_t code, const uip_ipaddr_t *from);

/* Bound to RPL_CALLBACK_PARENT_SWITCH in project-conf.h. */
void ids_parent_switch(rpl_nbr_t *old, rpl_nbr_t *new);

/* Paper-faithful neighbour attack (ATTACK_REBROADCAST): the hook queues one
 * rebroadcast per received DIO; the attacker process drains the queue outside
 * the RPL receive path. Enable/disable gates the attack interval. */
void ids_rebroadcast_enable(int on);
uint8_t ids_take_rebroadcast(void);   /* pending count, cleared on read */
uint16_t ids_rebroadcast_dropped(void);

/* Helpers shared with the node firmware. */
uint16_t ids_node_id(const uip_ipaddr_t *addr);   /* 0 when addr is NULL */
uint16_t ids_parent_changes(void);
uint16_t ids_window(void);                        /* windows completed so far */
const ids_nbr_t *ids_neighbors(uint8_t *count);   /* current table */

#endif /* IDS_H_ */
