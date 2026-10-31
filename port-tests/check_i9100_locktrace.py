#!/usr/bin/env python3
"""Run actual ARM simple-lock paths and bounded owner tracing in privileged QEMU."""
from pathlib import Path
import os
import argparse
import re
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--block',action='store_true');parser.add_argument('--unknown',action='store_true');parser.add_argument('--light',action='store_true',help='Exercise the withdrawn PERF20 collection-off experiment');args=parser.parse_args()
s=(root/'osfmk/arm/hw_lock.s').read_text()
bit=s[s.index('EnterARM(hw_lock_bit)'):s.index('LOAD_ADDR_GEN_DEF(thread_wakeup)')]
routines=(root/'osfmk/arm/machine_routines_asm.s').read_text()
disable=routines[routines.index('EnterARM(__disable_preemption)'):routines.index('EnterARM(get_preemption_level)')]
s=s[s.index('EnterThumb(hw_lock_init)'):s.index('/**\n * lock_read and friends')]+bit+disable
s=re.sub(r'Enter(Thumb|ARM)\((\w+)\)',lambda m:('\n.balign 4\n.thumb\n.thumb_func\n' if m[1]=='Thumb' else '\n.balign 4\n.arm\n.type tested_'+m[2]+',%function\n')+'.global tested_'+m[2]+'\ntested_'+m[2]+':',s)
increment_macro=(root/'osfmk/arm/asm_help.h').read_text()
macro_start=increment_macro.index('#if defined(BOARD_CONFIG_EXYNOS4210_I9100) && I9100_LOCK_TRACE\n#define IncrementPreemptLevel')
macro_end=increment_macro.index('\n#define DecrementPreemptLevel',macro_start)
increment_macro=increment_macro[macro_start:macro_end]
assembly='''.syntax unified
.arm
.text
#define LoadLockHardwareRegister(reg) ldr reg,=test_thread
#define LoadThreadRegister(reg) ldr reg,=test_thread
#define MACHINE_THREAD_PREEMPT_COUNT 0
__ACTUAL_INCREMENT_MACRO__
''' + s + '''
.arm
.global __enable_preemption
.type __enable_preemption,%function
__enable_preemption:
 ldr r12,=test_thread
#if I9100_LOCK_TRACE
 push {r0-r5,r7,r9,r12,lr}
 mov r0,r12
 bl _i9100_preempt_leave
 pop {r0-r5,r7,r9,r12,lr}
#endif
 ldr r2,[r12]
 sub r2,r2,#1
 str r2,[r12]
 bx lr
.global _i9100_spin_acquired
.set _i9100_spin_acquired,i9100_spin_acquired
.global _i9100_spin_forget
.set _i9100_spin_forget,i9100_spin_forget
.global _i9100_spin_busy
.set _i9100_spin_busy,i9100_spin_busy
.global _panic
.set _panic,panic
'''
assembly=assembly.replace('__ACTUAL_INCREMENT_MACRO__',
    (root/'osfmk/arm/i9100_trace_config.h').read_text()+'\n'+increment_macro)
