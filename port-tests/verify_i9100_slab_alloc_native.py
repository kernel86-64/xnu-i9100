#!/usr/bin/env python3
"""Verify slab_alloc frame recovery against unchanged supplied iOS ARM code.

RAM/list state and the __assert_rtn import are modeled. This does not identify
the writer in assertion2.jpg and does not modify or redistribute Apple images.
"""
import argparse
import hashlib
from pathlib import Path
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import *


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,required=True)
    args=parser.parse_args()
    data=args.cache.read_bytes()
    assert hashlib.sha256(data).hexdigest()=='cad2df775e122c660238f341e74c163a2ea0ed261e85bfd3190de750cd9c0d2c'
    offset,count=struct.unpack_from('<2I',data,16)
    maps=[struct.unpack_from('<3Q2I',data,offset+32*n) for n in range(count)]
    for alignment in (0,8):
        for bad in (False,True):
            u=Uc(UC_ARCH_ARM,UC_MODE_THUMB)
            u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A9)
            for va,size,file,_,_ in maps:
                u.mem_map(va,size)
                if va<=0x2f8f8000<va+size:
                    for start in (0x2f8f8000,0x38168000):
                        u.mem_write(start,data[file+start-va:file+start-va+4096])
                else:
                    u.mem_write(va,data[file:file+size])
            u.mem_map(0x10000000,0x10000)
            u.mem_map(0x12000000,0x10000)
            # Enable the real A9 NEON register bank needed by this prologue.
            u.cpr_write(15,0,1,0,2,0,False,0xf00000)
            u.reg_write(UC_ARM_REG_FPEXC,1<<30)
            context,candidate,bucket=0x10000000,0x10003000,7
            link=context+bucket*32+0x60
            expected=0xdeafbe00|bucket
            u.mem_write(link,struct.pack('<I',candidate))
            u.mem_write(candidate,struct.pack('<IIIHHI',link-4,link-4,candidate+0x100,10,0,
                                             0x12345678 if bad else expected))
            u.mem_write(candidate+0x100,bytes(4))
            asserted=False

            def hook(u,address,size,unused):
                nonlocal asserted
                if address==0x2fa16410:
                    asserted=True
                    u.reg_write(UC_ARM_REG_PC,0x38168bf9)
                elif address==0x38168c02:
                    assert_fp=u.reg_read(UC_ARM_REG_R7)
                    allocator_fp=struct.unpack('<I',u.mem_read(assert_fp,4))[0]
                    local=((allocator_fp+8-48)&~15)-112
                    slots=struct.unpack('<2I',u.mem_read(local+36,8))
                    assert slots==(link,expected)
                    assert struct.unpack('<I',u.mem_read(slots[0],4))[0]==candidate
                    assert struct.unpack('<I',u.mem_read(candidate+16,4))[0]==0x12345678
                    u.emu_stop()
                elif address==0x1200f000:
                    u.emu_stop()

            u.hook_add(UC_HOOK_CODE,hook)
            u.reg_write(UC_ARM_REG_R0,context);u.reg_write(UC_ARM_REG_R1,bucket)
            u.reg_write(UC_ARM_REG_SP,0x1000f000+alignment)
            u.reg_write(UC_ARM_REG_LR,0x1200f001)
            u.emu_start(0x2f8f8325,0x1200f000,count=10000)
            assert asserted==bad
            if not bad:
                assert u.reg_read(UC_ARM_REG_PC)==0x1200f000
                assert u.reg_read(UC_ARM_REG_R0)==candidate+0x100
    print('PASS: unchanged native slab_alloc/assert prologues, both8/16-byte entry alignments; good page returns object, bad magic reaches original assertion and exact localSP/link/expected/candidate recovery. No physical writer claim.')


if __name__=='__main__':
    main()
