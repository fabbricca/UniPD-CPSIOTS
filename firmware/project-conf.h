/*
 * Project configuration for the RPL IDS experiment.
 * Every deviation from Contiki-NG defaults is listed here so the report can
 * enumerate them. Values guarded by #ifndef can be overridden from the
 * Makefile command line (see firmware/Makefile).
 */
#ifndef PROJECT_CONF_H_
#define PROJECT_CONF_H_

/* ---- Topology / tables -------------------------------------------------- */
/* 40 nodes in 100 x 100 m with 50 m range: most nodes hear 15-25 others.
 * These sizes suit the cooja/native target used for the experiments; the
 * Tmote Sky build (ROM/RAM overhead measurement) overrides them smaller via
 * the Makefile SKY_FIT knobs. */
#ifndef NBR_TABLE_CONF_MAX_NEIGHBORS
#define NBR_TABLE_CONF_MAX_NEIGHBORS   32
#endif
#ifndef NETSTACK_MAX_ROUTE_ENTRIES
#define NETSTACK_MAX_ROUTE_ENTRIES     48
#endif
#ifndef UIP_CONF_MAX_ROUTES
#define UIP_CONF_MAX_ROUTES            48
#endif

/* ---- Application traffic: constant-bit-rate UDP toward the root --------- */
#define APP_UDP_CLIENT_PORT            8765
#define APP_UDP_SERVER_PORT            5678
#ifndef APP_SEND_INTERVAL_SEC
#define APP_SEND_INTERVAL_SEC          30
#endif
#ifndef APP_STATUS_INTERVAL_SEC
#define APP_STATUS_INTERVAL_SEC        30
#endif

/* ---- IDS parameters (paper defaults) ------------------------------------ */
#ifndef IDS_WINDOW_SEC
#define IDS_WINDOW_SEC                 300    /* paper: DIO counters reset every 5 min */
#endif
#ifndef IDS_DIS_THRESHOLD
#define IDS_DIS_THRESHOLD              3      /* paper: max normal DIS per window */
#endif
#ifndef IDS_BLOCK_THRESHOLD
#define IDS_BLOCK_THRESHOLD            2      /* paper: temporary blocks before permanent */
#endif
#ifndef IDS_TEMP_BLOCK_SEC
#define IDS_TEMP_BLOCK_SEC             60     /* paper: 1 minute */
#endif
/* Windows in which detection is suppressed (0 = paper behaviour). Kept as an
 * explicit experimental parameter for the warm-up discussion. */
#ifndef IDS_WARMUP_WINDOWS
#define IDS_WARMUP_WINDOWS             0
#endif
/* Sliding-window variant (original contribution). */
#ifndef IDS_SLIDE_BUCKET_SEC
#define IDS_SLIDE_BUCKET_SEC           10
#endif
#ifndef IDS_SLIDE_BUCKETS
#define IDS_SLIDE_BUCKETS              6      /* 6 x 10 s = 60 s window */
#endif
/* Per-neighbour table of the IDS itself (independent of RPL's table). */
#ifndef IDS_MAX_NEIGHBORS
#define IDS_MAX_NEIGHBORS              40
#endif
/* Log one EV line per received DIO/DIS (needed for time-series plots). */
#ifndef IDS_LOG_EVENTS
#define IDS_LOG_EVENTS                 1
#endif

/* ---- Instrumentation hooks ---------------------------------------------- */
/* Enables the guarded call in rpl-icmp6.c (patches/0001-...). */
#define RPL_IDS_HOOKS                  1
/* rpl-lite calls this on every preferred-parent change. */
#define RPL_CALLBACK_PARENT_SWITCH     ids_parent_switch

/* ---- Logging ------------------------------------------------------------ */
/* Our records are plain printf lines with a leading tag; keep the Contiki
 * log modules quiet so the serial output is dominated by them. */
#define LOG_CONF_LEVEL_RPL             LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_IPV6            LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_6LOWPAN         LOG_LEVEL_WARN
#define LOG_CONF_LEVEL_MAC             LOG_LEVEL_ERR   /* CSMA "not for us" is WARN and floods the log */
#ifndef LOG_CONF_LEVEL_MAIN
#define LOG_CONF_LEVEL_MAIN            LOG_LEVEL_INFO
#endif

#endif /* PROJECT_CONF_H_ */
