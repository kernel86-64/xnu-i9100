# Source provenance and licenses

This tree retains the original file notices and Apple [APSL text](APPLE_LICENSE).
It is a collection of code under several licenses; the top-level files do not
relicense every component. XNU includes Apple, BSD, Mach and other third-party
code. Consult each file's notice.

The board port derives from kOtusin/xnu-j1xlte and earlier HTC HD2 integration
credited to Garysss123. The initial local source snapshot and origin are recorded
in PROVENANCE.json. GT-I9100 development additions are included in this snapshot.

The EUR thermistor data in
`iokit/Drivers/KernelBuiltIn/ARM/AppleARMPlatform/i9100_battery_temperature.h`
comes from Samsung U1 mach-u1.c, distributed by
[CyanogenMod smdk4210 cm-10.1](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/cm-10.1/arch/arm/mach-exynos/mach-u1.c),
and retains its GPL-2.0-only attribution. The GPLv2 text is in LICENSES/GPL-2.0.txt.
Samsung U1 charger, GPIO and ADC sources were hardware references; the new board
policy and transport code are documented in their source. Original notices
must accompany redistribution. Apple userspace is not covered by these source
licenses and is not distributed here.

## GPU27 Mali bring-up

The new i9100_mali.c uses Mesa Lima MIT command/clear-shader material and Linux
Lima's MIT licensing option. Full notices are retained in that file. Pinned
versions and file hashes are in [GPU27_SOURCES.json](docs/progress/GPU27_SOURCES.json). Samsung U1 vendor sources
were hardware references, not imported as an Android driver. No Apple GPU
binaries, dyld cache or shader compiler are included in this source snapshot.

## GPU28 fixed test shader encodings

`i9100_mali_shaders.h` and `port-tests/generate_i9100_mali_shaders.py` use
Mesa mesa-24.3.4 Lima GP/PP bit layouts (MIT). Ben Brewer and Connor Abbott
notices are retained alongside the existing Lima notices in the C driver and
generated header. [GPU28_SOURCES.json](docs/progress/GPU28_SOURCES.json) pins layout/codegen/disassembler sources.
No general GLSL compiler or Apple shader program is included.

## GPU30 texture and blend tests

[GPU30_SOURCES.json](docs/progress/GPU30_SOURCES.json) pins Mesa24.3.4 texture descriptors, resource stride,
PP coordinate/texture instruction layout and render-state references (MIT).
Existing notices in the driver/generated header are retained. The new programs
are fixed self-test shaders, not a Mesa GLSL compiler or Apple GPU implementation.

## Previous branch snapshot

The [previous license notice](LICENSE-NOTICE.md) is retained. Earlier J1/HD2
compatibility headers, audit and manifest are archived in
[docs/progress/upstream-j1xlte](docs/progress/upstream-j1xlte/README.md).
Their original per-file notices remain; they are not part of the GT-I9100 build.
