/* SPDX-License-Identifier: GPL-2.0-only
 * mXT224/224E: CRC-checked object discovery, volatile wake/enable and T9 input.
 * One primary finger feeds the existing iOS7 digitizer queue. Other contacts
 * are tracked so releasing the primary never transfers a swipe to another.
 */
#include "i9100_touch.h"
#include <string.h>
#if defined(BOARD_CONFIG_EXYNOS4210_I9100) || defined(I9100_TOUCH_HOST_TEST)
static uint16_t le16(const uint8_t *p)
{ return (uint16_t)(p[0]|((uint16_t)p[1]<<8)); }
static void inc(uint32_t *p) { if(*p!=UINT32_MAX)++*p; }
static int fail(struct i9100_touch_state *s,int rc)
{ s->last_result=rc;inc(&s->errors);return rc; }
static uint32_t crc24(const uint8_t *data,unsigned bytes)
{
 uint32_t crc=0;unsigned i;
 for(i=0;i<bytes;i+=2) {
  uint32_t word=data[i];if(i+1<bytes)word|=(uint32_t)data[i+1]<<8;
  crc=(crc<<1)^word;if(crc&0x1000000U)crc^=0x80001bU;
 }
 return crc&0xffffffU;
}
static int set_verified(struct i9100_touch_state *s,uint16_t reg,uint8_t value)
{
 uint8_t check=0;int rc=s->io.write(s->io.cookie,reg,&value,1);
 if(!rc)rc=s->io.read(s->io.cookie,reg,&check,1);
 if(!rc && check!=value)rc=I9100_TOUCH_PROTOCOL;
 return rc;
}
int i9100_touch_init(struct i9100_touch_state *s,const struct i9100_touch_io *io)
{
 uint8_t cfg[22],power[3];unsigned objects,bytes,i,report=1;int rc;
 uint16_t power_size=0,command_size=0;
 if(!s || !io || !io->read || !io->write || !io->changed)return I9100_TOUCH_ARGUMENT;
 memset(s,0,sizeof(*s));s->io=*io;s->stage=1;
 rc=io->read(io->cookie,0,s->info,7);if(rc)return fail(s,rc);
 s->id_word=(uint32_t)s->info[0]|((uint32_t)s->info[1]<<8)|((uint32_t)s->info[2]<<16)|((uint32_t)s->info[3]<<24);
 if((s->info[0]!=0x80 && s->info[0]!=0x81) || !s->info[4] || !s->info[5] ||
    !s->info[6] || s->info[6]>I9100_TOUCH_OBJECT_CAP)return fail(s,I9100_TOUCH_PROTOCOL);
 objects=s->info[6];bytes=7U+objects*6U;
 rc=io->read(io->cookie,7,s->info+7,objects*6U+3U);if(rc)return fail(s,rc);
 if(crc24(s->info,bytes)!=((uint32_t)s->info[bytes]|((uint32_t)s->info[bytes+1]<<8)|((uint32_t)s->info[bytes+2]<<16)))return fail(s,I9100_TOUCH_CRC);
 s->stage=2;
 for(i=0;i<objects;i++) {
  const uint8_t *o=s->info+7+i*6U;
  unsigned size=(unsigned)o[3]+1U,instances=(unsigned)o[4]+1U,count=(unsigned)o[5]*instances;
  uint16_t address=le16(o+1);
  if(!address || address<bytes+3U || (uint32_t)address+size*instances>65536U ||
     report+count>255U)return fail(s,I9100_TOUCH_PROTOCOL);
  if(o[0]==5) {
   if(s->message_address || instances!=1 || size<7 || size>9)return fail(s,I9100_TOUCH_PROTOCOL);
   s->message_address=address;s->message_size=(uint16_t)size;
  } else if(o[0]==6) {
   if(s->command_address || instances!=1 || size<6)return fail(s,I9100_TOUCH_PROTOCOL);
   s->command_address=address;command_size=(uint16_t)size;
   s->command_report=count?(uint8_t)report:0;
  } else if(o[0]==7) {
   if(s->power_address || instances!=1 || size<3)return fail(s,I9100_TOUCH_PROTOCOL);
   s->power_address=address;power_size=(uint16_t)size;
  } else if(o[0]==9) {
   if(s->touch_address || instances!=1 || size<22 || !count || count>32)return fail(s,I9100_TOUCH_PROTOCOL);
   s->touch_address=address;s->touch_size=(uint16_t)size;
   s->first_report=(uint8_t)report;s->report_count=(uint8_t)count;
  }
  report+=count;
 }
 if(!s->message_address || !command_size || !power_size || !s->touch_address)return fail(s,I9100_TOUCH_PROTOCOL);
 s->stage=3;
 rc=io->read(io->cookie,s->touch_address,cfg,sizeof(cfg));if(rc)return fail(s,rc);
 if(!cfg[3] || !cfg[4])return fail(s,I9100_TOUCH_PROTOCOL); /* No sensor matrix configured. */
 s->orientation=cfg[9];
 {
  uint16_t x=le16(cfg+18),y=le16(cfg+20),swap;
  /* maXTouch defines range 0 as 1023. ORIENT applies in the controller;
   * only the reported axis ranges and 10/12-bit packing are swapped here. */
  if(!x)x=1023;if(!y)y=1023;
  if(x>4095 || y>4095)return fail(s,I9100_TOUCH_PROTOCOL);
  if(s->orientation&1U){swap=x;x=y;y=swap;}
  s->x_max=x;s->y_max=y;s->x_drop=x<1024?2:0;s->y_drop=y<1024?2:0;
 }
 rc=io->read(io->cookie,s->power_address,power,sizeof(power));if(rc)return fail(s,rc);
 if(!power[0] || !power[1]) {
  /* Samsung U1 awake defaults; volatile only, never T6 BACKUPNV. */
  power[0]=48;power[1]=255;power[2]=25;
  rc=io->write(io->cookie,s->power_address,power,sizeof(power));if(rc)return fail(s,rc);
 }
 if(!cfg[14]) {
  rc=set_verified(s,(uint16_t)(s->touch_address+14),1);if(rc)return fail(s,rc);
 }
 rc=set_verified(s,s->touch_address,(uint8_t)(cfg[0]|0x83U));if(rc)return fail(s,rc);
 /* Calibrate once after enabling, then request actual controller reports.
  * Do not reset, back up, flash firmware, or replace its saved board tuning. */
 {
  uint8_t one=1;
  rc=io->write(io->cookie,(uint16_t)(s->command_address+2),&one,1);if(rc)return fail(s,rc);
  rc=io->write(io->cookie,(uint16_t)(s->command_address+3),&one,1);if(rc)return fail(s,rc);
 }
 s->ready=1;s->stage=4;s->last_result=0;return 0;
}
static unsigned contacts(uint32_t mask)
{ unsigned n=0;while(mask){n+=mask&1U;mask>>=1;}return n; }
static int emit(struct i9100_touch_state *s,unsigned down,const uint8_t *message,unsigned bytes,struct i9100_touch_report *out)
{
 struct i9100_touch_report result;
 memset(&result,0,sizeof(result));inc(&s->sequence);inc(&s->packets);
 result.sequence=s->sequence;result.x=s->last_x;result.y=s->last_y;
 result.down=(uint8_t)down;result.contacts=(uint8_t)contacts(s->active_mask);
 memcpy(result.raw,message,bytes);
 s->last_contacts=result.contacts;s->last_result=0;*out=result;return 1;
}
int i9100_touch_decode(struct i9100_touch_state *s,const uint8_t *message,uint32_t bytes,
                       struct i9100_touch_report *out)
{
 unsigned id,status,index;uint32_t bit,prior;int down,release;
 if(!s || !message || !out || !s->ready || bytes!=s->message_size || bytes<7 || bytes>9)return I9100_TOUCH_ARGUMENT;
 id=message[0];status=message[1];s->last_status=status;
 if(id==0xffU){inc(&s->empty_messages);return 0;}
 if(s->command_report && id==s->command_report) {
  inc(&s->other_messages);
  /* Real controller reset/calibration invalidates its contact state. */
  if(status&(0x80U|0x10U)) {
   unsigned was_primary=s->primary;s->active_mask=0;s->primary=0;s->last_contacts=0;
   if(was_primary)return emit(s,0,message,bytes,out);
  }
  return 0;
 }
 if(id<s->first_report || id>=(unsigned)s->first_report+s->report_count){inc(&s->other_messages);return 0;}
 index=id-s->first_report;bit=1U<<index;prior=s->active_mask;
 release=!!(status&(0x20U|0x02U)); /* RELEASE or SUPPRESS */
 down=!release && (status&0x80U) && (status&(0x40U|0x10U|0x04U));
 if(release) {
  s->active_mask&=~bit;s->last_contacts=(uint8_t)contacts(s->active_mask);
  if(s->primary!=id)return 0;
  s->primary=0;
  /* Release coordinates are not required to be valid; keep last real XY. */
  return emit(s,0,message,bytes,out);
 }
 if(!down)return 0;
 {
  uint16_t x=(uint16_t)(((message[2]<<4)|(message[4]>>4))>>s->x_drop);
  uint16_t y=(uint16_t)(((message[3]<<4)|(message[4]&15U))>>s->y_drop);
  if(x>s->x_max || y>s->y_max)return fail(s,I9100_TOUCH_PROTOCOL);
  s->active_mask|=bit;s->last_contacts=(uint8_t)contacts(s->active_mask);
  if(!s->primary && !prior)s->primary=(uint8_t)id;
  if(s->primary!=id)return 0;
  s->last_x=(uint16_t)((uint32_t)x*479U/s->x_max);
  s->last_y=(uint16_t)((uint32_t)y*799U/s->y_max);
 }
 return emit(s,1,message,bytes,out);
}
int i9100_touch_poll(struct i9100_touch_state *s,struct i9100_touch_report *out)
{
 unsigned n;
 if(!s || !out)return I9100_TOUCH_ARGUMENT;
 if(!s->ready)return I9100_TOUCH_NOT_READY;
 inc(&s->polls);s->stage=5;
 for(n=0;n<16;n++) {
  uint8_t message[9];int rc=s->io.changed(s->io.cookie);
  if(rc<0)return fail(s,rc);
  if(!rc)return 0;
  rc=s->io.read(s->io.cookie,s->message_address,message,s->message_size);
  if(rc)return fail(s,rc);
  rc=i9100_touch_decode(s,message,s->message_size,out);
  if(rc)return rc;
  if(message[0]==0xffU)return 0;
 }
 return 0;
}
#endif
