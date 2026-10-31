/* Host tests cannot establish real GPIO wiring, signal timing or UI behavior. */
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include "i9100_touch.h"
#include "IOS7LeoTouchWire.h"
#include "i9100_home.h"
#include "i9100_touch_observation.h"
volatile I9100TouchObservation i9100_touch_observation;

static void observation_checks()
{
 struct {uint32_t before;char line[64];uint32_t after;} out={0x12345678,{0},0x87654321};
 i9100_touch_observation.ready=1;i9100_touch_observation.init_result=(uint32_t)-5;
 i9100_touch_observation.stage=5;i9100_touch_observation.opened=1;
 i9100_touch_observation.polls=0x10002;i9100_touch_observation.reports=3;
 i9100_touch_observation.enqueued=4;i9100_touch_observation.head=0x120;
 i9100_touch_observation.tail=0x1f0;i9100_touch_observation.errors=6;
 i9100_touch_status_text(out.line);
 assert(out.before==0x12345678 && out.after==0x87654321 && strlen(out.line)<60);
 assert(strstr(out.line,"TCH R1 Ifffffffb S5 O1"));
 assert(strstr(out.line,"P0002 N0003 Q0004 H0120 T01f0 E0006"));
 assert(i9100_touch_observation.polls==0x10002 && i9100_touch_observation.enqueued==4);
 puts("Touch status: negative init error, real progress/cursors, low16 counters and bounded RAM-only formatting passed");
}

