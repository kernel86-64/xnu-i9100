/* Bounded 480x800x32 RAM framebuffer copy; callback supplies platform bcopy. */
#ifndef I9100_FRAMEBUFFER_COPY_H
#define I9100_FRAMEBUFFER_COPY_H
#include <stdint.h>
typedef void (*i9100_frame_copy_fn)(void *,const void *,uint32_t);
static inline int i9100_copy_frame(void *destination,const uint8_t *source,
 uint32_t bytes,uint32_t stride,i9100_frame_copy_fn copy)
{
 unsigned y;
 if(!destination || !source || !copy || stride<1920U ||
    (uint64_t)stride*799U+1920U>bytes)return 0;
 if(stride==1920U)copy(destination,source,1536000U);
 else for(y=0;y<800U;y++)copy((uint8_t *)destination+y*1920U,source+(uint64_t)y*stride,1920U);
 return 1;
}
#endif
