/* DODAG root and UDP sink. Runs no detector: the IDS is distributed. */
#include "contiki.h"
#include "net/routing/routing.h"
#include "net/netstack.h"
#include "net/ipv6/simple-udp.h"
#include "net/ipv6/uip-ds6-route.h"
#include "net/routing/rpl-lite/rpl-neighbor.h"
#include "ids.h"
#include <stdio.h>

static struct simple_udp_connection udp_conn;
static uint32_t rx_count;

PROCESS(root_process, "RPL IDS root");
AUTOSTART_PROCESSES(&root_process);
/*---------------------------------------------------------------------------*/
static void
udp_rx_callback(struct simple_udp_connection *c,
                const uip_ipaddr_t *sender_addr, uint16_t sender_port,
                const uip_ipaddr_t *receiver_addr, uint16_t receiver_port,
                const uint8_t *data, uint16_t datalen)
{
  rx_count++;
  printf("RX\t%u\t%.*s\n", ids_node_id(sender_addr), (int)datalen, (const char *)data);
}
/*---------------------------------------------------------------------------*/
PROCESS_THREAD(root_process, ev, data)
{
  static struct etimer status_timer;

  PROCESS_BEGIN();

  NETSTACK_ROUTING.root_start();
  simple_udp_register(&udp_conn, APP_UDP_SERVER_PORT, NULL,
                      APP_UDP_CLIENT_PORT, udp_rx_callback);
  printf("ROOT\tstart\n");

  etimer_set(&status_timer, APP_STATUS_INTERVAL_SEC * CLOCK_SECOND);
  while(1) {
    PROCESS_WAIT_EVENT_UNTIL(etimer_expired(&status_timer));
    printf("RSTAT\t%lu\t%d\t%d\n", (unsigned long)rx_count,
           rpl_neighbor_count(), uip_ds6_route_num_routes());
    etimer_reset(&status_timer);
  }

  PROCESS_END();
}
/*---------------------------------------------------------------------------*/
