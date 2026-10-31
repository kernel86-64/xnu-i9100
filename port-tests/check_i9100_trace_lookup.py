#!/usr/bin/env python3
"""Compare production diagnostic lookups with the previous bounded probe policy."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
source = (root/'osfmk/arm/machine_routines.c').read_text()


def function(name):
    match = re.search(r'static volatile struct \w+ \*'+name+r'\([^)]*\)\s*\{', source)
    assert match, name
    start, level = match.start(), 1
    for pos in range(match.end(), len(source)):
        level += (source[pos] == '{') - (source[pos] == '}')
        if not level:
            return source[start:pos+1]
    raise AssertionError(name)


code = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#define I9100_SPIN_SLOTS 2048U
#define I9100_SPIN_PROBES 16U
#define I9100_SCOPE_SLOTS 1024U
struct i9100_spin_record {uint32_t key,caller,parent,thread,irq,depth;};
struct i9100_scope_record {uint32_t thread,depth,caller,parent,site;};
static volatile struct i9100_spin_record i9100_spin_records[I9100_SPIN_SLOTS];
static volatile struct i9100_scope_record i9100_scope_records[I9100_SCOPE_SLOTS];
static uint8_t i9100_spin_span[I9100_SPIN_SLOTS],i9100_scope_span[I9100_SCOPE_SLOTS];
static volatile struct i9100_spin_record before_spin[I9100_SPIN_SLOTS];
static volatile struct i9100_scope_record before_scope[I9100_SCOPE_SLOTS];
/* Previous algorithm scans all16 slots on a miss. It retains the first hole
 * but continues past it to locate an already-live colliding key. */
static volatile struct i9100_spin_record *old_spin(uint32_t key,int create){
 uint32_t slot=((key>>2)^(key>>13))&(I9100_SPIN_SLOTS-1U);
 volatile struct i9100_spin_record *empty=0;
 for(uint32_t n=0;n<I9100_SPIN_PROBES;n++){
  volatile struct i9100_spin_record *p=&before_spin[(slot+n)&(I9100_SPIN_SLOTS-1U)];
  if(p->key==key)return p;
  if(!p->key && !empty)empty=p;
 }
 return create?empty:0;
}
static volatile struct i9100_scope_record *old_scope(uint32_t thread,uint32_t depth,int create){
 uint32_t slot=((thread>>4)^(thread>>14)^(depth*31U))&(I9100_SCOPE_SLOTS-1U);
 volatile struct i9100_scope_record *empty=0;
 for(uint32_t n=0;n<16U;n++){
  volatile struct i9100_scope_record *p=&before_scope[(slot+n)&(I9100_SCOPE_SLOTS-1U)];
  if(p->thread==thread && p->depth==depth)return p;
  if(!p->thread && !empty)empty=p;
 }
 return create?empty:0;
}
'''+function('i9100_spin_find')+'\n'+function('i9100_scope_find')+r'''
static uint32_t rng=0xc0ffee;
static uint32_t random_word(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static void spin_step(uint32_t key,unsigned action){
 volatile struct i9100_spin_record *a=old_spin(key,action==1),*b=i9100_spin_find(key,action==1);
 assert(!!a==!!b);
 if(!a)return;
 assert(a-before_spin==b-i9100_spin_records);
 assert(a->key==b->key);
 if(action==1){a->key=key;b->key=key;a->caller=b->caller=key^0x1234;}
 if(action==2){a->key=0;b->key=0;}
}
static void scope_step(uint32_t thread,uint32_t depth,unsigned action){
 volatile struct i9100_scope_record *a=old_scope(thread,depth,action==1),*b=i9100_scope_find(thread,depth,action==1);
 assert(!!a==!!b);
 if(!a)return;
 assert(a-before_scope==b-i9100_scope_records);
 assert(a->thread==b->thread && a->depth==b->depth);
 if(action==1){a->thread=b->thread=thread;a->depth=b->depth=depth;a->caller=b->caller=thread^depth;}
 if(action==2){a->thread=0;b->thread=0;}
}
int main(void){
 // Fill colliding buckets at both array ends, delete holes, then reuse them.
 for(unsigned target=0;target<2;target++){
  uint32_t keys[17],threads[17],n=0;
  for(uint32_t k=0x81000000;n<17;k+=4)
   if((((k>>2)^(k>>13))&2047U)==(target?2047U:0U))keys[n++]=k;
  n=0;
  for(uint32_t t=0x81000000;n<17;t+=16)
   if((((t>>4)^(t>>14)^31U)&1023U)==(target?1023U:0U))threads[n++]=t;
  for(unsigned i=0;i<17;i++){spin_step(keys[i],1);scope_step(threads[i],1,1);}
  assert(!i9100_spin_find(keys[16],0) && !i9100_scope_find(threads[16],1,0));
  for(unsigned i=0;i<16;i+=2){spin_step(keys[i],2);scope_step(threads[i],1,2);}
  for(unsigned i=1;i<16;i+=2){spin_step(keys[i],1);scope_step(threads[i],1,1);}
  spin_step(keys[16],1);scope_step(threads[16],1,1);
  for(unsigned i=0;i<17;i++){spin_step(keys[i],2);scope_step(threads[i],1,2);}
 }
 for(unsigned n=0;n<200000;n++){
  uint32_t k=0x82000000+(random_word()%4096U)*4U;
  spin_step(k,random_word()%3U);
  uint32_t thread=0x83000000+(random_word()%512U)*16U,depth=random_word()%8U+1U;
  scope_step(thread,depth,random_word()%3U);
 }
 assert(!memcmp((const void*)before_spin,(const void*)i9100_spin_records,sizeof(before_spin)));
 assert(!memcmp((const void*)before_scope,(const void*)i9100_scope_records,sizeof(before_scope)));
 // Overestimated bounds stay safe and preserve the old bounded policy.
 memset(i9100_spin_span,255,sizeof(i9100_spin_span));
 memset(i9100_scope_span,255,sizeof(i9100_scope_span));
 for(unsigned n=0;n<10000;n++){
  spin_step(0x82000000+(random_word()%4096U)*4U,random_word()%3U);
  scope_step(0x83000000+(random_word()%512U)*16U,random_word()%8U+1U,random_word()%3U);
 }
 puts("PASS: actual lookups match previous exact slots across420000 mixed operations, collisions, deleted holes, wrapped/full buckets and capped bounds");
}
'''
with tempfile.TemporaryDirectory(prefix='i9100-trace-lookup-') as directory:
    path = Path(directory)
    (path/'test.c').write_text(code)
    subprocess.run(['clang', '-O1', '-fsanitize=address,undefined', str(path/'test.c'),
                    '-o', str(path/'test')], check=True)
    subprocess.run([str(path/'test')], check=True)
