#!/usr/bin/env python3
"""Run the linked ARMv7 userspace executable with mocked IOKit imports.

No kernel/GPU emulation here. This verifies actual binary ABI, payloads,
readback validation, retry/error handling and cleanup, separately from the
actual C driver tests. Never presented as a physical-device result.
"""
import argparse
import hashlib
from pathlib import Path
import struct
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--client',required=True,type=Path);a=p.parse_args()
b=a.client.read_bytes();assert struct.unpack_from('<II',b)==(0xfeedface,12)
segments=[];sections=[];cursor=28;commands={}
for _ in range(struct.unpack_from('<I',b,16)[0]):
 cmd,size=struct.unpack_from('<II',b,cursor);commands[cmd]=cursor
 if cmd==1:
  va,sz,off,fs=struct.unpack_from('<IIII',b,cursor+24);segments.append((va,sz,off,fs))
  for n in range(struct.unpack_from('<I',b,cursor+48)[0]):
   s=cursor+56+n*68
   name=b[s:s+16].split(b'\0')[0].decode()
   addr,length,offset=struct.unpack_from('<III',b,s+32)
   flags,reserved=struct.unpack_from('<II',b,s+56)
   sections.append((name,addr,length,offset,flags&255,reserved))
 cursor+=size
sy,count,strings,_=struct.unpack_from('<IIII',b,commands[2]+8)
indirect=struct.unpack_from('<I',b,commands[0xb]+56)[0]
symbols=[]
for n in range(count):
 ix,typ,sect,desc,value=struct.unpack_from('<IBBHI',b,sy+12*n)
 name=b[strings+ix:b.index(b'\0',strings+ix)].decode() if ix else ''
 symbols.append((name,desc,value))
main=next((v|(1 if d&8 else 0)) for name,d,v in symbols if name=='_main')
# This kernel's code-signing path consumes slot0 SHA1, not alternate SHA256.
off,size=struct.unpack_from('<II',b,commands[0x1d]+8)
_,_,entries=struct.unpack_from('>III',b,off)
cd=None
for n in range(entries):
 slot,relative=struct.unpack_from('>II',b,off+12+n*8)
 if slot==0:cd=off+relative
assert cd and b[cd+36:cd+38]==bytes([20,1])
hashoff,_,special,pages,limit=struct.unpack_from('>IIIII',b,cd+16)
assert b[cd+39]==12 and limit==off
for n in range(pages):assert hashlib.sha1(b[n*4096:min((n+1)*4096,limit)]).digest()==b[cd+hashoff+n*20:cd+hashoff+(n+1)*20]

for mode in ('success','retry','missing','open','pixel','gpu_error','not_ready'):
 u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A9)
 u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
 for va,sz,offset,fs in segments:
  if not fs:continue
  u.mem_map(va,(sz+4095)&~4095);u.mem_write(va,b[offset:offset+fs])
 u.mem_map(0x10000000,0x100000);u.mem_map(0x11000000,0x1000);u.mem_map(0x12000000,0x10000)
 u.mem_write(0x11000000,struct.pack('<I',99));hooks={};calls=[];state={'close':0,'connect':0}
 def word(address):return struct.unpack('<I',u.mem_read(address,4))[0]
 def reg(n):return u.reg_read([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3][n])
 def cstring(address):
  out=bytearray()
  while True:
   ch=bytes(u.mem_read(address,1));address+=1
   if ch==b'\0':return out.decode()
   out+=ch;assert len(out)<1024
 def blend(s,d):
  alpha=s>>24;out=0
  for n in range(4):out|=min(255,((s>>(8*n))&255)+(((d>>(8*n))&255)*(255-alpha)+127)//255)<<(8*n)
  return out
 for _,address,length,_,kind,first in sections:
  if kind not in (6,7):continue
  for n in range(length//4):
   index=struct.unpack_from('<I',b,indirect+(first+n)*4)[0]
   if index&0xc0000000:continue
   name=symbols[index][0]
   if name=='_mach_task_self_':target=0x11000000
   else:
    target=0x12000000+len(hooks)*16;hooks[target]=name;target|=1
   u.mem_write(address+n*4,struct.pack('<I',target))
 def hook(uc,pc,size,data):
  if pc==0x1200f000:u.emu_stop();return
  name=hooks.get(pc)
  if name is None:return
  result=0
  if name=='_IOServiceMatching':assert cstring(reg(0))=='IOS7I9100Mali';result=1
  elif name=='_IOServiceGetMatchingService':assert reg(0)==0 and reg(1)==1;result=0 if mode=='missing' else 123
  elif name=='_IOServiceOpen':
   assert (reg(0),reg(1),reg(2))==(123,99,0);u.mem_write(reg(3),struct.pack('<I',321));result=1 if mode=='open' else 0
  elif name=='_IOObjectRelease':assert reg(0)==123
  elif name=='_IOServiceClose':assert reg(0)==321;state['close']+=1
  elif name=='_usleep':assert reg(0)==100000
  elif name in ('_puts','_printf'):cstring(reg(0))
  elif name=='_IOConnectCallStructMethod':
   assert (reg(0),reg(1),reg(3))==(321,0,32)
   sp=u.reg_read(UC_ARM_REG_SP);output,sizeptr=word(sp),word(sp+4);assert word(sizeptr)==1040
   version,op,bg,reserved,*texels=struct.unpack('<8I',u.mem_read(reg(2),32));assert version==1 and op in (1,2,3) and reserved==0
   state['connect']+=1
   if mode=='not_ready' or (mode=='retry' and state['connect']<=2):result=0xe00002d8
   else:
    calls.append(op);pixels=[]
    for y in range(16):
     for x in range(16):
      v=bg if op==1 else texels[x//8+2*(y//8)]
      if op==3:v=blend(v,bg)
      pixels.append(v)
    if mode=='pixel':pixels[70]^=0x00101010
    reply=struct.pack('<4I256I',1,(-12)&0xffffffff if mode=='gpu_error' else 0,1,256,*pixels)
    u.mem_write(output,reply);u.mem_write(sizeptr,struct.pack('<I',len(reply)))
  else:raise AssertionError(name)
  u.reg_write(UC_ARM_REG_R0,result);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 u.hook_add(UC_HOOK_CODE,hook)
 u.reg_write(UC_ARM_REG_SP,0x100ff000);u.reg_write(UC_ARM_REG_LR,0x1200f001)
 u.emu_start(main,0x1200f000,count=2000000)
 assert u.reg_read(UC_ARM_REG_PC)==0x1200f000
 result=u.reg_read(UC_ARM_REG_R0)
 expected={'success':0,'retry':0,'missing':1,'open':2,'pixel':4,'gpu_error':3,'not_ready':3}[mode]
 assert result==expected,(mode,result)
 if result==0:assert calls==[1,2,3] and state['close']==1
 if mode=='not_ready':assert state['connect']==100 and state['close']==1
 print('PASS: actual ARMv7 client',mode)
print('PASS: primary SHA1 CodeDirectory/page hashes; native IOKit wire/readback/retry/error branches. No physical Mali execution.')
