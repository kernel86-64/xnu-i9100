#!/usr/bin/env python3
"""Read-only ARM emulation of screen queries from the supplied iOS 7.1.2 cache.

Requires Unicorn 2.x. No Apple code is distributed or patched. Real native
MobileGestalt/GraphicsServices code runs; IOKit calls and CoreFoundation object
storage are modeled. This tests geometry calculation, not UIKit scene rendering.
"""
from pathlib import Path
import argparse, struct, sys, hashlib, math
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--cache', required=True, type=Path)
parser.add_argument('--dtb', required=True, type=Path)
parser.add_argument('--before', type=Path, help='Previous DT as a missing-property control')
args = parser.parse_args()
cache = args.cache.read_bytes()
expected = 'cad2df775e122c660238f341e74c163a2ea0ed261e85bfd3190de750cd9c0d2c'
if hashlib.sha256(cache).hexdigest() != expected:
    raise SystemExit('Unsupported cache identity: native function addresses require re-audit')

def chosen_scale(path):
    data = path.read_bytes()
    def decode(pos, parent):
        count, children = struct.unpack_from('<2I', data, pos);pos += 8
        props = {}
        for _ in range(count):
            name = data[pos:pos+32].split(b'\0', 1)[0].decode('ascii')
            size = struct.unpack_from('<I', data, pos+32)[0];pos += 36
            assert pos+size <= len(data)
            props[name] = data[pos:pos+size];pos += (size+3)&~3
        name = props['name'].rstrip(b'\0').decode('ascii')
        entries = {parent+'/'+name:props}
        for _ in range(children):
            pos, child = decode(pos, parent+'/'+name);entries.update(child)
        return pos, entries
    end, entries = decode(0, '')
    assert end == len(data)
    return entries['/device-tree/chosen'].get('display-scale')
mo,mc,io,ic=struct.unpack_from('<4I',cache,16);maps=[struct.unpack_from('<3Q2I',cache,mo+32*i) for i in range(mc)]
def fileoff(a):
 for va,sz,o,_,_ in maps:
  if va<=a<va+sz:return a-va+o
 raise ValueError(hex(a))
