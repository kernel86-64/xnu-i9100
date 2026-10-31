#!/usr/bin/env python3
"""Execute linked ARM partial-page copy, then the supplied native slab_dealloc.

Kernel and Apple instructions are unmodified. RAM/mapping and the assertion
boundary are modeled. A reproduction of a possible corruption mechanism does
not identify the writer in a physical-device crash.
"""
import argparse
import hashlib
from pathlib import Path
import random
import re
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import *
from verify_i9100_trace_native import Kernel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--assym', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    args = parser.parse_args()
    cache = args.cache.read_bytes()
    assert hashlib.sha256(cache).hexdigest() == 'cad2df775e122c660238f341e74c163a2ea0ed261e85bfd3190de750cd9c0d2c'
    offset, count = struct.unpack_from('<2I', cache, 16)
    maps = [struct.unpack_from('<3Q2I', cache, offset+i*32) for i in range(count)]
    offsets = {name: int(value) for name, value in re.findall(
        r'^#define (\w+_NUM)\s+(\d+)', args.assym.read_text(), re.M)}

    def native_dealloc(page):
        u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A9)
        for va, size, file, _, _ in maps:
            u.mem_map(va, size)
            for code in (0x2f918000, 0x38168000):
                if va <= code < va+size:
                    start = file+code-va
                    u.mem_write(code, cache[start:start+4096])
        u.mem_map(0x10000000, 0x10000)
        u.mem_write(0x10000000, page)
        u.mem_map(0x12000000, 0x10000)
        asserted = False

        def hook(u, address, size, unused):
            nonlocal asserted
            if address == 0x2fa16410:  # native ___assert_rtn import boundary
                asserted = True
                u.reg_write(UC_ARM_REG_PC, 0x38168bf9)
            elif address == 0x38168c02:  # after the actual assertion prologue
                fp = u.reg_read(UC_ARM_REG_R7)
                assert struct.unpack('<I', u.mem_read(fp-16, 4))[0] == 0x10008000
                assert struct.unpack('<I', u.mem_read(fp-4, 4))[0] == 0xdeafbe01
                u.emu_stop()
            elif address == 0x1200f000:
                u.emu_stop()

        u.hook_add(UC_HOOK_CODE, hook)
        for reg, value in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2),
                              (0x10008000, 0x10000100, 1)):
            u.reg_write(reg, value)
        u.reg_write(UC_ARM_REG_SP, 0x1000f000)
        u.reg_write(UC_ARM_REG_R8, 0x10008000)
        u.reg_write(UC_ARM_REG_LR, 0x1200f001)
        u.emu_start(0x2f918a75, 0x1200f000, count=10000)
        assert u.reg_read(UC_ARM_REG_PC) in (0x38168c02, 0x1200f000)
        return asserted

    kernels = [Kernel(path, offsets) for path in (args.before, args.kernel)]
    for kernel in kernels:
        kernel.put(kernel.symbols['_gPhysBase'][0], 0x22000000)
        kernel.put(kernel.symbols['_gVirtBase'][0], 0x81000000)

    def copy(kernel, source, destination, size, mask, same=False):
        kernel.u.mem_write(0x100ff000, struct.pack('<I', size))
        return kernel.call('_pmap_copy_part_page',
            (0x22008, source, 0x22008 if same else 0x2200a, destination), mask)

    for index, kernel in enumerate(kernels):
        source = bytearray(b'\x55'*4096)
        destination = bytearray(b'\x66'*4096)
        struct.pack_into('<I', source, 16, 0xdeadf00d)
        struct.pack_into('<I', destination, 8, 0x10000400)
        struct.pack_into('<H', destination, 14, 2)
        struct.pack_into('<I', destination, 16, 0xdeafbe01)
        kernel.u.mem_write(0x81008000, bytes(source))
        kernel.u.mem_write(0x8100a000, bytes(destination))
        copy(kernel, 16, 512, 4, 0)
        result = bytes(kernel.u.mem_read(0x8100a000, 4096))
        asserted = native_dealloc(result)
        assert asserted == (index == 0)
        print(('OLD' if index == 0 else 'FIXED')+': native slab_dealloc assertion='+str(asserted)
              +', magic='+hex(struct.unpack_from('<I', result, 16)[0]))
    randoms = random.Random(25)
    kernel = kernels[1]
    total = 0
    for mask in (0, 0x40, 0x80, 0xc0):
        for same in (False, True):
            for _ in range(40):
                src, dst = randoms.randrange(4096), randoms.randrange(4096)
                size = randoms.randrange(1, min(4096-src, 4096-dst)+1)
                data = bytes((i*19+(i>>3))&255 for i in range(0x5000))
                reference = bytearray(data)
                destination = 0x1000 if same else 0x3000
                reference[destination+dst:destination+dst+size] = data[0x1000+src:0x1000+src+size]
                kernel.u.mem_write(0x81007000, data)
                copy(kernel, src, dst, size, mask, same)
                assert bytes(kernel.u.mem_read(0x81007000, len(data))) == reference
                total += 1
    print('PASS:', total, 'actual linked ARM helper+bcopy cases, all4 masks, overlap/whole-buffer guards;'
          ' old corruption triggers supplied native slab assertion, fixed copy preserves it;'
          ' physical causality remains unproven')


if __name__ == '__main__':
    main()
