#!/usr/bin/env python3
"""Execute the actual ARM enable_preemption routine with modeled thread/CPU fields.

QEMU runs in privileged ARM mode, so CPSID/MRS/MSR operate on real CPSR bits.
The AST stub deliberately clobbers caller-saved r3 to exercise the return path.
"""
from pathlib import Path
import argparse
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,default=root/'osfmk/arm/machine_routines_asm.s')
parser.add_argument('--trace', action='store_true', help='Also exercise diagnostic callback preservation')
args = parser.parse_args()
s = args.source.read_text()
s = s[s.index('EnterARM(__enable_preemption)'):s.index('EnterARM(current_thread)')]
s = s.replace('EnterARM(__enable_preemption)', '.global tested_enable_preemption\ntested_enable_preemption:')
s = s.replace('EnterARM(_enable_preemption)', '').replace('EnterARM(enable_preemption)', '')
assembly = '''
.syntax unified
.arm
.text
#define LoadThreadRegister(reg) ldr reg,=test_thread
#define MACHINE_THREAD_PREEMPT_COUNT 0
#define MACHINE_THREAD_CPU_DATA 4
#define CPU_PENDING_AST 0
''' + s + '''
.global _i9100_preempt_leave
.type _i9100_preempt_leave,%function
_i9100_preempt_leave:
 mov r0,#99
 mov r1,#88
 mov r2,#77
 mov r3,#66
 mov r9,#55
 mov r12,#44
 bx lr
.global _ast_taken
.type _ast_taken,%function
_ast_taken:
 ldr r2,=ast_calls
 ldr r3,[r2]
 add r3,r3,#1
 str r3,[r2]
 cmp r0,#7
 cmpeq r1,#1
 ldrne r2,=ast_bad
 movne r3,#1
 strne r3,[r2]
 mrs r2,cpsr
 tst r2,#0x80
 ldreq r2,=ast_bad
 moveq r3,#1
 streq r3,[r2]
 mov r3,#0
 bx lr
'''
c = r'''
typedef unsigned int u32;
struct cpu { u32 pending; } test_cpu;
struct thread { u32 preemption; struct cpu *cpu; } test_thread;
volatile u32 ast_calls,ast_bad;
void tested_enable_preemption(void);
static u32 flags(void) {u32 r;__asm__ volatile("mrs %0,cpsr":"=r"(r));return r;}
static void semihost(u32 op,const void *p) {
 register u32 r0 __asm__("r0")=op;
 register const void *r1 __asm__("r1")=p;
 __asm__ volatile("svc 0x123456":"+r"(r0):"r"(r1):"memory");
}
static void finish(u32 code) {u32 r[2]={0x20026,code};semihost(0x20,r);for(;;){}}
void run(void) {
 test_thread.cpu=&test_cpu;
 for(u32 mask=0;mask<4;mask++)for(u32 nesting=1;nesting<=2;nesting++)for(u32 ast=0;ast<2;ast++) {
  u32 want=((mask&1)?0x80:0)|((mask&2)?0x40:0);
  u32 psr=(flags()&~0xc0U)|want;
  test_thread.preemption=nesting;test_cpu.pending=ast?4:0;ast_calls=ast_bad=0;
  __asm__ volatile("msr cpsr_c,%0"::"r"(psr):"memory","cc");
  tested_enable_preemption();
  u32 after=flags();
  __asm__ volatile("cpsid if":::"memory","cc");
  u32 expected=(nesting==1 && !(want&0x80) && ast)?1:0;
  if((after&0xc0U)!=want || test_thread.preemption!=nesting-1 || ast_calls!=expected || ast_bad) {
   semihost(4,"FAIL: enable_preemption lost I/F state, nesting or AST return\n");finish(1);
  }
 }
 semihost(4,"ARM preemption: all 16 I/F, nesting and AST cases preserve caller masks; AST clobber handled\n");
 finish(0);
}
'''
entry = '''
.syntax unified
.arm
.global _start
_start:
 cpsid if
 ldr sp,=0x60200000
 bl run
1: b 1b
'''
with tempfile.TemporaryDirectory(prefix='i9100-preemption-') as d:
 d=Path(d)
 (d/'routine.S').write_text(assembly)
 (d/'entry.S').write_text(entry)
 (d/'test.c').write_text(c)
 binary=d/'test.elf'
 subprocess.run(['arm-none-eabi-gcc','-mcpu=cortex-a9','-marm','-O1','-ffreestanding','-fno-builtin','-nostdlib',
  '-DBOARD_CONFIG_EXYNOS4210_I9100=1','-DI9100_LOCK_TRACE='+str(int(args.trace)),'-Wl,-Ttext,0x60010000','-Wl,-e,_start',str(d/'entry.S'),str(d/'routine.S'),str(d/'test.c'),'-o',str(binary)],check=True)
 result = subprocess.run(['qemu-system-arm','-M','vexpress-a9','-cpu','cortex-a9','-m','128M','-nographic','-monitor','none','-serial','none','-semihosting-config','enable=on,target=native','-kernel',str(binary)],env=dict(os.environ,QEMU_AUDIO_DRV="none"),capture_output=True,text=True,timeout=15)
 print(result.stdout + result.stderr,end="")
 if result.returncode:raise SystemExit(result.returncode)