struct Controller {
 uint8_t mem[2048];std::vector<std::vector<uint8_t> > messages;
 unsigned readMessages,writes;int readError;bool badReadback;
 static void le16(uint8_t *p,unsigned value) { p[0]=value;p[1]=value>>8; }
 /* Independent fixture checksum; bit 24 is reduced after each 16-bit word. */
 void checksum() {
  uint64_t sum=0;
  for(unsigned i=0;i<31;i+=2) {
   unsigned word=mem[i]|(i+1<31?unsigned(mem[i+1])<<8:0);
   sum=sum*2U^word;
   if(sum>=0x1000000U)sum^=0x180001bU;
  }
  mem[31]=sum;mem[32]=sum>>8;mem[33]=sum>>16;
 }
 void object(unsigned index,unsigned type,unsigned address,unsigned size,unsigned reports) {
  uint8_t *o=mem+7+index*6;o[0]=type;le16(o+1,address);o[3]=size-1;o[4]=0;o[5]=reports;
 }
 Controller(unsigned family=0x80):readMessages(0),writes(0),readError(0),badReadback(false) {
  memset(mem,0,sizeof(mem));mem[0]=family;mem[1]=1;mem[2]=0x22;mem[3]=0xaa;mem[4]=19;mem[5]=11;mem[6]=4;
  object(0,5,0x100,9,0);object(1,6,0x110,6,1);object(2,7,0x120,3,0);object(3,9,0x130,35,10);
  checksum();mem[0x133]=19;mem[0x134]=11;mem[0x139]=1;mem[0x13e]=10;
  le16(mem+0x142,799);le16(mem+0x144,479);
 }
 static int read(void *cookie,uint16_t address,uint8_t *out,uint32_t bytes) {
  Controller *c=(Controller *)cookie;
  if(c->readError)return c->readError;
  assert(unsigned(address)+bytes<=sizeof(c->mem));
  if(address==0x100) {
   c->readMessages++;assert(bytes==9 && !c->messages.empty());
   memcpy(out,c->messages.front().data(),bytes);c->messages.erase(c->messages.begin());
  } else {
   memcpy(out,c->mem+address,bytes);
   if(c->badReadback && address==0x130 && bytes==1)out[0]^=1;
  }
  return 0;
 }
 static int write(void *cookie,uint16_t address,const uint8_t *data,uint32_t bytes) {
  Controller *c=(Controller *)cookie;
  /* Disallow resets, NVM backup, firmware and unrelated object writes. */
  assert((address==0x120 && bytes==3) || (address==0x130 && bytes==1) ||
         (address==0x13e && bytes==1) || ((address==0x112 || address==0x113) && bytes==1));
  c->writes++;memcpy(c->mem+address,data,bytes);return 0;
 }
 static int changed(void *cookie) { return !((Controller *)cookie)->messages.empty(); }
 i9100_touch_io io() { i9100_touch_io result={this,read,write,changed};return result; }
 void message(unsigned id,unsigned status,unsigned x=0,unsigned y=0) {
  std::vector<uint8_t> m(9);x<<=2;y<<=2;m[0]=id;m[1]=status;m[2]=x>>4;m[3]=y>>4;m[4]=((x&15)<<4)|(y&15);
  m[5]=5;m[6]=100;messages.push_back(m);
 }
};
static void unchanged(const i9100_touch_report &a,const i9100_touch_report &b)
{ assert(!memcmp(&a,&b,sizeof(a))); }
static void protocol_checks() {
 i9100_touch_state s;Controller c;i9100_touch_io io=c.io();
 assert(i9100_touch_init(&s,&io)==0 && s.ready && s.first_report==2 && s.report_count==10);
 assert(s.x_max==479 && s.y_max==799 && s.x_drop==2 && s.y_drop==2);
 assert(c.mem[0x120]==48 && c.mem[0x121]==255 && c.mem[0x122]==25 && c.mem[0x130]==0x83);
 i9100_touch_report out,sentinel;memset(&out,0xa5,sizeof(out));sentinel=out;
 assert(i9100_touch_poll(&s,&out)==0 && !c.readMessages);unchanged(out,sentinel);
 c.message(2,0xc0,0,0);assert(i9100_touch_poll(&s,&out)==1 && out.down && out.x==0 && out.y==0);
 c.message(2,0x90,479,799);assert(i9100_touch_poll(&s,&out)==1 && out.down && out.x==479 && out.y==799);
 c.readError=I9100_TOUCH_NACK;sentinel=out;c.message(2,0x20,1,1);
 assert(i9100_touch_poll(&s,&out)==I9100_TOUCH_NACK && s.primary==2);unchanged(out,sentinel);
 c.readError=0;assert(i9100_touch_poll(&s,&out)==1 && !out.down && out.x==479 && out.y==799);
 c.message(2,0x20);sentinel=out;assert(i9100_touch_poll(&s,&out)==0);unchanged(out,sentinel);
 c.message(2,0xc0,200,300);assert(i9100_touch_poll(&s,&out)==1);
 c.message(3,0xc0,400,500);sentinel=out;assert(i9100_touch_poll(&s,&out)==0 && s.last_contacts==2);unchanged(out,sentinel);
 c.message(2,0x20);assert(i9100_touch_poll(&s,&out)==1 && !out.down && out.contacts==1);
 c.message(3,0x90,450,600);sentinel=out;assert(i9100_touch_poll(&s,&out)==0 && !s.primary);unchanged(out,sentinel);
 c.message(3,0x20);assert(i9100_touch_poll(&s,&out)==0 && !s.active_mask);
 c.message(4,0xc0,30,40);assert(i9100_touch_poll(&s,&out)==1 && out.down && out.x==30 && out.y==40);
 c.message(4,0x02);assert(i9100_touch_poll(&s,&out)==1 && !out.down);
 c.message(2,0xc0,500,0);sentinel=out;
 assert(i9100_touch_poll(&s,&out)==I9100_TOUCH_PROTOCOL && !s.active_mask);unchanged(out,sentinel);
 for(unsigned i=0;i<17;i++)c.message(80,0);
 c.message(2,0xc0,50,60);unsigned before=c.readMessages;
 assert(i9100_touch_poll(&s,&out)==0 && c.readMessages-before==16);
 assert(i9100_touch_poll(&s,&out)==1 && out.x==50 && out.y==60);
 c.message(1,0x10);assert(i9100_touch_poll(&s,&out)==1 && !out.down && !s.active_mask);
 c.message(0xff,0);sentinel=out;assert(i9100_touch_poll(&s,&out)==0);unchanged(out,sentinel);
 Controller e(0x81);io=e.io();assert(i9100_touch_init(&s,&io)==0 && s.info[0]==0x81);
 e.mem[5]^=1;io=e.io();e.writes=0;
 assert(i9100_touch_init(&s,&io)==I9100_TOUCH_CRC && !s.ready && !e.writes);
 assert(i9100_touch_poll(&s,&out)==I9100_TOUCH_NOT_READY);unchanged(out,sentinel);
 Controller unknown(0x99);io=unknown.io();assert(i9100_touch_init(&s,&io)==I9100_TOUCH_PROTOCOL && !unknown.writes);
 Controller badObject;badObject.object(3,9,0x130,35,33);badObject.checksum();io=badObject.io();
 assert(i9100_touch_init(&s,&io)==I9100_TOUCH_PROTOCOL && !badObject.writes);
 Controller broken;broken.badReadback=true;io=broken.io();assert(i9100_touch_init(&s,&io)==I9100_TOUCH_PROTOCOL && !s.ready);
 Controller large;large.mem[0x139]=0;Controller::le16(large.mem+0x142,4095);Controller::le16(large.mem+0x144,2047);
 io=large.io();assert(i9100_touch_init(&s,&io)==0 && !s.x_drop && !s.y_drop);
 uint8_t raw[9]={2,0xc0,0xff,0x7f,0xff,1,1,0,0};
 assert(i9100_touch_decode(&s,raw,sizeof(raw),&out)==1 && out.x==479 && out.y==799);
 puts("Atmel: CRC/object discovery, volatile wake, range/orientation, down/move/up, suppression, primary ownership, failures and bounded drain passed");
}

