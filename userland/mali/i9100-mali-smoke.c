/* Original diagnostic client for the bounded i9100 Mali userspace ABI.
 * No Apple SDK headers or binaries are included. This is not a GLES backend. */
#include <stdint.h>
#include <stddef.h>
#include "i9100_mali_user.h"
typedef uint32_t port_t;
extern port_t mach_task_self_;
extern void *IOServiceMatching(const char *);
extern port_t IOServiceGetMatchingService(port_t,void *);
extern int IOServiceOpen(port_t,port_t,uint32_t,port_t *);
extern int IOObjectRelease(port_t);
extern int IOServiceClose(port_t);
extern int IOConnectCallStructMethod(port_t,uint32_t,const void *,size_t,void *,size_t *);
extern int printf(const char *,...);
extern int usleep(unsigned);
static unsigned blend(unsigned s,unsigned d){
 unsigned v=0,a=s>>24;
 for(unsigned n=0;n<4;n++){
  unsigned x=((s>>(8*n))&255)+(((d>>(8*n))&255)*(255-a)+127)/255;
  v|=(x>255?255:x)<<(8*n);
 }
 return v;
}
int main(void){
 port_t service=0,connection=0;
 for(unsigned n=0;n<100 && !service;n++){
  service=IOServiceGetMatchingService(0,IOServiceMatching("IOS7I9100Mali"));
  if(!service)usleep(100000);
 }
 if(!service){printf("MALI USER: service missing\n");return 1;}
 int e=IOServiceOpen(service,mach_task_self_,0,&connection);IOObjectRelease(service);
 if(e){printf("MALI USER: open %08x\n",e);return 2;}
 struct i9100_mali_request r={1,1,0xff123456,0,{0}};
 struct i9100_mali_reply out;
 for(unsigned op=1;op<=3;op++){
  r.operation=op;
  for(unsigned n=0;n<4;n++)r.texels[n]=op==1?0:op==2?(0xff112233U+n*0x00110110U):(0x80402010U+n*0x000a0502U);
  size_t size=sizeof(out);
  for(unsigned attempt=0;attempt<100;attempt++){
   size=sizeof(out);e=IOConnectCallStructMethod(connection,0,&r,sizeof(r),&out,&size);
   if((uint32_t)e!=0xe00002d8U)break; /* kIOReturnNotReady, boot test may still run */
   usleep(100000);
  }
  if(e || size!=sizeof(out)){
   printf("MALI USER: submit op%u failed status=%08x\n",op,e);IOServiceClose(connection);return 3;
  }
  if(out.version!=1 || out.error || out.restore!=1 || out.pixels!=256){
   printf("MALI USER: GPU op%u error=%d restore=%u pixels=%u\n",op,out.error,out.restore,out.pixels);
   IOServiceClose(connection);return 3;
  }
  for(unsigned y=0;y<16;y++)for(unsigned x=0;x<16;x++){
   unsigned expected=op==1?r.background:r.texels[x/8+2*(y/8)];
   if(op==3)expected=blend(expected,r.background);
   unsigned actual=out.output[y*16+x];
   for(unsigned shift=0;shift<32;shift+=8){
    int delta=(int)((actual>>shift)&255)-(int)((expected>>shift)&255);
    if(delta<-(op==3?1:0) || delta>(op==3?1:0)){
     printf("MALI USER: pixel mismatch op%u x%u y%u got%08x expected%08x\n",op,x,y,actual,expected);
     IOServiceClose(connection);return 4;
    }
   }
  }
  printf("MALI USER: op%u PASS256 pixels\n",op);
 }
 IOServiceClose(connection);printf("MALI USER: PASS clear/copy/blend submitted from userspace\n");return 0;
}
