#!/usr/bin/env python3
"""Run the actual set/way assembly under QEMU ARM with instrumented CP15.

CLIDR/CCSIDR reads supply Cortex-A9 geometries; each DCISW/DCCISW records its
operand. The traversal/branches are the real kernel assembly, not a C model.
This validates coverage/order, not cache coherence on a physical Exynos.
"""
from pathlib import Path
import argparse
import os
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=root / 'osfmk/arm/armv/cpufunc-v7.s')
args = parser.parse_args()
source = args.source.read_text()
assembly = '.syntax unified\n.arm\n.text\n'
for name in ['arm_dcache_inv_all', 'arm_dcache_wbinv_all']:
    body = source.split('ENTRY_NP(' + name + ')', 1)[1].split('END(' + name + ')', 1)[0]
    body = re.sub(r'mrc\s+p15,\s*1,\s*r0,\s*c0,\s*c0,\s*1',
                  'ldr r0, =0x01000003', body)  # LoC=1, separate I/D at L1.
    body = re.sub(r'mrc\s+p15,\s*1,\s*r0,\s*c0,\s*c0,\s*0',
                  'ldr r0, =test_ccsidr\n\tldr r0, [r0]', body)
    body = re.sub(r'mcr\s+p15,\s*0,\s*r3,\s*c7,\s*c(?:6|14),\s*2',
                  'push {r0-r3,r12,lr}\n\tmov r0,r3\n\tbl record_sw\n\tpop {r0-r3,r12,lr}', body)
    body = re.sub(r'mcr\s+p15,\s*2,\s*r[03],\s*c0,\s*c0,\s*0', 'nop', body)
    assembly += '\n.global tested_' + name + '\ntested_' + name + ':\n' + body

c_source = r'''
typedef unsigned int u32;
volatile u32 test_ccsidr;
static u32 sets, count, bad;
static unsigned char seen[2048];
void tested_arm_dcache_inv_all(void);
void tested_arm_dcache_wbinv_all(void);
void record_sw(u32 operand) {
 u32 way=operand>>30, set=(operand>>5)&0x1ffU;
 if ((operand&0x3fffc01fU) || set>=sets) { bad=1; return; }
 u32 index=way*sets+set;
 if(index>=2048 || seen[index]) {bad=1;return;}
 seen[index]=1;count++;
}
static void semihost(u32 operation, const void *argument) {
 register u32 r0 __asm__("r0")=operation;
 register const void *r1 __asm__("r1")=argument;
 __asm__ volatile("svc 0x123456" : "+r"(r0) : "r"(r1) : "memory");
}
static void finish(u32 status) {
 u32 result[2]={0x20026,status};semihost(0x20,result);for(;;){}
}
void run(void) {
 for(sets=128;sets<=512;sets*=2) {
  test_ccsidr=((sets-1U)<<13)|(3U<<3)|1U;
  for(u32 operation=0;operation<2;operation++) {
   for(u32 n=0;n<2048;n++)seen[n]=0;
   count=bad=0;
   if(operation)tested_arm_dcache_wbinv_all();else tested_arm_dcache_inv_all();
   if(bad || count!=sets*4U) {
    semihost(4,"FAIL: set/way traversal missed or duplicated L1 cache lines\n");finish(1);
   }
  }
 }
 semihost(4,"ARM cache assembly: invalidate and clean/invalidate cover every L1 set/way for 16/32/64KiB A9 geometries\n");
 finish(0);
}
'''
entry = r'''
.syntax unified
.arm
.global _start
_start:
 cpsid if
 ldr sp,=0x60200000
 bl run
1: b 1b
'''
with tempfile.TemporaryDirectory(prefix='i9100-cacheops-') as directory:
    directory = Path(directory)
    (directory / 'ops.S').write_text(assembly)
    (directory / 'entry.S').write_text(entry)
    (directory / 'test.c').write_text(c_source)
    binary = directory / 'test.elf'
    subprocess.run(['arm-none-eabi-gcc', '-mcpu=cortex-a9', '-marm', '-O1',
                    '-ffreestanding', '-fno-builtin', '-nostdlib',
                    '-DBOARD_CONFIG_EXYNOS4210_I9100=1', '-Wl,-Ttext,0x60010000',
                    '-Wl,-e,_start', str(directory / 'entry.S'), str(directory / 'ops.S'),
                    str(directory / 'test.c'), '-o', str(binary)], check=True)
    env = dict(os.environ, QEMU_AUDIO_DRV='none')
    result = subprocess.run(['qemu-system-arm', '-M', 'vexpress-a9', '-cpu', 'cortex-a9',
                             '-m', '128M', '-nographic', '-monitor', 'none', '-serial', 'none',
                             '-semihosting-config', 'enable=on,target=native',
                             '-kernel', str(binary)], env=env, capture_output=True, text=True, timeout=15)
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit(result.returncode)
