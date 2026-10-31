#!/usr/bin/env python3
"""Actual ARM pmap_expand with a competing expansion during page allocation."""
from pathlib import Path
import argparse
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=root/'osfmk/arm/pmap.c')
args = parser.parse_args()
source = args.source.read_text()
start = source.index('void pmap_expand(pmap_t map, vm_offset_t v)')
body = source.index('{', start)
depth = 1
for end in range(body + 1, len(source)):
    depth += (source[end] == '{') - (source[end] == '}')
    if not depth:
        break
actual = source[start:end + 1]
code = r'''
typedef unsigned int uint32_t;typedef uint32_t vm_offset_t;typedef uint32_t spl_t;
#define PAGE_SHIFT 12
#define PAGE_SIZE 4096U
#define ARM_PAGE_MASK_VALUE 3U
#define ARM_PAGE_SECTION 2U
#define ARM_PAGE_PAGE_TABLE 1U
#define L1_PTE_ADDR_MASK 0xfffffc00U
#define L1_TYPE_PTE 1U
#define _COMM_PAGE_BASE_ADDRESS 0x40000000U
struct object {uint32_t resident;};
struct map {uint32_t pm_l1_size;struct object *pm_obj;uint32_t entries[4];};
typedef struct map *pmap_t;
struct page {uint32_t phys_page,freed;struct object *object;};typedef struct page *vm_page_t;
static struct object object;
static struct map kernel,user;static pmap_t kernel_pmap=&kernel;
static struct page pages[8];static uint32_t tables[8][256];
static uint32_t allocated,freed,depth,object_depth,inject,winner,published,flushes;
static int inuse_ptepages_count,alloc_ptepages_count;
static void semihost(uint32_t op,const void *p){
 register uint32_t r0 __asm__("r0")=op;register const void *r1 __asm__("r1")=p;
 __asm__ volatile("svc 0x123456":"+r"(r0):"r"(r1):"memory");
}
static void __attribute__((noreturn)) finish(uint32_t status){uint32_t v[2]={0x20026,status};semihost(0x20,v);for(;;){}}
#define CHECK(v) do{if(!(v)){semihost(4,"FAIL: " #v "\n");finish(1);}}while(0)
#define panic(...) do{semihost(4,"FAIL: unexpected expansion panic\n");finish(1);}while(0)
#define PMAP_LOCK(m) do{(void)(m);CHECK(!depth);depth++;}while(0)
#define PMAP_UNLOCK(m) do{(void)(m);CHECK(depth==1);depth--;}while(0)
#define tte_offset(v) (((v)>>20)*4U)
#define OSAddAtomic(n,p) (*(p)+=(n))
static vm_offset_t pmap_tte(pmap_t map,vm_offset_t v){return (uint32_t)&map->entries[(v>>20)&3U];}
void pmap_expand(pmap_t,vm_offset_t);
static vm_page_t pmap_grab_page(pmap_t map){
 CHECK(!depth && !object_depth && allocated<8);
 vm_page_t p=&pages[allocated];p->phys_page=0x42000+allocated;
 p->object=map->pm_obj;p->freed=0;allocated++;object.resident++;
 inuse_ptepages_count++;alloc_ptepages_count++;
 if(inject){
  // This thread blocks in allocation. Another thread completes expansion.
  uint32_t va=inject;inject=0;pmap_expand(map,va);
  winner=*(uint32_t *)pmap_tte(map,va);
  tables[((winner&L1_PTE_ADDR_MASK)>>12)-0x42000][7]=0x4567804e;
 }
 return p;
}
static void pmap_expand_ttb(pmap_t map,vm_offset_t size){CHECK(depth==1 && size<=map->pm_l1_size);}
static void pte_sync(void *p){(void)p;CHECK(depth==1);published++;}
static void pmap_flush_tlbs(pmap_t map,vm_offset_t a,vm_offset_t b){(void)map;CHECK(depth==1 && b==a+4096);flushes++;}
static void vm_object_lock(struct object *o){CHECK(o==&object && !depth && !object_depth);object_depth++;}
static void vm_object_unlock(struct object *o){CHECK(o==&object && object_depth==1);object_depth--;}
static void free_page(vm_page_t p){
 CHECK(!depth && object_depth==1 && p->object==&object && !p->freed);
 p->freed=1;freed++;object.resident--;
}
#define VM_PAGE_FREE(p) free_page(p)
''' + actual + r'''
static void scenario(pmap_t map,uint32_t va){
 for(uint32_t k=0;k<4;k++)map->entries[k]=0;
 for(uint32_t p=0;p<8;p++)for(uint32_t k=0;k<256;k++)tables[p][k]=0;
 allocated=freed=published=flushes=winner=0;inuse_ptepages_count=alloc_ptepages_count=0;
 object.resident=0;map->pm_obj=&object;map->pm_l1_size=4096;
 inject=va;pmap_expand(map,va);
 CHECK(*(uint32_t *)pmap_tte(map,va)==winner);
 CHECK(tables[((winner&L1_PTE_ADDR_MASK)>>12)-0x42000][7]==0x4567804e);
 CHECK(allocated==2 && freed==1 && object.resident==1);
 CHECK(inuse_ptepages_count==1 && alloc_ptepages_count==2 && !depth && !object_depth);
 CHECK(published==1 && flushes==1);
 // Repeated expansion is idempotent and does not allocate, replace or leak.
 pmap_expand(map,va);
 CHECK(allocated==2 && freed==1 && *(uint32_t *)pmap_tte(map,va)==winner);
 // A different L1 slot still gets a zeroed independent table.
 pmap_expand(map,va+0x100000);
 CHECK(allocated==3 && freed==1 && object.resident==2 && inuse_ptepages_count==2);
 CHECK(*(uint32_t *)pmap_tte(map,va)==winner && published==2 && flushes==2);
}
void run(void){
 scenario(&kernel,0xd1e00000);scenario(&user,0x01000000);
 semihost(4,"ARM pmap expansion: competing allocation preserves existing mappings; spare page freed outside pmap lock; counters, repeat and new-slot behavior passed\n");finish(0);
}
'''
with tempfile.TemporaryDirectory(prefix='i9100-expand-') as tmp:
    tmp = Path(tmp)
    (tmp/'test.c').write_text(code)
    (tmp/'entry.S').write_text('.syntax unified\n.arm\n.global _start\n_start:\n cpsid if\n ldr sp,=0x60200000\n bl run\n1: b 1b\n')
    subprocess.run(['arm-none-eabi-gcc','-mcpu=cortex-a9','-marm','-O1','-ffreestanding','-fno-builtin','-nostdlib','-DBOARD_CONFIG_EXYNOS4210_I9100=1','-Wl,-Ttext,0x60010000','-Wl,-e,_start',str(tmp/'entry.S'),str(tmp/'test.c'),'-o',str(tmp/'test.elf')],check=True)
    r = subprocess.run(['qemu-system-arm','-M','vexpress-a9','-cpu','cortex-a9','-m','128M','-nographic','-monitor','none','-serial','none','-semihosting-config','enable=on,target=native','-kernel',str(tmp/'test.elf')],env=dict(os.environ,QEMU_AUDIO_DRV='none'),capture_output=True,text=True,timeout=15)
    print(r.stdout+r.stderr,end='')
    raise SystemExit(r.returncode)
