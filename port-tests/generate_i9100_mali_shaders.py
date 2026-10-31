#!/usr/bin/env python3
"""Encode fixed GPU28/GPU30 test programs, not a GLSL compiler.

Bit layouts: Mesa mesa-24.3.4 Lima ir/{gp,pp}/codegen.h (MIT).
GP copies already viewport-transformed vec4 positions via two MUL-by-one
instructions; PP returns a literal RGBA vec4. No Apple shader code is used.
"""
import argparse
from pathlib import Path
import struct

GP = [('mul0_src0',5),('mul0_src1',5),('mul1_src0',5),('mul1_src1',5),
      ('mul0_neg',1),('mul1_neg',1),('acc0_src0',5),('acc0_src1',5),
      ('acc1_src0',5),('acc1_src1',5),('acc0_src0_neg',1),('acc0_src1_neg',1),
      ('acc1_src0_neg',1),('acc1_src1_neg',1),('load_addr',9),('load_offset',3),
      ('register0_addr',4),('register0_attribute',1),('register1_addr',4),
      ('store0_temporary',1),('store1_temporary',1),('branch',1),('branch_target_lo',1),
      ('store0_src_x',3),('store0_src_y',3),('store1_src_z',3),('store1_src_w',3),
      ('acc_op',3),('complex_op',4),('store0_addr',4),('store0_varying',1),
      ('store1_addr',4),('store1_varying',1),('mul_op',3),('pass_op',3),
      ('complex_src',5),('pass_src',5),('unknown_1',4),('branch_target',8)]


def pack(fields, values):
    result = offset = 0
    for name, width in fields:
        value = values.get(name, 0)
        assert 0 <= value < 1 << width, name
        result |= value << offset
        offset += width
    return result


def programs():
    default = {name:21 for name in ('mul0_src0','mul0_src1','mul1_src0','mul1_src1',
                                   'acc0_src0','acc0_src1','acc1_src0','acc1_src1',
                                   'complex_src','pass_src')}
    default.update(load_offset=7,pass_op=2,register0_attribute=1,
                   store0_src_x=7,store0_src_y=7,store1_src_z=7,store1_src_w=7)
    vs = []
    for pair in (0, 1):
        values = dict(default, mul0_src0=2*pair,mul0_src1=22,
                      mul1_src0=2*pair+1,mul1_src1=22)
        if not pair:
            values.update(store0_src_x=2,store0_src_y=3,store0_varying=1)
        else:
            values.update(store1_src_z=2,store1_src_w=3,store1_varying=1)
        vs += list(struct.unpack('<4I', pack(GP,values).to_bytes(16,'little')))
    result = {'gpu28_vs':vs}
    values=dict(default,register0_addr=1,mul0_src0=0,mul0_src1=22,
                mul1_src0=1,mul1_src1=22,store0_src_x=2,store0_src_y=3,
                store0_addr=1,store0_varying=1)
    result['gpu30_vs_uv']=vs+list(struct.unpack('<4I',pack(GP,values).to_bytes(16,'little')))
    # Single PP VADD MOV: $0.xyzw = ^const0.xyzw, with stop.
    acc = pack([('arg0_source',4),('arg0_swizzle',8),('arg0_absneg',2),
                ('arg1_source',4),('arg1_swizzle',8),('arg1_absneg',2),
                ('dest',4),('mask',4),('modifier',2),('op',5),('mul_in',1)],
               {'arg0_source':12,'arg0_swizzle':0xe4,'mask':15,'op':31})
    for name, color in [('red',(1,0,0,1)),('green',(0,1,0,1))]:
        literal=int.from_bytes(struct.pack('<4e',*color),'little')
        payload=(acc | literal << 44).to_bytes(16,'little')
        result['gpu28_fs_'+name]=[5 | 1<<5 | ((1<<5)|(1<<10))<<7,
                                *struct.unpack('<4I',payload)]
    # PP varying vec2 -> sampler0 -> MOV ^texture to color0, in one bundle.
    varying=pack([('perspective',2),('source_type',2),('unknown0',1),('alignment',2),
                  ('unknown1',3),('offset_vector',4),('unknown2',2),('offset_scalar',2),
                  ('index',6),('dest',4),('mask',4),('unknown3',2)],
                 {'alignment':1,'offset_vector':15,'dest':15,'mask':3})
    sampler=0x39001 << 42
    texture_acc=(acc&~15)|14
    payload=(varying | sampler<<34 | texture_acc<<96).to_bytes(20,'little')
    result['gpu30_fs_texture']=[6 | 1<<5 | 1<<6 | ((1<<0)|(1<<1)|(1<<5))<<7,
                              *struct.unpack('<5I',payload)]
    # Mesa lima_tex_desc, linear normalized2D nearest/clamp, mip0 only.
    fields=[('format',6),('flag1',1),('swap_r_b',1),('unknown01',8),('stride',15),('unknown02',1),
            ('unknown11',7),('unnorm_coords',1),('unknown12',1),('cube',1),('sampler_dim',2),
            ('min_lod',8),('max_lod',8),('lod_bias',9),('unknown21',3),('has_stride',1),
            ('min_mipfilter',2),('min_nearest',1),('mag_nearest',1),
            ('wrap_s',3),('wrap_t',3),('wrap_r',3),('width',13),('height',13),('depth',13),
            ('border_red',16),('border_green',16),('border_blue',16),('border_alpha',16),
            ('unknown51',3),('unknown61',13),('layout',2),('unknown62',15),('va0',26)]
    descriptor=pack(fields,{'format':0x16,'stride':64,'sampler_dim':1,'lod_bias':8,'has_stride':1,
                            'min_nearest':1,'mag_nearest':1,'wrap_s':1,'wrap_t':1,'wrap_r':1,
                            'width':2,'height':2,'depth':1,'va0':0x0100b400>>6})
    result['gpu30_texture_desc']=list(struct.unpack('<16I',descriptor.to_bytes(64,'little')))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',action='store_true')
    args=p.parse_args()
    root=Path(__file__).resolve().parent.parent
    target=root/'iokit/Drivers/KernelBuiltIn/ARM/AppleARMPlatform/i9100_mali_shaders.h'
    notice=(target.parent/'i9100_mali.c').read_text().split(' * Copyright',1)[1].split(' */',1)[0]
    out='/* Generated by tools/generate_i9100_mali_shaders.py. Fixed test shaders.\n * Copyright'+notice+' */\n'
    out+='#ifndef I9100_MALI_SHADERS_H\n#define I9100_MALI_SHADERS_H\n'
    for name,words in programs().items():
        out+='static const uint32_t '+name+'['+str(len(words))+'] = {\n '
        out+=', '.join('0x%08xU'%v for v in words)+'\n};\n'
    out+='#endif\n'
    if args.check:
        assert target.read_text()==out,'Generated shader header is stale'
        print('PASS: fixed GP/PP shader encodings reproducible.')
    else:
        target.write_text(out)
        print(target)


if __name__=='__main__':
    main()
