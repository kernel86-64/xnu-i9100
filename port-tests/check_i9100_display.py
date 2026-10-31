#!/usr/bin/env python3
"""Check the generated I9100 screen contract consumed by native MobileGestalt."""
import argparse
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--generator', type=Path, help='Use a previous generator as a regression control')
args = parser.parse_args()
candidates = [root/'port-tests/github-prepare-payloads.py',
              root.parent/'uniloader/scripts/i9100/prepare-payloads.py']
generator = args.generator or next(p for p in candidates if p.is_file())


def decode_tree(data):
    def decode(offset, parent):
        properties, children = struct.unpack_from('<2I', data, offset)
        offset += 8
        values = {}
        for _ in range(properties):
            name = data[offset:offset+32].split(b'\0', 1)[0].decode('ascii')
            size = struct.unpack_from('<I', data, offset+32)[0]
            offset += 36
            assert name not in values and offset+size <= len(data)
            values[name] = data[offset:offset+size]
            offset += (size+3)&~3
        name = values['name'].rstrip(b'\0').decode('ascii')
        path = parent+'/'+name
        entries = {path: values}
        for _ in range(children):
            offset, child = decode(offset, path)
            entries.update(child)
        return offset, entries
    end, entries = decode(0, '')
    assert end == len(data)
    return entries


with tempfile.TemporaryDirectory(prefix='i9100-display-') as directory:
    blob = Path(directory)
    # Invoke the production CLI, not a copy of its serialization logic.
    subprocess.run([sys.executable, str(generator), str(blob)], check=True)
    assert (blob/'ramdisk').read_bytes() == b''
    tree = (blob/'dtb').read_bytes()
    entries = decode_tree(tree)
    assert set(entries) == {'/device-tree', '/device-tree/chosen'}
    assert entries['/device-tree']['model'] == b'Samsung Galaxy S2 (GT-I9100)\0'
    assert entries['/device-tree']['compatible'] == b'samsung,i9100\0samsung,exynos4210\0'
    chosen = entries['/device-tree/chosen']
    assert chosen['debug-enabled'] == b'\1'
    assert chosen['firmware-version'] == b'uniLoader-i9100\0'
    # Native MG requires uint32 OSData, not an OSNumber, text, float or 1 byte.
    assert chosen.get('display-scale') == b'\x01\x00\x00\x00', 'missing uint32 display-scale=1'
    assert chosen['display-scale'] != struct.pack('<f', 1.0)
    sentinel = b'existing ramdisk payload must survive DT-only generation'
    (blob/'ramdisk').write_bytes(sentinel)
    subprocess.run([sys.executable, str(generator), str(blob), '--dt-only'], check=True)
    assert (blob/'dtb').read_bytes() == tree and (blob/'ramdisk').read_bytes() == sentinel
print('Display: real Apple DT generator/CLI, chosen native uint32 scale=1, alignment, preserved board properties and DT-only ramdisk preservation passed')
