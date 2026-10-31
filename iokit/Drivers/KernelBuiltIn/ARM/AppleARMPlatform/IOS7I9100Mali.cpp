#if defined(BOARD_CONFIG_EXYNOS4210_I9100)
#include <IOKit/IOService.h>
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IOWorkLoop.h>
#include <IOKit/IOTimerEventSource.h>
#include <IOKit/IOLib.h>
#include <pexpert/pexpert.h>
#include <pexpert/arm/boot.h>
#include "i9100_mali.h"
#include "i9100_power.h"
extern "C" {
#include <vm/pmap.h>
/* Built-in board driver; this ARM internal is deliberately not a public KPI. */
vm_offset_t pmap_pte(pmap_t,vm_offset_t);
void pmap_set_cache_attributes(ppnum_t,unsigned int);
}
extern "C" void _disable_preemption(void);
extern "C" void _enable_preemption(void);

class IOS7I9100Mali : public IOService {
 OSDeclareDefaultStructors(IOS7I9100Mali)
 IOMemoryDescriptor *device[4]; IOMemoryMap *mapping[4];
 volatile uint8_t *regs[4];
 IOBufferMemoryDescriptor *arena;
 IOWorkLoop *loop; IOTimerEventSource *timer;
 i9100_power_hw pmic;
 static uint32_t read(void *,unsigned,unsigned);
 static void write(void *,unsigned,unsigned,uint32_t);
 static uint32_t busRead(void *,unsigned,unsigned);
 static void busWrite(void *,unsigned,unsigned,uint32_t);
 static int pmicRead(void *,unsigned,uint8_t *);
 static int pmicWrite(void *,unsigned,uint8_t);
 static void delay(void *,unsigned);
 static void barrier(void *);
 static void enter(void *);static void leave(void *);
 static void tick(OSObject *,IOTimerEventSource *);
 void run(void);
public:
 virtual bool init(void);
 virtual bool start(IOService *);
 virtual void free(void);
};
OSDefineMetaClassAndStructors(IOS7I9100Mali,IOService)
bool IOS7I9100Mali::init(void)
{
 if(!IOService::init())return false;
 bzero(device,sizeof(device));bzero(mapping,sizeof(mapping));bzero(regs,sizeof(regs));
 bzero(&pmic,sizeof(pmic));arena=0;loop=0;timer=0;return true;
}
uint32_t IOS7I9100Mali::read(void *cookie,unsigned region,unsigned offset)
{
 IOS7I9100Mali *s=(IOS7I9100Mali *)cookie;
 unsigned bytes=region==1?0x18000U:region==3?0x1000U:0x10000U;
 if(region>=4 || !s->regs[region] || (offset&3) || offset>=bytes)return 0xffffffffU;
 __asm__ volatile("dsb sy" ::: "memory");
 uint32_t value=*(volatile uint32_t *)(s->regs[region]+offset);
 __asm__ volatile("dsb sy" ::: "memory");return value;
}
void IOS7I9100Mali::write(void *cookie,unsigned region,unsigned offset,uint32_t value)
{
 IOS7I9100Mali *s=(IOS7I9100Mali *)cookie;
 unsigned bytes=region==1?0x18000U:region==3?0x1000U:0x10000U;
 if(region>=4 || !s->regs[region] || (offset&3) || offset>=bytes)return;
 *(volatile uint32_t *)(s->regs[region]+offset)=value;
 __asm__ volatile("dsb sy" ::: "memory");
}
uint32_t IOS7I9100Mali::busRead(void *c,unsigned r,unsigned o)
{return r==0?read(c,3,o):0xffffffffU;}
void IOS7I9100Mali::busWrite(void *c,unsigned r,unsigned o,uint32_t v)
{if(r==0)write(c,3,o,v);}
int IOS7I9100Mali::pmicRead(void *c,unsigned r,uint8_t *v)
{return i9100_power_pmic_read(&((IOS7I9100Mali *)c)->pmic,r,v);}
int IOS7I9100Mali::pmicWrite(void *c,unsigned r,uint8_t v)
{return i9100_power_pmic_write(&((IOS7I9100Mali *)c)->pmic,r,v);}
void IOS7I9100Mali::delay(void *,unsigned us){IODelay(us);}
void IOS7I9100Mali::barrier(void *){__asm__ volatile("dsb sy" ::: "memory");}
/* Same UP exclusion as the existing MAX8997 driver: GPIO transactions cannot
 * interleave with its power workloop, and IRQ state remains unchanged. */
