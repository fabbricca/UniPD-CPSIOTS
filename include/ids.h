/*
 * ids.h - lightweight distributed anomaly IDS for RPL (Farzaneh et al. 2019)
 *
 * Every normal node monitors the RPL control traffic it hears from each
 * neighbour. At the end of every observation window it builds the normal
 * profile (mean and standard deviation of per-neighbour DIO counts), derives
 * the dynamic threshold mean + k*sigma with k from the paper's polynomial
 * (include/ids-k-table.h), flags neighbours above it (neighbour attack) or
 * above the fixed DIS threshold (DIS attack), and blocks them: temporarily
 * for IDS_TEMP_BLOCK_SEC while block_count < IDS_BLOCK_THRESHOLD, then
 * permanently. Blocking drops the neighbour's DIS/DIO in the rpl-icmp6.c hook
 * before RPL sees them. Counting continues while blocked so the paper's
 * repeated-detection escalation works.
 *
 * All arithmetic is integer, scaled by 1000 ("x1000" fields).
 *
 * Log record formats (tab separated, printed with printf; Cooja's control
 * script prepends "<time_us>\t<mote_id>\t"):
 *   IDS   init window=W dis_thr=D block_thr=B temp_block=T warmup=U mode=M
 *   EV    <DIO|DIS> <nbr_id>                          one per received message
 *   NBR   <win> <nbr_id> <dio> <dis> <dropped> <bstate>   per neighbour at window end
 *                                                   bstate: 0 none, 1 temp, 2 permanent
 *   DET   <win> <n> <mean_x1000> <sigma_x1000> <k_x1000> <thr_x1000>   window profile
 *   ALERT <win> <nbr_id> <DIO|DIS> <count> <thr_x1000>
 *   BLOCK <nbr_id> <temp|perm|expire> <block_count> <duration_s>
 *   PAR   <old_id> <new_id> <changes>                 preferred-parent switch
 *   WIN   <win> <n_heard> <n_rpl> <dio_sum> <dis_sum>  window summary
 */
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
