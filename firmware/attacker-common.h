/*
 * attacker-common.h - shared attack scheduling for the neighbour and DIS
 * attackers. An attacker is a normal RPL node (joins the DODAG, sends CBR UDP
 * so it looks operational) plus a timer that emits extra RPL control messages
 * between ATTACK_START_SEC and ATTACK_START_SEC + ATTACK_DURATION_SEC.
 *
 * Ground-truth records (Cooja prepends "<time_us>\t<mote_id>\t"):
 *   ATK  start <type> <period_ms>          attack window begins
 *   ATK  send  <type> <seq>                one injected control message
 *   ATK  stop  <type> <sent>               attack window ends, total injected
 * The host analysis derives ground truth from these and the scenario's
 * .truth.csv, never from IDS output.
 *
 * Build parameters (firmware/Makefile pass-through):
 *   ATTACK_START_SEC     default 75  (paper: attack starts 75 s in)
 *   ATTACK_DURATION_SEC  default 600 (10 min); 0 = until end of run
 *   ATTACK_PERIOD_MS     fixed inter-message period; 0 = random 5-60 s (DIS)
 */
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
