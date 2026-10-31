#!/usr/bin/env python3
"""Exercise the actual secondary-abort gate on ARM and backtrace bounds under ASan."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent

def function(source, name):
    pos = source.index(name + '(')
    start = source.rfind('\n', 0, pos) + 1
    body = source.index('{', start)
    depth = 1
    for end in range(body + 1, len(source)):
        depth += (source[end] == '{') - (source[end] == '}')
        if not depth:
            return source[start:end + 1]
    raise RuntimeError(name)

panel = (root/'pexpert/arm/pe_exynos4210_i9100.c').read_text()
gate = function(panel, 'ios7i9100_abort_during_fatal')
stop = 'for(;;)__asm__ volatile("dsb sy\\n\\twfi" ::: "memory");'
assert stop in gate
gate = gate.replace(stop, 'test_stop();')
preamble = r'''
typedef unsigned int uint32_t;
static unsigned int i9100_fatal_active, calls, reenter, output_count;
static char output[512];
static void test_stop(void) __attribute__((noreturn));
static void i9100_puts(const char *);
static void i9100_puthex(unsigned int);
void ios7i9100_abort_during_fatal(unsigned int,unsigned int,unsigned int,unsigned int,unsigned int,unsigned int);
static void semihost(uint32_t op,const void *p){
 register uint32_t r0 __asm__("r0")=op;register const void *r1 __asm__("r1")=p;
 __asm__ volatile("svc 0x123456":"+r"(r0):"r"(r1):"memory");
}
static void __attribute__((noreturn)) finish(uint32_t status){uint32_t v[2]={0x20026,status};semihost(0x20,v);for(;;){}}
#define CHECK(v) do{if(!(v)){semihost(4,"FAIL: " #v "\n");finish(1);}}while(0)
static int contains(const char *s){
 for(unsigned n=0;n<output_count;n++){
  unsigned k=0;while(s[k] && n+k<output_count && output[n+k]==s[k])k++;
  if(!s[k])return 1;
 }return 0;
}
static void i9100_puts(const char *s){
 calls++;
 if(reenter)ios7i9100_abort_during_fatal(9,9,9,9,9,9);
 while(*s && output_count<sizeof(output)-1)output[output_count++]=*s++;
}
static void i9100_puthex(unsigned int n){
 char text[9];for(unsigned k=0;k<8;k++)text[k]="0123456789abcdef"[(n>>(28-4*k))&15];
 text[8]=0;i9100_puts(text);
}
static void test_stop(void){
 uint32_t mask;__asm__ volatile("mrs %0,cpsr":"=r"(mask));CHECK((mask&0xc0)==0xc0);
 if(reenter){CHECK(calls==1 && !output_count);}
 else{CHECK(contains("PC=12345678 LR=23456789 TYPE=00000003"));
  CHECK(contains("FAR=34567890 FSR=00000002 PSR=000001d3"));}
 semihost(4,"ARM secondary-abort gate: ordinary faults return; fatal faults mask IRQ/FIQ, preserve fields and stop; recursive output cannot print or enter again\n");finish(0);
}
'''
main = r'''
void run(void){
 uint32_t before,after;
 __asm__ volatile("mrs %0,cpsr":"=r"(before));
 ios7i9100_abort_during_fatal(0,0,0,0,0,0);
 __asm__ volatile("mrs %0,cpsr":"=r"(after));CHECK((before&0xdf)==(after&0xdf) && !calls);
 i9100_fatal_active=1;reenter=TEST_REENTER;
 ios7i9100_abort_during_fatal(0x12345678,0x23456789,0x34567890,2,0x1d3,3);CHECK(0);
}
'''
model = (root/'osfmk/arm/model_dep.c').read_text()
start = model.index('void\npanic_arm_backtrace(')
end = model.index('\n\n\nvoid\nDebuggerWithContext', start)
backtrace = model[start:end]
host = r'''
#include <stdint.h>
#include <stdarg.h>
#include <assert.h>
#include <stdio.h>
typedef uintptr_t vm_offset_t;typedef uintptr_t vm_address_t;
typedef int boolean_t;typedef struct { int unused; } arm_saved_state_t;
typedef struct cframe { struct cframe *prev; uintptr_t caller; } cframe_t;
#define DUMPFRAMES 32
#define FALSE 0
static unsigned dumped;
static int cpu_number(void){return 0;}
static void PE_parse_boot_argn(const char *s,void *p,unsigned n){(void)s;(void)p;(void)n;}
static void kdb_printf(const char *s,...){(void)s;}
static uintptr_t kvtophys(uintptr_t p){return p;}
static void panic_print_symbol_name(vm_address_t p){(void)p;}
static void panic_display_system_configuration(void){}
static void kmod_panic_dump(vm_offset_t *p,int n){
 volatile uintptr_t sum=0;dumped=n;for(int k=0;k<n;k++)sum+=p[k];(void)sum;
}
'''
hostmain = r'''
int main(void){
 cframe_t frames[48];
 for(unsigned k=0;k<48;k++){frames[k].caller=0x80000000+k;frames[k].prev=k<47?&frames[k+1]:0;}
 panic_arm_backtrace(frames,48,0,0,0);assert(dumped==32);
 panic_arm_backtrace(frames+45,48,0,0,0);assert(dumped==3);
 puts("Backtrace: 48 walked frames pass only 32 initialized addresses to kmod dump; short trace preserved");
}
'''
with tempfile.TemporaryDirectory(prefix='i9100-fatal-') as tmp:
    tmp = Path(tmp)
    (tmp/'entry.S').write_text('.syntax unified\n.arm\n.global _start\n_start:\n cpsid if\n ldr sp,=0x60200000\n bl run\n1: b 1b\n')
    (tmp/'gate.c').write_text(preamble + gate + main)
    for reenter in (0, 1):
        subprocess.run(['arm-none-eabi-gcc','-mcpu=cortex-a9','-marm','-O1','-ffreestanding','-fno-builtin','-nostdlib','-DTEST_REENTER='+str(reenter),'-Wl,-Ttext,0x60010000','-Wl,-e,_start',str(tmp/'entry.S'),str(tmp/'gate.c'),'-o',str(tmp/'gate.elf')],check=True)
        r = subprocess.run(['qemu-system-arm','-M','vexpress-a9','-cpu','cortex-a9','-m','128M','-nographic','-monitor','none','-serial','none','-semihosting-config','enable=on,target=native','-kernel',str(tmp/'gate.elf')],env=dict(os.environ,QEMU_AUDIO_DRV='none'),capture_output=True,text=True,timeout=15)
        print(r.stdout+r.stderr,end='')
        if r.returncode:raise SystemExit(r.returncode)
    # Control: the previous code must fail when kmod reads 48 entries from 32.
    old = backtrace.replace('frame_index < DUMPFRAMES ? frame_index : DUMPFRAMES','frame_index')
    for name, fragment in [('old',old),('fixed',backtrace)]:
        (tmp/'trace.c').write_text(host+fragment+hostmain)
        subprocess.run(['cc','-fsanitize=address,undefined',str(tmp/'trace.c'),'-o',str(tmp/'trace')],check=True)
        r = subprocess.run([str(tmp/'trace')],capture_output=True,text=True)
        if name=='old':
            assert r.returncode and 'stack-buffer-overflow' in r.stderr
            print('Old backtrace control: ASan stack-buffer-overflow reproduced')
        else:
            assert not r.returncode,r.stdout+r.stderr
            print(r.stdout,end='')

    debug = (root/'osfmk/kern/debug.c').read_text()
    prologue = debug[debug.index('static spl_t\npanic_prologue('):debug.index('\n\nstatic void\npanic_epilogue')]
    nested = function(panel, 'ios7i9100_nested_panic_stop').replace(stop, 'test_stop();')
    old_prologue = re.sub(r'#if defined\(BOARD_CONFIG_EXYNOS4210_I9100\).*?#endif', '', prologue, flags=re.S)
    for label, tested, reenter in [('normal',prologue,0),('recursive-output',prologue,1),('old-control',old_prologue,0)]:
        (tmp/'nested-under-test.inc').write_text(nested+'\n'+tested)
        subprocess.run(['arm-none-eabi-gcc','-mcpu=cortex-a9','-marm','-O1','-ffreestanding','-fno-builtin','-nostdlib','-DBOARD_CONFIG_EXYNOS4210_I9100=1','-DTEST_REENTER='+str(reenter),'-I'+str(tmp),'-Wl,-Ttext,0x60010000','-Wl,-e,_start',str(tmp/'entry.S'),str(root/'port-tests/i9100_nested_panic_test.c'),'-o',str(tmp/'nested.elf')],check=True)
        r = subprocess.run(['qemu-system-arm','-M','vexpress-a9','-cpu','cortex-a9','-m','128M','-nographic','-monitor','none','-serial','none','-semihosting-config','enable=on,target=native','-kernel',str(tmp/'nested.elf')],env=dict(os.environ,QEMU_AUDIO_DRV='none'),capture_output=True,text=True,timeout=15)
        if label=='old-control':
            assert r.returncode and 'nested panic entered Debugger' in r.stdout+r.stderr
            print('Old double-panic control: recursive Debugger entry reproduced')
        else:
            print(r.stdout+r.stderr,end='')
            if r.returncode:raise SystemExit(r.returncode)
