#!/usr/bin/env python3
"""Exercise real I9100 pmap policy/alias updates with a mock MMU on the host."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
source = (root / 'osfmk/arm/pmap.c').read_text()

def function(name):
    # These functions have no braces in literals/comments. Keep their board
    # preprocessor branches, letting the C compiler select the real code.
    match = re.search(r'(?m)^(?:static )?(?:inline )?(?:unsigned int|boolean_t|void)\s+' +
                      name + r'\([^;]*?\)\s*\{', source)
    if not match:
        raise RuntimeError('Missing function: ' + name)
    start, depth = match.end(), 1
    for end in range(start, len(source)):
        depth += (source[end] == '{') - (source[end] == '}')
        if depth == 0:
            return source[match.start():end + 1]
    raise RuntimeError('Unclosed function: ' + name)

names = ['pmap_valid_page', 'pmap_get_cache_attributes', 'pmap_cache_attributes',
         'i9100_pte_set_cache', 'pmap_update_cache_attributes_locked',
         'pmap_set_cache_attributes', 'pmap_next_page']
reservation = source[source.index('    avail_remaining = (avail_end - first_avail)'):
                     source.index('    vm_first_phys = first_avail;')]
with tempfile.TemporaryDirectory(prefix='i9100-cache-') as directory:
    directory = Path(directory)
    (directory / 'pmap-under-test.inc').write_text('\n\n'.join(map(function, names)) +
        '\nstatic void reservation_count(void) {\n' + reservation + '\n}\n')
    output = directory / 'cache-tests'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-I' + str(directory),
                    '-I' + str(root / 'osfmk/arm'),
                    str(root / 'port-tests/i9100_cache_test.c'), '-o', str(output)], check=True)
    subprocess.run([str(output)], check=True)
