"""Add only the original Mali job to an unsigned legacy iOS XPC plist cache.

Preserves every existing job and all bytes outside the fixed-size plist section.
No instruction, image address, code-signing setting or other job is modified.
"""
import hashlib
import mmap
import os
import plistlib
import struct

JOB_PATH='/System/Library/LaunchDaemons/org.i9100.mali-smoke.plist'
CACHE_IMAGE='/System/Library/Caches/com.apple.xpcd/xpcd_cache.dylib'


def fixed_plist(value, size):
    data=plistlib.dumps(value,fmt=plistlib.FMT_BINARY,sort_keys=False)
    if len(data)>size:raise ValueError('Rebuilt XPC plist does not fit its original section')
    # A binary plist's trailer must remain the final32 bytes. Insert unused
    # space before the offset table, preserving every object offset and index.
    padding=size-len(data)
    table=struct.unpack_from('>Q',data,len(data)-8)[0]
    trailer=bytearray(data[-32:]);struct.pack_into('>Q',trailer,24,table+padding)
    result=data[:table]+b'\0'*padding+data[table:-32]+trailer
    if len(result)!=size or plistlib.loads(result)!=value:raise ValueError('Invalid fixed-size plist')
    return result


def plan(data, job):
    if job.get('Label')!='org.i9100.mali-smoke' or job.get('ProgramArguments')!=['/usr/local/libexec/i9100-mali-smoke']:
        raise ValueError('Unexpected job identity/program')
    if len(data)<64 or not data[:16].startswith(b'dyld_v1') or b'armv7' not in data[:16]:
        raise ValueError('Expected legacy ARMv7 dyld cache')
    if struct.unpack_from('<Q',data,48)[0]:raise ValueError('Signed caches require a separate signing workflow')
    mo,mc,io,ic=struct.unpack_from('<4I',data,16)
    if not 0<mc<32 or not 0<ic<10000 or mo+mc*32>len(data) or io+ic*32>len(data):
        raise ValueError('Invalid cache tables')
    maps=[struct.unpack_from('<3Q2I',data,mo+32*i) for i in range(mc)]
    def offset(address,length):
        for va,size,fileoff,_,_ in maps:
            if va<=address and address+length<=va+size:
                result=fileoff+address-va
                if result+length<=len(data):return result
        raise ValueError('Address outside cache mappings')
    section=None
    for i in range(ic):
        address,_,_,path=struct.unpack_from('<3QI',data,io+32*i)
        end=data.find(b'\0',path)
        if not 0<path<end<len(data):raise ValueError('Invalid image path')
        if data[path:end].decode()!=CACHE_IMAGE:continue
        head=offset(address,28)
        if struct.unpack_from('<I',data,head)[0]!=0xfeedface:raise ValueError('Expected32-bit Mach-O')
        count,commands=struct.unpack_from('<II',data,head+16);cursor=head+28
        if count>4096 or cursor+commands>len(data):raise ValueError('Invalid Mach-O commands')
        for _ in range(count):
            cmd,size=struct.unpack_from('<II',data,cursor)
            if size<8 or cursor+size>head+28+commands:raise ValueError('Bad load command')
            if cmd==1:
                ns=struct.unpack_from('<I',data,cursor+48)[0]
                if 56+ns*68>size:raise ValueError('Bad section list')
                for n in range(ns):
                    p=cursor+56+n*68
                    if data[p:p+16].split(b'\0')[0]==b'__xpcd_cache':
                        va,length=struct.unpack_from('<II',data,p+32)
                        if section is not None:raise ValueError('Ambiguous XPC cache section')
                        section=(offset(va,length),length)
            cursor+=size
    if section is None:raise ValueError('No embedded XPC plist section')
    start,length=section;before=bytes(data[start:start+length]);root=plistlib.loads(before)
    jobs=root.get('LaunchDaemons')
    if not isinstance(jobs,dict):raise ValueError('No LaunchDaemons dictionary')
    old_count=len(jobs)
    if JOB_PATH in jobs and jobs[JOB_PATH]!=job:raise ValueError('Conflicting cached Mali job')
    jobs[JOB_PATH]=job
    after=fixed_plist(root,length)
    return {'offset':start,'length':length,'before':before,'after':after,
            'jobs_before':old_count,'jobs_after':len(jobs)}


def add_job(cache,job):
    with cache.open('r+b') as f:
        with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mapped:change=plan(mapped,job)
        f.seek(change['offset']);assert f.read(change['length'])==change['before']
        f.seek(change['offset']);f.write(change['after']);f.flush();os.fsync(f.fileno())
        f.seek(change['offset']);assert f.read(change['length'])==change['after']
    return {k:v for k,v in change.items() if k not in ('before','after')} | {
        'before_section_sha256':hashlib.sha256(change['before']).hexdigest(),
        'after_section_sha256':hashlib.sha256(change['after']).hexdigest()}
