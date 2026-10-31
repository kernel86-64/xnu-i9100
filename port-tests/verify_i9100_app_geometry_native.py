#!/usr/bin/env python3
"""Run the supplied iOS 7 SpringBoard launch parser/classifier and UIKit metrics.

Requires Unicorn 2.x and a locally supplied rootfs, mounted read-only. Apple
instructions are executed without modification. Objective-C containers, device
identity, resource lookup and GS results are modeled at their call boundaries.
This does not test the live render server, compositor or touch on the phone.
"""
import argparse
import hashlib
from pathlib import Path
import plistlib
import struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import *

SB_SHA = '203507844fe39bd5f024ade40779b3902ced6f8f243ff194b047bf4d89835028'
CACHE_SHA = 'cad2df775e122c660238f341e74c163a2ea0ed261e85bfd3190de750cd9c0d2c'
REGS = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
NATIVE = {'_imageNamesFromInfoDictionary:': 0x1be044,
          '_calculateSupportedTypesLazilyIfNecessary': 0x3e704,
          '_infoplist_defaultPNGCalculateContainsCorgiImage': 0x1bf398,
          'supportsApplicationType:': 0x3ea30}


class Native:
    def __init__(self, root):
        self.root = root
        self.sb = (root/'System/Library/CoreServices/SpringBoard.app/SpringBoard').read_bytes()
        self.cache = (root/'System/Library/Caches/com.apple.dyld/dyld_shared_cache_armv7').read_bytes()
        assert hashlib.sha256(self.sb).hexdigest() == SB_SHA, 'SpringBoard identity changed'
        assert hashlib.sha256(self.cache).hexdigest() == CACHE_SHA, 'Cache identity changed'
        mo, mc = struct.unpack_from('<2I', self.cache, 16)
        self.maps = [struct.unpack_from('<3Q2I', self.cache, mo+32*i) for i in range(mc)]
        self.u = u = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A9)
        u.mem_map(0x1000, 0x500000)
        p = 28
        for _ in range(struct.unpack_from('<I', self.sb, 16)[0]):
            cmd, size = struct.unpack_from('<2I', self.sb, p)
            if cmd == 1:
                va, vs, off, fs = struct.unpack_from('<4I', self.sb, p+24)
                if fs:
                    u.mem_write(va, self.sb[off:off+fs])
            p += size
        for va, size, off, _, _ in self.maps:
            u.mem_map(va, size)
            if va != self.maps[0][0]:
                u.mem_write(va, self.cache[off:off+size])
        # UIKit code, selector strings and the original 320x480 constant.
        start, size = 0x2fc77000, 0x790000
        u.mem_write(start, self.cache[self.offset(start):self.offset(start)+size])
        u.mem_map(0x10000000, 0x100000)
        u.mem_map(0x11000000, 0x400000)
        u.mem_map(0x12000000, 0x10000)
        u.reg_write(UC_ARM_REG_C1_C0_2, 0xf00000)
        u.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        self.next = 0x11001000
        self.objects = {}
        for addr, kind in [(0x3b2cc8, 'dict'), (0x3b2ce0, 'list'),
                           (0x3b2ce8, 'str'), (0x3b2d04, 'list'), (0x3b2de4, 'dict'),
                           (0x3b2ce4, 'screen'), (0x3b2d7c, 'device')]:
            self.putword(addr, self.obj(('class', kind)))
        self.putword(0x329da4, self.alloc(struct.pack('<I', 0x12345678)))
        self.screen = self.alloc(bytes(0x100))
        self.device = self.obj(('device', None))
        self.application = self.obj(('application', None))
        self.mode = self.obj(('mode', None))
        self.putword(self.screen+4, self.obj(('display', None)))
        self.trace = set()
        u.hook_add(UC_HOOK_CODE, self.hook)

    def offset(self, address):
        for va, size, off, _, _ in self.maps:
            if va <= address < va+size:
                return off+address-va
        raise ValueError(hex(address))

    def reg(self, n):
        return self.u.reg_read(REGS[n])

    def putword(self, address, value):
        self.u.mem_write(address, struct.pack('<I', value & 0xffffffff))

    def word(self, address):
        return struct.unpack('<I', self.u.mem_read(address, 4))[0]

    def cstr(self, address):
        result = bytearray()
        while True:
            ch = self.u.mem_read(address, 1)[0]
            if not ch:
                return result.decode()
            result.append(ch)
            address += 1
            assert len(result) < 1000

    def alloc(self, data):
        result = self.next
        self.next += (len(data)+15) & ~15
        self.u.mem_write(result, data)
        return result

    def obj(self, value):
        if value is None:
            return 0
        if isinstance(value, dict):
            value = {k:self.obj(v) for k,v in value.items()}
        elif isinstance(value, list):
            value = [self.obj(v) for v in value]
        ptr = self.alloc(bytes(16))
        self.objects[ptr] = value
        return ptr

    def value(self, ptr):
        if not ptr:
            return None
        if ptr in self.objects:
            return self.objects[ptr]
        return self.cstr(self.word(ptr+8))  # Original constant NSString.

    def ret(self, value):
        self.u.reg_write(UC_ARM_REG_R0, value & 0xffffffff)
        self.u.reg_write(UC_ARM_REG_PC, self.u.reg_read(UC_ARM_REG_LR))

    def hook(self, u, address, size, unused):
        if address == 0x1200f000:
            u.emu_stop()
            return
        if address in NATIVE.values() or address in (0x3e8b8, 0x2fce7fcc):
            self.trace.add(address)
        if address in (0x328e70, 0x302a8cc4):
            self.message()
        elif address in (0x328e7c, 0x302a8cf4):
            selector = self.cstr(self.reg(2))
            assert selector == 'bounds', selector
            u.mem_write(self.reg(0), struct.pack('<4f', 0, 0, *self.points))
            self.ret(self.reg(0))
        elif address == 0x328658:  # MGCopyAnswer ProductVersion
            assert self.value(self.reg(0)) == 'ProductVersion'
            self.ret(self.obj('7.1.2'))
        elif address == 0x3289f8:  # CGRectGetHeight, soft-float ABI
            self.ret(self.reg(3))
        elif address in (0x328a68, 0x3287dc):
            width, height = struct.unpack('<2f', struct.pack('<2I', self.reg(0), self.reg(1)))
            self.ret(self.obj('{%g, %g}' % (width, height)))
        elif address in (0x328e48, 0x328e4c):
            self.ret(1)
        elif address == 0x302a7184:  # GSMainScreenScaleFactor, DISP18 verified separately.
            self.ret(0x3f800000)
        elif address == 0x302a7174:  # GSMainScreenPointSize, DISP18 verified separately.
            u.mem_write(self.reg(0), struct.pack('<2f', *self.points))
            self.ret(self.reg(0))
        elif address in (0x328a48, 0x328374):
            raise AssertionError('Native parser error/stack check: '+hex(address))

    def message(self):
        receiver, selector, a, b = (self.reg(i) for i in range(4))
        name = self.cstr(selector)
        if name in NATIVE:
            self.u.reg_write(UC_ARM_REG_PC, NATIVE[name] | 1)
            return
        value = (self.value(receiver) if name in ('isEqualToString:', 'isKindOfClass:',
                                                  'compare:options:')
                 else self.objects.get(receiver))
        if name in ('retain', 'autorelease', 'copy', 'init', 'class'):
            result = receiver
        elif name == 'release':
            result = 0
        elif name == 'currentDevice':
            result = self.device
        elif name == 'userInterfaceIdiom':
            result = 0
        elif name == 'mainScreen':
            result = self.screen
        elif name == 'sharedApplication':
            result = self.application
        elif name == 'alloc':
            assert value[0] == 'class'
            result = self.obj({} if value[1] == 'dict' else [])
        elif name == 'arrayWithObjects:count:':
            result = self.obj([])
            self.objects[result] = [self.word(a+4*i) for i in range(b)]
        elif name == 'array':
            result = self.obj([])
        elif name == 'objectForKey:':
            key = self.value(a)
            assert isinstance(key, str), (name, value, key, hex(self.u.reg_read(UC_ARM_REG_LR)))
            result = value.get(key, 0) if value else 0
        elif name == 'setObject:forKey:':
            value[self.value(b)] = a
            result = 0
        elif name == 'addObject:':
            value.append(a)
            result = 0
        elif name == 'containsObject:':
            result = int(self.value(a) in [self.value(x) for x in value])
        elif name == 'isEqualToString:':
            result = int(value == self.value(a))
        elif name == 'isKindOfClass:':
            kind = self.value(a)[1]
            result = int(isinstance(value, {'str':str, 'dict':dict, 'list':list}[kind]))
        elif name == 'compare:options:':
            left = tuple(int(x) for x in value.split('.'))
            right = tuple(int(x) for x in self.value(a).split('.'))
            result = (left > right) - (left < right)
        elif name == 'countByEnumeratingWithState:objects:count:':
            items = [self.obj(k) for k in value] if isinstance(value, dict) else (value or [])
            pos = self.word(a)
            count = min(len(items)-pos, self.word(self.u.reg_read(UC_ARM_REG_SP)))
            for i in range(count):
                self.putword(b+4*i, items[pos+i])
            self.putword(a, pos+count)
            self.putword(a+4, b)
            self.putword(a+8, a+16)
            result = count
        elif name in ('sortUsingComparator:', '_updateOverscanCompensationAllowingBackgroundUpdate:',
                      '_updateWorkspaceCapableScreenType'):
            result = 0
        elif name == 'launchingInterfaceOrientationForCurrentOrientation':
            result = 1
        elif name == '_defaultPNGPathForScreen:launchingOrientation:imageOrientation:resultingScale:':
            # Baseline has no 568h (or any height-qualified) launch assets.
            # No matching fullscreen resource: the original fallback remains classic.
            assert not list(self.app.glob('*568*'))
            result = 0
        elif name == 'currentMode':
            result = self.mode
        elif name == '_isMainScreen':
            result = 1
        elif name in ('_isExternal', '_fakingRequiresHighResolution', '_isNTSCOrPAL'):
            result = 0
        elif name == '_isClassic':
            result = self.classic
        elif name == 'pixelAspectRatio':
            result = 0x3f800000
        else:
            raise AssertionError(f'Unmodeled Objective-C boundary: {name} at LR={self.u.reg_read(UC_ARM_REG_LR):x}')
        self.ret(result)

    def call(self, address, *values):
        for i, value in enumerate(values):
            self.u.reg_write(REGS[i], value)
        self.u.reg_write(UC_ARM_REG_SP, 0x100ff000)
        self.u.reg_write(UC_ARM_REG_LR, 0x1200f001)
        self.u.emu_start(address | 1, 0x1200f000, count=100000)
        assert self.u.reg_read(UC_ARM_REG_PC) == 0x1200f000, hex(self.u.reg_read(UC_ARM_REG_PC))
        return self.reg(0)

    def run(self, app, points, info=None):
        self.app, self.points = app, points
        if info is None:
            info = plistlib.loads((app/'Info.plist').read_bytes())
        application = self.alloc(bytes(0x200))
        self.putword(application+0x84, 1)  # Phone support, UIDeviceFamily includes1.
        parsed = self.call(0x1be044, application, 0, self.obj(info))
        self.putword(application+0x18, parsed)
        self.classic = self.call(0x3e8b8, application, 0)
        flags = self.word(application+0x84)
        self.call(0x2fce7fcc, self.screen, 0)
        bounds = struct.unpack('<4f', self.u.mem_read(self.screen+8, 16))
        print(f'{app.name}: points={points}, native supportedTypes={flags}, classic={self.classic}, UIKit bounds={bounds}')
        return self.classic, bounds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--expect', required=True, choices=('classic', 'fullscreen'))
    args = parser.parse_args()
    native = Native(args.root)
    apps = [p.parent for p in sorted((args.root/'Applications').glob('*.app/Info.plist'))
            if 1 in plistlib.loads(p.read_bytes()).get('UIDeviceFamily', [])]
    assert len(apps) == 21
    for app in apps:
        classic, bounds = native.run(app, (480, 800))
        assert classic == (args.expect == 'classic')
        assert bounds == ((0, 0, 320, 480) if classic else (0, 0, 480, 800))
    # A 320x480 phone continues through the original nonclassic path.
    classic, bounds = native.run(args.root/'Applications/Preferences.app', (320, 480))
    assert classic == 0 and bounds == (0, 0, 320, 480)
    if args.expect == 'fullscreen':
        # The real parser must reject a mismatched size and a future OS profile.
        # These controls catch tests that merely assume all metadata is accepted.
        app = args.root/'Applications/Preferences.app'
        for key, value in [('UILaunchImageSize', '{480, 799}'),
                           ('UILaunchImageMinimumOSVersion', '99.0')]:
            info = plistlib.loads((app/'Info.plist').read_bytes())
            for entry in info['UILaunchImages']:
                entry[key] = value
            classic, bounds = native.run(app, (480, 800), info)
            assert classic == 1 and bounds == (0, 0, 320, 480), key
            print('PASS rejection control:', key, value)
    required = {0x1be044, 0x3e704, 0x3ea30, 0x3e8b8, 0x2fce7fcc}
    if args.expect == 'fullscreen':
        required.add(0x1bf398)
    assert required <= native.trace
    print('PASS: original SpringBoard parser/classifier + UIKit metrics; Objective-C/GS boundaries modeled; live UI pending')


if __name__ == '__main__':
    main()
