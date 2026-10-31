/* Host regression checks. MMIO emulation tests protocol/error ordering;
 * it cannot validate physical clocks, power, signal integrity or a real mount. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "i9100_sdmmc.h"
#include "fat_locator.h"

struct host {
 uint8_t regs[256], sector[512], volume[512];
 unsigned pos, reads, stops, fifo_reads, lba, min_div, corrupt_div;
 int has_volume;
 int error, once, unstable, sdsc;
};
static uint32_t get32(const uint8_t *p)
{ return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24; }
static void put16(uint8_t *p, uint16_t v)
{ p[0]=(uint8_t)v; p[1]=(uint8_t)(v>>8); }
static void put32(uint8_t *p, uint32_t v)
{ put16(p,(uint16_t)v); put16(p+2,(uint16_t)(v>>16)); }
static uint32_t hr32(void *o, unsigned reg) {
 struct host *h=o;
 if (reg==0x20) {
  uint32_t value=get32((h->has_volume && h->lba==2048 ? h->volume : h->sector)+h->pos);
  if (!h->pos && h->corrupt_div && (h->regs[0x2d]<h->corrupt_div)) value^=0x20U;
  if (!h->pos && h->unstable && h->reads>1) value^=1;
  h->pos+=4; h->fifo_reads++;
  if (h->pos==512) put32(h->regs+0x30,2U | (h->error==3 ? 1U<<21 : 0));
  return value;
 }
 return get32(h->regs+reg);
}
static void hw32(void *o, unsigned reg, uint32_t v) {
 struct host *h=o;
 if (reg==0x30) put32(h->regs+reg,get32(h->regs+reg)&~v);
 else put32(h->regs+reg,v);
}
static uint16_t hr16(void *o, unsigned reg) {
 struct host *h=o;
 return (uint16_t)(h->regs[reg] | h->regs[reg+1]<<8);
}
static void hw16(void *o, unsigned reg, uint16_t value) {
 struct host *h=o;
 put16(h->regs+reg,value);
 if (reg==0x2c && (value&1)) h->regs[reg]|=2;
 if (reg!=0x0e) return;
 unsigned cmd=value>>8;
 put32(h->regs+0x10,0);
 put32(h->regs+0x30,1);
 switch(cmd) {
 case 8: put32(h->regs+0x10,0x1aa); break;
 case 55: put32(h->regs+0x10,0x20); break;
 case 41: put32(h->regs+0x10,h->sdsc?0x80ff8000U:0xc0ff8000U); break;
 case 3: put32(h->regs+0x10,0x12340000); break;
 case 9:
  if (h->sdsc) {
   /* C_SIZE=1023, C_SIZE_MULT=5, READ_BL_LEN=9 -> 131072 sectors. */
   put32(h->regs+0x14,(1023U<<22)|(5U<<7));
   put32(h->regs+0x18,9U<<8); put32(h->regs+0x1c,0);
  } else {
   put32(h->regs+0x14,127U<<8);
   put32(h->regs+0x18,0); put32(h->regs+0x1c,1U<<22);
  }
  break;
 case 12: h->stops++; break;
 case 13: put32(h->regs+0x10,0x900); break;
 case 17:
  h->reads++; h->pos=0;
  h->lba=get32(h->regs+8);if(h->sdsc)h->lba>>=9;
  put32(h->regs+0x30,1U|32U);
  if (!h->once || h->reads==1) {
   if (h->error==1) put32(h->regs+0x30,1U|32U|2U|(1U<<21));
   if (h->error==2) put32(h->regs+0x30,1U|32U|(1U<<17));
   if (h->error==4) put32(h->regs+0x10,1U<<31);
   if (h->error==5) put32(h->regs+0x30,1U); /* no buffer-ready */
  }
  if(h->min_div && h->regs[0x2d]<h->min_div)put32(h->regs+0x30,1U|32U|2U|(1U<<21));
  break;
 default: break;
 }
}
static uint8_t hr8(void *o, unsigned reg) { return ((struct host *)o)->regs[reg]; }
static void hw8(void *o, unsigned reg, uint8_t value) {
 struct host *h=o;
 h->regs[reg]=reg==0x2f?0:value;
 if(reg==0x2f) put32(h->regs+0x24,0);
}
static int hdelay(void *o, uint32_t us) { (void)o; (void)us; return 1; }
static void host_setup(struct host *h, struct i9100_sd_card *card) {
 memset(h,0,sizeof(*h));
 for(unsigned i=0;i<512;i++) h->sector[i]=(uint8_t)(i*7U);
 h->sector[510]=0x55; h->sector[511]=0xaa;
 struct i9100_sd_io io={h,hr32,hw32,hr16,hw16,hr8,hw8,hdelay,0,8};
 i9100_sd_init(card,&io);
 card->ready=1; card->sdhc=1; card->sectors=131072; card->rca=0x1234;
}
static void check_sd(void) {
 struct host h; struct i9100_sd_card card; uint8_t data[514];
 host_setup(&h,&card); memset(data,0xa5,sizeof(data));
 assert(i9100_sd_read512(&card,7,data+1)==0);
 assert(!memcmp(data+1,h.sector,512) && data[0]==0xa5 && data[513]==0xa5);
 assert(get32(h.regs+8)==7);
 assert(i9100_sd_read_multi(&card,0,data,0)==I9100_SD_ARG);
 assert(i9100_sd_read_multi(&card,131071,data,2)==I9100_SD_ARG);
 assert(i9100_sd_read512(&card,UINT64_MAX,data)==I9100_SD_ARG);
 card.ready=0; assert(i9100_sd_read512(&card,0,data)==I9100_SD_NODEV);
 for(int error=1;error<=5;error++) {
  host_setup(&h,&card); h.error=error;
  assert(i9100_sd_read512(&card,0,data)!=0);
  assert(h.reads==3 && h.stops==3);
  if(error==1 || error==2 || error==4 || error==5) assert(!h.fifo_reads);
 }
 host_setup(&h,&card); h.error=1; h.once=1;
 assert(i9100_sd_read512(&card,0,data)==0 && h.reads==2 && h.stops==1);
 for(int sdsc=0;sdsc<=1;sdsc++) {
  host_setup(&h,&card); h.sdsc=sdsc;
  assert(i9100_sd_probe(&card)==0 && card.ready && card.sectors==131072 && h.reads==5 && card.clock_div==2);
  assert(get32(h.regs+0x80)==0xc0004120U && get32(h.regs+0x84)==0x80808080U);
  if(sdsc) {
   assert(!card.sdhc && i9100_sd_read512(&card,3,data)==0);
   assert(get32(h.regs+8)==1536);
  }
 }
 host_setup(&h,&card);h.min_div=4;
 assert(i9100_sd_probe(&card)==0 && card.clock_div==4);
 host_setup(&h,&card);h.corrupt_div=4;
 assert(i9100_sd_probe(&card)==0 && card.clock_div==4);
 host_setup(&h,&card);assert(i9100_sd_probe(&card)==0);h.min_div=8;
 assert(i9100_sd_read512(&card,3,data)==0 && card.clock_div==8 && card.speed_fallbacks==2);
 host_setup(&h,&card);h.has_volume=1;
 h.sector[450]=0x0c;put32(h.sector+454,2048);put32(h.sector+458,129024);
 for(unsigned i=0;i<512;i++)h.volume[i]=(uint8_t)(i*11U+0x37U);
 assert(i9100_sd_probe(&card)==0 && card.clock_div==2 && h.reads==8);
 host_setup(&h,&card); h.sector[510]=0xaf; h.sector[511]=0x10;
 assert(i9100_sd_probe(&card)!=0 && !card.ready);
 host_setup(&h,&card); h.unstable=1;
 assert(i9100_sd_probe(&card)!=0 && !card.ready);
 puts("SD: error + completion, CRC retries, timeout, R1, range, alignment, SDHC/SDSC, raw MBR/VBR, transfer-clock verification/fallback checks passed");
}

