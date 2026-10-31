#!/usr/bin/env python3
"""Host checks for real touch protocol, GPIO I2C and native HID serialization."""
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parent.parent
platform=root/'iokit/Drivers/KernelBuiltIn/ARM/AppleARMPlatform'
with tempfile.TemporaryDirectory(prefix='i9100-touch-') as directory:
    work=Path(directory)
    flags=['-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g','-DI9100_TOUCH_HOST_TEST','-I'+str(platform)]
    objects=[]
    for name in ['i9100_touch.c','i9100_touch_gpio.c']:
        obj=work/(name+'.o');objects.append(str(obj))
        subprocess.run(['cc','-std=c99',*flags,'-c',str(platform/name),'-o',str(obj)],check=True)
    binary=work/'touch-tests'
    subprocess.run(['c++','-std=c++11',*flags,str(root/'port-tests/i9100_touch_test.cpp'),*objects,'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
