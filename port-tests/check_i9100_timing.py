#!/usr/bin/env python3
"""Check overflow-safe time math and bounded framebuffer copies on the host."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='i9100-timing-') as directory:
    output=Path(directory)/'timing-tests'
    subprocess.run(['c++','-std=c++11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    '-I'+str(root/'osfmk/arm'),'-I'+str(root/'pexpert/arm'),
                    str(root/'port-tests/i9100_timing_test.cpp'),'-o',str(output)],check=True)
    subprocess.run([str(output)],check=True)
