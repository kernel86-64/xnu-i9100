/* GPU31: original Exynos4210 bring-up around Mesa/Linux Lima register/command
 * encodings and Mesa's clear shader. No Linux DRM ABI or Apple GPU impersonation.
 * References/pinned versions are recorded in GPU27_MALI_BRINGUP_20261031.md.
 *
 * Copyright (c) 2011-2013 Luc Verhaegen <libv@skynet.be>
 * Copyright (c) 2017-2019 Lima Project
 * Copyright (c) 2013 Ben Brewer (ben.brewer@codethink.co.uk)
 * Copyright (c) 2013 Connor Abbott (connor@abbott.cx)
 * Copyright 2017-2019 Qiang Yu <yuq825@gmail.com>
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */
#include "i9100_mali.h"
#include "i9100_mali_shaders.h"
volatile struct i9100_mali_status i9100_mali_observation;
#define GPU I9100_MALI_GPU
#define CMU I9100_MALI_CMU
#define PMU I9100_MALI_PMU
#define SRC 0xc22cU
#define DIV 0xc52cU
#define DIVSTAT 0xc62cU
#define GATE 0xc92cU
#define DOMAIN 0x3c60U
#define GP_ERRORS ((1U<<2)|(1U<<5)|(1U<<6)|(1U<<9)|(1U<<10)|(1U<<11)|(1U<<13)|(1U<<14)|(7U<<20))
#define PP_ERRORS ((15U<<2)|(15U<<8))
static const unsigned pp[4]={0x8000,0xa000,0xc000,0xe000};
static const unsigned mmu[5]={0x3000,0x4000,0x5000,0x6000,0x7000};
static uint32_t rd(const struct i9100_mali_io *io,unsigned region,unsigned off)
{ return io->read(io->cookie,region,off); }
static void wr(const struct i9100_mali_io *io,unsigned region,unsigned off,uint32_t v)
{ io->write(io->cookie,region,off,v); }
static void update(const struct i9100_mali_io *io,unsigned r,unsigned o,uint32_t mask,uint32_t v)
{ wr(io,r,o,(rd(io,r,o)&~mask)|(v&mask)); }
static int wait_bits(const struct i9100_mali_io *io,unsigned r,unsigned o,
                     unsigned mask,unsigned value,unsigned attempts)
{
 for(unsigned n=0;n<attempts;n++) {
  if((rd(io,r,o)&mask)==value)return 1;
  io->delay_us(io->cookie,10);
 }
 return 0;
}
static int pmic_set(const struct i9100_mali_io *io,unsigned reg,uint8_t value)
{
 uint8_t check;
 return io->pmic_write(io->cookie,reg,value) &&
        io->pmic_read(io->cookie,reg,&check) && check==value;
}
static int reset_cores(const struct i9100_mali_io *io)
{
 wr(io,GPU,0x2c,0); wr(io,GPU,0x28,1U<<19); wr(io,GPU,0x20,1U<<10);
 if(!wait_bits(io,GPU,0x24,1U<<19,1U<<19,100))return 0;
 wr(io,GPU,0x28,0x7fffff);
 for(unsigned n=0;n<4;n++) {
  wr(io,GPU,pp[n]+0x1028,0); wr(io,GPU,pp[n]+0x1020,0x1fff);
  wr(io,GPU,pp[n]+0x100c,1U<<7);
  if(!wait_bits(io,GPU,pp[n]+0x1020,0x1fff,1U<<12,100) ||
     !wait_bits(io,GPU,pp[n]+0x1008,1,0,100))return 0;
  wr(io,GPU,pp[n]+0x1024,0x1fff);
 }
 return 1;
}
static int flush_l2(const struct i9100_mali_io *io)
{
 wr(io,GPU,0x1010,1);
 return wait_bits(io,GPU,0x1008,1,0,100);
}
static int stop_bus(const struct i9100_mali_io *io)
{
 wr(io,GPU,0x2c,0);wr(io,GPU,0x20,1U<<9);
 for(unsigned i=0;i<4;i++) {
  wr(io,GPU,pp[i]+0x1028,0);wr(io,GPU,pp[i]+0x100c,1);
 }
 int ok=wait_bits(io,GPU,0x68,1U<<2,1U<<2,100);
 for(unsigned i=0;i<4;i++)
  if(!wait_bits(io,GPU,pp[i]+0x1008,1U<<4,1U<<4,100))ok=0;
 return ok;
}
static unsigned fault(const struct i9100_mali_io *io)
{
 unsigned value=0;
 for(unsigned n=0;n<5;n++)if((rd(io,GPU,mmu[n]+4)&2) || rd(io,GPU,mmu[n]+0x14))value|=1U<<n;
 return value;
}
static void build_triangle(volatile uint32_t *b,unsigned index)
{
 unsigned start=0x2300+index*0xc0,vs=0x2500+index*0x80;
 unsigned attrib=0x2640+index*0x10,vertices=0x2700+index*0x40;
 unsigned rsw=0x2880+index*0x40;
 const uint32_t plbu[38]={
  0x200,0x1000010b,0,0x1000010c,0,0x10000109,1,0x30000000,
  I9100_MALI_VA+0x2100,0x28000001,
  0,0x10000107,0x41800000,0x10000108,0,0x10000105,0x41800000,0x10000106,
  0x10002,0x60000000,0x2200,0x1000010b,
  I9100_MALI_VA+rsw,0x80000000|((I9100_MALI_VA+0xa080)>>4),
  15U<<15,0x70000000|(15U<<13),0,0x1000010a,
  0,0x1000010e,0x3f800000,0x1000010f,
  3U<<24,4U<<16,0x10001,0x60000000,0,0x50000000};
 for(unsigned n=0;n<38;n++)b[start/4+n]=plbu[n];
 const uint32_t commands[24]={
  0x28000,0x50000000,1,0x50000000,
  I9100_MALI_VA+0x2680,0x30020000,
  I9100_MALI_VA+0x2600,0x40020000,0x100400,0x10000040,
  0,0x10000042,3,0x10000041,
  I9100_MALI_VA+attrib,0x20020000,I9100_MALI_VA+0x2660,0x20020008,
  3U<<24,0,0,0x60000000,0,0x50000000};
 for(unsigned n=0;n<24;n++)b[vs/4+n]=commands[n];
 b[attrib/4]=I9100_MALI_VA+vertices;b[attrib/4+1]=0x8003;
 b[0x2660/4]=I9100_MALI_VA+0xa080;b[0x2660/4+1]=0x8020;
 /* Post-viewport x/y/z and reciprocal w. Opposite triangles, subpixel edges
  * chosen away from pixel centres; no CPU rasterization or prefilled output. */
 const uint32_t positions[2][12]={
  {0x3e800000,0x3e800000,0x3f000000,0x3f800000,
   0x41740000,0x3e800000,0x3f000000,0x3f800000,
   0x3e800000,0x41740000,0x3f000000,0x3f800000},
  {0x417c0000,0x417c0000,0x3f000000,0x3f800000,
   0x3f400000,0x417c0000,0x3f000000,0x3f800000,
   0x417c0000,0x3f400000,0x3f000000,0x3f800000}};
 for(unsigned n=0;n<12;n++)b[vertices/4+n]=positions[index][n];
 b[rsw/4+2]=0xfc3b1ad2;b[rsw/4+3]=0x3e;b[rsw/4+4]=0xffff0000;
 b[rsw/4+5]=b[rsw/4+6]=0xff000007;b[rsw/4+7]=0xffff;
 b[rsw/4+8]=0xf807;b[rsw/4+9]=(I9100_MALI_VA+0x2800+index*0x40)|5;
 b[rsw/4+13]=0x1300;
}
static void build_texture(volatile uint32_t *b)
{
 const uint32_t attributes[4]={I9100_MALI_VA+0x2c00,0x8003,I9100_MALI_VA+0x2c80,0x8001};
 const uint32_t outputs[4]={I9100_MALI_VA+0xa080,0x8020,I9100_MALI_VA+0xa180,0x8001};
 for(unsigned n=0;n<4;n++){b[0x2a00/4+n]=attributes[n];b[0x2a40/4+n]=outputs[n];}
 /* Two triangles cover the entire tile. UVs are a separate GP attribute and
  * varying; the PP samples a private linear2x2 BGRA texture at mip0. */
 const unsigned xy[6][2]={{0,0},{1,0},{0,1},{1,0},{1,1},{0,1}};
 for(unsigned v=0;v<6;v++) {
  b[0x2c00/4+v*4]=xy[v][0]?0x41800000:0;
  b[0x2c00/4+v*4+1]=xy[v][1]?0x41800000:0;
  b[0x2c00/4+v*4+2]=0x3f000000;b[0x2c00/4+v*4+3]=0x3f800000;
  b[0x2c80/4+v*4]=xy[v][0]?0x3f800000:0;
  b[0x2c80/4+v*4+1]=xy[v][1]?0x3f800000:0;
 }
 for(unsigned n=0;n<12;n++)b[0x2d00/4+n]=gpu30_vs_uv[n];
 for(unsigned n=0;n<24;n++)b[0x2d80/4+n]=b[0x2500/4+n];
 b[0x2d80/4+6]=I9100_MALI_VA+0x2d00;b[0x2d80/4+7]=0x40030000;
 b[0x2d80/4+8]=0x200800;b[0x2d80/4+10]=0x01000100;
 b[0x2d80/4+14]=I9100_MALI_VA+0x2a00;b[0x2d80/4+15]=0x20040000;
 b[0x2d80/4+16]=I9100_MALI_VA+0x2a40;b[0x2d80/4+17]=0x20040008;
 b[0x2d80/4+18]=6U<<24;
 for(unsigned n=0;n<38;n++) {
  b[0x2e00/4+n]=b[0x2300/4+n];b[0xb200/4+n]=b[0x2300/4+n];
 }
 b[0x2e00/4+22]=I9100_MALI_VA+0x2ec0;b[0x2e00/4+32]=6U<<24;
 b[0xb200/4+22]=I9100_MALI_VA+0xb0c0;b[0xb200/4+32]=6U<<24;
 for(unsigned n=0;n<16;n++) {
  b[0x2ec0/4+n]=b[0x2880/4+n];b[0xb000/4+n]=gpu30_texture_desc[n];
 }
 b[0x2ec0/4+9]=(I9100_MALI_VA+0x2f00)|6;
 b[0x2ec0/4+10]=1;b[0x2ec0/4+12]=I9100_MALI_VA+0x2f80;
 b[0x2ec0/4+13]=0x5322;b[0x2ec0/4+15]=I9100_MALI_VA+0xa180;
 for(unsigned n=0;n<16;n++)b[0xb0c0/4+n]=b[0x2ec0/4+n];
 /* Premultiplied source-over: ONE, INV_SRC_ALPHA for both RGB and alpha.
  * Unlike opaque overwrite, blending must disable pixel-kill optimization. */
 b[0xb0c0/4+2]=0xfc000000U|2|(2U<<3)|(11U<<6)|(24U<<11)|(11U<<16)|(8U<<20);
 b[0xb0c0/4+13]=0x4322;
 for(unsigned n=0;n<6;n++)b[0x2f00/4+n]=gpu30_fs_texture[n];
 b[0x2f80/4]=I9100_MALI_VA+0xb000;
}
static uint32_t texel(unsigned pattern,unsigned quadrant)
{
 static const uint32_t colors[3][4]={
  {0xffff0000,0xff00ff00,0xff0000ff,0xffffff00},
  {0xff00ffff,0xffff00ff,0xffffffff,0xff000000},
  {0x80800000,0x80008000,0x80000080,0x80402010}};
 return colors[pattern][quadrant];
}
static uint32_t source_over(uint32_t source,uint32_t destination)
{
 unsigned alpha=source>>24;uint32_t result=0;
 for(unsigned shift=0;shift<32;shift+=8) {
  unsigned channel=((source>>shift)&255)+(((destination>>shift)&255)*(255-alpha)+127)/255;
  result|=(channel>255?255:channel)<<shift;
 }
 return result;
}
static void build_arena(volatile uint32_t *b,uint32_t pa)
{
 for(unsigned n=0;n<I9100_MALI_BYTES/4;n++)b[n]=0;
 /* PD and PT are GPU-readable via the walker only, never GPU-VA mapped.
  * Commands/shader page read-only; GPU can write only its private job data. */
 b[I9100_MALI_VA>>22]=(pa+4096)|1;
 for(unsigned n=2;n<=11;n++) b[1024+n]=(pa+n*4096)|((n==2 || n==11)?3U:7U);
 volatile uint32_t *cmd=b+0x2000/4;
 const uint32_t head[12]={0x200,0x1000010b,0,0x1000010c,0,0x10000109,
                         1,0x30000000,I9100_MALI_VA+0x2100,0x28000001,0,0x50000000};
 for(unsigned n=0;n<12;n++)cmd[n]=head[n];
 for(unsigned n=0;n<8;n++)b[(0x2100/4)+n]=I9100_MALI_VA+0x3000+n*512;
 uint32_t list=0xe0000002U|(((I9100_MALI_VA+0x3000)>>3)&~0xe0000003U);
 const uint32_t stream[8]={0,0xb8000000,list,0xb0000000,0,0xbc000000,0,0};
 for(unsigned n=0;n<8;n++)b[0x2180/4+n]=stream[n];
 b[0x2200/4+8]=0xf008; b[0x2200/4+9]=I9100_MALI_VA+0x2240;
 b[0x2200/4+13]=0x100;
 const uint32_t shader[8]={0x00020425,0x0000000c,0x01e007cf,0xb0000000,
                           0x000005f5,0,0,0};
 for(unsigned n=0;n<8;n++)b[0x2240/4+n]=shader[n];
 for(unsigned n=0;n<8;n++)b[0x2600/4+n]=gpu28_vs[n];
 for(unsigned n=0;n<5;n++) {
  b[0x2800/4+n]=gpu28_fs_red[n];b[0x2840/4+n]=gpu28_fs_green[n];
 }
 build_triangle(b,0);build_triangle(b,1);
 build_texture(b);
 for(unsigned n=0xc000/4;n<I9100_MALI_BYTES/4;n++)b[n]=0x5aa5c33c;
}
static uint32_t protected_sum(volatile uint32_t *b)
{
 uint32_t sum=0x12345678;
 for(unsigned n=0;n<I9100_MALI_BYTES/4;n++)
  if(n<0x3000/4 || n>=0xb000/4) { sum=(sum<<5)|(sum>>27);sum^=b[n]+n; }
 return sum;
}
static int render(const struct i9100_mali_io *io,volatile uint32_t *b,
                  unsigned trial,volatile struct i9100_mali_status *s)
{
 s->trial=trial+1;
 unsigned textured=trial>=4,triangle=trial>=2,index=trial&1;
 unsigned pattern=textured?(trial-4)%3:0,core=textured?(trial-4)/3:0,base=pp[core];
 unsigned color=pattern==2 || trial==1?0xff402010U:trial?0xff000000U:0xffffffffU;
 if(!reset_cores(io))return -8;
 for(unsigned n=0;n<4096/4;n++)b[0x8000/4+n]=0x5aa5c33c;
 for(unsigned n=0;n<4096/4;n++)b[0xa000/4+n]=0x5aa5c33c;
 for(unsigned n=0;n<4096/4;n++)b[0x3000/4+n]=0;
 io->barrier(io->cookie);
 if(!flush_l2(io))return -10;
 s->phase=8;
 unsigned vs=textured?0x2d80:0x2500+index*0x80;
 unsigned plbu=textured?(pattern==2?0xb200:0x2e00):0x2300+index*0xc0;
 const uint32_t gp[6]={triangle?I9100_MALI_VA+vs:0,triangle?I9100_MALI_VA+vs+96:0,
                       I9100_MALI_VA+(triangle?plbu:0x2000),
                       I9100_MALI_VA+(triangle?plbu+152:0x2030),
                       I9100_MALI_VA+0x4000,I9100_MALI_VA+0x8000};
 for(unsigned n=0;n<6;n++)wr(io,GPU,n*4,gp[n]);
 wr(io,GPU,0x20,1U<<4); wr(io,GPU,0x20,triangle?3:2);
 unsigned n;
 for(n=0;n<10000;n++) {
  s->gp_irq=rd(io,GPU,0x24); s->mmu_fault=fault(io);
  if(s->mmu_fault || (s->gp_irq&GP_ERRORS))return -11;
  unsigned done=triangle?3:2;
  if((s->gp_irq&done)==done && !(rd(io,GPU,0x68)&10))break;
  io->delay_us(io->cookie,10);
 }
 if(n==10000)return -11;
 wr(io,GPU,0x28,0x7fffff);
 if(!flush_l2(io))return -10;
 if(triangle) {
  io->barrier(io->cookie);
  unsigned vertices=textured?6:3;
  for(n=0;n<1024;n++) {
   unsigned expected=0x5aa5c33c;
   if(n>=32 && n<32+vertices*4)
    expected=b[(textured?0x2c00:0x2700+index*0x40)/4+n-32];
   if(textured && n>=96 && n<120 && ((n-96)&3)<2)expected=b[0x2c80/4+n-96];
   if(b[0xa000/4+n]!=expected) {
    s->bad_offset=0xa000+n*4;s->actual=b[0xa000/4+n];return -17;
   }
  }
  s->vertices+=vertices;
 }
 s->phase=9;
 uint32_t frame[23]={0};
 frame[0]=I9100_MALI_VA+0x2180; frame[1]=I9100_MALI_VA+0x2200;
 frame[3]=2; frame[4]=0xffffff;
 /* PP clear registers are RGBA, while our linear writeback is BGRA. White
  * and black hid this mismatch; VseSDoli.jpg exposed it in source-over. */
 unsigned clear=(color&0xff00ff00U)|((color&255U)<<16)|((color>>16)&255U);
 frame[6]=frame[7]=frame[8]=frame[9]=clear;
 frame[10]=frame[11]=15; frame[12]=I9100_MALI_VA+0x9000;
 frame[16]=1; frame[17]=31; frame[18]=0x77; frame[19]=1;
 frame[21]=0xe0c; frame[22]=0x8888;
 for(n=0;n<23;n++)wr(io,GPU,base+n*4,frame[n]);
 for(unsigned wb=0;wb<3;wb++)for(n=0;n<12;n++) {
  unsigned value=0;
  if(!wb) { if(n==0)value=2; if(n==1)value=I9100_MALI_VA+0x8080;
            if(n==2)value=3; if(n==5)value=8; }
  wr(io,GPU,base+0x100*(wb+1)+n*4,value);
 }
 io->barrier(io->cookie); wr(io,GPU,base+0x100c,1U<<6);
 for(n=0;n<10000;n++) {
  s->pp_irq=rd(io,GPU,base+0x1020); s->mmu_fault=fault(io);
  if(s->mmu_fault || (s->pp_irq&PP_ERRORS))return -12;
  if((s->pp_irq&1) && !(rd(io,GPU,base+0x1008)&1))break;
  io->delay_us(io->cookie,10);
 }
 if(n==10000)return -12;
 wr(io,GPU,base+0x1024,0x1fff);
 if(!flush_l2(io))return -10;
 io->barrier(io->cookie); s->phase=10;
 for(n=0;n<1024;n++) {
  unsigned expected=n>=32 && n<32+256?color:0x5aa5c33c;
  if(textured && n>=32 && n<288) {
   unsigned x=(n-32)&15,y=(n-32)>>4;
   expected=texel(pattern,(x>>3)+2*(y>>3));
   if(pattern==2) {
    expected=source_over(expected,color);
    /* FP16/filter/blend rounding may differ by one output code point. */
    uint32_t actual=b[0x8000/4+n];int match=(actual>>24)==255;
    for(unsigned shift=0;shift<24;shift+=8) {
     int delta=(int)((actual>>shift)&255)-(int)((expected>>shift)&255);
     if(delta < -1 || delta > 1)match=0;
    }
    if(match)continue;
   }
  } else if(triangle && n>=32 && n<288) {
   unsigned x=(n-32)&15,y=(n-32)>>4;
   /* Leave a full-pixel band around edges unconstrained by exact coverage.
    * Sample positions differ across Mali revisions; interior/exterior and
    * every guard must still be exact. Edge pixels must be covered blends. */
   int inside=index?(x>=2 && y>=2 && x<=14 && y<=14 && x+y>=18):
                    (x>=1 && y>=1 && x+y<=12);
   int outside=index?(x+y<=14):(x+y>=17);
   unsigned value=b[0x8000/4+n],ink=index?0xff00ff00U:0xffff0000U;
   if(inside)expected=ink;
   else if(!outside) {
    /* Permit antialiasing only in the expected color channel; alpha255. */
    unsigned mask=index?0x00ff00U:0xff0000U;
    if((value&~mask)==0xff000000U)continue;
    expected=ink;
   }
  }
  if(b[0x8000/4+n]!=expected) {
   s->bad_offset=0x8000+n*4;s->actual=b[0x8000/4+n];return textured?-18:-13;
  }
 }
 s->pixels+=256;
 if(triangle)s->triangles+=textured?2:1;
 if(textured){s->textures++;s->render_mask|=1U<<core;if(pattern==2)s->blends++;}
 return 0;
}
int i9100_mali_selftest(const struct i9100_mali_io *io,volatile uint32_t *b,
 uint32_t pa,unsigned bytes,volatile struct i9100_mali_status *s)
{
 if(!io || !io->read || !io->write || !io->pmic_read || !io->pmic_write ||
    !io->delay_us || !io->barrier || !b || !s || (pa&4095) ||
    !pa || ((uintptr_t)b&3) || bytes<I9100_MALI_BYTES || pa>0xffffffffU-I9100_MALI_BYTES)return -1;
 s->phase=2;s->error=0;s->restore=0;s->pixels=0;s->guard=0;
 s->trial=0;s->vertices=0;s->triangles=0;
 s->textures=0;s->blends=0;s->render_mask=0;
 uint8_t control,voltage;
 if(!io->pmic_read(io->cookie,0x2a,&control) || !io->pmic_read(io->cookie,0x2b,&voltage))return s->error=-2;
 if(voltage>63)return s->error=-3;
 unsigned old_domain=rd(io,PMU,DOMAIN)&7, old_status=rd(io,PMU,DOMAIN+4)&7;
 if((old_status!=0 && old_status!=7) || old_domain!=old_status)return s->error=-5;
 if((control&1) && (voltage>9 || (old_status==7 && voltage<3)))return s->error=-3;
 if(old_status==7 && !(control&1))return s->error=-3;
 unsigned old_src=rd(io,CMU,SRC),old_div=rd(io,CMU,DIV),old_gate=rd(io,CMU,GATE);
 if(old_status==7) {
  /* Check a bootloader-owned, possibly clock-gated core before changing its
   * voltage or parent/divider. Leave an active inherited job entirely alone. */
  if(!(old_gate&1)) { update(io,CMU,GATE,1,1);io->delay_us(io->cookie,10); }
  unsigned busy=rd(io,GPU,0x68)&10;
  for(unsigned i=0;i<4;i++)busy|=rd(io,GPU,pp[i]+0x1008)&1;
  if(!(old_gate&1))update(io,CMU,GATE,1,0);
  if(busy)return s->error=-7;
 }
 uint32_t pll=rd(io,CMU,0x14108),parent=24000000;
 if(rd(io,CMU,0x14200)&(1U<<8)) {
  unsigned m=(pll>>16)&1023,p=(pll>>8)&63,shift=pll&7;
  if((pll&0xa0000000U)!=0xa0000000U || !m || !p)return s->error=-4;
  uint64_t hz=24000000ULL*m/((uint64_t)p<<shift);
  if(hz<100000000 || hz>1600000000)return s->error=-4;
  parent=(uint32_t)hz;
 }
 unsigned divisor=(parent+159999999U)/160000000U;
 if(!divisor || divisor>16)return s->error=-4;
 int error=0,touched=1,owns_hw=0;
 if(!(control&1) || voltage<4 || voltage>9) {
  if(!pmic_set(io,0x2b,7)){error=-2;goto restore;}
 }
 if(!pmic_set(io,0x2a,control|1)){error=-2;goto restore;}
 io->delay_us(io->cookie,1000);
 s->phase=3;
 update(io,CMU,GATE,1,0);
 update(io,CMU,DIV,15,divisor-1);
 if(!wait_bits(io,CMU,DIVSTAT,1,0,100)){error=-4;goto restore;}
 update(io,CMU,SRC,0x101,0);io->delay_us(io->cookie,10);
 if((rd(io,CMU,SRC)&0x101) || (rd(io,CMU,DIV)&15)!=divisor-1){error=-4;goto restore;}
 update(io,CMU,GATE,1,1);s->clock_mhz=parent/divisor/1000000;
 s->phase=4;update(io,PMU,DOMAIN,7,7);
 if(!wait_bits(io,PMU,DOMAIN+4,7,7,1000)){error=-5;goto restore;}
 s->phase=5;s->gp_version=rd(io,GPU,0x6c);s->pp_mask=0;
 if((s->gp_version>>16)!=0x0b07){error=-6;goto restore;}
 for(unsigned i=0;i<4;i++) {
  unsigned version=rd(io,GPU,pp[i]+0x1000);
  if(!i)s->pp_version=version;
  if((version>>16)!=0xcd07){error=-6;goto restore;}
  s->pp_mask|=1U<<i;
 }
 if(rd(io,GPU,0x68)&10){error=-7;goto restore;}
 for(unsigned i=0;i<4;i++)if(rd(io,GPU,pp[i]+0x1008)&1){error=-7;goto restore;}
 owns_hw=1;
 s->phase=6;
 if(!reset_cores(io)){error=-8;goto restore;}
 if(!flush_l2(io)){error=-10;goto restore;}
 wr(io,GPU,0x101c,3);wr(io,GPU,0x1018,0x1c);
 build_arena(b,pa);uint32_t checksum=protected_sum(b);io->barrier(io->cookie);
 s->phase=7;
 for(unsigned i=0;i<5;i++) {
  wr(io,GPU,mmu[i]+0x1c,0);wr(io,GPU,mmu[i]+8,6);
  if(!wait_bits(io,GPU,mmu[i],0xfffff000U,0,100)){error=-9;goto restore;}
  wr(io,GPU,mmu[i]+0x18,3);wr(io,GPU,mmu[i],pa);
  wr(io,GPU,mmu[i]+8,0);
  if(!wait_bits(io,GPU,mmu[i]+4,1,1,100)){error=-9;goto restore;}
 }
 for(unsigned trial=0;trial<16;trial++) {
  if(trial>=4) {
   /* Upload only private input texels, never expected output pixels. The
    * preceding job has completed/read back; the next job resets cores and
    * invalidates L2 before reading the same texture VA again. */
   for(unsigned n=0;n<4;n++)b[0xb400/4+(n/2)*16+n%2]=texel((trial-4)%3,n);
   checksum=protected_sum(b);
  }
  error=render(io,b,trial,s);
  if(!error && protected_sum(b)!=checksum)error=-14;
  if(error)break;
 }
 if(!error)s->guard=1;
restore:
 /* Shut down the domain before restoring rail/clock state. The arena remains
  * retained by the service even if the domain does not acknowledge shutdown. */
 if(touched) {
  /* A job timeout is not evidence of AXI quiescence. Retain power, clocks and
   * private DMA pages if STOP_BUS is not acknowledged; never power-cut a live
   * bus master or let the allocator reuse its page tables. */
  if(owns_hw && !stop_bus(io)) { s->restore=2;goto done; }
  update(io,PMU,DOMAIN,7,0);
  if(!wait_bits(io,PMU,DOMAIN+4,7,0,1000)) { s->restore=2;update(io,CMU,GATE,1,0); }
  else {
   update(io,CMU,GATE,1,0);update(io,CMU,SRC,0x101,old_src);
   update(io,CMU,DIV,15,old_div);
   int ok=wait_bits(io,CMU,DIVSTAT,1,0,100);
   if(!pmic_set(io,0x2a,control&~1U))ok=0;
   if(!pmic_set(io,0x2b,voltage))ok=0;
   if(!pmic_set(io,0x2a,control))ok=0;
   if(ok) {
    update(io,CMU,GATE,1,old_gate);update(io,PMU,DOMAIN,7,old_domain);
    if(!wait_bits(io,PMU,DOMAIN+4,7,old_status,1000))ok=0;
   }
   s->restore=ok?1:2;
  }
 }
done:
 if(s->restore==2 && !error)error=-15;
 s->error=error;if(!error)s->phase=11;
 return error;
}
