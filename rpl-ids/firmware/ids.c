/* Detector core: counts RPL control messages per neighbour, applies the
 * paper's threshold at each evaluation, and blocks offenders. */
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
#define IDS_EVAL_PERIOD_SEC IDS_SLIDE_BUCKET_SEC
#else
#define IDS_MODE_NAME "paper"
#define IDS_EVAL_PERIOD_SEC IDS_WINDOW_SEC
#endif

static ids_nbr_t table[IDS_MAX_NEIGHBORS];
static uint8_t table_count;
static uint16_t window;              /* evaluations completed so far */
static uint16_t parent_changes;
static struct ctimer eval_timer;
static uint8_t initialised;
#if ATTACK_REBROADCAST
/* Queue of DIOs to rebroadcast, capped so a mutual echo between attackers
 * cannot saturate the medium; drops are counted and logged. */
#ifndef ATTACK_REBCAST_QUEUE
#define ATTACK_REBCAST_QUEUE 16
#endif
/* Minimum seconds between two rebroadcasts of DIOs from the same source.
 * Without it, attackers rebroadcast each other's rebroadcasts and the echo
 * grows without bound; the paper's ContikiMAC duty cycling throttles this
 * implicitly, while CSMA with the radio always on does not. */
#ifndef ATTACK_REBCAST_MIN_INTERVAL
#define ATTACK_REBCAST_MIN_INTERVAL 10
#endif
#ifndef ATTACK_REBCAST_SOURCES
#define ATTACK_REBCAST_SOURCES 24
#endif
static uint8_t rebcast_pending;
static uint8_t rebcast_on;
static uint16_t rebcast_dropped;
static uint16_t rebcast_src_id[ATTACK_REBCAST_SOURCES];
static unsigned long rebcast_src_last[ATTACK_REBCAST_SOURCES];
static uint8_t rebcast_src_count;

