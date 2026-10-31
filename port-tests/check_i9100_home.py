#!/usr/bin/env python3
"""Run the real Home polling method through the production native HID queue."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
platform = root/'iokit/Drivers/KernelBuiltIn/ARM/AppleARMPlatform'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--queue-header', type=Path, help='Use a previous queue implementation as a regression control')
args = parser.parse_args()
source = (platform/'IOS7LeoHIDTouch.cpp').read_text()
match = re.search(r'void IOHIDEventService::pollHome\(void\)\s*\{', source)
if not match:
    raise RuntimeError('Home polling method not found')
depth = 1
for end in range(match.end(), len(source)):
    depth += (source[end] == '{') - (source[end] == '}')
    if not depth:
        polling = source[match.start():end+1]
        break
else:
    raise RuntimeError('Unclosed Home polling method')

code = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include "IOS7LeoTouchWire.h"
#include "i9100_home.h"
#include "i9100_home_observation.h"
#include "IOS7LeoTouchQueueProtocol.h"
volatile I9100HomeObservation i9100_home_observation;
static uint64_t now = 1000000000ULL;
static uint64_t mach_absolute_time() {return now;}
static unsigned held;
static void IOLockLock(void *) {assert(!held);held=1;}
static void IOLockUnlock(void *) {assert(held);held=0;}
#define IOLog(...) ((void)0)
static uint32_t le32(const unsigned char *p)
{return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);}
static uint64_t le64(const unsigned char *p) {return le32(p)|(uint64_t(le32(p+4))<<32);}
static void barrier(void *) {}
static void copy(void *,void *out,const void *in,uint32_t size) {memcpy(out,in,size);}
struct Queue {
 uint32_t head=0,tail=0,flags=0;
 uint32_t storage[1024]={};
 bool sane() {return head<=4096 && tail<=4096 && !(head&3) && !(tail&3);}
 uint32_t readerHead() {return head;}
 uint32_t writerTail() {return tail;}
 bool enqueue(void *data,uint32_t size) {
  assert(held);
  LeoTouchQueueHooks hooks={nullptr,barrier,copy};
  return leo_touch_queue_enqueue(&head,&tail,4096,(unsigned char *)storage,data,size,&hooks,&flags)!=0;
 }
 /* Consumer follows IODataQueue's size-prefixed entries and wrap sentinel,
  * independently decoding bytes instead of casting the producer structs. */
 std::vector<unsigned char> dequeue() {
  assert(head!=tail);auto bytes=(unsigned char *)storage;uint32_t pos=head;
  if(pos+4>4096)pos=0;
  uint32_t size=le32(bytes+pos);
  if(pos+4+size>4096){pos=0;size=le32(bytes);}
  assert(size==52 || size==204);assert(pos+4+size<=4096);
  std::vector<unsigned char> packet(bytes+pos+4,bytes+pos+4+size);
  head=pos+4+size;return packet;
 }
};
class IOHIDEventService {
public:
 Queue backing;Queue *queue=&backing;void *lock=nullptr;
 bool opened=false,lastHomeValid=false;unsigned eventLogs=0,raw=1U<<5;
 I9100HomeState homeState;I9100HomePacket lastHomePacket;
 IOHIDEventService() {i9100_home_reset(&homeState);}
 static uint32_t readRegister(void *p,uint32_t region,uint32_t offset) {
  assert(held && region==1 && offset==0xc64);return ((IOHIDEventService *)p)->raw;
 }
 uint64_t getRegistryEntryID() {return 0x100000002ULL;}
 void publishSnapshot() {
  assert(held);i9100_home_observation.opened=opened;
  i9100_home_observation.head=queue->readerHead();i9100_home_observation.tail=queue->writerTail();
 }
 void pollHome();
 void sample(unsigned down) {raw=down?0:1U<<5;now+=20000000ULL;pollHome();assert(!held);}
 void edge(unsigned down) {sample(down);sample(down);}
};
'''
code += polling
code += r'''
static uint64_t check_key(const std::vector<unsigned char> &p,unsigned down)
{
 assert(p.size()==52 && le32(p.data()+24)==1 && le32(p.data()+20)==0);
 assert(le64(p.data()+8)==0x100000002ULL && le64(p.data())!=0);
 assert(le32(p.data()+28)==24 && le32(p.data()+32)==3);
 assert(p[40]==0 && p[44]==12 && p[45]==0 && p[46]==64 && p[47]==0);
 assert(le32(p.data()+48)==down);return le64(p.data());
}
int main()
{
 // Exercise exact pin masks: unrelated card-detect/mux/pull bits survive.
 for(unsigned bit=0;bit<32;bit++) {
  uint32_t value=1U<<bit,con=i9100_home_input_con(value),pull=i9100_home_input_pull(value);
  assert(con==(value&~0x00f00000U));assert((pull&0xc00U)==0xc00U);
  assert((pull&~0xc00U)==(value&~0xc00U));
  assert(i9100_home_restore_con(con,value)==value);
  assert(i9100_home_restore_pull(pull,value)==value);
 }
 assert(i9100_home_down(0xffffffffU)==0 && i9100_home_down(~(1U<<5))==1);
 IOHIDEventService s;
 s.sample(1);assert(i9100_home_observation.down==1 && !s.homeState.count);
 s.opened=true;s.edge(1);assert(s.backing.head==s.backing.tail); // Boot-held suppression.
 s.edge(0);assert(s.homeState.armed && s.backing.head==s.backing.tail);
 s.edge(1);
 // This assertion fails with the previous bytes==204 queue restriction.
 assert(s.lastHomeValid && s.backing.tail==56 && !s.homeState.count);
 assert(s.backing.flags&LEO_TOUCH_UP_NOTIFY_SELECTED);
 auto down=s.backing.dequeue();uint64_t downTime=check_key(down,1);
 for(unsigned n=0;n<50;n++)s.sample(1);
 assert(s.backing.head==s.backing.tail); // No fabricated repeats.
 s.edge(0);auto up=s.backing.dequeue();assert(check_key(up,0)-downTime>=1000000000ULL);
 // Real queue pressure: capacity fits 73 Home records, retain the next 7.
 s.backing.head=s.backing.tail=0;
 for(unsigned n=0;n<80;n++)s.edge((n&1U)?0:1);
 assert(s.homeState.count==7);
 assert(i9100_home_observation.edges==82 && i9100_home_observation.enqueued==75);
 uint64_t last=0;
 for(unsigned n=0;n<73;n++) {
  auto packet=s.backing.dequeue();uint64_t t=check_key(packet,(n&1U)?0:1);assert(t>last);last=t;
 }
 s.sample(0);assert(!s.homeState.count);
 for(unsigned n=73;n<80;n++) {
  auto packet=s.backing.dequeue();uint64_t t=check_key(packet,(n&1U)?0:1);assert(t>last);last=t;
 }
 assert(s.backing.head==s.backing.tail && i9100_home_observation.enqueued==82);
 // Both allowed native sizes must wrap/dequeue at every aligned frontier.
 LeoHIDPacket touch;assert(leo_touch_make_hid_packet(15,20,1,false,123,7,&touch));
 I9100HomePacket key;assert(i9100_home_packet(1,123,0x100000002ULL,&key));
 for(unsigned start=0;start<=4096;start+=4) {
  s.backing.head=s.backing.tail=start;IOLockLock(nullptr);
  assert(s.backing.enqueue(&key,52));IOLockUnlock(nullptr);
  check_key(s.backing.dequeue(),1);assert(s.backing.head==s.backing.tail);
  s.backing.head=s.backing.tail=start;IOLockLock(nullptr);
  assert(s.backing.enqueue(&touch,204));IOLockUnlock(nullptr);
  assert(s.backing.dequeue().size()==204 && s.backing.head==s.backing.tail);
 }
 // Invalid lengths/full frontiers never mutate the queue.
 s.backing.head=56;s.backing.tail=0;uint32_t saved[1024];memcpy(saved,s.backing.storage,sizeof(saved));
 IOLockLock(nullptr);assert(!s.backing.enqueue(&key,52));
 for(unsigned size=0;size<208;size++)if(size!=52 && size!=204)assert(!s.backing.enqueue(&touch,size));
 IOLockUnlock(nullptr);assert(!memcmp(saved,s.backing.storage,sizeof(saved)) && s.backing.tail==0);
 struct {char before;char line[46];char after;} text={'L',{},'R'};
 i9100_home_observation.enabled=1;i9100_home_observation.down=1;i9100_home_observation.opened=1;
 i9100_home_observation.edges=0x12345678;i9100_home_observation.enqueued=0x90abcdef;
 i9100_home_observation.head=0x1000;i9100_home_observation.tail=0x38;
 i9100_home_status_text(text.line);
 assert(!strcmp(text.line,"HOME E1 P1 O1 D12345678 Q90abcdef H1000 T0038"));
 assert(text.before=='L' && text.after=='R');
 puts("Home integration: actual poll -> 52B native queue -> consumer down/hold/up, FIFO backpressure, all 1025 wrap frontiers for both sizes, invalid/full queues, GPIO masks and bounded status text passed");
}
'''
with tempfile.TemporaryDirectory(prefix='i9100-home-') as directory:
    work = Path(directory)
    if args.queue_header:
        shutil.copy2(args.queue_header, work/'IOS7LeoTouchQueueProtocol.h')
    (work/'test.cpp').write_text(code)
    binary = work/'test'
    subprocess.run(['c++', '-std=c++11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-I'+str(platform),
                    str(work/'test.cpp'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
