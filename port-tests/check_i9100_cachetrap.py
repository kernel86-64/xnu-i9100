#!/usr/bin/env python3
"""Run actual cache-trap dispatch/helpers with CP15 events and dirty-line model."""
from pathlib import Path
import argparse,os,re,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,default=root/'osfmk/arm/armv/cpufunc-v7.s')
p.add_argument('--traps',type=Path,default=root/'osfmk/arm/traps_lo.s')
p.add_argument('--data-only',action='store_true');a=p.parse_args()
s=a.source.read_text();traps=a.traps.read_text()
asm='''.syntax unified
.arm
.text
#define _C_LABEL(x) _ ##x
'''
def event(op,operand='r0'):
 return 'push {r0-r5,r12,lr}\n mrs r4,cpsr\n mov r1,'+operand+'\n mov r0,#'+str(op)+'\n bl record_event\n msr cpsr_f,r4\n pop {r0-r5,r12,lr}'
for name in ['arm_icache_inv_all','arm_dcache_inv_all','arm_dcache_wbinv_all','arm_icache_sync_all','arm_idcache_wbinv_all']:
 body=re.search(r'ENTRY(?:_NP)?\('+name+r'\)(.*?)END\('+name+r'\)',s,re.S)[1]
 body=re.sub(r'mrc\s+p15,\s*1,\s*r0,\s*c0,\s*c0,\s*1','ldr r0,=0x01000003',body)
 body=re.sub(r'mrc\s+p15,\s*1,\s*r[02],\s*c0,\s*c0,\s*0',lambda m:'ldr '+('r2' if 'r2' in m[0] else 'r0')+',=test_ccsidr\n ldr '+('r2' if 'r2' in m[0] else 'r0')+', ['+('r2' if 'r2' in m[0] else 'r0')+']',body)
 body=re.sub(r'mcr\s+p15,\s*0,\s*(r\d+|ip),\s*c7,\s*c(6|14),\s*2',lambda m:event(1 if m[2]=='6' else 2,m[1]),body)
 body=re.sub(r'mcr\s+p15,\s*0,\s*(r\d+|ip),\s*c7,\s*c5,\s*(0|6)',lambda m:event(3 if m[2]=='0' else 4,m[1]),body)
 body=re.sub(r'mcr\s+p15,\s*2,\s*(r\d+|ip),\s*c0,\s*c0,\s*0',lambda m:event(7,m[1]),body)
 body=re.sub(r'(?m)^\s*dsb(?:\s+sy)?\s*(?=@|$)',lambda m:'\n dsb sy\n'+event(5)+'\n',body)
 body=re.sub(r'(?m)^\s*isb(?:\s+sy)?\s*(?=@|$)',lambda m:'\n isb sy\n'+event(6)+'\n',body)
 if re.search(r'\b(mcr|mrc)\s+p15',body):raise RuntimeError('Uninstrumented CP15: '+name)
 asm+='\n.balign 4\n.global _'+name+'\n_'+name+':\n'+body+'\n'
# Dispatch and maintenance blocks are copied unchanged, selecting I9100 in CPP.
asm+='\n.global tested_cache_request\ntested_cache_request:\n push {r4-r11,r12,lr}\n mov r3,r0\n mov r11,#0x80000000\n b swi_trap\n'
asm+=traps[traps.index('swi_trap:\n'):traps.index('swi_trap_tb:\n')]
asm+=traps[traps.index('icache_inv_trap:\n'):traps.index('thread_set_cthread_trap:\n')]
asm+='''
swi_trap_ret:
_thread_exception_return:
 mrs r0,cpsr
 ldr r1,=return_mask
 str r0,[r1]
 pop {r4-r11,r12,pc}
thread_set_cthread_trap:
thread_get_cthread_trap:
 b unexpected_request
'''
with tempfile.TemporaryDirectory(prefix='i9100-cachetrap-') as d:
 d=Path(d);(d/'ops.S').write_text(asm)
 (d/'start.S').write_text('.syntax unified\n.arm\n.global _start\n_start:\n cpsid if\n ldr sp,=0x60200000\n bl run\n1: b 1b\n')
 subprocess.run(['arm-none-eabi-gcc','-mcpu=cortex-a9','-marm','-O1','-ffreestanding','-fno-builtin','-nostdlib','-DBOARD_CONFIG_EXYNOS4210_I9100=1','-DDATA_ONLY='+str(int(a.data_only)),'-Wl,-Ttext,0x60010000','-Wl,-e,_start',str(d/'start.S'),str(d/'ops.S'),str(root/'port-tests/i9100_cachetrap_test.c'),'-o',str(d/'test.elf')],check=True)
 r=subprocess.run(['qemu-system-arm','-M','vexpress-a9','-cpu','cortex-a9','-m','128M','-nographic','-monitor','none','-serial','none','-semihosting-config','enable=on,target=native','-kernel',str(d/'test.elf')],env=dict(os.environ,QEMU_AUDIO_DRV='none'),capture_output=True,text=True,timeout=20)
 print(r.stdout+r.stderr,end='');raise SystemExit(r.returncode)