/* True at most once per ATTACK_REBCAST_MIN_INTERVAL per source. */
static int
rebcast_due(uint16_t id)
{
  uint8_t i;
  unsigned long now = clock_seconds();
  for(i = 0; i < rebcast_src_count; i++) {
    if(rebcast_src_id[i] == id) {
      if(now - rebcast_src_last[i] < ATTACK_REBCAST_MIN_INTERVAL) {
        return 0;
      }
      rebcast_src_last[i] = now;
      return 1;
    }
  }
  if(rebcast_src_count < ATTACK_REBCAST_SOURCES) {
    rebcast_src_id[rebcast_src_count] = id;
    rebcast_src_last[rebcast_src_count] = now;
    rebcast_src_count++;
  }
  return 1;
}
#endif
#if IDS_MODE_SLIDING
static uint8_t head;                 /* current bucket index */
static uint8_t filled;               /* buckets accumulated so far (<= N) */
#endif

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
/* Window counts for neighbour i, per mode. */
static uint16_t
win_dio(ids_nbr_t *n)
{
#if IDS_MODE_SLIDING
  uint16_t s = 0;
  uint8_t b;
  for(b = 0; b < IDS_SLIDE_BUCKETS; b++) {
    s += n->dio_buckets[b];
  }
  return s;
#else
  return n->dio;
#endif
}
/*---------------------------------------------------------------------------*/
static uint16_t
win_dis(ids_nbr_t *n)
{
#if IDS_MODE_SLIDING
  uint16_t s = 0;
  uint8_t b;
  for(b = 0; b < IDS_SLIDE_BUCKETS; b++) {
    s += n->dis_buckets[b];
  }
  return s;
#else
  return n->dis;
#endif
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
#if ATTACK_REBROADCAST
void
ids_rebroadcast_enable(int on)
{
  rebcast_on = on ? 1 : 0;
  if(!on) {
    rebcast_pending = 0;
  } else {
    rebcast_src_count = 0;
  }
}
/*---------------------------------------------------------------------------*/
uint8_t
ids_take_rebroadcast(void)
{
  uint8_t v = rebcast_pending;
  rebcast_pending = 0;
  return v;
}
/*---------------------------------------------------------------------------*/
uint16_t
ids_rebroadcast_dropped(void)
{
  return rebcast_dropped;
}
/*---------------------------------------------------------------------------*/
#endif /* ATTACK_REBROADCAST */
int
ids_rpl_input(uint8_t code, const uip_ipaddr_t *from)
{
  uint16_t id = ids_node_id(from);
  ids_nbr_t *n;

#if ATTACK_REBROADCAST
  /* Paper's neighbour attack: rebroadcast every DIO received from a neighbour.
   * Queued here and emitted by the attacker process, never from this path. */
  if(rebcast_on && code == RPL_CODE_DIO && rebcast_due(id)) {
    if(rebcast_pending < ATTACK_REBCAST_QUEUE) {
      rebcast_pending++;
    } else {
      rebcast_dropped++;
    }
  }
#endif
  if(!initialised) {
    return 1;                       /* root or attacker: pass through */
  }
  n = lookup(id, 1);
  if(n == NULL) {
    return 1;                       /* table full: count nothing, accept */
  }
  if(code == RPL_CODE_DIO) {
#if IDS_MODE_SLIDING
    if(n->dio_buckets[head] < 255) { n->dio_buckets[head]++; }
#else
    n->dio++;
#endif
#if IDS_LOG_EVENTS
    printf("EV\tDIO\t%u\n", id);
#endif
  } else if(code == RPL_CODE_DIS) {
#if IDS_MODE_SLIDING
    if(n->dis_buckets[head] < 255) { n->dis_buckets[head]++; }
#else
    n->dis++;
#endif
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
/* Paper Algorithms 1 and 2 over per-neighbour window counts. Scaled by 1000;
 * scripts/ids_model.py is the bit-exact reference. dio[]/dis[] are indexed in
 * lock-step with table[0..n-1]. */
static void
detect_over(const uint16_t *dio, const uint16_t *dis, uint8_t n)
{
  uint8_t i;
  uint32_t sum = 0, sumsq = 0;
  uint32_t mean_x1000 = 0, sigma_x1000 = 0;
  uint16_t k_x1000 = ids_k_x1000[n < IDS_K_TABLE_MAX ? n : IDS_K_TABLE_MAX];
  uint32_t thr_x1000 = 0;

  for(i = 0; i < n; i++) {
    sum += dio[i];
    sumsq += (uint32_t)dio[i] * dio[i];
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
    return;
  }
  for(i = 0; i < n; i++) {
    if((uint32_t)dio[i] * 1000UL > thr_x1000) {
      printf("ALERT\t%u\t%u\tDIO\t%u\t%lu\n", window, table[i].id, dio[i],
             (unsigned long)thr_x1000);
      block(&table[i]);
    }
    if(dis[i] > IDS_DIS_THRESHOLD) {
      printf("ALERT\t%u\t%u\tDIS\t%u\t%lu\n", window, table[i].id, dis[i],
             (unsigned long)IDS_DIS_THRESHOLD * 1000UL);
      block(&table[i]);
    }
  }
}
/*---------------------------------------------------------------------------*/
static void
evaluate(void *ptr)
{
  uint8_t i;
  uint16_t wd[IDS_MAX_NEIGHBORS];
  uint16_t ws[IDS_MAX_NEIGHBORS];
  uint16_t dio_sum = 0, dis_sum = 0;

  for(i = 0; i < table_count; i++) {
    wd[i] = win_dio(&table[i]);
    ws[i] = win_dis(&table[i]);
    printf("NBR\t%u\t%u\t%u\t%u\t%u\t%u\n", window, table[i].id, wd[i], ws[i],
           table[i].dropped, block_state(&table[i]));
    dio_sum += wd[i];
    dis_sum += ws[i];
  }
  printf("WIN\t%u\t%u\t%d\t%u\t%u\n", window, table_count,
         rpl_neighbor_count(), dio_sum, dis_sum);

  detect_over(wd, ws, table_count);

#if IDS_MODE_SLIDING
  /* Advance the ring: next bucket becomes current and is cleared. The dropped
   * counter is per-evaluation and reset each tick. */
  head = (head + 1) % IDS_SLIDE_BUCKETS;
  for(i = 0; i < table_count; i++) {
    table[i].dio_buckets[head] = 0;
    table[i].dis_buckets[head] = 0;
    table[i].dropped = 0;
  }
  if(filled < IDS_SLIDE_BUCKETS) {
    filled++;
  }
#else
  /* Paper: reset all counters at the end of the window. */
  for(i = 0; i < table_count; i++) {
    table[i].dio = 0;
    table[i].dis = 0;
    table[i].dropped = 0;
  }
#endif
  window++;
  ctimer_reset(&eval_timer);
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
#if IDS_MODE_SLIDING
  head = 0;
  filled = 0;
#endif
  ctimer_set(&eval_timer, (clock_time_t)IDS_EVAL_PERIOD_SEC * CLOCK_SECOND,
             evaluate, NULL);
  printf("IDS\tinit\twindow=%u\tdis_thr=%u\tblock_thr=%u\ttemp_block=%u\twarmup=%u\tmode=%s\teval=%u\n",
         IDS_WINDOW_SEC, IDS_DIS_THRESHOLD, IDS_BLOCK_THRESHOLD, IDS_TEMP_BLOCK_SEC,
         IDS_WARMUP_WINDOWS, IDS_MODE_NAME, IDS_EVAL_PERIOD_SEC);
}
/*---------------------------------------------------------------------------*/
uint16_t ids_parent_changes(void) { return parent_changes; }
uint16_t ids_window(void) { return window; }
const ids_nbr_t *ids_neighbors(uint8_t *count)
{
  if(count) { *count = table_count; }
  return table;
}
/*---------------------------------------------------------------------------*/
