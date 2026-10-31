#!/usr/bin/env python3
"""Sanitizer checks of real charger policy, bounded I2C and ADC/GPIO code."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parent.parent
platform = root / 'iokit/Drivers/KernelBuiltIn/ARM/AppleARMPlatform'
with tempfile.TemporaryDirectory(prefix='i9100-power-') as directory:
    work = Path(directory)
    flags = ['-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-g',
             '-I' + str(platform)]
    objects = []
    for name in ['i9100_power.c', 'i9100_power_bus.c']:
        obj = work / (name + '.o')
        subprocess.run(['cc', '-std=c99', *flags, '-c', str(platform / name),
                        '-o', str(obj)], check=True)
        objects.append(str(obj))
    binary = work / 'power-tests'
    subprocess.run(['c++', '-std=c++11', *flags, str(root / 'port-tests/i9100_power_test.cpp'),
                    *objects, '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
