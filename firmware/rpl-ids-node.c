/* Normal node: RPL router, CBR UDP client toward the root, IDS monitor. */
#include "contiki.h"
#include "net/routing/routing.h"
#include "net/netstack.h"
#include "net/ipv6/simple-udp.h"
#include "net/routing/rpl-lite/rpl.h"
#include "net/routing/rpl-lite/rpl-neighbor.h"
#include "random.h"
#include "ids.h"
#include <stdio.h>
#include <string.h>

static struct simple_udp_connection udp_conn;
static uint32_t tx_count;

PROCESS(node_process, "RPL IDS node");
AUTOSTART_PROCESSES(&node_process);
/*---------------------------------------------------------------------------*/
static void
print_status(void)
{
  uint8_t ids_nbrs = 0;
  uint16_t rank = 0, parent = 0;

  /* Rank/parent are only meaningful once RPL reports the root reachable;
   * before that both are logged as 0, which parse_logs.py uses as "not joined". */
  if(NETSTACK_ROUTING.node_is_reachable() && curr_instance.used) {
    rank = curr_instance.dag.rank;
    if(curr_instance.dag.preferred_parent != NULL) {
      parent = ids_node_id(rpl_neighbor_get_ipaddr(curr_instance.dag.preferred_parent));
    }
  }
  ids_neighbors(&ids_nbrs);
  printf("STAT\t%u\t%u\t%u\t%lu\t%d\t%u\n", rank, parent, ids_parent_changes(),
         (unsigned long)tx_count, rpl_neighbor_count(), ids_nbrs);
}
/*---------------------------------------------------------------------------*/
PROCESS_THREAD(node_process, ev, data)
{
  static struct etimer send_timer;
  static struct etimer status_timer;
  static char buf[16];
  uip_ipaddr_t root;

  PROCESS_BEGIN();

  simple_udp_register(&udp_conn, APP_UDP_CLIENT_PORT, NULL,
                      APP_UDP_SERVER_PORT, NULL);
  ids_init();

  /* Desynchronise senders: first send at a random point in the interval. */
  etimer_set(&send_timer, random_rand() % (APP_SEND_INTERVAL_SEC * CLOCK_SECOND));
  etimer_set(&status_timer, APP_STATUS_INTERVAL_SEC * CLOCK_SECOND);

  while(1) {
    PROCESS_WAIT_EVENT();

    if(etimer_expired(&send_timer)) {
      if(NETSTACK_ROUTING.node_is_reachable() &&
         NETSTACK_ROUTING.get_root_ipaddr(&root)) {
        snprintf(buf, sizeof(buf), "%lu", (unsigned long)tx_count);
        simple_udp_sendto(&udp_conn, buf, strlen(buf), &root);
        printf("TX\t%lu\n", (unsigned long)tx_count);
        tx_count++;
      }
      /* Constant bit rate with +-1 s jitter to avoid lockstep collisions. */
      etimer_set(&send_timer, APP_SEND_INTERVAL_SEC * CLOCK_SECOND
                 - CLOCK_SECOND + (random_rand() % (2 * CLOCK_SECOND)));
    }
    if(etimer_expired(&status_timer)) {
      print_status();
      etimer_reset(&status_timer);
    }
  }

  PROCESS_END();
}
/*---------------------------------------------------------------------------*/
