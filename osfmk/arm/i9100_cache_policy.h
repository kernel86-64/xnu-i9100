/* ARMv7 short descriptors, SCTLR.TRE=0. Cortex-A9 cannot cache WT pages. */
#ifndef I9100_CACHE_POLICY_H
#define I9100_CACHE_POLICY_H
#include <stdint.h>

#define I9100_L2_CACHE_MASK 0x1ccU
#define I9100_L2_NORMAL_WBWA 0x04cU /* TEX=001, C=1, B=1, S=0 */
#define I9100_L2_NORMAL_NC   0x040U /* TEX=001, C=0, B=0, S=0 */
#define I9100_L1_NORMAL_NC   0x1000U

extern uint32_t i9100_ram_start, i9100_ram_bytes;
extern uint32_t i9100_scanout_start, i9100_scanout_end;

static inline unsigned i9100_ram_cache_policy(uint32_t pa, uint32_t ram_start,
    uint32_t ram_bytes, uint32_t scanout_start, uint32_t scanout_end, int inhibit)
{
    /* Subtraction avoids an overflowing RAM end address. MMIO stays ordered. */
    if (pa < ram_start || pa - ram_start >= ram_bytes) return 0;
    if (inhibit || (pa >= scanout_start && pa < scanout_end))
        return I9100_L2_NORMAL_NC;
    return I9100_L2_NORMAL_WBWA;
}

static inline unsigned i9100_cache_policy(uint32_t pa, int inhibit)
{
    return i9100_ram_cache_policy(pa, i9100_ram_start, i9100_ram_bytes,
        i9100_scanout_start, i9100_scanout_end, inhibit);
}
#endif