/* I2C slave responds to GPIO transitions, not to driver helper calls. */
struct GPIOModel {
 enum Phase {IDLE,RX,SLAVE_ACK,TX,MASTER_ACK};
 uint32_t regs[2][1024];uint8_t memory[65536];
 Phase phase,next;bool oldClock,oldData,slaveLow,expectAddress,readMode,nackAddress,stuckClock,stuckData,masterACK;
 unsigned bits,ackPhase,rxByte,registerBytes,pointer,txByte,starts,stops,waits;
 unsigned enters=0,leaves=0,guardDepth=0,nacksRemaining=0;bool rejectByte=false;
 std::vector<uint8_t> received;
 GPIOModel():phase(IDLE),next(IDLE),oldClock(true),oldData(true),slaveLow(false),expectAddress(true),
 readMode(false),nackAddress(false),stuckClock(false),stuckData(false),masterACK(false),bits(0),ackPhase(0),rxByte(0),
 registerBytes(0),pointer(0),txByte(0),starts(0),stops(0),waits(0) {
  memset(regs,0,sizeof(regs));memset(memory,0,sizeof(memory));
  regs[0][0x20/4]=0x22333322;regs[0][0x24/4]=0xa0;regs[0][0x28/4]=0x12345678;
  regs[1][0xc0/4]=0x12345678;regs[1][0xc4/4]=0x87654321;regs[1][0xc8/4]=0xabcdef00;
  regs[1][0xc00/4]=0x22334455;regs[1][0xc08/4]=0x55667788;regs[1][0xc04/4]=0x10;
 }
 bool master(unsigned pin) const {
  unsigned function=(regs[0][0x20/4]>>(pin*4))&15U;
  if(function!=1)return true;
  /* Outputs must always be low; highs are supplied only by pull-ups. */
  assert(!(regs[0][0x24/4]&(1U<<pin)));return false;
 }
 bool clock()const { return master(3) && !stuckClock; }
 bool data()const { return master(2) && !slaveLow && !stuckData; }
 void beginTX() { phase=TX;bits=0;txByte=memory[pointer];slaveLow=!(txByte&0x80U); }
 void acceptedByte() {
  received.push_back((uint8_t)rxByte);next=RX;
  rejectByte=expectAddress && (nackAddress || nacksRemaining);
  if(expectAddress && nacksRemaining)--nacksRemaining;
  if(expectAddress) {
   expectAddress=false;assert((rxByte>>1)==0x4aU);
   readMode=rxByte&1U;if(!readMode)registerBytes=0;
   if(readMode)next=TX;
  } else if(!readMode) {
   if(registerBytes==0){pointer=rxByte;registerBytes++;}
   else if(registerBytes==1){pointer|=rxByte<<8;registerBytes++;}
   else memory[pointer++]=(uint8_t)rxByte;
  }
  phase=SLAVE_ACK;ackPhase=0;
 }
 void step() {
  bool clk=clock(),dat=data();
  if(oldClock && clk && oldData!=dat) {
   if(!dat) { phase=RX;bits=0;rxByte=0;expectAddress=true;slaveLow=false;starts++; }
   else { phase=IDLE;slaveLow=false;stops++; }
  } else if(!oldClock && clk) {
   if(phase==RX) { rxByte=(rxByte<<1)|dat;if(++bits==8)acceptedByte(); }
   else if(phase==TX) { if(++bits==8){phase=MASTER_ACK;ackPhase=0;} }
   else if(phase==MASTER_ACK && ackPhase==1)masterACK=!dat;
  } else if(oldClock && !clk) {
   if(phase==SLAVE_ACK) {
    if(!ackPhase){slaveLow=!rejectByte;ackPhase=1;}
    else {
     slaveLow=false;
     if(rejectByte)phase=IDLE;
     else if(next==TX)beginTX();
     else{phase=RX;bits=0;rxByte=0;}
    }
   } else if(phase==TX) slaveLow=!(txByte&(0x80U>>bits));
   else if(phase==MASTER_ACK) {
    if(!ackPhase){slaveLow=false;ackPhase=1;}
    else if(masterACK){pointer++;beginTX();}
    else {phase=IDLE;slaveLow=false;}
   }
  }
  oldClock=clock();oldData=data();
 }
 static uint32_t read(void *cookie,uint32_t region,uint32_t offset) {
  GPIOModel *m=(GPIOModel *)cookie;assert(region<2 && offset<4096 && !(offset&3));
  uint32_t value=m->regs[region][offset/4];
  if(!region && offset==0x24)value=(value&~12U)|(m->clock()?8U:0)|(m->data()?4U:0);
  return value;
 }
 static void write(void *cookie,uint32_t region,uint32_t offset,uint32_t value) {
  GPIOModel *m=(GPIOModel *)cookie;assert(region<2 && offset<4096 && !(offset&3));
  /* Exact allowed board registers; writes to SD/PMIC/CMU are rejected. */
  assert((region==0 && (offset==0x20 || offset==0x24 || offset==0x28)) ||
         (region==1 && (offset==0xc0 || offset==0xc4 || offset==0xc8 || offset==0xc00 || offset==0xc08)));
  m->regs[region][offset/4]=value;
  if(!region && (offset==0x20 || offset==0x24))m->step();
 }
 static int delay(void *cookie,uint32_t) { ((GPIOModel *)cookie)->waits++;return 1; }
 static void enter(void *cookie) { GPIOModel *m=(GPIOModel *)cookie;assert(!m->guardDepth);m->guardDepth++;m->enters++; }
 static void leave(void *cookie) { GPIOModel *m=(GPIOModel *)cookie;assert(m->guardDepth==1);m->guardDepth--;m->leaves++; }
 i9100_touch_gpio_io io() { i9100_touch_gpio_io result={this,read,write,delay,4,enter,leave};return result; }
};
static void gpio_checks() {
 GPIOModel model;i9100_touch_bus bus;i9100_touch_gpio_io io=model.io();
 uint32_t initial[2][1024];memcpy(initial,model.regs,sizeof(initial));
 assert(i9100_touch_bus_init(&bus,&io)==0 && bus.configured);
 assert((model.regs[1][0xc4/4]&8U) && ((model.regs[1][0xc0/4]>>12)&15U)==1);
 assert(i9100_touch_bus_changed(&bus)==0);model.regs[1][0xc04/4]=0;assert(i9100_touch_bus_changed(&bus)==1);
 model.memory[0x1234]=0xa6;model.memory[0x1235]=0x5b;
 uint8_t data[2]={0,0};assert(i9100_touch_bus_read(&bus,0x1234,data,2)==0);
 assert(data[0]==0xa6 && data[1]==0x5b && model.enters==1 && model.leaves==1 && !model.guardDepth);
 const uint8_t expected[]={0x94,0x34,0x12,0x95};assert(model.received.size()==sizeof(expected));
 assert(!memcmp(model.received.data(),expected,sizeof(expected)) && model.starts==2);
 unsigned entered=model.enters;
 uint8_t longData[64];assert(i9100_touch_bus_read(&bus,0x1234,longData,sizeof(longData))==0 && model.enters==entered);
 model.nacksRemaining=1;
 assert(i9100_touch_bus_read(&bus,0x1234,data,1)==0 && data[0]==0xa6 && !model.nacksRemaining);
 uint8_t byte=0x38;assert(i9100_touch_bus_write(&bus,0x2345,&byte,1)==0 && model.memory[0x2345]==byte);
 model.nackAddress=true;data[0]=0xc1;
 assert(i9100_touch_bus_read(&bus,0x1234,data,1)==I9100_TOUCH_NACK && data[0]==0xc1 && bus.last_phase==2 && bus.last_register==0x1234);
 model.nackAddress=false;model.stuckClock=true;unsigned waits=model.waits;
 assert(i9100_touch_bus_read(&bus,0,data,1)==I9100_TOUCH_TIMEOUT && model.waits-waits<100);
 model.stuckClock=false;assert(!model.guardDepth && model.enters==model.leaves);i9100_touch_bus_fini(&bus);assert(!bus.configured);
 for(unsigned region=0;region<2;region++)for(unsigned i=0;i<1024;i++) {
  if(region==0 && i==0x24/4)assert((model.regs[region][i]&~12U)==(initial[region][i]&~12U));
  else if(region==1 && i==0xc04/4)continue;
  else assert(model.regs[region][i]==initial[region][i]);
 }
 puts("GPIO I2C: open-drain only, exact pin masks, recovery, repeated START, LE register pointer, ACK/NACK, bounded stretch, transient NACK retry, balanced scheduling guards and restoration passed");
}
static void wire_checks() {
 LeoHIDPacket packet;assert(leo_touch_make_hid_packet(479,799,1,false,100,7,&packet));
 assert(sizeof(packet)==204 && packet.header.eventCount==2 && packet.header.timeStamp==100 && packet.header.senderID==7);
 assert(packet.hand.x==65536 && packet.hand.y==65536 && packet.finger.x==65536 && packet.finger.y==65536);
 assert(packet.hand.type==11 && packet.finger.type==11 && packet.finger.depth==1 && packet.finger.pressure==65536);
 assert((packet.finger.eventMask&3)==3 && (packet.finger.options&0x20000));
 assert(leo_touch_make_hid_packet(100,200,1,true,200,7,&packet) && packet.finger.eventMask==4);
 assert(leo_touch_make_hid_packet(100,200,0,true,300,7,&packet) && !(packet.finger.options&0x30000) && !packet.finger.pressure);
 assert(!leo_touch_make_hid_packet(100,200,0,false,400,7,&packet));
 assert(!leo_touch_make_hid_packet(480,0,1,false,400,7,&packet));
 puts("Native HID: 204-byte ABI, normalized axes, real sender/time and down/move/up flags passed");
}
static void home_checks() {
 I9100HomeState s;i9100_home_reset(&s);uint64_t now=1000000000ULL;
 i9100_home_sample(&s,1,now);i9100_home_sample(&s,1,now+=1000000000ULL);
 assert(!s.armed && !s.count); // Held during boot/open is not a fresh press.
 i9100_home_sample(&s,0,now+=20000000);i9100_home_sample(&s,0,now+=20000000);
 assert(s.armed && !s.count);
 i9100_home_sample(&s,1,now+=20000000);i9100_home_sample(&s,0,now+=5000000);
 i9100_home_sample(&s,0,now+=20000000);assert(!s.count); // Bounce rejected.
 i9100_home_sample(&s,1,now+=20000000);i9100_home_sample(&s,1,now+=20000000);
 assert(s.count==1 && s.edges[0].down==1);
 uint64_t pressed=s.edges[0].timestamp;
 for(unsigned n=0;n<50;n++)i9100_home_sample(&s,1,now+=20000000);
 assert(s.count==1); // Real hold, no synthetic repeat or release.
 i9100_home_sample(&s,0,now+=20000000);i9100_home_sample(&s,0,now+=20000000);
 assert(s.count==2 && !s.edges[1].down && s.edges[1].timestamp-pressed>=1000000000ULL);
 for(unsigned n=0;n<20;n++){
  unsigned down=n%2==0;i9100_home_sample(&s,down,now+=20000000);i9100_home_sample(&s,down,now+=20000000);
 }
 assert(s.count==16 && s.overflows); // Queue pressure keeps a bounded, ordered prefix.
 for(unsigned n=0;n<16;n++)assert(s.edges[n].down==(n%2==0));
 s.head=(s.head+1)&15U;s.count--;
 i9100_home_sample(&s,1,now+=20000000);i9100_home_sample(&s,1,now+=20000000);
 assert(s.count==16 && s.edges[0].down);
 I9100HomePacket packet;
 assert(i9100_home_packet(1,123,77,&packet));
 assert(sizeof(packet)==52 && packet.header.eventCount==1 && packet.header.attributeLength==0);
 assert(packet.header.timeStamp==123 && packet.header.senderID==77 && packet.key.size==24);
 assert(packet.key.type==3 && packet.key.usagePage==12 && packet.key.usage==0x40 && packet.key.down==1);
 assert(packet.key.depth==0 && !packet.key.reserved[0] && !packet.key.reserved[1] && !packet.key.reserved[2]);
 assert(i9100_home_packet(0,456,77,&packet) && packet.key.down==0);
 assert(!i9100_home_packet(2,456,77,&packet) && !i9100_home_packet(1,0,77,&packet));
 puts("Home: GPIO debounce, boot-held suppression, real hold/release timestamps, bounded backpressure and native52B Consumer 0c/40 ABI passed");
}
int main() { protocol_checks();gpio_checks();wire_checks();home_checks();observation_checks();return 0; }