#define PART 2048U
#define TOTAL 129024U
#define SPF 1024U
#define DATA (PART+32U+SPF*2U)
struct disk { int fault, active; };
static void be16(uint8_t *p, unsigned v) { p[0]=(uint8_t)(v>>8);p[1]=(uint8_t)v; }
static void be32(uint8_t *p, uint32_t v) { be16(p,v>>16);be16(p+2,v); }
static void directory(uint8_t *out,const char *name,unsigned attr,unsigned cluster,unsigned bytes) {
 memcpy(out,name,11);out[11]=(uint8_t)attr;put16(out+20,(uint16_t)(cluster>>16));
 put16(out+26,(uint16_t)cluster);put32(out+28,bytes);
}
static int disk_read(void *cookie,uint64_t lba,uint8_t out[512]) {
 struct disk *d=cookie; memset(out,0,512);
 if(d->fault==8 && lba==DATA) return -123;
 if(lba==0) {
  out[510]=0x55;out[511]=0xaa;out[450]=0x0b;
  put32(out+454,PART);put32(out+458,TOTAL);
  if(d->fault==1)out[511]=0;
 } else if(lba==PART) {
  put16(out+11,512);out[13]=1;put16(out+14,32);out[16]=2;
  put32(out+28,PART);put32(out+32,TOTAL);put32(out+36,SPF);put32(out+44,2);
  if(d->active)put16(out+40,0x81);
  out[510]=0x55;out[511]=0xaa;
 } else if(lba==PART+32 || lba==PART+32+SPF) {
  put32(out,0x0ffffff8U);put32(out+4,0x0fffffffU);
  put32(out+8,0x0fffffffU);put32(out+12,0x0fffffffU);
  put32(out+16,6);for(unsigned c=6;c<12;c++)put32(out+c*4,c+1);
  put32(out+12*4,0x0fffffffU);
  if(d->fault==3 && lba==PART+32+SPF)put32(out+6*4,9);
  if(d->active && lba==PART+32)put32(out+6*4,9);
  if(d->fault==4)put32(out+6*4,4);
 } else if(lba==DATA) {
  if(d->fault!=5)directory(out,"IOS7       ",0x10,3,0);
  if(d->fault==6)directory(out+32,"IOS7       ",0x10,3,0);
 } else if(lba==DATA+1) directory(out,"ROOTFS  HFS",0x20,4,4096);
 else if(lba==DATA+5 || lba==DATA+9) {
  be16(out,0x482b);be16(out+2,4);be32(out+4,0x100);
  be32(out+40,512);be32(out+44,8);be32(out+48,1);
  if(d->fault==7)out[0]=0xc8;
  if(d->fault==9 && lba==DATA+9)be32(out+44,7);
 }
 if(d->fault==2) {
  for(unsigned i=0;i<511;i++)out[i]=(uint8_t)((out[i]<<1)|(out[i+1]>>7));
  out[511]<<=1;
 }
 return 0;
}
static void check_fat(void) {
 struct disk d={0,0};struct fl32_work w;struct fl32_image image;struct fl32_extent ext[8];
 struct fl32_io io={&d,disk_read,PART+TOTAL};struct fl32_limits lim={1000,128,0};
 assert(fl32_locate(&io,&lim,&w,ext,8,&image)==0 && image.extent_count==2 && image.file_bytes==4096);
 uint64_t physical;uint32_t run;
 assert(fl32_translate(&image,ext,8,2,&physical,&run)==0 && physical==DATA+5 && run==6);
 assert(fl32_translate(&image,ext,8,8,&physical,&run)!=0);
 const int expected[]={0,FL32_FORMAT,FL32_FORMAT,FL32_MIRROR,FL32_CHAIN,FL32_NOT_FOUND,FL32_DUPLICATE,FL32_HFS,FL32_IO,FL32_HFS};
 for(int fault=1;fault<=9;fault++) {
  d.fault=fault;memset(&image,0xa5,sizeof(image));
  assert(fl32_locate(&io,&lim,&w,ext,8,&image)==expected[fault]);
  assert(!image.magic && !image.extent_count);
  if(fault==8)assert(w.backend_error==-123);
 }
 d.fault=0;d.active=1;
 assert(fl32_locate(&io,&lim,&w,ext,8,&image)==0);
 assert(fl32_locate(&io,&lim,&w,ext,1,&image)==FL32_LIMIT);
 lim.read_budget=1;
 assert(fl32_locate(&io,&lim,&w,ext,8,&image)==FL32_LIMIT);
 puts("FAT/HFS: fragmented image, mirror/active FAT, cycle, duplicate/missing directory, shifted/corrupt headers, I/O failure, limits passed");
}
int main(void) { check_sd();check_fat();return 0; }
