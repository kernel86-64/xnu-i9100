/* I9100 fatal-path witnesses. Include after the platform uint32_t definition. */
#ifndef _ARM_I9100_DIAGNOSTICS_H_
#define _ARM_I9100_DIAGNOSTICS_H_
#include "i9100_trace_config.h"
struct i9100_fault_snapshot {
    uint32_t thread, type, pc, lr, sp, far, fsr, psr, result;
};
void i9100_fault_failed(const struct i9100_fault_snapshot *, uint32_t);
void i9100_log_watch(uint32_t);
#endif
