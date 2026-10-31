#ifndef I9100_MALI_H
#define I9100_MALI_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define I9100_MALI_BYTES 65536U
#define I9100_MALI_VA 0x01000000U
enum { I9100_MALI_GPU=0, I9100_MALI_CMU=1, I9100_MALI_PMU=2 };
struct i9100_mali_io {
 void *cookie;
 uint32_t (*read)(void *,unsigned,unsigned);
 void (*write)(void *,unsigned,unsigned,uint32_t);
 void (*delay_us)(void *,unsigned);
 void (*barrier)(void *);
 int (*pmic_read)(void *,unsigned,uint8_t *);
 int (*pmic_write)(void *,unsigned,uint8_t);
};
struct i9100_mali_status {
 unsigned phase; int error;
 unsigned restore, gp_version, pp_version, pp_mask, clock_mhz;
 unsigned gp_irq, pp_irq, mmu_fault, pixels, bad_offset, actual, guard;
 unsigned trial, vertices, triangles;
 unsigned textures, blends, render_mask;
};
extern volatile struct i9100_mali_status i9100_mali_observation;
/* Private wired NC arena, contiguous/aligned, never a display or userspace BO.
 * Caller retains arena even on errors; GPU quiescence is not assumed on timeout. */
int i9100_mali_selftest(const struct i9100_mali_io *, volatile uint32_t *,
                      uint32_t, unsigned, volatile struct i9100_mali_status *);
#ifdef __cplusplus
}
#endif
#endif
