#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <vector>
#include "i9100_time_math.h"
#include "i9100_framebuffer_copy.h"
static void time_checks()
{
 const uint64_t hz=24000000;
 uint64_t previous=0;
 for(unsigned seconds=0;seconds<=3600;seconds++) {
  uint64_t now=i9100_ticks_to_nanoseconds(hz*seconds,hz);
  assert(now==uint64_t(seconds)*1000000000ULL);
  if(seconds)assert(now>previous);
  previous=now;
 }
 const uint64_t ticks[]={1,2,3,hz-1,hz,hz+1,18446744073ULL,18446744074ULL,UINT64_MAX};
 for(uint64_t value:ticks)
  assert(i9100_ticks_to_nanoseconds(value,hz)==uint64_t((__uint128_t(value)*1000000000ULL)/hz));
 assert(i9100_ticks_to_nanoseconds(123,0)==0);
 const uint64_t values[]={0,1,1000000000ULL,180000000000ULL,3600000000000ULL,UINT64_MAX};
 const uint64_t scales[]={0,1,103079215ULL,178956970666ULL,UINT64_MAX};
 for(uint64_t value:values)for(uint64_t scale:scales)
  assert(i9100_scale_fixed32(value,scale)==uint64_t((__uint128_t(value)*scale)>>32));
 for(unsigned microseconds=0;microseconds<=50;microseconds++)assert(i9100_delay_should_spin(microseconds*1000ULL));
 assert(!i9100_delay_should_spin(50001) && !i9100_delay_should_spin(1000000));
 puts("Time: 24MHz -> ns across the old 12m49s overflow, hour monotonicity, full-width fixed point and microdelay spin boundaries passed");
}
static unsigned copies;
static void copy(void *destination,const void *source,uint32_t bytes)
{ ++copies;memcpy(destination,source,bytes); }
static void framebuffer_checks()
{
 const unsigned frame=480*800*4;
 std::vector<uint8_t> dst(frame+2,0xcc),src(frame);
 for(unsigned i=0;i<frame;i++)src[i]=uint8_t(i*17U+29U);
 assert(i9100_copy_frame(dst.data()+1,src.data(),frame,1920,copy));
 assert(copies==1 && !memcmp(dst.data()+1,src.data(),frame) && dst.front()==0xcc && dst.back()==0xcc);
 const unsigned pitch=2048,required=799*pitch+1920;
 std::vector<uint8_t> padded(required);
 for(unsigned i=0;i<required;i++)padded[i]=uint8_t(i*7U+19U);
 copies=0;assert(i9100_copy_frame(dst.data()+1,padded.data(),required,pitch,copy));assert(copies==800);
 for(unsigned y=0;y<800;y++)assert(!memcmp(dst.data()+1+y*1920,padded.data()+y*pitch,1920));
 unsigned before=copies;
 assert(!i9100_copy_frame(dst.data()+1,padded.data(),required-1,pitch,copy));
 assert(!i9100_copy_frame(dst.data()+1,padded.data(),required,1919,copy));
 assert(!i9100_copy_frame(dst.data()+1,padded.data(),UINT32_MAX,UINT32_MAX,copy));
 assert(!i9100_copy_frame(nullptr,padded.data(),required,pitch,copy));
 assert(!i9100_copy_frame(dst.data(),nullptr,required,pitch,copy));
 assert(copies==before && dst.front()==0xcc && dst.back()==0xcc);
 puts("Framebuffer: one burst for tightly packed frames, pitched rows, exact source bounds, unaligned pointers and guard bytes passed");
}
int main(){time_checks();framebuffer_checks();return 0;}
