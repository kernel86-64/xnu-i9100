#!/usr/bin/env python3
"""Run the linked ARM syscall marshaler and inspect its real syscall table."""
import argparse
from pathlib import Path
import re
import struct
from verify_i9100_trace_native import Kernel
from unicorn.arm_const import UC_ARM_REG_R0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--assym', type=Path, required=True)
    args = parser.parse_args()
    offsets = {name:int(value) for name,value in re.findall(
        r'^#define (\w+_NUM)\s+(\d+)', args.assym.read_text(), re.M)}
    k = Kernel(args.kernel, offsets)
    table = k.symbols['_sysent'][0]
    count = k.word(k.symbols['_nsysent'][0])
    assert 400 < count < 1024
    entries = [struct.unpack('<hbbIIIIH2x', k.u.mem_read(table+i*24,24)) for i in range(count)]
    assert max(e[0] for e in entries) <= 12
    for number, name in [(303,'_psynch_cvbroad'),(304,'_psynch_cvsignal'),(305,'_psynch_cvwait')]:
        e = entries[number]
        assert e[0] == 11 and e[-1] == 44
        assert e[3] & ~1 == k.symbols[name][0]
    address, registers = 0x10010000, 0x10011000
    words = [0x12340000+n*0x111 for n in range(13)]
    k.u.mem_write(registers, struct.pack('<13I', *words))
    cases = 0
    for mask in (0,0x40,0x80,0xc0):
        for indirect in (0,1):
            for capacity in range(13):
                for size in range(17):
                    k.u.mem_write(address-16, b'\xa5'*112)
                    k.u.mem_write(0x100ff000, struct.pack('<I',indirect))
                    k.call('_arm_syscall_store_args',(address,capacity,registers,size),mask)
                    rejected = size > capacity or size > 12-indirect
                    assert k.u.reg_read(UC_ARM_REG_R0) == (22 if rejected else 0)
                    expected = bytearray(b'\xa5'*112)
                    if not rejected:
                        expected[16:16+size*4] = struct.pack('<'+'I'*size,*words[indirect:indirect+size])
                    assert bytes(k.u.mem_read(address-16,112)) == expected
                    cases += 1
    print(f'PASS: actual linked ARM marshaler {cases} exact-buffer cases/all4 masks;'
          f' actual sysent{count} entries max args{max(e[0] for e in entries)};'
          ' all3 CV handlers require11 words/44 bytes. No physical crash-causality claim.')


if __name__ == '__main__':
    main()
