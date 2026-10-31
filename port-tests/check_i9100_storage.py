#!/usr/bin/env python3
"""Run host checks for SD error handling and strict FAT/HFS image discovery."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
platform = root / 'iokit/Drivers/KernelBuiltIn/ARM/AppleARMPlatform'
with tempfile.TemporaryDirectory(prefix='i9100-storage-') as directory:
    work = Path(directory)
    (work / 'kern').mkdir()
    (work / 'kern/debug.h').write_text('#include <stdio.h>\n#define kprintf printf\n')
    binary = work / 'storage-tests'
    subprocess.run([
        'cc', '-std=c99', '-Wall', '-Wextra', '-Werror',
        '-fsanitize=address,undefined', '-g',
        '-DBOARD_CONFIG_EXYNOS4210_I9100=1', '-I' + str(work), '-I' + str(platform),
        str(root / 'port-tests/i9100_storage_test.c'), str(platform / 'i9100_sdmmc.c'),
        str(platform / 'fat_locator.c'), '-o', str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
