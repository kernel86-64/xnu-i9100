#!/usr/bin/env python3
"""Add the smoke client/one-shot launch job to a NEW raw HFS+ rootfs copy.

Never edits the input. BSD ownership is fixed offline using the source tree's
HFSPlusCatalogFile/Folder layout, since macOS mounts these images noowners.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import tempfile


def catalog_permissions(image, paths):
    with image.open('r+b') as f:
        f.seek(1024);header=f.read(512)
        if header[:2] not in (b'H+',b'HX') or struct.unpack_from('>I',header,4)[0]&0x2000:
            raise ValueError('Expected raw non-journaled HFS+')
        block=struct.unpack_from('>I',header,40)[0]
        size=struct.unpack_from('>Q',header,272)[0]
        extents=[struct.unpack_from('>II',header,288+8*i) for i in range(8)]
        if not block or size>sum(n*block for _,n in extents):
            raise ValueError('Unsupported catalog extents')
        def physical(offset,length):
            for start,count in extents:
                span=count*block
                if offset<span:
                    if length>span-offset:raise ValueError('Catalog record crosses extent')
                    return start*block+offset
                offset-=span
            raise ValueError('Catalog offset outside fork')
        def read(offset,length):
            f.seek(physical(offset,length));data=f.read(length)
            if len(data)!=length:raise ValueError('Short catalog read')
            return data
        first=read(0,64);node_size=struct.unpack_from('>H',first,32)[0]
        if node_size not in (512,1024,2048,4096,8192,16384,32768):raise ValueError('Bad B-tree node size')
        leaf=struct.unpack_from('>I',first,24)[0]
        entries={};seen=set()
        while leaf:
            if leaf in seen or leaf*node_size>=size:raise ValueError('Invalid catalog leaf chain')
            seen.add(leaf);node=read(leaf*node_size,node_size)
            if node[8]!=255:raise ValueError('Expected leaf node')
            count=struct.unpack_from('>H',node,10)[0]
            if count>node_size//8:raise ValueError('Invalid record count')
            for i in range(count):
                off=struct.unpack_from('>H',node,node_size-2*(i+1))[0]
                key=struct.unpack_from('>H',node,off)[0]
                if off<14 or off+key+2+48>node_size-2*(count+1):continue
                parent,chars=struct.unpack_from('>IH',node,off+2)
                if chars>255 or key!=6+2*chars:raise ValueError('Bad catalog key')
                name=node[off+8:off+8+2*chars].decode('utf-16-be')
                data=off+key+2;kind=struct.unpack_from('>h',node,data)[0]
                if kind in (1,2):
                    ident=struct.unpack_from('>I',node,data+8)[0]
                    entries[(parent,name)]=(ident,kind,leaf*node_size+data)
            leaf=struct.unpack_from('>I',node)[0]
        changes=[]
        for path in paths:
            parent=2
            for component in Path(path).parts:
                ident,kind,offset=entries[(parent,component)];parent=ident
            before=read(offset+32,16)
            mode=0o40755 if kind==1 else 0o100644 if path.endswith('.plist') else 0o100755
            after=bytearray(before);struct.pack_into('>II',after,0,0,0);struct.pack_into('>H',after,10,mode)
            changes.append((path,physical(offset+32,16),before,bytes(after)))
        # Validate all targets before the first write; change only fixed BSD fields.
        for path,off,before,after in changes:
            f.seek(off);assert f.read(16)==before
            f.seek(off);f.write(after)
        f.flush();os.fsync(f.fileno())
        return [{'path':path,'uid':0,'gid':0,'mode':oct(struct.unpack_from('>H',after,10)[0])}
                for path,_,_,after in changes]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();source=args.source.resolve();output=args.output.resolve()
    here=Path(__file__).resolve().parent;binary=here/'out/i9100-mali-smoke'
    if not binary.is_file():p.error('Run build.py first')
    with source.open('rb') as f:
        f.seek(1024);header=f.read(8)
    if header[:2] not in (b'H+',b'HX') or struct.unpack_from('>I',header,4)[0]&0x2000:p.error('Expected raw non-journaled HFS+')
    with output.open('xb') as dest,source.open('rb') as src:shutil.copyfileobj(src,dest,1024*1024)
    with tempfile.TemporaryDirectory(prefix='mali33-install-') as directory:
        mount=Path(directory);attached=False
        try:
            subprocess.run(['hdiutil','attach','-readwrite','-nobrowse','-noverify','-noautofsck','-mountpoint',directory,'-imagekey','diskimage-class=CRawDiskImage',str(output)],check=True)
            attached=True
            target=mount/'usr/local/libexec/i9100-mali-smoke'
            jobpath=mount/'System/Library/LaunchDaemons/org.i9100.mali-smoke.plist'
            for candidate in (target,jobpath):
                if candidate.is_symlink() or not candidate.resolve().is_relative_to(mount.resolve()):
                    raise ValueError('Install path escapes the copied rootfs')
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(binary,target);target.chmod(0o755)
            job={'Label':'org.i9100.mali-smoke','ProgramArguments':['/usr/local/libexec/i9100-mali-smoke'],
                 'RunAtLoad':True,'StandardOutPath':'/var/log/i9100-mali-smoke.log',
                 'StandardErrorPath':'/var/log/i9100-mali-smoke.log'}
            with jobpath.open('xb') as f:plistlib.dump(job,f)
            jobpath.chmod(0o644);os.sync()
        finally:
            if attached:subprocess.run(['hdiutil','detach',directory],check=True)
    permissions=catalog_permissions(output,['usr/local','usr/local/libexec',
       'usr/local/libexec/i9100-mali-smoke','System/Library/LaunchDaemons/org.i9100.mali-smoke.plist'])
    # A read/write macOS mount can upgrade HFSX folder-count metadata. Check
    # and repair only this newly created copy before treating it as deliverable.
    entities=plistlib.loads(subprocess.check_output(['hdiutil','attach','-readwrite',
       '-nomount','-noverify','-imagekey','diskimage-class=CRawDiskImage','-plist',str(output)]))['system-entities']
    device=next(e['dev-entry'] for e in entities if e.get('dev-entry'))
    try:
        raw=device.replace('/dev/disk','/dev/rdisk')
        checked=subprocess.run(['/sbin/fsck_hfs','-fy',raw],capture_output=True,text=True)
        output.with_suffix(output.suffix+'.fsck.log').write_text(checked.stdout+checked.stderr)
        if checked.returncode:raise RuntimeError('New output failed fsck_hfs; inspect its .fsck.log')
        subprocess.run(['/sbin/fsck_hfs','-fn',raw],check=True)
    finally:subprocess.run(['hdiutil','detach',device],check=True)
    report={'source':str(source),'output':str(output),'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
            'permissions':permissions,'scope':'one-shot private16x16 Mali userspace test; no GLES or compositor change'}
    output.with_suffix(output.suffix+'.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
