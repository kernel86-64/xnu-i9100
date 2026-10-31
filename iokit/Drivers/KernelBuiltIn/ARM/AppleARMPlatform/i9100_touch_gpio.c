/* SPDX-License-Identifier: GPL-2.0-only
 * Open-drain I2C on the dedicated Samsung U1 touchscreen GPIOs.
 * No writes to CMU, PMIC, SD pins, other I2C devices or controller flash.
 */
#include "i9100_touch.h"
#include <string.h>
#if defined(BOARD_CONFIG_EXYNOS4210_I9100) || defined(I9100_TOUCH_HOST_TEST)
#define A_CON 0x20U
#define A_DAT 0x24U
#define A_PUD 0x28U
#define L_CON 0xc0U
#define L_DAT 0xc4U
#define L_PUD 0xc8U
#define X_CON 0xc00U
#define X_DAT 0xc04U
#define X_PUD 0xc08U
#define SDA 2U
#define SCL 3U
#define ADDRESS 0x4aU
static uint32_t rd(struct i9100_touch_bus *b,unsigned region,unsigned reg)
{ return b->io.read(b->io.cookie,region,reg); }
static void wr(struct i9100_touch_bus *b,unsigned region,unsigned reg,uint32_t value)
{ b->io.write(b->io.cookie,region,reg,value); }
static void update(struct i9100_touch_bus *b,unsigned region,unsigned reg,uint32_t mask,uint32_t bits)
{ wr(b,region,reg,(rd(b,region,reg)&~mask)|(bits&mask)); }
static void pause_us(struct i9100_touch_bus *b,unsigned us)
{ (void)b->io.delay_us(b->io.cookie,us); }
static void release_line(struct i9100_touch_bus *b,unsigned pin)
{ update(b,0,A_CON,15U<<(pin*4),0); }
static void pull_low(struct i9100_touch_bus *b,unsigned pin)
{
 update(b,0,A_DAT,1U<<pin,0);
 update(b,0,A_CON,15U<<(pin*4),1U<<(pin*4));
}
static int clock_high(struct i9100_touch_bus *b)
{
 unsigned n;
 release_line(b,SCL);
 for(n=0;n<b->io.poll_bound;n++) {
  if(rd(b,0,A_DAT)&(1U<<SCL)){pause_us(b,5);return 0;}
  pause_us(b,1);
 }
 return I9100_TOUCH_TIMEOUT;
}
static int stop(struct i9100_touch_bus *b)
{
 int rc;
 pull_low(b,SCL);pull_low(b,SDA);pause_us(b,5);
 rc=clock_high(b);release_line(b,SDA);pause_us(b,5);
 return rc;
}
static int recover(struct i9100_touch_bus *b)
{
 unsigned n;
 release_line(b,SDA);
 for(n=0;n<9;n++) {
  pull_low(b,SCL);pause_us(b,5);
  if(clock_high(b)){release_line(b,SDA);return I9100_TOUCH_TIMEOUT;}
 }
 if(stop(b))return I9100_TOUCH_TIMEOUT;
 b->recoveries++;
 return (rd(b,0,A_DAT)&12U)==12U?0:I9100_TOUCH_BUS;
}
static int start(struct i9100_touch_bus *b)
{
 release_line(b,SDA);pause_us(b,5);
 if(clock_high(b))return I9100_TOUCH_TIMEOUT;
 if(!(rd(b,0,A_DAT)&(1U<<SDA)))return I9100_TOUCH_BUS;
 pull_low(b,SDA);pause_us(b,5);pull_low(b,SCL);pause_us(b,5);
 return 0;
}
static int send(struct i9100_touch_bus *b,uint8_t value)
{
 int i,rc;
 for(i=7;i>=0;i--) {
  if(value&(1U<<i))release_line(b,SDA);else pull_low(b,SDA);
  pause_us(b,5);rc=clock_high(b);if(rc)return rc;
  pull_low(b,SCL);pause_us(b,5);
 }
 release_line(b,SDA);pause_us(b,5);
 rc=clock_high(b);if(rc)return rc;
 rc=(rd(b,0,A_DAT)&(1U<<SDA))?I9100_TOUCH_NACK:0;
 pull_low(b,SCL);pause_us(b,5);
 return rc;
}
static int receive(struct i9100_touch_bus *b,uint8_t *value,int ack)
{
 unsigned i;uint8_t byte=0;int rc;
 release_line(b,SDA);
 for(i=0;i<8;i++) {
  pause_us(b,5);rc=clock_high(b);if(rc)return rc;
  byte=(uint8_t)((byte<<1)|!!(rd(b,0,A_DAT)&(1U<<SDA)));
  pull_low(b,SCL);pause_us(b,5);
 }
 if(ack)pull_low(b,SDA);else release_line(b,SDA);
 pause_us(b,5);rc=clock_high(b);if(rc)return rc;
 pull_low(b,SCL);pause_us(b,5);release_line(b,SDA);
 *value=byte;return 0;
}
static int begin_transfer(struct i9100_touch_bus *b,uint16_t reg,uint32_t bytes)
{
 b->last_register=reg;b->last_phase=1;
 /* Keep short GPIO transactions on the current thread. IRQs stay enabled;
  * lengthy startup info-block reads do not hold off thread scheduling. */
 if(bytes<=32U && b->io.enter_transfer){b->io.enter_transfer(b->io.cookie);return 1;}
 return 0;
}
static int finish(struct i9100_touch_bus *b,int rc,int guarded)
{
 int end;
 if(!rc)b->last_phase=8;
 end=stop(b);if(!rc)rc=end;
 if(rc)(void)recover(b);else b->last_phase=0;
 b->last_error=rc;b->transfers++;
 if(guarded)b->io.leave_transfer(b->io.cookie);
 return rc;
}
int i9100_touch_bus_read(void *cookie,uint16_t reg,uint8_t *out,uint32_t bytes)
{
 struct i9100_touch_bus *b=cookie;uint32_t i,attempt;int rc;
 if(!b || !b->configured || !out || !bytes || bytes>I9100_TOUCH_INFO_BYTES || (uint32_t)reg+bytes>65536U)return I9100_TOUCH_ARGUMENT;
 for(attempt=0;attempt<2;attempt++) {
  int guarded=begin_transfer(b,reg,bytes);
  rc=start(b);
  if(!rc){b->last_phase=2;rc=send(b,ADDRESS<<1);}
  if(!rc){b->last_phase=3;rc=send(b,(uint8_t)reg);}
  if(!rc){b->last_phase=4;rc=send(b,(uint8_t)(reg>>8));}
  if(!rc){b->last_phase=5;rc=start(b);}
  if(!rc){b->last_phase=6;rc=send(b,(ADDRESS<<1)|1U);}
  if(!rc)b->last_phase=7;
  for(i=0;i<bytes && !rc;i++)rc=receive(b,out+i,i+1U<bytes);
  rc=finish(b,rc,guarded);
  /* A prefix NACK consumed no report. Partial reads/timeouts are not replayed. */
  if(rc!=I9100_TOUCH_NACK)break;
  pause_us(b,20);
 }
 return rc;
}
int i9100_touch_bus_write(void *cookie,uint16_t reg,const uint8_t *data,uint32_t bytes)
{
 struct i9100_touch_bus *b=cookie;uint32_t i;int rc,guarded;
 if(!b || !b->configured || !data || !bytes || bytes>32U || (uint32_t)reg+bytes>65536U)return I9100_TOUCH_ARGUMENT;
 guarded=begin_transfer(b,reg,bytes);rc=start(b);
 if(!rc){b->last_phase=2;rc=send(b,ADDRESS<<1);}
 if(!rc){b->last_phase=3;rc=send(b,(uint8_t)reg);}
 if(!rc){b->last_phase=4;rc=send(b,(uint8_t)(reg>>8));}
 if(!rc)b->last_phase=7;
 for(i=0;i<bytes && !rc;i++)rc=send(b,data[i]);
 return finish(b,rc,guarded);
}

