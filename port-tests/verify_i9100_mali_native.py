#!/usr/bin/env python3
"""Execute the linked Mali arena builder and check GPU page permissions/wire data.

This runs real kernel ARM instructions with RAM modeled by Unicorn. It does not
execute Mali shaders or claim a physical render result.
"""
import argparse
from pathlib import Path
import re
import struct
from verify_i9100_trace_native import Kernel
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_CPSR,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel',type=Path,required=True)
    parser.add_argument('--assym',type=Path,required=True)
    args=parser.parse_args()
    offsets={name:int(value) for name,value in re.findall(r'^#define (\w+_NUM)\s+(\d+)',args.assym.read_text(),re.M)}
    k=Kernel(args.kernel,offsets)
    address,physical=0x10020000,0x42000000
    start,desc=k.symbols['_build_arena']
    snapshots=[]
    for mask in (0,0x40,0x80,0xc0):
        k.u.mem_write(address-32,b'\xa5'*(65536+64))
        k.u.reg_write(UC_ARM_REG_R0,address);k.u.reg_write(UC_ARM_REG_R1,physical)
        k.u.reg_write(UC_ARM_REG_CPSR,0x13|mask)
        k.u.reg_write(UC_ARM_REG_SP,0x100ff000);k.u.reg_write(UC_ARM_REG_LR,0x1200f001)
        k.u.emu_start(start|(1 if desc&8 else 0),0x1200f000,count=2000000)
        assert k.u.reg_read(UC_ARM_REG_PC)==0x1200f000
        assert k.u.reg_read(UC_ARM_REG_CPSR)&0xc0==mask
        assert bytes(k.u.mem_read(address-32,32))==b'\xa5'*32
        assert bytes(k.u.mem_read(address+65536,32))==b'\xa5'*32
        data=bytes(k.u.mem_read(address,65536));snapshots.append(data)
        words=struct.unpack('<16384I',data)
        assert [(i,value) for i,value in enumerate(words[:1024]) if value]==[(4,physical+4096+1)]
        assert words[1024:1026]==(0,0)
        for page in range(2,12):
            assert words[1024+page]==physical+page*4096+(3 if page in (2,11) else 7)
        assert not any(words[1036:2048])
        assert words[0x2000//4:0x2030//4]==(0x200,0x1000010b,0,0x1000010c,0,0x10000109,
                                                  1,0x30000000,0x01002100,0x28000001,0,0x50000000)
        assert words[0x2180//4+1]==0xb8000000 and words[0x2180//4+5]==0xbc000000
        assert words[0x2200//4+8]==0xf008 and words[0x2200//4+9]==0x01002240
        assert words[0x2240//4:0x2240//4+8]==(0x00020425,0x0000000c,0x01e007cf,0xb0000000,0x000005f5,0,0,0)
        from generate_i9100_mali_shaders import programs
        for name,offset in [('gpu28_vs',0x2600),('gpu28_fs_red',0x2800),('gpu28_fs_green',0x2840),('gpu30_vs_uv',0x2d00),('gpu30_fs_texture',0x2f00),('gpu30_texture_desc',0xb000)]:
            program=programs()[name]
            assert list(words[offset//4:offset//4+len(program)])==program
        for index in (0,1):
            command_start=0x2300+index*0xc0
            assert words[(command_start+144)//4:(command_start+152)//4]==(0,0x50000000)
            assert words[(command_start+128)//4:(command_start+136)//4]==(3<<24,4<<16)
            vs=0x2500+index*0x80
            assert words[(vs+16)//4:(vs+32)//4]==(0x01002680,0x30020000,0x01002600,0x40020000)
            assert words[(vs+72)//4:(vs+80)//4]==(3<<24,0)
            assert words[(0x2640+index*16)//4:(0x2640+index*16)//4+2]==(0x01002700+index*0x40,0x8003)
            assert words[(0x2880+index*0x40)//4+9]==(0x01002800+index*0x40)|5
        assert words[0x2660//4:0x2660//4+2]==(0x0100a080,0x8020)
        assert words[0x2a00//4:0x2a00//4+4]==(0x01002c00,0x8003,0x01002c80,0x8001)
        assert words[0x2a40//4:0x2a40//4+4]==(0x0100a080,0x8020,0x0100a180,0x8001)
        assert words[0x2d80//4+7]==0x40030000 and words[0x2d80//4+18]==6<<24
        assert words[0x2e00//4+22]==0x01002ec0 and words[0xb200//4+22]==0x0100b0c0
        assert words[0x2ec0//4+9]==0x01002f06 and words[0x2ec0//4+12]==0x01002f80
        assert words[0x2ec0//4+13]==0x5322 and words[0x2ec0//4+15]==0x0100a180
        assert words[0xb0c0//4+2]==0xfc8bc2d2 and words[0xb0c0//4+13]==0x4322
        assert words[0x2f80//4]==0x0100b000
        assert not any(words[0x3000//4:0xb000//4])
        assert all(value==0x5aa5c33c for value in words[0xc000//4:])
    assert all(data==snapshots[0] for data in snapshots)
    print('PASS: actual linked ARM Mali arena builder, all4 I/F masks; private PD/PT, unmapped guards/RO commands/RW data, GP/PP streams, Mesa clear shader and generated VS/triangle/texture/fragment programs, descriptor and premultiplied blend state. No physical Mali execution.')


if __name__=='__main__':
    main()