void IOS7I9100Mali::enter(void *){_disable_preemption();}
void IOS7I9100Mali::leave(void *){_enable_preemption();}
bool IOS7I9100Mali::start(IOService *provider)
{
 if(!IOService::start(provider))return false;
 boot_args *args=(boot_args *)PE_state.bootArgs;
 if(!args || args->machineType!=0xdc4U)return false;
 unsigned enabled=1;
 PE_parse_boot_argn("i9100gpu",&enabled,sizeof(enabled));
 setName("IOS7I9100Mali");
 setProperty("GPUModel","ARM Mali-400 MP4");
 setProperty("DriverStage","isolated texture/blend/4PP test; no iOS GL backend");
 if(!enabled) { setProperty("SelfTestEnabled",false);registerService();return true; }
 i9100_mali_observation.phase=1;
 const uint32_t address[4]={0x13000000U,0x10030000U,0x10020000U,0x11400000U};
 const unsigned length[4]={0x10000U,0x18000U,0x10000U,0x1000U};
 for(unsigned n=0;n<4;n++) {
  device[n]=IOMemoryDescriptor::withPhysicalAddress(address[n],length[n],kIODirectionInOut);
  mapping[n]=device[n]?device[n]->map(kIOMapInhibitCache):0;
  if(!mapping[n] || !mapping[n]->getAddress()) { i9100_mali_observation.error=-1;return false; }
  regs[n]=(volatile uint8_t *)mapping[n]->getAddress();
 }
 pmic.cookie=this;pmic.read32=busRead;pmic.write32=busWrite;
 pmic.delay_us=delay;pmic.enter=enter;pmic.leave=leave;
 loop=IOWorkLoop::workLoop();timer=IOTimerEventSource::timerEventSource(this,tick);
 if(!loop || !timer || loop->addEventSource(timer)!=kIOReturnSuccess) {
  i9100_mali_observation.error=-1;return false;
 }
 setProperty("SelfTestEnabled",true);registerService();
 timer->setTimeoutMS(20);return true;
}
void IOS7I9100Mali::tick(OSObject *owner,IOTimerEventSource *)
{((IOS7I9100Mali *)owner)->run();}
void IOS7I9100Mali::run(void)
{
 /* NC attributes on all CPU aliases are set by the existing pmap/IOKit path.
  * No user mapping, scanout allocation, shader compiler or global cache trap. */
 arena=IOBufferMemoryDescriptor::withOptions(kIODirectionInOut|
        kIOMemoryPhysicallyContiguous|kIOMapInhibitCache,I9100_MALI_BYTES,4096);
 bool prepared=arena && arena->prepare(kIODirectionInOut)==kIOReturnSuccess;
 IOByteCount bytes=0;
 addr64_t pa=prepared?arena->getPhysicalSegment(0,&bytes):0;
 void *memory=arena?arena->getBytesNoCopy():0;
 int error=-1;
 if(memory && pa && pa<=0xffffffffULL && bytes>=I9100_MALI_BYTES) {
  bool nc=true;
  for(unsigned off=0;off<I9100_MALI_BYTES;off+=4096) {
   /* Explicitly set and verify Normal-NC CPU aliases. The named-memory entry
    * alone is not used as proof of DMA coherence on this port. */
   pmap_set_cache_attributes((ppnum_t)((pa+off)>>12),
       VM_MEM_COHERENT|VM_MEM_NOT_CACHEABLE|VM_MEM_GUARDED);
   vm_offset_t ptep=pmap_pte(kernel_pmap,(vm_offset_t)memory+off);
   unsigned value=ptep?*(volatile unsigned *)ptep:0;
   if(!(value&2U) || (value&0xfffff000U)!=(uint32_t)(pa+off) || (value&0x1ccU)!=0x40U)nc=false;
  }
  if(nc) {
   i9100_mali_io io;
   io.cookie=this;io.read=read;io.write=write;io.delay_us=delay;
   io.barrier=barrier;io.pmic_read=pmicRead;io.pmic_write=pmicWrite;
   error=i9100_mali_selftest(&io,(volatile uint32_t *)memory,(uint32_t)pa,
                            I9100_MALI_BYTES,&i9100_mali_observation);
  } else error=-16;
 }
 i9100_mali_observation.error=error;
 setProperty("SelfTestResult",(unsigned long long)(uint32_t)error,32);
 setProperty("VerifiedPixels",(unsigned long long)i9100_mali_observation.pixels,32);
 setProperty("VerifiedVertices",(unsigned long long)i9100_mali_observation.vertices,32);
 setProperty("VerifiedTriangles",(unsigned long long)i9100_mali_observation.triangles,32);
 setProperty("VerifiedTexturePasses",(unsigned long long)i9100_mali_observation.textures,32);
 setProperty("VerifiedBlendPasses",(unsigned long long)i9100_mali_observation.blends,32);
 setProperty("RenderedPPMask",(unsigned long long)i9100_mali_observation.render_mask,32);
 setProperty("GPVersion",(unsigned long long)i9100_mali_observation.gp_version,32);
 setProperty("PPVersion",(unsigned long long)i9100_mali_observation.pp_version,32);
 setProperty("PPMask",(unsigned long long)i9100_mali_observation.pp_mask,32);
 IOLog("I9100 Mali GPU31 phase=%u error=%d restore=%u GP=%08x PP=%08x cores=%x verified=%u/4096 guards=%u vertices=%u triangles=%u trial=%u textures=%u blends=%u rendered=%x\n",
  i9100_mali_observation.phase,error,i9100_mali_observation.restore,
  i9100_mali_observation.gp_version,i9100_mali_observation.pp_version,
  i9100_mali_observation.pp_mask,i9100_mali_observation.pixels,i9100_mali_observation.guard,
  i9100_mali_observation.vertices,i9100_mali_observation.triangles,i9100_mali_observation.trial,
  i9100_mali_observation.textures,i9100_mali_observation.blends,i9100_mali_observation.render_mask);
}
void IOS7I9100Mali::free(void)
{
 if(timer) { timer->cancelTimeout();if(loop)loop->removeEventSource(timer);timer->release(); }
 if(loop)loop->release();
 /* The isolated64KiB arena is deliberately retained for the boot lifetime.
  * A failed GPU reset/power transition must never turn into DMA-after-free. */
 for(unsigned n=0;n<4;n++) { if(mapping[n])mapping[n]->release();if(device[n])device[n]->release(); }
 IOService::free();
}
void ios7i9100_register_mali(IOService *platform)
{
 IOS7I9100Mali *gpu=new IOS7I9100Mali;
 if(gpu && (!gpu->init() || !gpu->attach(platform) || !gpu->start(platform)))gpu->release();
}
#endif
