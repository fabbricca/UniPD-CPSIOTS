/* Shared attack scheduling. An attacker is a normal node plus a timer that
 * injects control messages between ATTACK_START_SEC and +ATTACK_DURATION_SEC.
 * ATTACK_PERIOD_MS = 0 selects the paper's random 5-60 s interval. */
#ifndef ATTACKER_COMMON_H_
#define ATTACKER_COMMON_H_

#include "contiki.h"
#include "net/routing/routing.h"
#include "net/ipv6/simple-udp.h"
#include "random.h"
#include <stdio.h>
#include <string.h>

#ifndef ATTACK_START_SEC
#define ATTACK_START_SEC     75
#endif
#ifndef ATTACK_DURATION_SEC
#define ATTACK_DURATION_SEC  600
#endif
#ifndef ATTACK_PERIOD_MS
#define ATTACK_PERIOD_MS     0     /* 0 = random 5..60 s, paper's DIS default */
#endif

/* Next inter-message delay in clock ticks. */
static inline clock_time_t
attack_next_delay(void)
{
  if(ATTACK_PERIOD_MS > 0) {
    return (ATTACK_PERIOD_MS * CLOCK_SECOND) / 1000;
  }
  /* Random 5..60 s (paper). random_rand() is 16-bit. */
  return (5 + (random_rand() % 56)) * CLOCK_SECOND;
}

#endif /* ATTACKER_COMMON_H_ */
