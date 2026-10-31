/* PERF20's collection-off image lost touch on the phone. Keep the previously
 * working instrumented lock/preemption path until that regression is isolated.
 * The collection-off variant remains an explicitly selected host experiment. */
#ifndef _ARM_I9100_TRACE_CONFIG_H_
#define _ARM_I9100_TRACE_CONFIG_H_
#ifndef I9100_LOCK_TRACE
#define I9100_LOCK_TRACE 1
#endif
#endif
