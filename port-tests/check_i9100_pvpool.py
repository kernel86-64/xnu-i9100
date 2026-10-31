#!/usr/bin/env python3
"""Run actual PV free-list macros, startup seeding and self-hosted priming on ARM."""
from pathlib import Path
import argparse,os,re,subprocess,tempfile
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,default=root/'osfmk/arm/pmap.c')
p.add_argument('--expect-empty-panic',action='store_true',help='Control for WIRE14 source without bootstrap reserve')
a=p.parse_args();s=a.source.read_text()
def function(name):
 m=re.search(r'(?m)^(?:static )?(?:void|pv_hashed_entry_t) '+name+r'\([^;]*?\)\s*\{',s)
 if not m:raise RuntimeError(name)
 depth=1
 for end in range(m.end(),len(s)):
  depth+=(s[end]=='{')-(s[end]=='}')
  if not depth:return s[m.start():end+1]
structs=s[s.index('typedef struct pv_rooted_entry {    /* common prefix'):s.index('#define NPVHASH')]
macros=s[s.index('pv_hashed_entry_t pv_hashed_free_list ='):s.index('zone_t pv_hashed_list_zone;')]
if not a.expect_empty_panic:
 init=function('pmap_init')
 assert init.index('simple_lock_init(&pv_hashed_kern_free_list_lock') < init.index('i9100_pv_bootstrap_seed();') < init.index('pmap_initialized = TRUE')
with tempfile.TemporaryDirectory(prefix='i9100-pvpool-') as d:
 d=Path(d);(d/'pvpool-under-test.inc').write_text(structs+macros+'\n'+function('leo_node_get')+'\n'+function('mapping_free_prime'))
 (d/'start.S').write_text('.syntax unified\n.arm\n.global _start\n_start:\n cpsid if\n ldr sp,=0x60200000\n bl run\n1: b 1b\n')
 subprocess.run(['arm-none-eabi-gcc','-mcpu=cortex-a9','-marm','-O1','-ffreestanding','-fno-builtin','-nostdlib','-DBOARD_CONFIG_EXYNOS4210_I9100=1','-DTEST_OLD='+str(int(a.expect_empty_panic)),'-I'+str(d),'-Wl,-Ttext,0x60010000','-Wl,-e,_start',str(d/'start.S'),str(root/'port-tests/i9100_pvpool_test.c'),'-o',str(d/'test.elf')],check=True)
 r=subprocess.run(['qemu-system-arm','-M','vexpress-a9','-cpu','cortex-a9','-m','128M','-nographic','-monitor','none','-serial','none','-semihosting-config','enable=on,target=native','-kernel',str(d/'test.elf')],env=dict(os.environ,QEMU_AUDIO_DRV='none'),capture_output=True,text=True,timeout=25)
 print(r.stdout+r.stderr,end='');raise SystemExit(r.returncode)
