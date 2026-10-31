#!/usr/bin/env python3
"""Measure original linked ARM lock observers before/after a lookup optimization.

Unicorn executes the kernel's own helpers without instruction patches. Thread
and CPU storage are modeled with offsets supplied by matching assym.s. Counts
describe executed instructions/table reads, not physical Exynos latency or FPS.
"""
import argparse
from pathlib import Path
import re
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.arm_const import *

REGS = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)


class Kernel:
    def __init__(self, path, offsets):
        self.path = path
        self.offsets = offsets
        data = path.read_bytes()
        assert struct.unpack_from('<I', data)[0] == 0xfeedface
        pos, segments = 28, []
        for _ in range(struct.unpack_from('<I', data, 16)[0]):
            cmd, size = struct.unpack_from('<2I', data, pos)
            if cmd == 1:
                segments.append(struct.unpack_from('<4I', data, pos+24))
            if cmd == 2:
                symoff, count, strings, _ = struct.unpack_from('<4I', data, pos+8)
            pos += size
        self.symbols = {}
        for i in range(count):
            si, typ, section, desc, addr = struct.unpack_from('<IBBHI', data, symoff+12*i)
            if si and not typ & 0xe0 and typ & 0xe == 0xe:
                name = data[strings+si:data.index(b'\0', strings+si)].decode()
                self.symbols[name] = (addr & ~1, desc)
        self.u = u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A9)
        base = min(va for va, size, off, fs in segments if size) & ~4095
        end = max(va+size for va, size, off, fs in segments)
        assert 0 < end-base < 32*1024*1024
        u.mem_map(base, (end-base+4095) & ~4095)
        for va, size, off, fs in segments:
            if fs:
                u.mem_write(va, data[off:off+fs])
        u.mem_map(0x10000000, 0x100000)
        u.mem_map(0x12000000, 0x10000)
        u.mem_map(0x81000000, 0x10000)
        self.thread, self.cpu = 0x81000000, 0x81002000
        self.put(self.thread+offsets['MACHINE_THREAD_PREEMPT_COUNT_NUM'], 1)
        self.put(self.thread+offsets['MACHINE_THREAD_CPU_DATA_NUM'], self.cpu)
        u.reg_write(UC_ARM_REG_CPSR, 0x13)
        # Initialize the bank actually read by the kernel's MRC, rather than
        # assuming the emulator's coprocessor-register security-bank selector.
        u.mem_write(0x12000000, struct.pack('<I', 0xee0d0f90))  # MCR p15,0,r0,c13,c0,4
        u.reg_write(UC_ARM_REG_R0, self.thread)
        u.emu_start(0x12000000, 0x12000004, count=1)
        self.tables = []
        for name, size in [('_i9100_spin_records', 2048*24), ('_i9100_scope_records', 1024*20)]:
            self.tables.append((self.symbols[name][0], size))
        self.instructions = self.reads = 0
        u.hook_add(UC_HOOK_CODE, self.code)
        u.hook_add(UC_HOOK_MEM_READ, self.read)

    def put(self, addr, value):
        self.u.mem_write(addr, struct.pack('<I', value & 0xffffffff))

    def word(self, addr):
        return struct.unpack('<I', self.u.mem_read(addr, 4))[0]

    def code(self, u, address, size, unused):
        if address == 0x1200f000:
            u.emu_stop()
        else:
            self.instructions += 1

    def read(self, u, access, address, size, value, unused):
        if any(base <= address < base+length for base, length in self.tables):
            self.reads += 1

    def call(self, name, args, mask):
        u = self.u
        start, desc = self.symbols[name]
        for reg, value in zip(REGS, args):
            u.reg_write(reg, value)
        u.reg_write(UC_ARM_REG_CPSR, 0x13 | mask)
        u.reg_write(UC_ARM_REG_SP, 0x100ff000)
        u.reg_write(UC_ARM_REG_LR, 0x1200f001)
        before = self.instructions, self.reads
        try:
            u.emu_start(start | (1 if desc & 8 else 0), 0x1200f000, count=100000)
        except Exception:
            print('Native failure:', self.path, name, 'PC', hex(u.reg_read(UC_ARM_REG_PC)),
                  'LR', hex(u.reg_read(UC_ARM_REG_LR)),
                  'r0-r3', [hex(u.reg_read(reg)) for reg in REGS], flush=True)
            raise
        assert u.reg_read(UC_ARM_REG_PC) == 0x1200f000, hex(u.reg_read(UC_ARM_REG_PC))
        assert u.reg_read(UC_ARM_REG_CPSR) & 0xc0 == mask
        return self.instructions-before[0], self.reads-before[1]

    def roundtrip(self, mask):
        counts = [0, 0]
        calls = [('_i9100_preempt_enter', (self.thread, 0x80001001, 0, 0x80002000)),
                 ('_i9100_preempt_leave', (self.thread,)),
                 ('_i9100_spin_acquired', (0x81004000, 0x80001001, 0, self.thread)),
                 ('_i9100_spin_forget', (0x81004000, 0x80001001, 2, self.thread))]
        for name, args in calls:
            result = self.call(name, args, mask)
            counts = [a+b for a, b in zip(counts, result)]
        assert self.word(self.thread+self.offsets['MACHINE_THREAD_PREEMPT_COUNT_NUM']) == 1
        assert self.word(0x81004000) == 0  # Observers never modify the lock itself.
        return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--assym', type=Path, required=True)
    args = parser.parse_args()
    offsets = {name:int(value) for name,value in re.findall(
        r'^#define (\w+_NUM)\s+(\d+)', args.assym.read_text(), re.M)}
    old, new = Kernel(args.before, offsets), Kernel(args.kernel, offsets)
    old.roundtrip(0)
    new.roundtrip(0)
    totals = [0, 0], [0, 0]
    for mask in (0, 0x40, 0x80, 0xc0):
        for _ in range(100):
            for index, kernel in enumerate((old, new)):
                result = kernel.roundtrip(mask)
                for field in range(2):
                    totals[index][field] += result[field]
    before, after = totals
    assert after[0] < before[0] and after[1] < before[1], totals
    print('Actual linked observer instructions before/after:', before[0], after[0])
    print('Actual table reads before/after:', before[1], after[1])
    print('Instruction reduction %.1f%%; table-read reduction %.1f%%' % (
        100*(1-after[0]/before[0]), 100*(1-after[1]/before[1])))
    # Execute the actual linked Clang Thumb callbacks used around touchscreen
    # I2C transfers, through real ARM disable/enable_preemption and observers.
    # No GPIO/controller behavior is modeled by this callback-only check.
    for kernel in (old, new):
        for mask in (0, 0x40, 0x80, 0xc0):
            for nesting in (0, 1):
                offset = offsets['MACHINE_THREAD_PREEMPT_COUNT_NUM']
                kernel.put(kernel.thread+offset, nesting)
                kernel.call('__ZN17IOHIDEventService18beginTouchTransferEPv', (0,), mask)
                assert kernel.word(kernel.thread+offset) == nesting+1
                kernel.call('__ZN17IOHIDEventService16endTouchTransferEPv', (0,), mask)
                assert kernel.word(kernel.thread+offset) == nesting
    print('PASS: actual linked touch transfer callbacks preserve all I/F masks and nested preemption before/after')
    print('PASS:400 real native observer roundtrips preserve all I/F masks, preempt count and lock data; phone timing/touch remain untested')


if __name__ == '__main__':
    main()
