/* Instrumented actual CP15 instructions feed this explicit data/coherence model.
 * QEMU itself does not emulate the physical A9 write-back cache. */
typedef unsigned int u32;
volatile u32 test_ccsidr,return_mask;
static u32 ram[2048],cache[2048],pending[2048];
static unsigned char valid[2048],dirty[2048],queued[2048],seen[2048];
static u32 sets,lines,lost,writes,dcops,ici,bp,barriers,bad_masks,bad_order;
void tested_cache_request(u32);
static void semihost(u32 op,const void*p){register u32 r0 __asm__("r0")=op;register const void*r1 __asm__("r1")=p;__asm__ volatile("svc 0x123456":"+r"(r0):"r"(r1):"memory");}
static void __attribute__((noreturn)) finish(u32 c){u32 v[2]={0x20026,c};semihost(0x20,v);for(;;){}}
static void hex(u32 n){char b[9];for(u32 k=0;k<8;k++)b[k]="0123456789abcdef"[(n>>(28-4*k))&15];b[8]=0;semihost(4,b);}
#define CHECK(x) do{if(!(x)){semihost(4,"FAIL: " #x "\n");finish(1);}}while(0)
void unexpected_request(void){CHECK(0);}
void record_event(u32 op,u32 operand){
 u32 flags;__asm__ volatile("mrs %0,cpsr":"=r"(flags));
 if(op==1||op==2){
  if((flags&0xc0)!=0xc0)bad_masks=1;
  u32 way=operand>>30,set=(operand>>5)&0x1ffU;
  CHECK(!(operand&0x3fffc01fU)&&set<sets);
  u32 i=way*sets+set;CHECK(i<lines&&!seen[i]);seen[i]=1;dcops++;
  if(valid[i]&&dirty[i]){
   if(op==1)lost++;
   else{pending[i]=cache[i];queued[i]=1;writes++;}
  }
  dirty[i]=0;valid[i]=0;
 }else if(op==3){
  ici++;
  // An I-side invalidate before D clean completion permits a stale refill.
  for(u32 i=0;i<lines;i++)if(dirty[i]||queued[i])bad_order=1;
 }else if(op==4)bp++;
 else if(op==5){
  barriers++;for(u32 i=0;i<lines;i++)if(queued[i]){ram[i]=pending[i];queued[i]=0;}
 }else if(op==7)CHECK(operand==0);
}
void run(void){
 for(sets=128;sets<=512;sets*=2)for(u32 selector=DATA_ONLY?1:0;selector<=1;selector++)for(u32 mask=0;mask<4;mask++){
  lines=sets*4;test_ccsidr=((sets-1)<<13)|(3<<3)|1;
  lost=writes=dcops=ici=bp=barriers=bad_masks=bad_order=0;
  // Dirty kernel/IPC/lock words live in unrelated sets as well as user lines.
  for(u32 i=0;i<lines;i++){ram[i]=0xdead0000+i;cache[i]=0xbeef0000+i;valid[i]=dirty[i]=1;queued[i]=seen[i]=0;}
  u32 before;__asm__ volatile("mrs %0,cpsr":"=r"(before));
  u32 want=((mask&1)?0x80:0)|((mask&2)?0x40:0);
  before=(before&~0xc0U)|want;__asm__ volatile("msr cpsr_c,%0"::"r"(before):"memory","cc");
  tested_cache_request(selector);__asm__ volatile("cpsid if":::"memory","cc");
  if(lost){semihost(4,"FAIL: runtime cache trap discards dirty lines without writeback; selector=");hex(selector);semihost(4," lost=");hex(lost);semihost(4,"\n");finish(1);}
  if(!dcops){semihost(4,"FAIL: runtime data-cache request performs no D-cache maintenance\n");finish(1);}
  for(u32 i=0;i<lines;i++)CHECK(ram[i]==0xbeef0000+i && !dirty[i] && !queued[i]);
  CHECK(dcops==lines&&writes==lines&&!bad_masks&&(return_mask&0xc0U)==want);
  if(selector==0)CHECK(ici==1&&bp==1&&!bad_order);else CHECK(!ici);
  CHECK(barriers);
 }
 semihost(4,"ARM cache trap: real dispatch/helpers preserve every modeled dirty line, clean completes before I invalidate, set/way coverage and caller IRQ/FIQ masks pass across 16/32/64KiB geometries\n");finish(0);
}
