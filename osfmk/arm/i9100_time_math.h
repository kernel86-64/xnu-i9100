/* GT-I9100 time conversion helpers. Absolute time is nanoseconds; MCT is Hz. */
#ifndef I9100_TIME_MATH_H
#define I9100_TIME_MATH_H
#include <stdint.h>
static inline uint64_t i9100_ticks_to_nanoseconds(uint64_t ticks,uint64_t hz)
{
 if(!hz)return 0;
 /* Avoid ticks*1e9 overflow after ~12m49s with a 24MHz MCT. */
 return (ticks/hz)*1000000000ULL+((ticks%hz)*1000000000ULL)/hz;
}
static inline uint64_t i9100_scale_fixed32(uint64_t value,uint64_t scale)
{
 /* Low 64 bits of the full 128-bit product shifted right by 32. */
 uint64_t low=(uint64_t)(uint32_t)value*(uint32_t)scale;
 uint64_t middle1=(value>>32)*(uint32_t)scale;
 uint64_t middle2=(scale>>32)*(uint32_t)value;
 uint64_t high=(value>>32)*(scale>>32);
 return (low>>32)+middle1+middle2+(high<<32);
}
static inline int i9100_delay_should_spin(uint64_t nanoseconds)
{
 /* GPIO I2C and SD status polls require real microsecond delays. */
 return nanoseconds<=50000ULL;
}
#endif
