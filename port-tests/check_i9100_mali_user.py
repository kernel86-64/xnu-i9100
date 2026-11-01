#!/usr/bin/env python3
"""Exercise the actual user-client selector gate with poisoned rejected buffers."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
folder=root/'iokit/Drivers/KernelBuiltIn/ARM/AppleARMPlatform'
s=(folder/'IOS7I9100Mali.cpp').read_text()
a=s.index('IOReturn IOS7I9100MaliClient::externalMethod(')
b=s.index('\nIOReturn IOS7I9100Mali::newUserClient',a)
method=s[a:b]
code=r"""
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#include "i9100_mali_user.h"
typedef int IOReturn;
enum {kIOReturnSuccess=0,kIOReturnUnsupported=1,kIOReturnBadArgument=2,kIOReturnNotAttached=3};
struct OSObject {};struct IOExternalMethodDispatch {};
struct IOExternalMethodArguments {
 unsigned scalarInputCount,scalarOutputCount;
 void *structureInputDescriptor,*structureOutputDescriptor;
 const void *structureInput;void *structureOutput;
 size_t structureInputSize,structureOutputSize;
};
struct IOS7I9100Mali {
 unsigned calls=0;
 IOReturn draw(const i9100_mali_request *r,i9100_mali_reply *o){assert(i9100_mali_request_valid(r));calls++;return 0;}
};
#define OSDynamicCast(type,value) ((type *)(value))
struct IOS7I9100MaliClient {
 IOS7I9100Mali *provider;
 void *getProvider(){return provider;}
 IOReturn externalMethod(uint32_t,IOExternalMethodArguments *,IOExternalMethodDispatch *,OSObject *,void *);
};
"""+method+r"""
int main(){
 static_assert(sizeof(i9100_mali_request)==32,"wire request");
 static_assert(sizeof(i9100_mali_reply)==1040,"wire reply");
 IOS7I9100Mali gpu;IOS7I9100MaliClient c={&gpu};
 auto invoke=[&](IOExternalMethodArguments *a){return c.externalMethod(0,a,0,0,0);};
 assert(invoke(0)==kIOReturnBadArgument);
 assert(c.externalMethod(1,(IOExternalMethodArguments *)1,0,0,0)==kIOReturnUnsupported);
 i9100_mali_request r={1,1,0xff112233,0,{0}};i9100_mali_reply out;
 IOExternalMethodArguments a={0,0,0,0,&r,&out,sizeof(r),sizeof(out)};
 assert(invoke(&a)==0 && gpu.calls==1);
 for(unsigned n=0;n<6;n++){
  auto invalid=a;
  if(n==0)invalid.scalarInputCount=1;
  if(n==1)invalid.scalarOutputCount=1;
  if(n==2)invalid.structureInputDescriptor=(void*)1;
  if(n==3)invalid.structureOutputDescriptor=(void*)1;
  if(n==4)invalid.structureInputSize--;
  if(n==5)invalid.structureOutputSize++;
  invalid.structureInput=(void*)1;
  assert(invoke(&invalid)==kIOReturnBadArgument && gpu.calls==1);
 }
 r.reserved=1;assert(invoke(&a)==kIOReturnBadArgument && gpu.calls==1);
 r.reserved=0;c.provider=0;assert(invoke(&a)==kIOReturnNotAttached);
 puts("PASS: actual user-client gate; exact wire sizes, selector/scalar/descriptor/size rejection before poisoned pointers, reserved bits and detached provider; ASan/UBSan.");
}
"""
with tempfile.TemporaryDirectory(prefix='mali-user-') as d:
 d=Path(d);(d/'test.cpp').write_text(code)
 subprocess.run(['clang++','-std=c++11','-O1','-fsanitize=address,undefined','-I',str(folder),str(d/'test.cpp'),'-o',str(d/'test')],check=True)
 subprocess.run([str(d/'test')],check=True)
# Exercise the provider's real serialization/quarantine/readback wrapper too.
start=s.index('IOReturn IOS7I9100Mali::draw(')
provider=s[start:s.index('class IOS7I9100MaliClient',start)]
wrapped=r'''
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#include "i9100_mali.h"
typedef int IOReturn;typedef unsigned long IOByteCount;typedef uint64_t addr64_t;
enum {kIOReturnSuccess=0,kIOReturnBadArgument=2,kIOReturnNotReady=4};
struct IOLock {bool held;};
void IOLockLock(IOLock *p){assert(!p->held);p->held=true;}
void IOLockUnlock(IOLock *p){assert(p->held);p->held=false;}
static unsigned mode,gpu_calls;
struct Buffer {
 uint32_t data[I9100_MALI_BYTES/4];
 addr64_t getPhysicalSegment(unsigned index,IOByteCount *n){assert(!index);*n=mode==7?4096:I9100_MALI_BYTES;return mode==5?0:mode==6?0x142000000ULL:0x42000000;}
 void *getBytesNoCopy(){return data;}
};
volatile unsigned i9100_mali_user_completed;
volatile int i9100_mali_user_error;
struct IOS7I9100Mali {
 IOLock lock={false};IOLock *submitLock=&lock;bool usable=true;unsigned submissions=0;
 Buffer memory;Buffer *arena=&memory;
 static uint32_t read(void *,unsigned,unsigned){return 0;}
 static void write(void *,unsigned,unsigned,uint32_t){}
 static void delay(void *,unsigned){}static void barrier(void *){}
 static int pmicRead(void *,unsigned,uint8_t *){return 0;}
 static int pmicWrite(void *,unsigned,uint8_t){return 0;}
 void setProperty(const char *,bool){}void setProperty(const char *,unsigned long long,unsigned){}
 IOReturn draw(const i9100_mali_request *,i9100_mali_reply *);
};
int i9100_mali_render_request(const i9100_mali_io *io,volatile uint32_t *b,uint32_t pa,unsigned bytes,volatile i9100_mali_status *s,const i9100_mali_request *r){
 gpu_calls++;assert(io->cookie && i9100_mali_request_valid(r) && pa==0x42000000 && bytes==65536);
 s->restore=mode==2?2:1;s->guard=mode==3?0:1;s->pixels=mode==4?255:256;
 for(unsigned n=0;n<256;n++)b[0x8080/4+n]=0x80000000+n;
 return mode==1?-12:0;
}
'''+provider+r'''
int main(){
 for(mode=0;mode<8;mode++){
  IOS7I9100Mali gpu;gpu_calls=0;i9100_mali_user_completed=0;i9100_mali_user_error=0;
  i9100_mali_request r={1,1,0xff123456,0,{0}};i9100_mali_reply out;
  assert(gpu.draw(&r,&out)==0 && !gpu.lock.held && out.version==1);
  if(!mode){
   assert(gpu.usable && gpu.submissions==1 && i9100_mali_user_completed==1);
   for(unsigned n=0;n<256;n++)assert(out.output[n]==0x80000000+n);
  }else{
   assert(!gpu.usable && out.error==(mode==1?-12:mode>=5?-1:-19));
   assert(i9100_mali_user_error==out.error && !i9100_mali_user_completed);
   for(unsigned n=0;n<256;n++)assert(!out.output[n]);
   unsigned calls=gpu_calls;assert(gpu.draw(&r,&out)==kIOReturnNotReady && calls==gpu_calls);
   if(mode>=5)assert(!gpu_calls);
  }
 }
 puts("PASS: actual provider wrapper: serialized success/readback, error/R2/guard/pixel quarantine, invalid/64-bit/short PA rejection before GPU, zero outputs on failure, no subsequent GPU reuse; ASan/UBSan.");
}
'''
with tempfile.TemporaryDirectory(prefix='mali-provider-') as d:
 d=Path(d);(d/'test.cpp').write_text(wrapped)
 subprocess.run(['clang++','-std=c++11','-O1','-fsanitize=address,undefined','-I',str(folder),str(d/'test.cpp'),'-o',str(d/'test')],check=True)
 subprocess.run([str(d/'test')],check=True)
