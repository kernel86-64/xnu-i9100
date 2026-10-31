#!/usr/bin/env python3
"""Run the I9100 host/ARM regressions as one batch, without accessing a phone."""
import argparse
from pathlib import Path
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--log', type=Path, help='Save complete test output here')
parser.add_argument('--list', action='store_true', help='List commands without running them')
args = parser.parse_args()
folder = Path(__file__).resolve().parent
commands = [[sys.executable, str(p)] for p in sorted(folder.glob('check_i9100_*.py'))]
commands += [[sys.executable, str(folder/'check_i9100_locktrace.py'), mode]
             for mode in ('--unknown', '--block', '--light')]
commands += [[sys.executable, str(folder/'check_i9100_preemption.py'), '--trace']]
commands += [[sys.executable, str(folder/'check_i9100_enter.py'), '--refmod'],
             [sys.executable, str(folder/'generate_i9100_mali_shaders.py'), '--check']]
if args.list:
    for command in commands:
        print(' '.join(command))
    raise SystemExit(0)
log = args.log.open('w') if args.log else None
try:
    for command in commands:
        start = time.monotonic()
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            print('TIMEOUT:', ' '.join(command), file=sys.stderr)
            raise SystemExit(1)
        output = result.stdout + result.stderr
        if log:
            log.write('$ ' + ' '.join(command) + '\n' + output)
            log.flush()
        print(('PASS' if not result.returncode else 'FAIL') + ': ' +
              ' '.join(Path(x).name for x in command[1:]) +
              f' ({time.monotonic()-start:.1f}s)', flush=True)
        if result.returncode:
            print(output, file=sys.stderr)
            raise SystemExit(result.returncode)
finally:
    if log:
        log.close()