def le(v):return struct.pack('<I',v&0xffffffff)
class Run:
 def __init__(self,scale):
  self.uc=Uc(UC_ARCH_ARM,UC_MODE_THUMB);self.uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A9)
  u=self.uc
  for va,sz,o,_,_ in maps:u.mem_map(va,sz)
  # Native code/strings for GraphicsServices and MobileGestalt; shared data
  # includes CFStrings and their original pointers. No Apple code is modified.
  for a,sz in [(0x32295000,0x18000),(0x37234000,0x18000)]:u.mem_write(a,cache[fileoff(a):fileoff(a)+sz])
  va,sz,o,_,_=maps[1];u.mem_write(va,cache[o:o+sz])
  u.mem_map(0x10000000,0x10000);u.mem_map(0x11000000,0x100000);u.mem_map(0x12000000,0x10000)
  u.reg_write(UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
  self.next=0x11001000;self.objects={};self.scale=scale;self.info=None;self.props=[];self.values={};self.screendict=None
  self.hooks={
   0x37235500:lambda:1,0x3723687c:self.resolve,
   0x12000000:self.display,0x12000010:self.size,0x12000020:self.pitch,
   0x3724293c:self.registry_path,0x3724291c:self.registry_property,
   0x372428cc:lambda:0,0x3724267c:lambda:0,
   0x3724261c:self.typeid,0x3724256c:lambda:4,0x3724254c:self.length,0x3724252c:self.bytesptr,
   0x372424fc:self.data_create,0x37242e7c:self.rindex,
   0x37234cb0:lambda:0,
   0x3724262c:self.number_create,0x37237100:self.answer,
   0x372425ac:self.dict_create,0x372425fc:self.dict_set,
   0x322a25a4:self.gs_answer,0x322a27d4:self.dict_get,0x322a2894:self.number_get,0x322a2934:lambda:0,
  }
  u.hook_add(UC_HOOK_CODE,self.hook)
 def reg(self,n):return self.uc.reg_read([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3][n])
 def put(self,a,data):self.uc.mem_write(a,data)
 def word(self,a):return struct.unpack('<I',self.uc.mem_read(a,4))[0]
 def cstr(self,a):
  s=bytearray()
  while a:
   c=self.uc.mem_read(a,1)[0]
   if not c:break
   s.append(c);a+=1
   if len(s)>1000:raise ValueError('unterminated string')
  return s.decode()
 def cfstr(self,a):return self.cstr(self.word(a+8))
 def alloc(self,data):
  a=self.next;self.next+=(len(data)+15)&~15;self.put(a,data);return a
 def obj(self,kind,value):
  a=self.alloc(b'\0'*16);self.objects[a]=(kind,value);return a
 def hook(self,u,a,size,cookie):
  if a==0x1200f000:u.emu_stop();return
  f=self.hooks.get(a)
  if f is not None:
   r=f();u.reg_write(UC_ARM_REG_R0,r if r is not None else 0);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 def call(self,a,*regs):
  for i,v in enumerate(regs):self.uc.reg_write([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3][i],v)
  self.uc.reg_write(UC_ARM_REG_SP,0x1000f000);self.uc.reg_write(UC_ARM_REG_LR,0x1200f001)
  try:self.uc.emu_start(a|1,0x1200f000,count=200000)
  except Exception:
   print("PC",hex(self.uc.reg_read(UC_ARM_REG_PC)),"LR",hex(self.uc.reg_read(UC_ARM_REG_LR)))
   raise
  assert self.uc.reg_read(UC_ARM_REG_PC)==0x1200f000,hex(self.uc.reg_read(UC_ARM_REG_PC))
  return self.uc.reg_read(UC_ARM_REG_R0)
 def resolve(self):return {5:0x12000011,6:0x12000021,7:0x12000001}[self.reg(0)]
 def display(self):self.put(self.reg(0),le(0x1234));return 0
 def size(self):self.put(self.reg(1),struct.pack('<2f',480,800));return 0
 def pitch(self):return 0xe00002c7
 def registry_path(self):assert self.cstr(self.reg(1))=='IODeviceTree:/chosen';return 0x123
 def registry_property(self):
  key=self.cfstr(self.reg(1));self.props.append(key)
  if key=='display-scale' and self.scale is not None:
   data=self.scale;ptr=self.alloc(data);return self.obj('data',(ptr,len(data)))
  return 0
 def typeid(self):return 4 if self.objects[self.reg(0)][0]=='data' else 0
 def length(self):return self.objects[self.reg(0)][1][1]
 def bytesptr(self):return self.objects[self.reg(0)][1][0]
 def data_create(self):
  p,n=self.reg(1),self.reg(2);data=bytes(self.uc.mem_read(p,n));ptr=self.alloc(data);return self.obj('data',(ptr,n))
 def rindex(self):
  s=self.cstr(self.reg(0));n=s.rfind(chr(self.reg(1)));return self.reg(0)+n if n>=0 else 0
 def number_create(self):
  typ=self.reg(1);assert typ in (3,12);data=bytes(self.uc.mem_read(self.reg(2),4));v=struct.unpack('<f' if typ==12 else '<i',data)[0]
  return self.obj('number',v)
 def answer(self):
  key=self.cfstr(self.reg(0))
  if key=='oBbtJ8x+s1q0OkaiocPuog':return self.info
  return self.values.get(key,0)
 def dict_create(self):return self.obj('dict',{})
 def dict_set(self):self.objects[self.reg(0)][1][self.cfstr(self.reg(1))]=self.reg(2);return 0
 def gs_answer(self):assert self.cfstr(self.reg(0))=='screen-dimensions';return self.screendict
 def dict_get(self):return self.objects[self.reg(0)][1].get(self.cfstr(self.reg(1)),0)
 def number_get(self):
  v=self.objects[self.reg(0)][1];typ=self.reg(1);assert typ in (9,12)
  self.put(self.reg(2),struct.pack('<f',float(v)) if typ==12 else struct.pack('<i',int(v)));return 1
 def run(self):
  self.info=self.call(0x3723e990)
  ptr,n=self.objects[self.info][1];data=bytes(self.uc.mem_read(ptr,n));assert n==24
  print('native MG static',struct.unpack('<3i2fi',data),'IO properties',self.props)
  keys=['main-screen-width','main-screen-height','main-screen-pitch','main-screen-scale','main-screen-orientation','main-screen-class']
  for n,key in enumerate(keys,1):
   v=self.call(0x3723ed98,n)
   if v:self.values[key]=v
  self.screendict=self.call(0x3723a1a8)
  print('native MG screen-dimensions',{k:self.objects[v][1] for k,v in self.objects[self.screendict][1].items()})
  result=0x11000000;self.call(0x3229f1f4,result)
  points=struct.unpack('<2f',self.uc.mem_read(result,8));scale=struct.unpack('<f',le(self.call(0x3229f3c0)))[0]
  print('native GS point size',points,'scale',scale)
  return points,scale
if args.before:
    value = chosen_scale(args.before)
    assert value is None, 'The control must omit display-scale'
    print('Previous DT:', args.before)
    points, scale = Run(value).run()
    assert scale == 0.0 and all(math.isinf(p) for p in points)
value = chosen_scale(args.dtb)
assert value == struct.pack('<I', 1), 'Expected four-byte native integer display-scale=1'
print('Corrected DT:', args.dtb)
points, scale = Run(value).run()
assert points == (480.0, 800.0) and scale == 1.0
print('PASS: original MG/GS ARM code reads the actual corrected DT and computes finite full-panel geometry; no binary patch or rootfs write')