assembly+='\n.global _i9100_preempt_enter\n.set _i9100_preempt_enter,i9100_preempt_enter\n.global _i9100_preempt_leave\n.set _i9100_preempt_leave,i9100_preempt_leave\n'
assembly+='''
.arm
.global tested_bit_roundtrip
.type tested_bit_roundtrip,%function
tested_bit_roundtrip:
 push {r4-r7,r9,lr}
 mov r4,r0
 mov r5,r1
 bl tested_hw_lock_bit
 ldr r6,[r4]
 mov r0,r4
 mov r1,r5
 bl tested_hw_unlock_bit
 mov r0,r6
 pop {r4-r7,r9,pc}
'''
source=(root/'osfmk/arm/machine_routines.c').read_text()
start=source.index('#if defined(BOARD_CONFIG_EXYNOS4210_I9100)\n/* UP diagnostic ownership table.')
fragment=source[start:source.index('\n#define DBG',start)]
code=r'''
typedef unsigned int uint32_t;typedef unsigned int uintptr_t;typedef unsigned char uint8_t;
struct thread { struct { uint32_t preempt_count; } machine; uint32_t kernel_stack; } test_thread;
typedef struct thread *thread_t;
typedef struct {uint32_t cpu_int_stack_top;int cpu_interrupt_level;} cpu_data_t;
static cpu_data_t test_cpu;
static cpu_data_t *current_cpu_datap(void){return &test_cpu;}
#define KERNEL_STACK_SIZE 16384U
#define INTSTACK_SIZE 16384U
void panic(const char *,...) __attribute__((noreturn));
'''+(root/'osfmk/arm/i9100_diagnostics.h').read_text().replace('#include "i9100_trace_config.h"',(root/'osfmk/arm/i9100_trace_config.h').read_text())+fragment+r'''
void tested_hw_lock_init(uint32_t *);
void tested_disable_preemption(void);
void __enable_preemption(void);
uint32_t tested_bit_roundtrip(uint32_t *,uint32_t);
uint32_t tested_hw_lock_held(uint32_t *);
void tested_hw_lock_lock(uint32_t *);
void tested_hw_lock_unlock(uint32_t *);
uint32_t tested_hw_lock_try(uint32_t *);
uint32_t tested_hw_lock_to(uint32_t *,uint32_t);
static uint32_t test_lock,expect_busy,expect_owner,expect_block;
static uint32_t flags(void){uint32_t r;__asm__ volatile("mrs %0,cpsr":"=r"(r));return r;}
static void masks(uint32_t bits){uint32_t r=(flags()&~0xc0U)|bits;__asm__ volatile("msr cpsr_c,%0"::"r"(r):"memory","cc");}
static void semihost(uint32_t op,const void *p){
 register uint32_t r0 __asm__("r0")=op;register const void *r1 __asm__("r1")=p;
 __asm__ volatile("svc 0x123456":"+r"(r0):"r"(r1):"memory");
}
static void __attribute__((noreturn)) finish(uint32_t status){uint32_t v[2]={0x20026,status};semihost(0x20,v);for(;;){}}
#define CHECK(v) do{if(!(v)){semihost(4,"FAIL: " #v "\n");finish(1);}}while(0)
void panic(const char *fmt,...){
 (void)fmt;__builtin_va_list ap;uint32_t a[40];
 __builtin_va_start(ap,fmt);for(uint32_t n=0;n<(expect_block?25U:33U);n++)a[n]=__builtin_va_arg(ap,uint32_t);__builtin_va_end(ap);
 if(expect_block){
  CHECK(a[0]==1 && a[1]==(uint32_t)&test_thread && a[2]==0 && a[3]==1);
  CHECK(a[4]==(uint32_t)&test_lock && a[5]==expect_owner);
  CHECK(a[7]==0 && a[8]==0 && a[9]==0 && (flags()&0xc0U)==0xc0U);
  CHECK(a[11]==1 && a[12]==expect_owner && a[14]>=0x60010000U && a[15]==0);
  CHECK(a[16]==i9100_fault_sequence && a[17]==4 && a[18]==2);
  CHECK(a[19]==0x12345678 && a[20]==0x23456789 && a[21]==0x34567890);
  CHECK(a[22]==0x45678901 && a[23]==0x805 && a[24]==0x10);
  semihost(4,"ARM scheduler guard: actual CPU thread register and owned lock/caller captured before terminal panic passed\n");finish(0);
 }
 CHECK(expect_busy && a[0]==(uint32_t)&test_lock && a[1]==1);
 CHECK(a[2]>=0x60010000U && a[2]<0x60100000U);
 CHECK(a[4]==(uint32_t)&test_thread && a[5]==1);
 #if I9100_TEST_UNKNOWN
 CHECK(!a[6] && !a[8] && !a[9] && !a[10] && !a[11]);
 CHECK(a[24]==2 && a[25]==1 && a[26]==0x81234567);
#else
 CHECK(a[6]==expect_owner && a[8]==(uint32_t)&test_thread && a[9]==0 && a[10]==1 && a[11]==1);
 CHECK(a[24]==1 && a[25]==1 && a[26]==expect_owner);
#endif
 CHECK(a[14]==i9100_fault_sequence && a[15]==4 && a[16]==2);
 CHECK(a[17]==0x12345678 && a[18]==0x23456789 && a[19]==0x34567890);
 CHECK(a[20]==0x45678901 && a[21]==0x805 && a[22]==0x10);
 CHECK(a[23]==i9100_log_sequence && a[27]==(uint32_t)&test_thread);
 CHECK(a[28]==i9100_log_sequence-1 && a[29]==(I9100_TEST_UNKNOWN?1U:2U));
 CHECK((flags()&0xc0U)==0xc0U && test_thread.machine.preempt_count==2);
 semihost(4,"ARM lock tracing: real init/lock/try/to/unlock, masks, nesting, caller ABI, bounded collisions, safe frame bounds, nested raw scopes, r9/r12 bitlock preservation and IRQ-reentry panic ownership passed\n");finish(0);
}
void run(void){
 uint32_t actual_thread=(uint32_t)&test_thread;
 __asm__ volatile("mcr p15,0,%0,c13,c0,4"::"r"(actual_thread):"memory");
#if !I9100_LOCK_TRACE
 // Execute the experimental collection-off assembler. No acquisition, scope or log
 // records may be generated, while lock words and preemption still balance.
 for(uint32_t mask=0;mask<4;mask++)for(uint32_t n=0;n<1000;n++){
  uint32_t want=((mask&1)?0x80:0)|((mask&2)?0x40:0);
  masks(want);tested_hw_lock_init(&test_lock);
  tested_disable_preemption();CHECK(test_thread.machine.preempt_count==1);
  tested_hw_lock_lock(&test_lock);CHECK(test_lock==1 && test_thread.machine.preempt_count==2);
  CHECK(!tested_hw_lock_try(&test_lock) && !tested_hw_lock_to(&test_lock,0));
  CHECK(test_thread.machine.preempt_count==2);
  tested_hw_lock_unlock(&test_lock);CHECK(!test_lock && test_thread.machine.preempt_count==1);
  __enable_preemption();CHECK(!test_thread.machine.preempt_count);
  CHECK(tested_hw_lock_try(&test_lock));tested_hw_lock_unlock(&test_lock);
  CHECK(tested_hw_lock_to(&test_lock,0));tested_hw_lock_unlock(&test_lock);
  test_lock=0xa0;CHECK(tested_bit_roundtrip(&test_lock,3)==0xa8 && test_lock==0xa0);
  CHECK((flags()&0xc0U)==want && !test_thread.machine.preempt_count);
 }
 CHECK(!i9100_spin_drops && !i9100_scope_drops && !i9100_log_sequence);
 for(uint32_t n=0;n<I9100_SPIN_SLOTS;n++)CHECK(!i9100_spin_records[n].key);
 for(uint32_t n=0;n<I9100_SCOPE_SLOTS;n++)CHECK(!i9100_scope_records[n].thread);
 semihost(4,"ARM experimental fast locks:4000 roundtrips, all masks, nested preemption, try/to/bitlocks; zero diagnostic records passed; phone touch regression unresolved\n");finish(0);
#endif
 static uint32_t stack[4096];
 test_thread.kernel_stack=(uint32_t)stack;
 CHECK(i9100_spin_parent(0,(uint32_t)&test_thread)==0);
 CHECK(i9100_spin_parent(1,(uint32_t)&test_thread)==0);
 CHECK(i9100_spin_parent((uint32_t)stack,0)==0);
 stack[5]=0x81234567;
 // QEMU test RAM is below kernel VA: use the validated interrupt-stack range.
 test_cpu.cpu_int_stack_top=(uint32_t)stack+sizeof(stack);
 CHECK(i9100_spin_parent((uint32_t)&stack[4],(uint32_t)&test_thread)==0x81234567);
 CHECK(i9100_spin_parent(test_cpu.cpu_int_stack_top-4,(uint32_t)&test_thread)==0);
 uint32_t keys[17],count=0;
 for(uint32_t key=0x81000000U;count<17;key+=4)
  if((((key>>2)^(key>>13))&(I9100_SPIN_SLOTS-1U))==0)keys[count++]=key;
 for(uint32_t n=0;n<17;n++)i9100_spin_acquired(keys[n],n+1,0,(uint32_t)&test_thread);
 CHECK(i9100_spin_drops==1 && i9100_spin_find(keys[16],0)==0);
 i9100_spin_forget(keys[0],0,2,(uint32_t)&test_thread);CHECK(i9100_spin_find(keys[15],0)->caller==16);
 i9100_spin_acquired(keys[16],17,0,(uint32_t)&test_thread);CHECK(i9100_spin_find(keys[16],0)->caller==17);
 for(uint32_t n=0;n<17;n++)i9100_spin_forget(keys[n],0,2,(uint32_t)&test_thread);
 tested_disable_preemption();
 CHECK(test_thread.machine.preempt_count==1 && i9100_scope_find((uint32_t)&test_thread,1,0));
 tested_disable_preemption();
 CHECK(test_thread.machine.preempt_count==2 && i9100_scope_find((uint32_t)&test_thread,2,0));
 __enable_preemption();
 CHECK(test_thread.machine.preempt_count==1 && i9100_scope_find((uint32_t)&test_thread,1,0) && !i9100_scope_find((uint32_t)&test_thread,2,0));
 __enable_preemption();CHECK(!test_thread.machine.preempt_count && !i9100_scope_find((uint32_t)&test_thread,1,0));
 test_lock=0xa0;
 CHECK(tested_bit_roundtrip(&test_lock,3)==0xa8 && test_lock==0xa0);
 CHECK(!test_thread.machine.preempt_count && !i9100_scope_find((uint32_t)&test_thread,1,0));
 for(uint32_t mask=0;mask<4;mask++){
  uint32_t want=((mask&1)?0x80:0)|((mask&2)?0x40:0);
  masks(want);tested_hw_lock_init(&test_lock);CHECK((flags()&0xc0U)==want);
  CHECK(test_lock==0 && test_thread.machine.preempt_count==0);
  tested_hw_lock_lock(&test_lock);CHECK((flags()&0xc0U)==want);
  CHECK(tested_hw_lock_held(&test_lock)==1 && test_thread.machine.preempt_count==1);
  volatile struct i9100_spin_record *r=i9100_spin_find((uint32_t)&test_lock,0);
  CHECK(r && r->thread==(uint32_t)&test_thread && r->depth==1 && r->caller>=0x60010000U);
  CHECK(tested_hw_lock_try(&test_lock)==0 && (flags()&0xc0U)==want && test_thread.machine.preempt_count==1);
  CHECK(tested_hw_lock_to(&test_lock,123)==0 && test_thread.machine.preempt_count==1);
  CHECK(i9100_spin_find((uint32_t)&test_lock,0)->caller==r->caller);
  tested_hw_lock_unlock(&test_lock);CHECK((flags()&0xc0U)==want);
  CHECK(!test_lock && !test_thread.machine.preempt_count && !i9100_spin_find((uint32_t)&test_lock,0));
  CHECK(!i9100_scope_find((uint32_t)&test_thread,1,0));
  CHECK(tested_hw_lock_try(&test_lock)==1 && test_thread.machine.preempt_count==1 && (flags()&0xc0U)==want);
  CHECK(i9100_spin_find((uint32_t)&test_lock,0));tested_hw_lock_unlock(&test_lock);
  CHECK(tested_hw_lock_to(&test_lock,123)==1 && test_thread.machine.preempt_count==1);
  CHECK(i9100_spin_find((uint32_t)&test_lock,0));tested_hw_lock_unlock(&test_lock);
  CHECK(!test_thread.machine.preempt_count && (flags()&0xc0U)==want);
 }
 // Fault records retain entry values even if the source is later overwritten.
 CHECK(!i9100_fault_find(actual_thread)->sequence);
 struct i9100_fault_snapshot fault={actual_thread,4,0x12345678,0x23456789,0x34567890,0x45678901,0x805,0x10,0};
 i9100_fault_failed(&fault,2);fault.pc=0;fault.far=0;
 CHECK(i9100_fault_find(actual_thread)->state.pc==0x12345678);
 CHECK(i9100_fault_find(actual_thread)->state.far==0x45678901);
 CHECK(!i9100_fault_find(actual_thread+4)->sequence);
 // A full ring evicts old records, and a reused slot cannot impersonate them.
 for(uint32_t n=0;n<16;n++){fault.thread=actual_thread+4;i9100_fault_failed(&fault,n);}
 CHECK(!i9100_fault_find(actual_thread)->sequence);
 fault.thread=actual_thread;fault.pc=0x12345678;fault.far=0x45678901;
 i9100_fault_failed(&fault,2);
 i9100_log_watch((uint32_t)&test_lock);
 i9100_log_watch((uint32_t)&test_lock+4);CHECK(i9100_log_key==(uint32_t)&test_lock);
 // Exercise history wrap and all three real assembly hooks.
 for(uint32_t n=0;n<20;n++){
  tested_hw_lock_init(&test_lock);tested_hw_lock_lock(&test_lock);tested_hw_lock_unlock(&test_lock);
 }
 CHECK(i9100_log_sequence==60);
 CHECK(i9100_log_events[60&15].kind==2 && i9100_log_events[60&15].value==0);
 CHECK(i9100_log_events[59&15].kind==1 && i9100_log_events[59&15].value==1);
 CHECK(i9100_log_events[58&15].kind==3 && i9100_log_events[58&15].value==0);
 masks(0);tested_hw_lock_lock(&test_lock);
 expect_owner=i9100_spin_find((uint32_t)&test_lock,0)->caller;
#if I9100_TEST_BLOCK
 expect_block=1;i9100_preempt_panic(1);CHECK(0);
#endif
#if I9100_TEST_UNKNOWN
 // Model the device's busy word without an owner; observation must not unlock.
 i9100_spin_forget((uint32_t)&test_lock,0x81234567,2,actual_thread);
 CHECK(test_lock==1 && !i9100_spin_find((uint32_t)&test_lock,0));
#endif
 expect_busy=1;test_cpu.cpu_interrupt_level=1;
 tested_hw_lock_lock(&test_lock);CHECK(0);
}
'''
entry='.syntax unified\n.arm\n.global _start\n_start:\n cpsid if\n ldr sp,=0x60200000\n bl run\n1: b 1b\n'
with tempfile.TemporaryDirectory(prefix='i9100-locks-') as d:
 d=Path(d);(d/'locks.S').write_text(assembly);(d/'entry.S').write_text(entry);(d/'test.c').write_text(code)
 binary=d/'test.elf'
 subprocess.run(['arm-none-eabi-gcc','-mcpu=cortex-a9','-marm','-O1','-ffreestanding','-fno-builtin','-nostdlib','-DBOARD_CONFIG_EXYNOS4210_I9100=1',*(['-DI9100_LOCK_TRACE=0'] if args.light else []),'-DI9100_TEST_BLOCK='+str(int(args.block)),'-DI9100_TEST_UNKNOWN='+str(int(args.unknown)),'-Wl,-Ttext,0x60010000','-Wl,-e,_start',str(d/'entry.S'),str(d/'locks.S'),str(d/'test.c'),'-o',str(binary)],check=True)
 if args.light:
  dis=subprocess.check_output(['arm-none-eabi-objdump','-d',str(binary)],text=True)
  symbols={name:int(address,16)&~1 for address,kind,name in
           (line.split() for line in subprocess.check_output(['arm-none-eabi-nm','--defined-only',str(binary)],text=True).splitlines())}
  blocks={int(address,16):body for address,body in
          re.findall(r'(?m)^([0-9a-f]+) <[^>]+>:\n(.*?)(?=\n[0-9a-f]+ <|\Z)',dis,re.S)}
  for name in ['hw_lock_init','hw_lock_lock','hw_lock_try','hw_lock_to','hw_lock_unlock','disable_preemption','hw_lock_bit','hw_unlock_bit']:
   block=blocks[symbols['tested_'+name]]
   assert not re.search(r'blx?\s+[^\n]*<(?:_?i9100_(?:spin_(?:acquired|forget)|preempt_(?:enter|leave)))>',block),name
 r=subprocess.run(['qemu-system-arm','-M','vexpress-a9','-cpu','cortex-a9','-m','128M','-nographic','-monitor','none','-serial','none','-semihosting-config','enable=on,target=native','-kernel',str(binary)],env=dict(os.environ,QEMU_AUDIO_DRV='none'),capture_output=True,text=True,timeout=15)
 print(r.stdout+r.stderr,end='')
 if r.returncode:raise SystemExit(r.returncode)
