#!/usr/bin/env python3
"""Run the actual Mali bring-up C against an explicit register/DMA model.

The model is a test fixture, not a Mali emulator or a physical GPU result.
It walks the actual private page tables and emulates PP writeback solely to
check sequencing, permissions, proof-of-write guards and failure recovery.
"""
from pathlib import Path
import subprocess
import tempfile
import argparse

root = Path(__file__).resolve().parent.parent
driver = root/'iokit/Drivers/KernelBuiltIn/ARM/AppleARMPlatform'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,default=driver/'i9100_mali.c')
parser.add_argument('--expect-rgba-clear-bug',action='store_true')
args=parser.parse_args()
code = r'''
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <assert.h>
#include "i9100_mali.h"
enum {OK,POWER_ON_TIMEOUT,RESET_GP,RESET_PP,MMU_RESET,MMU_PAGING,L2_BUSY,
 GP_TIMEOUT,GP_ERROR,MMU_FAULT,PP_TIMEOUT,PP_ERROR,NO_DMA,BAD_PIXEL,BAD_GUARD,
 TABLE_DAMAGE,POWER_OFF_TIMEOUT,BUS_STOP_TIMEOUT,BAD_ID,BAD_PLL,INHERITED_BUSY,INHERITED_PP_BUSY,NO_VS,BAD_VS,VS_IRQ_ONLY,VS_ACTIVE,EMPTY_TRIANGLE,WRONG_FS,STALE_FS,TRI_TABLE_DAMAGE,VS_PADDING,TRI_PP_TIMEOUT,TRI_MMU_FAULT,TEX_NO_DMA,TEX_UV,TEX_CHANNELS,TEX_AXES,TEX_STALE,TEX_RO_DAMAGE,TEX_DESC_DAMAGE,BLEND_OFF,BLEND_WRONG,PP1_PIXELS,PP2_TIMEOUT,PP3_MMU,TEX_EMPTY};
static struct model {
 uint32_t gpu[0x10000/4],cmu[0x18000/4],pmu[0x10000/4],arena[I9100_MALI_BYTES/4];
 uint8_t pmic[256];unsigned mode,writes,fail_write,fail_after,reads,fail_read;
 unsigned gp_jobs,pp_jobs,delays,barriers,rsw_va,position_va,vertex_count,pp_seen;
 uint32_t saved_texels[4];
} m;
static const uint32_t pa=0x42000000;
static const unsigned mmus[5]={0x3000,0x4000,0x5000,0x6000,0x7000};
static unsigned *walk(unsigned va,int writing){
 assert(va>=I9100_MALI_VA && va<I9100_MALI_VA+I9100_MALI_BYTES);
 unsigned pd=m.arena[va>>22];assert(pd==(pa+4096+1));
 unsigned pt=(pd&~4095U)-pa;
 unsigned pte=m.arena[pt/4+((va>>12)&1023)];assert((pte&3)==3 && (!writing || (pte&4)));
 unsigned physical=(pte&~4095U)+(va&4095U);
 assert(physical>=pa+8192 && physical<pa+I9100_MALI_BYTES);
 return &m.arena[(physical-pa)/4];
}
static uint32_t read32(void *cookie,unsigned region,unsigned off){
 assert(!(off&3));
 if(region==I9100_MALI_GPU){assert(off<0x10000);assert((m.pmu[0x3c64/4]&7)==7 && (m.cmu[0xc92c/4]&1));return m.gpu[off/4];}
 if(region==I9100_MALI_CMU){assert(off<0x18000);if(off==0xc62c)return 0;return m.cmu[off/4];}
 assert(region==I9100_MALI_PMU && off<0x10000);return m.pmu[off/4];
}
static unsigned bits(const unsigned *w,unsigned off,unsigned width){
 uint64_t value=w[off/32];if((off%32)+width>32)value|=(uint64_t)w[off/32+1]<<32;
 return (unsigned)(value>>(off%32))&((1U<<width)-1);
}
static void vs_job(void){
 unsigned *commands=walk(m.gpu[0],0);assert(m.gpu[1]-m.gpu[0]==96);
 int texture=m.gp_jobs>=5;unsigned count=texture?6:3,insns=texture?3:2;
 assert(commands[0]==0x28000 && commands[2]==1 && commands[4]==I9100_MALI_VA+0x2680);
 assert(commands[7]==(texture?0x40030000:0x40020000));
 assert(commands[8]==(texture?0x200800:0x100400) && commands[10]==(texture?0x01000100:0));
 unsigned *program=walk(commands[6],0),*attrib=walk(commands[14],0),*vary=walk(commands[16],0);
 assert(attrib[1]==0x8003 && vary[1]==0x8020 && commands[18]==count<<24);
 if(texture)assert(attrib[3]==0x8001 && vary[3]==0x8001);
 for(unsigned vertex=0;vertex<count;vertex++)for(unsigned insn=0;insn<insns;insn++) {
  unsigned *w=program+insn*4,attribute=bits(w,58,4);
  assert(bits(w,62,1)==1 && attribute<=(unsigned)texture && bits(w,20,2)==0 && bits(w,100,3)==0);
  unsigned *input=walk(attrib[attribute*2]+vertex*16,0);
  assert(bits(w,5,5)==22 && bits(w,15,5)==22);
  unsigned values[2]={input[bits(w,0,5)],input[bits(w,10,5)]};
  for(unsigned lane=0;lane<4;lane++) {
   unsigned source=bits(w,71+lane*3,3);
   if(source==7)continue;
   assert(source==2 || source==3);assert(bits(w,lane<2?94:99,1)==1);
   unsigned output_slot=bits(w,lane<2?90:95,4);assert(output_slot<=(unsigned)texture);
   unsigned *output=walk(vary[output_slot*2]+vertex*16+lane*4,1);
   if(m.mode!=NO_VS)*output=values[source-2];
  }
 }
 if(m.mode==BAD_VS)*walk(vary[0],1)^=1;
 if(m.mode==VS_PADDING)*walk(vary[0]-4,1)=0;
 if(texture && m.mode==TEX_UV)*walk(vary[2],1)^=1;
}
static void gp_job(void){
 m.gp_jobs++;m.rsw_va=0;m.vertex_count=0;int triangle=m.gpu[0]!=m.gpu[1];
 if(triangle)vs_job();assert(m.gpu[0x14/4]-m.gpu[0x10/4]==16384);
 unsigned *cmd=walk(m.gpu[8/4],0),*end=walk(m.gpu[12/4]-4,0);
 assert(end-cmd==(triangle?37:11));unsigned got=0;
 for(unsigned *p=cmd;p<=end;p+=2){
  switch(p[1]){
   case 0x1000010b:assert(p[0]==0x200 || (triangle && p[0]==0x2200));got|=1;break;
   case 0x1000010c:assert(!p[0]);got|=2;break;
   case 0x10000109:assert(!p[0]);got|=4;break;
   case 0x30000000:assert(p[0]==1);got|=8;break;
   case 0x28000001:{unsigned *array=walk(p[0],0);walk(array[0],1);got|=16;break;}
   case 0x50000000:assert(!p[0] && p+1==end);got|=32;break;
   case 0x10000107:case 0x10000105:assert(triangle && !p[0]);break;
   case 0x10000108:case 0x10000106:assert(triangle && p[0]==0x41800000);break;
   case 0x60000000:assert(triangle && (p[0]==0x10002 || p[0]==0x10001));break;
   case 0x80100a08:assert(triangle && walk(p[0],0));m.rsw_va=p[0];m.position_va=(p[1]&~0x80000000U)<<4;break;
   case 0x7001e000:assert(triangle && p[0]==15U<<15);break;
   case 0x1000010a:case 0x1000010e:assert(triangle && !p[0]);break;
   case 0x1000010f:assert(triangle && p[0]==0x3f800000);break;
   case 0x00040000:assert(triangle && p[0]==(m.gp_jobs>=5?6U:3U)<<24);m.vertex_count=p[0]>>24;break;
   default:assert(0);
  }
 }
 assert(got==63);
 if(m.mode==GP_TIMEOUT)return;
 if(m.mode==GP_ERROR){m.gpu[0x24/4]=1U<<11;return;}
 if(m.mode==MMU_FAULT){m.gpu[0x3004/4]|=2;return;}
 if(triangle && m.mode==VS_IRQ_ONLY){m.gpu[0x24/4]=1;return;}
 if(triangle && m.mode==VS_ACTIVE){m.gpu[0x24/4]=3;m.gpu[0x68/4]=2;return;}
 if(triangle && m.mode==TRI_MMU_FAULT){m.gpu[0x3004/4]|=2;return;}
 m.gpu[0x24/4]=triangle?3:2;
}
static uint32_t blend_fixture(uint32_t source,uint32_t destination){
 unsigned out=0,a=source>>24;
 for(unsigned channel=0;channel<4;channel++){
  unsigned value=(source>>(channel*8))&255;
  double result=value+((destination>>(channel*8))&255)*(1.0-a/255.0);
  if(result>255)result=255;out|=(unsigned)(result+0.5)<<(channel*8);
 }
 return out;
}
static void pp_job(unsigned base){
 m.pp_jobs++;assert(m.gp_jobs==m.pp_jobs);unsigned core=(base-0x8000)/0x2000;
 int texture=m.pp_jobs>=5,blending=texture && (m.pp_jobs-5)%3==2;
 assert(core==(texture?(m.pp_jobs-5)/3:0));m.pp_seen|=1U<<core;
 unsigned *stream=walk(m.gpu[base/4],0);
 assert(stream[0]==0 && stream[1]==0xb8000000 && stream[3]==0xb0000000 && stream[5]==0xbc000000);
 unsigned *rsw=walk(m.gpu[(base+4)/4],0);assert(rsw[8]==0xf008 && rsw[13]==0x100);
 unsigned *shader=walk(rsw[9],0);assert(shader[0]==0x00020425 && shader[2]==0x01e007cf);
 assert(m.gpu[(base+0x100)/4]==2 && m.gpu[(base+0x108)/4]==3 && !m.gpu[(base+0x110)/4]);
 assert(m.gpu[(base+0x200)/4]==0 && m.gpu[(base+0x300)/4]==0);
 unsigned w=m.gpu[(base+0x28)/4]+1,h=m.gpu[(base+0x2c)/4]+1,pitch=m.gpu[(base+0x114)/4]*8;
 assert(w==16 && h==16 && pitch==w*4);
 if(m.mode==PP_TIMEOUT || (m.mode==TRI_PP_TIMEOUT && m.pp_jobs>=3) || (core==2 && m.mode==PP2_TIMEOUT))return;
 if(m.mode==PP_ERROR){m.gpu[(base+0x1020)/4]=1U<<9;return;}
 if(core==3 && m.mode==PP3_MMU){m.gpu[mmus[core+1]/4+1]|=2;return;}
 unsigned *render=m.rsw_va?walk(m.rsw_va,0):NULL,*descriptor=NULL,tex_va=0,tex_stride=0,tex_width=0,tex_height=0;
 if(texture){
  assert(render && render[2]==(blending?0xfc8bc2d2:0xfc3b1ad2));
  assert(render[3]==0x3e && render[8]==0xf807 && render[10]==1 && render[13]==(blending?0x4322:0x5322));
  unsigned *fs=walk(render[9]&~31U,0);assert((render[9]&31)==6 && fs[0]==0x11e6);
  assert(bits(fs+1,5,2)==1 && bits(fs+1,10,4)==15 && bits(fs+1,24,4)==15 && bits(fs+1,28,4)==3);
  assert(bits(fs+1,34+42,20)==0x39001 && bits(fs+1,34+30,12)==0);
  assert(bits(fs+1,96,4)==14 && bits(fs+1,100,8)==0xe4 && bits(fs+1,128,4)==15 && bits(fs+1,134,5)==31);
  unsigned *list=walk(render[12],0);descriptor=walk(list[0],0);
  assert(bits(descriptor,0,6)==0x16 && !bits(descriptor,7,1) && !bits(descriptor,39,1));
  assert(bits(descriptor,42,2)==1 && !bits(descriptor,44,16) && bits(descriptor,60,9)==8);
  assert(bits(descriptor,72,1) && bits(descriptor,75,1) && bits(descriptor,76,1));
  assert(bits(descriptor,77,3)==1 && bits(descriptor,80,3)==1 && !bits(descriptor,205,2));
  tex_va=bits(descriptor,222,26)<<6;tex_stride=bits(descriptor,16,15);
  tex_width=bits(descriptor,86,13);tex_height=bits(descriptor,99,13);
  assert(tex_width==2 && tex_height==2 && tex_stride==64);
  if(m.pp_jobs==5)for(unsigned i=0;i<4;i++)m.saved_texels[i]=*walk(tex_va+(i/2)*tex_stride+(i%2)*4,0);
 }
 if(m.mode!=NO_DMA && !(texture && m.mode==TEX_NO_DMA))for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++) {
  unsigned raw_clear=m.gpu[(base+0x18)/4];
  unsigned color=(raw_clear&0xff00ff00U)|((raw_clear&255U)<<16)|((raw_clear>>16)&255U);
  if(m.vertex_count) {
   unsigned rgba=0;
   if(!texture){
    unsigned *r=render;assert(r[2]==0xfc3b1ad2 && r[3]==0x3e && r[8]==0xf807 && r[13]==0x1300);
    unsigned *fs=walk(r[9]&~31U,0);assert((r[9]&31)==5 && fs[0]==0x21025);
    assert(bits(fs+1,0,4)==12 && bits(fs+1,4,8)==0xe4 && bits(fs+1,32,4)==15 && bits(fs+1,38,5)==31);
    for(unsigned lane=0;lane<4;lane++) {
     unsigned half=bits(fs+1,44+lane*16,16);assert(half==0 || half==0x3c00);
     if(half)rgba|=255U<<((lane==0?2:lane==2?0:lane)*8);
    }
   }
   for(unsigned triangle=0;triangle<m.vertex_count/3;triangle++){
    float positions[12];memcpy(positions,walk(m.position_va+triangle*48,0),sizeof(positions));
    double weights[3];int inside=1;
    for(unsigned edge=0;edge<3;edge++) {
     unsigned next=(edge+1)%3;
     double ex=positions[next*4]-positions[edge*4],ey=positions[next*4+1]-positions[edge*4+1];
     weights[(edge+2)%3]=ex*(y+0.5-positions[edge*4+1])-ey*(x+0.5-positions[edge*4]);
     if(weights[(edge+2)%3]<0)inside=0;
    }
    if(m.mode==EMPTY_TRIANGLE || (texture && m.mode==TEX_EMPTY))inside=0;
    if(!inside)continue;
    if(texture){
     double uv[2]={0},area=weights[0]+weights[1]+weights[2];assert(area>0);
     for(unsigned vertex=0;vertex<3;vertex++){
      float value[2];memcpy(value,walk(render[15]+(triangle*3+vertex)*16,0),8);
      for(unsigned axis=0;axis<2;axis++)uv[axis]+=weights[vertex]*value[axis]/area;
     }
     unsigned tx=(unsigned)(uv[0]*tex_width),ty=(unsigned)(uv[1]*tex_height);
     if(tx>=tex_width)tx=tex_width-1;if(ty>=tex_height)ty=tex_height-1;
     if(m.mode==TEX_AXES){unsigned temp=tx;tx=ty;ty=temp;}
     rgba=*walk(tex_va+ty*tex_stride+tx*4,0);
     if(m.mode==TEX_STALE)rgba=m.saved_texels[ty*tex_width+tx];
     if(m.mode==TEX_CHANNELS)rgba=(rgba&0xff00ff00)|((rgba&255)<<16)|((rgba>>16)&255);
     if(blending && m.mode!=BLEND_OFF)rgba=blend_fixture(rgba,color);
     if(blending && m.mode==BLEND_WRONG)rgba^=0x00101010;
    }
    if(m.mode==WRONG_FS)rgba^=0x00010100;
    if(m.mode==STALE_FS && m.pp_jobs==4)rgba=0xffff0000;
    color=rgba;break;
   }
  }
  *walk(m.gpu[(base+0x104)/4]+y*pitch+x*4,1)=color;
 }
 if(texture && m.mode==TEX_RO_DAMAGE)*walk(tex_va,0)^=1;
 if(texture && m.mode==TEX_DESC_DAMAGE)descriptor[0]^=1;
 if(core==1 && m.mode==PP1_PIXELS)m.arena[0x8080/4]^=1;
 if(m.mode==TRI_TABLE_DAMAGE && m.pp_jobs>=3)m.arena[0]^=1;
 if(m.mode==BAD_PIXEL)m.arena[0x8080/4]^=1;
 if(m.mode==BAD_GUARD)m.arena[0x8000/4]^=1;
 if(m.mode==TABLE_DAMAGE)m.arena[0]^=1;
 m.gpu[(base+0x1020)/4]=1;
}
static void write32(void *cookie,unsigned region,unsigned off,uint32_t value){
 assert(!(off&3));
 if(region==I9100_MALI_CMU){assert(off==0xc22c||off==0xc52c||off==0xc92c);m.cmu[off/4]=value;return;}
 if(region==I9100_MALI_PMU){assert(off==0x3c60);m.pmu[off/4]=value;
  if((value&7)==7 && m.mode!=POWER_ON_TIMEOUT)m.pmu[(off+4)/4]=(m.pmu[(off+4)/4]&~7U)|7;
  if(!(value&7) && m.mode!=POWER_OFF_TIMEOUT)m.pmu[(off+4)/4]&=~7U;
  return;}
 assert(region==I9100_MALI_GPU);read32(cookie,region,off);m.gpu[off/4]=value;
 for(unsigned i=0;i<5;i++){
  unsigned base=mmus[i];
  if(off==base+8){
   if(value==6){m.gpu[base/4]=m.mode==MMU_RESET?0x12345000:0;m.gpu[(base+4)/4]=8;}
   if(value==0 && m.mode!=MMU_PAGING)m.gpu[(base+4)/4]|=1;
  }
  if(off==base+0x18)m.gpu[(base+0x14)/4]&=~value;
 }
 if(off==0x20 && value==(1U<<10))m.gpu[0x24/4]=m.mode==RESET_GP?0:1U<<19;
 if(off==0x20 && value==(1U<<9) && m.mode!=BUS_STOP_TIMEOUT)m.gpu[0x68/4]|=4;
 if(off==0x28)m.gpu[0x24/4]&=~value;
 if(off==0x20 && (value==2 || value==3))gp_job();
 for(unsigned i=0;i<4;i++){
  unsigned base=0x8000+i*0x2000;
  if(off==base+0x100c && value==(1U<<7))m.gpu[(base+0x1020)/4]=m.mode==RESET_PP?0:1U<<12;
  if(off==base+0x100c && value==1 && m.mode!=BUS_STOP_TIMEOUT)m.gpu[(base+0x1008)/4]|=16;
  if(off==base+0x1024)m.gpu[(base+0x1020)/4]&=~value;
 }
 if(off==0x1010)m.gpu[0x1008/4]=m.mode==L2_BUSY?1:0;
 for(unsigned i=0;i<4;i++)if(off==0x900c+i*0x2000 && value==(1U<<6))pp_job(0x8000+i*0x2000);
}
static int pmic_read(void *cookie,unsigned reg,uint8_t *value){
 assert(reg==0x2a||reg==0x2b);m.reads++;if(m.reads==m.fail_read)return 0;*value=m.pmic[reg];return 1;}
static int pmic_write(void *cookie,unsigned reg,uint8_t value){
 assert(reg==0x2a||reg==0x2b);m.writes++;
 if(m.writes==m.fail_write && !m.fail_after)return 0;
 m.pmic[reg]=value;return m.writes!=m.fail_write;}
static void delay(void *cookie,unsigned us){assert(us<=1000);m.delays++;assert(m.delays<40000);}
static void barrier(void *cookie){m.barriers++;}
static void initialize(unsigned mode,int on){
 memset(&m,0,sizeof(m));m.mode=mode;
 m.cmu[0xc22c/4]=0x12345511;m.cmu[0xc52c/4]=0x1357900a;m.cmu[0xc92c/4]=0xabcdef20|(on?1:0);
 m.cmu[0x14108/4]=0xa0000000|(200U<<16)|(3U<<8)|1;m.cmu[0x14200/4]=1U<<8;
 if(mode==BAD_PLL)m.cmu[0x14108/4]=0;
 m.pmu[0x3c60/4]=m.pmu[0x3c64/4]=0x12340000|(on?7:0);
 m.pmic[0x2a]=on?1:0;m.pmic[0x2b]=on?7:0;
 m.gpu[0x6c/4]=mode==BAD_ID?0:0x0b070100;
 for(unsigned i=0;i<4;i++)m.gpu[(0x9000+i*0x2000)/4]=0xcd070100;
 if(mode==INHERITED_BUSY)m.gpu[0x68/4]=2;
 if(mode==INHERITED_PP_BUSY)m.gpu[0x9008/4]=1;
}
int main(void){
 struct i9100_mali_io io={NULL,read32,write32,delay,barrier,pmic_read,pmic_write};
 volatile struct i9100_mali_status status;
 for(unsigned on=0;on<2;on++){
  initialize(OK,on);memset((void*)&status,0,sizeof(status));
  int e=i9100_mali_selftest(&io,m.arena,pa,sizeof(m.arena),&status);
#ifdef OLD_CLEAR_CONTROL
  assert(e==-18 && status.phase==10 && status.trial==7 && status.pixels==1536 && status.textures==2);
  assert(status.bad_offset==0x8080 && status.actual==0xff881020 && status.restore==1);
  puts("OLD CONTROL: exact GPU30 + corrected PP register model reproduces VseSDoli.jpg E-18 J7 P1536 B8080:ff881020");
  return 23;
#endif
  assert(!e && status.phase==11 && status.pixels==4096 && status.guard==1 && status.restore==1);
  assert(status.pp_mask==15 && status.clock_mhz==160 && m.gp_jobs==16 && m.pp_jobs==16 && status.vertices==78 && status.triangles==26 && status.trial==16 && status.textures==12 && status.blends==4 && status.render_mask==15 && m.pp_seen==15);
  assert(m.cmu[0xc22c/4]==0x12345511 && m.cmu[0xc52c/4]==0x1357900a && m.cmu[0xc92c/4]==(0xabcdef20|(on?1:0)));
  assert(m.pmu[0x3c60/4]==(0x12340000|(on?7:0)) && m.pmic[0x2a]==(on?1:0) && m.pmic[0x2b]==(on?7:0));
  // Directory/table/command pages and guard pages are not writable GPU mappings.
  assert(m.arena[1024]==0 && m.arena[1025]==0 && (m.arena[1026]&7)==3);
  assert((m.arena[1035]&7)==3);for(unsigned i=12;i<16;i++)assert(!m.arena[1024+i]);
 }
 unsigned cases=2;
 for(unsigned mode=POWER_ON_TIMEOUT;mode<=INHERITED_PP_BUSY;mode++){
  initialize(mode,mode>=INHERITED_BUSY);memset((void*)&status,0,sizeof(status));
  int result=i9100_mali_selftest(&io,m.arena,pa,sizeof(m.arena),&status);
  if(!result)fprintf(stderr,"unexpected success for injected mode%u\n",mode);
  assert(result!=0);
  assert(status.error && status.pixels<=4096);
  if(mode==POWER_OFF_TIMEOUT)assert(status.restore==2 && !(m.cmu[0xc92c/4]&1));
  else if(mode==BUS_STOP_TIMEOUT)assert(status.restore==2 && (m.cmu[0xc92c/4]&1) && (m.pmic[0x2a]&1));
  else if(mode!=INHERITED_BUSY && mode!=INHERITED_PP_BUSY){assert(m.pmic[0x2a]==0 && m.pmic[0x2b]==0);}
  if(mode>=INHERITED_BUSY)assert(!m.writes && !m.gp_jobs && !m.pp_jobs);
  cases++;
 }
 const int expected[]={-17,-17,-11,-11,-13,-13,-13,-14,-17,-12,-11};
 for(unsigned mode=NO_VS;mode<=TRI_MMU_FAULT;mode++) {
  initialize(mode,0);memset((void*)&status,0,sizeof(status));
  int result=i9100_mali_selftest(&io,m.arena,pa,sizeof(m.arena),&status);
  assert(result==expected[mode-NO_VS] && status.error==result && status.restore==1 && !status.guard);
  assert(status.trial>=3 && status.pixels>=512);cases++;
 }
 const int texture_errors[]={-18,-17,-18,-18,-18,-14,-14,-18,-18,-18,-12,-12,-18};
 for(unsigned mode=TEX_NO_DMA;mode<=TEX_EMPTY;mode++) {
  initialize(mode,0);memset((void*)&status,0,sizeof(status));
  int result=i9100_mali_selftest(&io,m.arena,pa,sizeof(m.arena),&status);
  assert(result==texture_errors[mode-TEX_NO_DMA] && status.error==result && status.restore==1 && !status.guard);
  assert(status.trial>=5 && status.pixels>=1024);cases++;
 }
 for(unsigned after=0;after<2;after++)for(unsigned n=1;n<=5;n++){
  initialize(OK,0);m.fail_write=n;m.fail_after=after;memset((void*)&status,0,sizeof(status));
  assert(i9100_mali_selftest(&io,m.arena,pa,sizeof(m.arena),&status)!=0 && status.error);cases++;
 }
 for(unsigned n=1;n<=2;n++){
  initialize(OK,0);m.fail_read=n;assert(i9100_mali_selftest(&io,m.arena,pa,sizeof(m.arena),&status)==-2 && !m.writes);cases++;
 }
 initialize(OK,0);m.pmic[0x2b]=255;assert(i9100_mali_selftest(&io,m.arena,pa,sizeof(m.arena),&status)==-3 && !m.writes);
 initialize(OK,0);assert(i9100_mali_selftest(&io,m.arena,pa+1,sizeof(m.arena),&status)==-1 && !m.writes);
 assert(i9100_mali_selftest(&io,m.arena,pa,4096,&status)==-1);
 printf("PASS: actual Mali core %u power/clock/MMU/job/DMA/failure cases; two clears/two triangles plus12 texture/blend draws on4PP,4096-pixel checks and78 vertex readbacks, no-DMA false-success rejection, guard corruption and bounded waits/rollback; ASan/UBSan. Model only, not physical Mali validation.\n",cases+3);
}
'''
with tempfile.TemporaryDirectory(prefix='i9100-mali-') as folder:
    path=Path(folder)
    (path/'test.c').write_text(code)
    subprocess.run(['clang','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all',
                    *(['-DOLD_CLEAR_CONTROL=1'] if args.expect_rgba_clear_bug else []),'-I',str(driver),str(args.source),str(path/'test.c'),
                    '-o',str(path/'test')],check=True)
    result=subprocess.run([str(path/'test')])
    raise SystemExit(0 if args.expect_rgba_clear_bug and result.returncode==23 else result.returncode if not args.expect_rgba_clear_bug else 1)
