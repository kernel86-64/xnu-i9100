#!/usr/bin/env python3
"""Exercise the actual VM partial-copy branch, wrapper and ARM pmap helper."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent


def block(source, start):
    brace = source.index('{', start)
    depth = 1
    pos = brace+1
    while depth:
        depth += (source[pos] == '{')-(source[pos] == '}')
        pos += 1
    return source[start:pos]


pmap = (root/'osfmk/arm/pmap.c').read_text()
resident = (root/'osfmk/vm/vm_resident.c').read_text()
fault = (root/'osfmk/vm/vm_fault.c').read_text()
helper = block(pmap, pmap.index('void pmap_copy_part_page('))
old = helper.replace('+ dst_offset), len);', '+ src_offset), len);')
assert old != helper
wrapper = block(resident, resident.index('void\nvm_page_part_copy('))
partial = block(fault, fault.index('if (!page_aligned(src_offset)'))
prefix = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#define PAGE_SIZE 4096U
#define PAGE_SHIFT 12
#define PAGE_MASK 4095U
#define FALSE 0
#define TRUE 1
#define VM_PAGE_NULL NULL
#define page_aligned(v) (!((v)&PAGE_MASK))
typedef unsigned ppnum_t;
typedef uintptr_t vm_offset_t;
typedef size_t vm_size_t;
typedef uint64_t vm_object_offset_t;
struct page {unsigned phys_page,dirty;void *object;};
typedef struct page *vm_page_t;
static unsigned char ram[4*PAGE_SIZE], reference[sizeof(ram)];
#define phys_to_virt(p) ((uintptr_t)ram+(p))
#define ovbcopy(s,d,n) memmove((d),(s),(n))
#define vm_object_trunc_page(v) ((v)&~(uint64_t)PAGE_MASK)
#define vm_object_lock(v) ((void)0)
#define vm_object_unlock(v) ((void)0)
#define SET_PAGE_DIRTY(p,v) ((p)->dirty=(v))
static void vm_page_part_zero_fill(vm_page_t p,vm_offset_t off,vm_size_t n){memset(ram+(p->phys_page<<12)+off,0,n);}
'''
body = r'''
static unsigned run(unsigned source,unsigned destination,unsigned size,unsigned same){
 struct page src={1,0,NULL},dst={same?1:2,0,NULL};
 vm_page_t result_page=&src,dst_page=&dst;void *dst_object=NULL;
 vm_object_offset_t src_offset=source,dst_offset=destination,amount_left=size;
 vm_size_t part_size=0;
 PARTIAL
 return part_size;
}
static unsigned random_value=0x12345678;
static unsigned random32(void){random_value^=random_value<<13;random_value^=random_value>>17;random_value^=random_value<<5;return random_value;}
static void initialize(void){for(unsigned n=0;n<sizeof(ram);n++)ram[n]=(unsigned char)(n*17+(n>>4));memcpy(reference,ram,sizeof(ram));}
int main(void){
 // A legitimate write at offset0x100 must not clobber a slab magic at0x10.
 initialize();uint32_t magic=0xdeafbe01,poison=0xdeadf00d;
 memcpy(ram+2*PAGE_SIZE+16,&magic,4);memcpy(ram+PAGE_SIZE+16,&poison,4);
 run(16,256,4,0);uint32_t actual;memcpy(&actual,ram+2*PAGE_SIZE+16,4);
 if(actual!=magic){puts("OLD CONTROL: destination's slab magic overwritten outside the requested range");return 23;}
 unsigned sizes[]={0,1,2,3,4,7,8,15,16,31,32,63,64,127,255,256,1023,2048,4095};
 unsigned offsets[]={0,1,3,4,15,16,31,63,127,128,255,256,1024,2048,4095};
 unsigned scenarios=0;
 for(unsigned same=0;same<2;same++)for(unsigned si=0;si<15;si++)for(unsigned di=0;di<15;di++)for(unsigned ni=0;ni<19;ni++){
  unsigned s=offsets[si],d=offsets[di],n=sizes[ni];
  if(!s&&!d&&!n)continue; // actual vm_fault_copy full-page condition
  if(n>PAGE_SIZE-s)n=PAGE_SIZE-s;if(n>PAGE_SIZE-d)n=PAGE_SIZE-d;
  initialize();memmove(reference+(same?1:2)*PAGE_SIZE+d,reference+PAGE_SIZE+s,n);
  assert(run(s,d,n,same)==n);assert(!memcmp(reference,ram,sizeof(ram)));scenarios++;
 }
 for(unsigned i=0;i<20000;i++){
  unsigned s=random32()&4095,d=random32()&4095,n=1+(random32()&4095),same=i&1;
  if(n>PAGE_SIZE-s)n=PAGE_SIZE-s;if(n>PAGE_SIZE-d)n=PAGE_SIZE-d;
  initialize();memmove(reference+(same?1:2)*PAGE_SIZE+d,reference+PAGE_SIZE+s,n);
  assert(run(s,d,n,same)==n);assert(!memcmp(reference,ram,sizeof(ram)));scenarios++;
 }
 printf("PASS: actual vm_fault_copy partial branch -> vm_page_part_copy -> pmap_copy_part_page; %u offset/boundary/same-page overlap cases; full RAM guards + slab magic preserved; ASan/UBSan\n",scenarios);
}
'''.replace('PARTIAL', partial)
with tempfile.TemporaryDirectory(prefix='i9100-pagecopy-') as folder:
    folder = Path(folder)
    for name, function in [('old', old), ('fixed', helper)]:
        (folder/(name+'.c')).write_text(prefix+function+'\n'+wrapper+'\n'+body)
        subprocess.run(['clang', '-O1', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                        str(folder/(name+'.c')), '-o', str(folder/name)], check=True)
        result = subprocess.run([str(folder/name)], capture_output=True, text=True)
        print(result.stdout, end='')
        assert result.returncode == (23 if name == 'old' else 0), result.stderr
