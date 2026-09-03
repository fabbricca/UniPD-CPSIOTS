/*
 * ids.c - per-neighbour RPL control-message accounting (section 2).
 *
 * The neighbour table here is deliberately independent of RPL's: the paper's
 * monitor counts DIOs from every node it can hear, including nodes RPL never
 * selects as parents. Entries are keyed by the 16-bit node id derived from
 * the sender's IPv6 address, which under Cooja's default addressing equals
 * the mote id, so ground-truth joins on the host are trivial.
 */
#include "ids.h"
#include "net/routing/rpl-lite/rpl-neighbor.h"
#include "sys/ctimer.h"
#include <stdio.h>
#include <string.h>

static ids_nbr_t table[IDS_MAX_NEIGHBORS];
static uint8_t table_count;
static uint16_t window;
static uint16_t parent_changes;
static struct ctimer window_timer;
static uint8_t initialised;

/*---------------------------------------------------------------------------*/
uint16_t
ids_node_id(const uip_ipaddr_t *addr)
{
  if(addr == NULL) {
    return 0;
  }
  return ((uint16_t)addr->u8[14] << 8) | addr->u8[15];
}
/*---------------------------------------------------------------------------*/
static ids_nbr_t *
lookup(uint16_t id, int create)
{
  uint8_t i;
  for(i = 0; i < table_count; i++) {
    if(table[i].id == id) {
      return &table[i];
    }
  }
  if(create && table_count < IDS_MAX_NEIGHBORS) {
    ids_nbr_t *n = &table[table_count++];
    memset(n, 0, sizeof(*n));
    n->id = id;
    n->used = 1;
    return n;
  }
  return NULL;
}
/*---------------------------------------------------------------------------*/
int
ids_rpl_input(uint8_t code, const uip_ipaddr_t *from)
{
  uint16_t id = ids_node_id(from);
  ids_nbr_t *n;

  if(!initialised) {
    return 1;                       /* root or attacker: pass through */
  }
  n = lookup(id, 1);
  if(n == NULL) {
    return 1;                       /* table full: count nothing, accept */
  }
  if(code == RPL_CODE_DIO) {
    n->dio++;
#if IDS_LOG_EVENTS
    printf("EV\tDIO\t%u\n", id);
#endif
  } else if(code == RPL_CODE_DIS) {
    n->dis++;
#if IDS_LOG_EVENTS
    printf("EV\tDIS\t%u\n", id);
#endif
  }
  return 1;                         /* section 3 adds the blocking decision */
}
/*---------------------------------------------------------------------------*/
void
ids_parent_switch(rpl_nbr_t *old, rpl_nbr_t *new)
{
  parent_changes++;
  printf("PAR\t%u\t%u\t%u\n",
         ids_node_id(old ? rpl_neighbor_get_ipaddr(old) : NULL),
         ids_node_id(new ? rpl_neighbor_get_ipaddr(new) : NULL),
         parent_changes);
}
/*---------------------------------------------------------------------------*/
static void
window_end(void *ptr)
{
  uint8_t i;
  uint16_t dio_sum = 0, dis_sum = 0;

  for(i = 0; i < table_count; i++) {
    printf("NBR\t%u\t%u\t%u\t%u\n", window, table[i].id, table[i].dio, table[i].dis);
    dio_sum += table[i].dio;
    dis_sum += table[i].dis;
  }
  printf("WIN\t%u\t%u\t%d\t%u\t%u\n", window, table_count,
         rpl_neighbor_count(), dio_sum, dis_sum);

  /* Paper: counters are reset at the end of every window. Neighbours stay
   * known so a silent neighbour still contributes a zero to the mean. */
  for(i = 0; i < table_count; i++) {
    table[i].dio = 0;
    table[i].dis = 0;
  }
  window++;
  ctimer_reset(&window_timer);
}
/*---------------------------------------------------------------------------*/
void
ids_init(void)
{
  memset(table, 0, sizeof(table));
  table_count = 0;
  window = 0;
  parent_changes = 0;
  initialised = 1;
  ctimer_set(&window_timer, (clock_time_t)IDS_WINDOW_SEC * CLOCK_SECOND,
             window_end, NULL);
  printf("IDS\tinit\twindow=%u\tdis_thr=%u\tblock_thr=%u\ttemp_block=%u\n",
         IDS_WINDOW_SEC, IDS_DIS_THRESHOLD, IDS_BLOCK_THRESHOLD, IDS_TEMP_BLOCK_SEC);
}
/*---------------------------------------------------------------------------*/
uint16_t
ids_parent_changes(void)
{
  return parent_changes;
}
/*---------------------------------------------------------------------------*/
uint16_t
ids_window(void)
{
  return window;
}
/*---------------------------------------------------------------------------*/
const ids_nbr_t *
ids_neighbors(uint8_t *count)
{
  if(count) {
    *count = table_count;
  }
  return table;
}
/*---------------------------------------------------------------------------*/
