#!/usr/bin/env python3
"""Execute linked UI exit/signal publishers, including their raw CPSR guards.

Kernel code runs unchanged in Unicorn. RAM and a current thread/CPU are modeled
by verify_i9100_trace_native.Kernel; no signal-delivery behavior is simulated.
"""
import argparse
from pathlib import Path
import re
import struct
from verify_i9100_trace_native import Kernel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--assym', type=Path, required=True)
    args = parser.parse_args()
    offsets = {name: int(value) for name, value in re.findall(
        r'^#define (\w+_NUM)\s+(\d+)', args.assym.read_text(), re.M)}
    k = Kernel(args.kernel, offsets)
    name = 0x10008000
    k.u.mem_write(name, b'launchd\0')
    pending = k.symbols['_i9100_signal_pending'][0]
    retained = k.symbols['_i9100_signal_exit'][0]
    sbexit = k.symbols['_i9100_process_exit'][0]
    bbexit = k.symbols['_i9100_backboard_exit'][0]
    # ARM32 ABI: ten unsigned words + char[17], padded to 4-byte alignment.
    request_size = 60

    def call(function, values, mask):
        k.u.mem_write(0x100ff000, struct.pack('<'+'I'*len(values[4:]), *values[4:]))
        k.call(function, values[:4], mask)

    for mask in (0, 0x40, 0x80, 0xc0):
        call('_ios7i9100_signal_request',
             (32, 0x81006000, 15, 1, name, 0x37001000, 0x74e7, 0x80123457, 0, 0), mask)
        call('_ios7i9100_signal_request',
             (32, 0x81006000, 9, 2, name, 0x37001000, 0x74e9, 0x80123499, 0, 1), mask)
        assert k.word(pending) and k.word(pending+request_size)
        call('_ios7i9100_process_exit',
             (1, 32, 0x81006000, 15, 0, 1, 0, 0, 0, 173214), mask)
        assert k.word(sbexit+4) == 32 and k.word(sbexit+8) == 15
        assert k.word(sbexit+32) == 173214
        assert not k.word(pending) and not k.word(pending+request_size)
        assert struct.unpack('<10I', k.u.mem_read(retained, 40))[1:] == (
            32, 0x81006000, 15, 1, 0x37001000, 0x74e7, 0x80123457, 0, 0)
        assert bytes(k.u.mem_read(retained+40, 17)) == b'launchd'+b'\0'*10
        snapshot = bytes(k.u.mem_read(retained, request_size))
        call('_ios7i9100_process_exit',
             (2, 31, 0x81007000, 11, 0, 1, 1, 2, 0x12345678, 173200), mask)
        assert k.word(bbexit+4) == 31 and k.word(bbexit+28) == 0x12345678
        assert bytes(k.u.mem_read(retained, request_size)) == snapshot
    if '_ios7i9100_abort_publish' in k.symbols:
        trace = 0x10009000
        stderr = 0x1000a000
        observation = k.symbols['_i9100_abort_observation'][0]
        # I9100AbortTrace: eight scalar fields, eight frames, five slab fields.
        k.u.mem_write(trace, struct.pack('<21I', 17, 0x81006000, 0x38001000,
            0x38188fdd, 0x10001000, 0x10001020, 2, 0,
            0x374b7cd7, 0x2d400001, 0, 0, 0, 0, 0, 0,
            0x10008000, 0x10008100, 0xdeafbe01, 0xdeadf00d, 1))
        maximum = 0
        for mask in (0, 0x40, 0x80, 0xc0):
            text = b"*** Terminating app due to uncaught exception 'NSException', reason: native test\n"
            for chunk in (text[i:i+32] for i in range(0, len(text), 32)):
                k.u.mem_write(stderr, chunk)
                instructions, _ = k.call('_ios7i9100_stderr_bytes',
                    (17, 0x81006000, stderr, len(chunk)), mask)
                maximum = max(maximum, instructions)
            k.u.mem_write(stderr, b'footer after the reason\n')
            k.call('_ios7i9100_stderr_bytes', (17, 0x81006000, stderr, 24), mask)
            k.call('_ios7i9100_abort_publish', (trace,), mask)
            assert k.word(observation+4) == 17 and k.word(observation+88) == 1
            assert k.word(observation+80) == 0xdeadf00d and k.word(observation+84) == 1
            assert b'reason: native test' in bytes(k.u.mem_read(observation+92, 241))
            call('_ios7i9100_signal_request',
                (17, 0x81006000, 6, 17, name, 0x38001000, 0x38188fdd, 0x80123457, 0, 4), mask)
            call('_ios7i9100_process_exit',
                (1, 17, 0x81006000, 6, 0, 1, 0, 0, 0, 163667), mask)
            assert k.word(retained+12) == 6 and k.word(retained+36) == 4
        print('PASS: linked stderr/SIGABRT publishers, split diagnostic retention, all4 I/F masks;'
              ' maximum observed32-byte append instructions:', maximum)
    print('PASS: unchanged linked ARM signal/exit publishers, real CPSR save/restore'
          ' all4 masks, stack arguments, independent fatal signals, retained origin'
          ' and independent backboardd status; no physical-device claim')


if __name__ == '__main__':
    main()
