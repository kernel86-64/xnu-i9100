#ifndef I9100_MALI_USER_H
#define I9100_MALI_USER_H
#include <stdint.h>
/* Versioned, pointer-free userspace request. Only fixed private GPU programs
 * are accepted; no user addresses, GPU registers or arbitrary command words. */
#define I9100_MALI_USER_ABI 1U
#define I9100_MALI_OP_CLEAR 1U
#define I9100_MALI_OP_COPY2X2 2U
#define I9100_MALI_OP_BLEND2X2 3U
struct i9100_mali_request {
 uint32_t version,operation,background,reserved,texels[4];
};
struct i9100_mali_reply {
 uint32_t version; int32_t error;
 uint32_t restore,pixels,output[256];
};
typedef char i9100_mali_request_size[(sizeof(struct i9100_mali_request)==32)?1:-1];
typedef char i9100_mali_reply_size[(sizeof(struct i9100_mali_reply)==1040)?1:-1];
static inline int i9100_mali_request_valid(const struct i9100_mali_request *r)
{
 if(!r || r->version!=I9100_MALI_USER_ABI || r->reserved ||
    r->operation<1 || r->operation>3)return 0;
 if(r->operation==3 && (r->background>>24)!=255)return 0;
 for(unsigned n=0;n<4;n++) {
  uint32_t v=r->texels[n],a=v>>24;
  if(r->operation==1 && v)return 0;
  if(r->operation==2 && a!=255)return 0;
  if(r->operation==3 && ((v&255)>a || ((v>>8)&255)>a || ((v>>16)&255)>a))return 0;
 }
 return 1;
}
#endif
