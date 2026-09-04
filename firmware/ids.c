/*
 * ids.c - distributed anomaly IDS for RPL neighbour and DIS attacks.
 * See include/ids.h for the algorithm summary and the log record formats.
 *
 * The neighbour table here is deliberately independent of RPL's: the paper's
 * monitor counts DIOs from every node it can hear, including nodes RPL never
 * selects as parents. Entries are keyed by the 16-bit node id derived from
 * the sender's IPv6 address, which under Cooja's default addressing equals
 * the mote id, so ground-truth joins on the host are trivial.
 */
#include "ids.h"
#include "ids-k-table.h"
#include "net/routing/rpl-lite/rpl-neighbor.h"
#include "sys/ctimer.h"
#include "sys/clock.h"
#include <stdio.h>
#include <string.h>

#ifndef IDS_WARMUP_WINDOWS
#define IDS_WARMUP_WINDOWS 0
#endif
#if IDS_MODE_SLIDING
#define IDS_MODE_NAME "sliding"
#else
#define IDS_MODE_NAME "paper"
#endif

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
/* Exact integer square root (floor) of a 64-bit value; runs once per window. */
static uint32_t
isqrt64(uint64_t x)
{
  uint64_t r = 0;
  uint64_t bit = (uint64_t)1 << 62;
  while(bit > x) {
    bit >>= 2;
  }
  while(bit != 0) {
    if(x >= r + bit) {
      x -= r + bit;
      r = (r >> 1) + bit;
    } else {
      r >>= 1;
    }
    bit >>= 2;
  }
  return (uint32_t)r;
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
    return n;
  }
  return NULL;
}
/*---------------------------------------------------------------------------*/
static uint8_t
block_state(ids_nbr_t *n)
{
  if(n->permanent) {
    return 2;
  }
  if(n->block_until != 0) {
    if(clock_seconds() < n->block_until) {
      return 1;
    }
    /* Temporary block elapsed: neighbour is reconsidered (paper phase IV). */
    n->block_until = 0;
    printf("BLOCK\t%u\texpire\t%u\t%u\n", n->id, n->block_count, IDS_TEMP_BLOCK_SEC);
  }
  return 0;
}
/*---------------------------------------------------------------------------*/
static void
block(ids_nbr_t *n)
{
  if(n->permanent) {
    return;
  }
  if(n->block_count < IDS_BLOCK_THRESHOLD) {
    n->block_count++;
    n->block_until = clock_seconds() + IDS_TEMP_BLOCK_SEC;
    printf("BLOCK\t%u\ttemp\t%u\t%u\n", n->id, n->block_count, IDS_TEMP_BLOCK_SEC);
  } else {
    n->permanent = 1;
    n->block_until = 0;
    printf("BLOCK\t%u\tperm\t%u\t0\n", n->id, n->block_count);
  }
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
  if(block_state(n) != 0) {
    n->dropped++;
    return 0;                       /* blocked: RPL never sees the message */
  }
  return 1;
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
/* Paper algorithms 1 and 2 over the counts of the window that just ended.
 * Scaled by 1000; scripts/ids_model.py is the bit-exact reference. */
static void
detect(void)
{
  uint8_t i;
  uint8_t n = table_count;
  uint32_t sum = 0, sumsq = 0;
  uint32_t mean_x1000 = 0, sigma_x1000 = 0;
  uint16_t k_x1000 = ids_k_x1000[n < IDS_K_TABLE_MAX ? n : IDS_K_TABLE_MAX];
  uint32_t thr_x1000 = 0;

  for(i = 0; i < n; i++) {
    sum += table[i].dio;
    sumsq += (uint32_t)table[i].dio * table[i].dio;
  }
  if(n > 0) {
    uint64_t num = (uint64_t)n * sumsq - (uint64_t)sum * sum;  /* n^2 * variance */
    mean_x1000 = (sum * 1000UL) / n;
    sigma_x1000 = isqrt64(num * 1000000ULL) / n;
    thr_x1000 = mean_x1000 + (uint32_t)(((uint64_t)k_x1000 * sigma_x1000) / 1000);
  }
  printf("DET\t%u\t%u\t%lu\t%lu\t%u\t%lu\n", window, n,
         (unsigned long)mean_x1000, (unsigned long)sigma_x1000, k_x1000,
         (unsigned long)thr_x1000);

  if(window < IDS_WARMUP_WINDOWS) {
    return;                         /* experimental parameter, 0 = paper */
  }
  for(i = 0; i < n; i++) {
    if((uint32_t)table[i].dio * 1000UL > thr_x1000) {
      printf("ALERT\t%u\t%u\tDIO\t%u\t%lu\n", window, table[i].id, table[i].dio,
             (unsigned long)thr_x1000);
      block(&table[i]);
    }
    if(table[i].dis > IDS_DIS_THRESHOLD) {
      printf("ALERT\t%u\t%u\tDIS\t%u\t%lu\n", window, table[i].id, table[i].dis,
             (unsigned long)IDS_DIS_THRESHOLD * 1000UL);
      block(&table[i]);
    }
  }
}
/*---------------------------------------------------------------------------*/
static void
window_end(void *ptr)
{
  uint8_t i;
  uint16_t dio_sum = 0, dis_sum = 0;

  for(i = 0; i < table_count; i++) {
    printf("NBR\t%u\t%u\t%u\t%u\t%u\t%u\n", window, table[i].id, table[i].dio,
           table[i].dis, table[i].dropped, block_state(&table[i]));
    dio_sum += table[i].dio;
    dis_sum += table[i].dis;
  }
  printf("WIN\t%u\t%u\t%d\t%u\t%u\n", window, table_count,
         rpl_neighbor_count(), dio_sum, dis_sum);

  detect();

  /* Paper: counters are reset at the end of every window. Neighbours stay
   * known so a silent neighbour still contributes a zero to the mean. */
  for(i = 0; i < table_count; i++) {
    table[i].dio = 0;
    table[i].dis = 0;
    table[i].dropped = 0;
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
  printf("IDS\tinit\twindow=%u\tdis_thr=%u\tblock_thr=%u\ttemp_block=%u\twarmup=%u\tmode=%s\n",
         IDS_WINDOW_SEC, IDS_DIS_THRESHOLD, IDS_BLOCK_THRESHOLD, IDS_TEMP_BLOCK_SEC,
         IDS_WARMUP_WINDOWS, IDS_MODE_NAME);
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
