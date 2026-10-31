#!/usr/bin/env python3
"""Execute unchanged linked ARM ref/mod queries/clear paths against PV RAM.

Actual pmap/PV/short-descriptor layouts are modeled; no instructions are patched
and no physical-device causality or complete VM/pageout emulation is claimed.
"""
import argparse
from pathlib import Path
import re
import struct
from unicorn.arm_const import UC_ARM_REG_R0
from verify_i9100_trace_native import Kernel


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',type=Path,required=True)
    p.add_argument('--kernel',type=Path,required=True)
    p.add_argument('--assym',type=Path,required=True)
    args=p.parse_args()
    offsets={n:int(v) for n,v in re.findall(r'^#define (\w+_NUM)\s+(\d+)',args.assym.read_text(),re.M)}
    old,new=[Kernel(path,offsets) for path in (args.before,args.kernel)]
    pn,root,node,owner,l1,l2=0x42001,0x10004018,0x10005000,0x10006000,0x10008000,0x1000b000

    def initialize(k,readonly=False,alias=False):
        for name,value in [('_gPhysBase',0x42000000),('_gVirtBase',0x10000000),
                           ('_avail_start',0x42000000),('_avail_end',0x42010000),
                           ('_pmap_initialized',1),('_pv_head_hash_table',0x10004000),
                           ('_i9100_scanout_start',0x42002000),('_i9100_scanout_end',0x42003000)]:
            k.put(k.symbols[name][0],value)
        # PV common prefix: qlink, va, pmap, mapping_wired, flags (24 bytes).
        k.u.mem_write(root,struct.pack('<6I',node if alias else root,node if alias else root,
                                      0x1000,owner,0,0x18))
        k.u.mem_write(node,struct.pack('<7I',root,root,0x2000,owner,0,pn,0))
        k.put(owner+4,l1);k.put(l1,0x4200b001)
        k.put(l2+4,(pn<<12)|0x7e|(0x200 if readonly else 0))
        k.put(l2+8,(pn<<12)|0x7e)

    def call(k,name,values,mask):
        k.call(name,values,mask)
        assert k.word(k.thread+offsets['MACHINE_THREAD_PREEMPT_COUNT_NUM'])==1
        return k.u.reg_read(UC_ARM_REG_R0)

    cases=0
    for mask in (0,0x40,0x80,0xc0):
        for alias in (False,True):
            for readonly in (False,True):
                for k in (old,new):initialize(k,readonly,alias)
                assert call(old,'_pmap_get_refmod',(pn,),mask)==0
                expected=3 if alias or not readonly else 2
                assert call(new,'_pmap_get_refmod',(pn,),mask)==expected
                assert call(new,'_pmap_is_modified',(pn,),mask)==int(bool(expected&1))
                assert call(new,'_pmap_is_referenced',(pn,),mask)==1
                call(new,'_pmap_clear_refmod',(pn,3),mask)
                assert new.word(root+20)==0x18
                assert call(new,'_pmap_get_refmod',(pn,),mask)==expected
                # Simulate retirement after harvesting: no tracked VA remains.
                new.put(root,root);new.put(root+12,0)
                assert call(new,'_pmap_get_refmod',(pn,),mask)==expected
                call(new,'_pmap_clear_modify',(pn,),mask)
                call(new,'_pmap_clear_reference',(pn,),mask)
                assert call(new,'_pmap_get_refmod',(pn,),mask)==0
                assert new.word(root+20)==0x18
                cases+=1
        initialize(new)
        new.put(l2+4,0x4200207e)  # stale PV must not harvest another PA.
        assert call(new,'_pmap_get_refmod',(pn,),mask)==0
        assert call(new,'_pmap_get_refmod',(0x11c00,),mask)==0
        assert call(new,'_pmap_get_refmod',(0x42002,),mask)==0
        cases+=3
    print(f'PASS: {cases} actual linked ARM ref/mod cases; old writable-alias false-negative reproduced, new RO/RW/hashed aliases, clear/reharvest, retained flags, unrelated attributes, stale-PTE/MMIO/scanout exclusion; all4 I/F masks and nested preemption preserved. RAM model, not phone proof.')


if __name__=='__main__':
    main()