int i9100_touch_bus_changed(void *cookie)
{
 struct i9100_touch_bus *b=cookie;
 if(!b || !b->configured)return I9100_TOUCH_NOT_READY;
 return !(rd(b,1,X_DAT)&(1U<<4));
}
int i9100_touch_bus_init(struct i9100_touch_bus *b,const struct i9100_touch_gpio_io *io)
{
 unsigned i;
 if(!b || !io || !io->read || !io->write || !io->delay_us || !io->poll_bound || io->poll_bound>1000U || (!!io->enter_transfer != !!io->leave_transfer))return I9100_TOUCH_ARGUMENT;
 memset(b,0,sizeof(*b));b->io=*io;
 for(i=0;i<3;i++){b->saved_a[i]=rd(b,0,A_CON+i*4);b->saved_l[i]=rd(b,1,L_CON+i*4);}
 b->saved_x[0]=rd(b,1,X_CON);b->saved_x[1]=rd(b,1,X_PUD);
 b->configured=1;
 /* Only the dedicated TSP power enable is driven high. */
 update(b,1,L_DAT,1U<<3,1U<<3);
 update(b,1,L_CON,15U<<12,1U<<12);
 update(b,1,L_PUD,3U<<6,0);
 update(b,1,X_CON,15U<<16,0); /* Poll CHG as input, no IRQ setup. */
 update(b,1,X_PUD,3U<<8,0);
 release_line(b,SDA);release_line(b,SCL);
 update(b,0,A_PUD,15U<<4,15U<<4);
 /* Samsung U1 uses 70ms rail settle + 40ms controller startup. */
 pause_us(b,70000);pause_us(b,40000);
 b->last_error=recover(b);
 return b->last_error;
}
void i9100_touch_bus_fini(struct i9100_touch_bus *b)
{
 if(!b || !b->configured)return;
 (void)stop(b);
 update(b,0,A_DAT,12U,b->saved_a[1]);
 update(b,0,A_PUD,15U<<4,b->saved_a[2]);
 update(b,0,A_CON,255U<<8,b->saved_a[0]);
 update(b,1,X_PUD,3U<<8,b->saved_x[1]);
 update(b,1,X_CON,15U<<16,b->saved_x[0]);
 update(b,1,L_DAT,1U<<3,b->saved_l[1]);
 update(b,1,L_PUD,3U<<6,b->saved_l[2]);
 update(b,1,L_CON,15U<<12,b->saved_l[0]);
 b->configured=0;
}
#endif
