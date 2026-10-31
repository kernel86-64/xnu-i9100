#!/usr/bin/env python3
"""Copy the supplied rootfs and declare native 480x800 launch support in its apps.

The iPhone 4 app resources omit tall-screen launch metadata. On a 480x800
phone, iOS 7 SpringBoard therefore launches them in 320x480 classic mode.
Use the original launch-image contract; no executable/cache hooks or patches.
The input image is never mounted writable or modified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import tempfile
import zlib

SPRINGBOARD_SHA = '203507844fe39bd5f024ade40779b3902ced6f8f243ff194b047bf4d89835028'
ORIENTATIONS = ('Portrait', 'PortraitUpsideDown', 'LandscapeLeft', 'LandscapeRight')
SIZE = '{480, 800}'  # UIScreen bounds, independent of interface orientation.


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def launch_png(width, height):
    """An opaque black launch image with the actual panel dimensions."""
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack(
            '>I', zlib.crc32(kind + payload) & 0xffffffff)
    pixels = (b'\0' + b'\0\0\0' * width) * height
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack(
        '>2I5B', width, height, 8, 2, 0, 0, 0)) +
        chunk(b'IDAT', zlib.compress(pixels, 9)) + chunk(b'IEND', b''))


def patch_apps(root):
    sb = root / 'System/Library/CoreServices/SpringBoard.app/SpringBoard'
    if sha(sb) != SPRINGBOARD_SHA:
        raise RuntimeError('Unsupported SpringBoard: audit the launch-image policy first')
    pictures = {'I9100LaunchPortrait': launch_png(480, 800),
                'I9100LaunchLandscape': launch_png(800, 480)}
    report = []
    for info in sorted((root / 'Applications').glob('*.app/Info.plist')):
        if info.is_symlink() or info.parent.is_symlink():
            raise RuntimeError(f'Refusing app symlink: {info}')
        original = info.read_bytes()
        data = plistlib.loads(original)
        if 1 not in data.get('UIDeviceFamily', []):
            continue
        entries = data.get('UILaunchImages', [])
        if not isinstance(entries, list):
            raise RuntimeError(f'Unexpected UILaunchImages type: {info}')
        # Retain every existing launch profile, including iPad and 568h entries.
        entries = list(entries)
        for orientation in ORIENTATIONS:
            name = 'I9100Launch' + ('Landscape' if orientation.startswith('Landscape') else 'Portrait')
            record = {'UILaunchImageName': name, 'UILaunchImageSize': SIZE,
                      'UILaunchImageOrientation': orientation,
                      'UILaunchImageMinimumOSVersion': '7.0'}
            if record not in entries:
                entries.append(record)
        data['UILaunchImages'] = entries
        executable = info.parent / data['CFBundleExecutable']
        executable_sha = sha(executable)
        for name, content in pictures.items():
            target = info.parent / (name + '.png')
            if target.exists() and target.read_bytes() != content:
                raise RuntimeError(f'Conflicting resource: {target}')
            if not target.exists():
                target.write_bytes(content)
                target.chmod(0o644)
        fmt = plistlib.FMT_BINARY if original.startswith(b'bplist00') else plistlib.FMT_XML
        updated = plistlib.dumps(data, fmt=fmt, sort_keys=False)
        if updated != original:
            # Write through the existing inode, retaining HFS ownership/mode.
            info.write_bytes(updated)
        assert sha(executable) == executable_sha
        report.append({'app': info.parent.name, 'bundle': data['CFBundleIdentifier'],
                       'info_before': hashlib.sha256(original).hexdigest(),
                       'info_after': sha(info), 'executable_sha256': executable_sha})
    if not any(x['bundle'] == 'com.apple.Preferences' for x in report):
        raise RuntimeError('Settings was not found')
    return report


def check_hfs(path):
    with path.open('rb') as stream:
        stream.seek(1024)
        header = stream.read(512)
    if header[:2] not in (b'H+', b'HX') or len(header) != 512:
        raise RuntimeError('Expected a raw HFS+/HFSX image')
    attrs, journal = struct.unpack_from('>I', header, 4)[0], struct.unpack_from('>I', header, 12)[0]
    if attrs & 0x2000 or journal:
        raise RuntimeError('The i9100 root filesystem must not be journaled')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    source, output = args.input.resolve(strict=True), args.output.absolute()
    if output.exists() or output.is_symlink() or source == output:
        parser.error('Output must be a new image; overwriting an existing image is refused')
    check_hfs(source)
    before = sha(source)
    # Exclusive creation also guards against selecting the input via an alias.
    with output.open('xb') as dest, source.open('rb') as src:
        shutil.copyfileobj(src, dest, 1024 * 1024)
    mounted = False
    with tempfile.TemporaryDirectory(prefix='i9100-app19-') as mount:
        try:
            subprocess.run(['hdiutil', 'attach', '-readwrite', '-nobrowse', '-noverify',
                            '-noautofsck', '-mountpoint', mount, '-imagekey',
                            'diskimage-class=CRawDiskImage', str(output)], check=True)
            mounted = True
            apps = patch_apps(Path(mount))
            os.sync()
        finally:
            if mounted:
                subprocess.run(['hdiutil', 'detach', mount], check=True)
    check_hfs(output)
    if sha(source) != before:
        raise RuntimeError('Input image changed during preparation')
    manifest = {'stage': 'APP19', 'input': str(source), 'input_sha256': before,
                'output': str(output), 'output_sha256': sha(output),
                'bytes': output.stat().st_size, 'panel_points': [480, 800],
                'scale': 1, 'apps': apps, 'device_result': 'pending'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'APP19: {len(apps)} apps, native 480x800 launch profiles; input unchanged')
    print(f'{output}: {manifest["output_sha256"]}')


if __name__ == '__main__':
    main()
