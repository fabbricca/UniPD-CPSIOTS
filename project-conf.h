/*
 * Project configuration for the RPL IDS experiment.
 * Every deviation from Contiki-NG defaults is documented here so the
 * report can list them (Phase 0 / Phase 1).
 */
#ifndef PROJECT_CONF_H_
#define PROJECT_CONF_H_

/* Dense topology: 40 nodes in 100x100 m with 50 m range. */
#define NBR_TABLE_CONF_MAX_NEIGHBORS   32
#define NETSTACK_MAX_ROUTE_ENTRIES     32

/* Application traffic: constant-bit-rate UDP toward the root. */
#define APP_UDP_PORT                   5678
#define APP_SEND_INTERVAL_SEC          30

/* IDS parameters (paper defaults). Override from the Makefile if needed. */
#ifndef IDS_WINDOW_SEC
#define IDS_WINDOW_SEC                 300    /* paper: DIO counters reset every 5 min */
#endif
#ifndef IDS_DIS_THRESHOLD
#define IDS_DIS_THRESHOLD              3      /* paper: max normal DIS per window */
#endif
#ifndef IDS_BLOCK_THRESHOLD
#define IDS_BLOCK_THRESHOLD            2      /* paper: temp blocks before permanent */
#endif
#ifndef IDS_TEMP_BLOCK_SEC
#define IDS_TEMP_BLOCK_SEC             60     /* paper: 1 minute */
#endif
/* Sliding-window variant (original contribution, Phase 7). */
#ifndef IDS_SLIDE_BUCKET_SEC
#define IDS_SLIDE_BUCKET_SEC           10
#endif
#ifndef IDS_SLIDE_BUCKETS
#define IDS_SLIDE_BUCKETS              6      /* 6 x 10 s = 60 s window */
#endif

/* Enable the two-line instrumentation hook in rpl-icmp6.c (patches/). */
#define RPL_IDS_HOOKS                  1

/* Quieter logs: only our CSV lines plus RPL warnings. */
#define LOG_CONF_LEVEL_RPL             LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_IPV6            LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_6LOWPAN         LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_MAC             LOG_LEVEL_WARN

#endif /* PROJECT_CONF_H_ */
