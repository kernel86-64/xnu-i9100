#!/usr/bin/env python3
"""Check fixed-size launch-cache registration; optional real cache is read-only."""
import argparse
import ctypes
import datetime
from pathlib import Path
import plistlib
import struct
import sys
import tempfile
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'userland/mali'))
from launch_cache import fixed_plist,plan,add_job,JOB_PATH,CACHE_IMAGE
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path);a=p.parse_args()
job={'Label':'org.i9100.mali-smoke','ProgramArguments':['/usr/local/libexec/i9100-mali-smoke'],
     'RunAtLoad':True,'StandardOutPath':'/var/log/i9100-mali-smoke.log','StandardErrorPath':'/var/log/i9100-mali-smoke.log'}
old={'LaunchDaemons':{'/System/Library/LaunchDaemons/old.plist':{'Label':'old','RunAtLoad':True}},
     'VersionNumber':1,'CreationDate':datetime.datetime(2013,1,1),'data':b'abc'}
data=bytearray(0x8000);data[:16]=b'dyld_v1   armv7\0';struct.pack_into('<4I',data,16,0x100,1,0x200,1)
struct.pack_into('<3Q2I',data,0x100,0x10000000,len(data),0,5,5)
struct.pack_into('<3QI',data,0x200,0x10001000,0,0,0x300)
path=CACHE_IMAGE.encode()+b'\0';data[0x300:0x300+len(path)]=path
struct.pack_into('<7I',data,0x1000,0xfeedface,12,9,6,1,124,0)
struct.pack_into('<II16s8I',data,0x101c,1,124,b'__TEXT',0x10001000,0x3000,0x1000,0x3000,5,5,1,0)
struct.pack_into('<16s16s9I',data,0x1054,b'__xpcd_cache',b'__TEXT',0x10002000,4096,0x2000,2,0,0,0,0,0)
data[0x2000:0x3000]=fixed_plist(old,4096)
change=plan(data,job);assert (change['offset'],change['length'])==(0x2000,4096)
new=bytearray(data);new[0x2000:0x3000]=change['after'];assert new[:0x2000]==data[:0x2000] and new[0x3000:]==data[0x3000:]
parsed=plistlib.loads(new[0x2000:0x3000]);assert parsed['LaunchDaemons'].pop(JOB_PATH)==job and parsed==old
assert plan(new,job)['jobs_after']==2
assert plan(new,job)['after']==change['after']
with tempfile.TemporaryDirectory() as folder:
 cache=Path(folder)/'synthetic-cache';cache.write_bytes(data)
 result=add_job(cache,job)
 assert cache.read_bytes()==bytes(new) and result['jobs_before']==1 and result['jobs_after']==2
 add_job(cache,job);assert cache.read_bytes()==bytes(new)
for mode in ('signed','missing','conflict','too_small'):
 bad=bytearray(data)
 try:
  if mode=='signed':struct.pack_into('<Q',bad,48,1)
  if mode=='missing':bad[0x300]=ord('x')
  if mode=='conflict':bad[0x2000:0x3000]=fixed_plist({'LaunchDaemons':{JOB_PATH:{'Label':'other'}}},4096)
  if mode=='too_small':fixed_plist(old,20)
  else:plan(bad,job)
 except ValueError:pass
 else:raise AssertionError(mode)
print('PASS: fixed-size binary-plist registration, semantic preservation, bounds, idempotence, signed/missing/conflicting/overflow rejection.')
if a.cache:
 before=a.cache.read_bytes();change=plan(before,job)
 first=plistlib.loads(change['before']);second=plistlib.loads(change['after'])
 assert JOB_PATH not in first['LaunchDaemons'];assert second['LaunchDaemons'].pop(JOB_PATH)==job;assert first==second
 if sys.platform=='darwin':
  cf=ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
  cf.CFDataCreate.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_long];cf.CFDataCreate.restype=ctypes.c_void_p
  cf.CFPropertyListCreateWithData.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)];cf.CFPropertyListCreateWithData.restype=ctypes.c_void_p
  cf.CFRelease.argtypes=[ctypes.c_void_p]
  for blob in (change['before'],change['after']):
   storage=ctypes.create_string_buffer(blob);d=cf.CFDataCreate(None,storage,len(blob));err=ctypes.c_void_p()
   obj=cf.CFPropertyListCreateWithData(None,d,0,None,ctypes.byref(err));assert obj and not err.value
   cf.CFRelease(obj);cf.CFRelease(d)
 print('PASS: actual private cache default lacks Mali job; patch preserves all%d existing jobs and metadata; both plists decoded by native CoreFoundation.'%change['jobs_before'])
