#!/usr/bin/env python3
"""Run actual ARM timer accounting functions against the kernel's real timer layout."""
from pathlib import Path
import argparse
import os
import re
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,default=root/'osfmk/arm/etimer.c')
args=parser.parse_args()

def function(source,name):
 m=re.search(r'(?m)^(?:void|uint64_t)\s+'+re.escape(name)+r'\([^;]*?\)\s*\{',source)
 if not m:raise RuntimeError('Missing function: '+name)
 depth=1
 for end in range(m.end(),len(source)):
  depth+=(source[end]=='{')-(source[end]=='}')
  if not depth:return source[m.start():end+1]
 raise RuntimeError('Unclosed function: '+name)
header=(root/'osfmk/kern/timer.h').read_text()
layout=header[header.index('struct timer {'):header.index('typedef struct timer')]
impl=args.source.read_text();common=(root/'osfmk/kern/timer.c').read_text()
code='typedef unsigned int uint32_t;typedef unsigned long long uint64_t;\n'+layout+'\ntypedef struct timer *timer_t;\n'
code+='\n'.join(function(impl,n) for n in ['timer_grab','timer_update'])
code+='\n'.join(function(common,n) for n in ['timer_init','timer_delta','timer_advance','timer_start','timer_stop','timer_switch'])
code+=r'''
_Static_assert(__builtin_offsetof(struct timer,low_bits)==8,"actual timer layout");
static void semihost(uint32_t op,const void *p) {
 register uint32_t r0 __asm__("r0")=op;
 register const void *r1 __asm__("r1")=p;
 __asm__ volatile("svc 0x123456":"+r"(r0):"r"(r1):"memory");
}
static void finish(uint32_t code) {uint32_t result[2]={0x20026,code};semihost(0x20,result);for(;;){}}
#define CHECK(x) do {if(!(x)){semihost(4,"FAIL: " #x "\n");finish(1);}}while(0)
void run(void) {
 struct timer a,b;uint64_t saved=0;
 timer_init(&a);timer_init(&b);
 a.tstamp=0x123456789abcdef0ULL;
 CHECK(timer_grab(&a)==0);
 timer_update(&a,0x123,0xfffffffeU);
 CHECK(a.tstamp==0x123456789abcdef0ULL);
 CHECK(a.high_bits==0x123 && a.low_bits==0xfffffffeU && a.high_bits_check==0x123);
 CHECK(timer_grab(&a)==0x123fffffffeULL);
 timer_advance(&a,5);
 CHECK(timer_grab(&a)==0x12400000003ULL);
 CHECK(a.high_bits_check==a.high_bits);
 CHECK(a.tstamp==0x123456789abcdef0ULL);
 saved=timer_grab(&a);timer_advance(&a,0x300000007ULL);
 CHECK(timer_delta(&a,&saved)==0x300000007ULL);
 CHECK(saved==timer_grab(&a));
 timer_init(&a);timer_init(&b);
 uint64_t expected=0;
 for(uint32_t i=0;i<128;i++) {
  uint64_t start=0x100000000ULL+((uint64_t)i<<33);
  timer_start(&a,start);timer_stop(&a,start+0x100000003ULL);
  expected+=0x100000003ULL;
  CHECK(timer_grab(&a)==expected);
  CHECK(a.tstamp==start);
 }
 timer_switch(&a,a.tstamp+7,&b);
 CHECK(timer_grab(&a)==expected+7);
 CHECK(b.tstamp==a.tstamp+7 && timer_grab(&b)==0);
 semihost(4,"ARM accounting: actual struct layout, timestamp isolation, carry publication, deltas, stop/switch and repeated >4s CPU intervals passed\n");
 finish(0);
}
'''
entry='.syntax unified\n.arm\n.global _start\n_start:\n cpsid if\n ldr sp,=0x60200000\n bl run\n1: b 1b\n'
with tempfile.TemporaryDirectory(prefix='i9100-accounting-') as d:
 d=Path(d);(d/'test.c').write_text(code);(d/'entry.S').write_text(entry)
 binary=d/'test.elf'
 subprocess.run(['arm-none-eabi-gcc','-mcpu=cortex-a9','-marm','-O1','-ffreestanding','-fno-builtin','-nostdlib','-DBOARD_CONFIG_EXYNOS4210_I9100=1','-Wl,-Ttext,0x60010000','-Wl,-e,_start',str(d/'entry.S'),str(d/'test.c'),'-o',str(binary)],check=True)
 r=subprocess.run(['qemu-system-arm','-M','vexpress-a9','-cpu','cortex-a9','-m','128M','-nographic','-monitor','none','-serial','none','-semihosting-config','enable=on,target=native','-kernel',str(binary)],env=dict(os.environ,QEMU_AUDIO_DRV='none'),capture_output=True,text=True,timeout=15)
 print(r.stdout+r.stderr,end='')
 if r.returncode:raise SystemExit(r.returncode)
