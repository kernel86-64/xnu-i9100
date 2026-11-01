# XNU for Samsung Galaxy S2 GT-I9100

Experimental Darwin/XNU 2422 (iOS 7 era) ARMv7 port to the international
Samsung Galaxy S2, Exynos4210, 1 GB RAM, 480×800 display. **MALI34, 2026-11-01; kernel MALI33.**

Based on [kOtusin/xnu-j1xlte](https://github.com/kOtusin/xnu-j1xlte), with earlier
HTC HD2 work credited to Garysss123. Historical reference:
[zenkernelsam/xnu-S2I9100](https://github.com/zenkernelsam/xnu-S2I9100/tree/6ec0eaf).
See [provenance](PROVENANCE.json), [source manifest](SOURCE_MANIFEST.json) and
[component licenses](THIRD_PARTY.md). Apple userspace is supplied separately.

Published branch: [kernel86-64/xnu-i9100, i9100-source](https://github.com/kernel86-64/xnu-i9100/tree/i9100-source).
Companion loader: [kernel86-64/uniloader, i9100](https://github.com/kernel86-64/uniloader/tree/i9100).

## Current status

MALI33 adds an initial [userspace Mali transport](userland/mali/README.md) and
ARMv7 smoke client for private16x16 clear/copy/blend requests. It is prepared
for phone validation, not connected to the live compositor. After the user reported
U0/0 with both MALI33 files installed, MALI34 fixes its boot registration in the
embedded XPC LaunchDaemons cache. All existing jobs are preserved. Replace only
the rootfs, retaining the MALI33 kernel; device confirmation is pending. Full
userspace image acceleration remains in development.

The runtime overlay now occupies three bottom rows: compact GPU status, BAT and
LIVE IRQ; GPU also shows user submission count/error. GPU failures add one detail row. Home/touch, storage/performance and
SpringBoard/backboard/abort diagnostics are retained in RAM and hidden from
the runtime overlay. Fatal reports keep their separate emergency console.

The phone boots iOS 7 to SpringBoard with touch and a software display path.
The user reports that complete freezes stopped after the cache fixes; random
SpringBoard exits and limited performance remain. PERF22 restored touch and
made home-screen page scrolling smoother. Home is enabled, with its queue fix
retained. Battery telemetry and running-kernel charging exist; a complete charge
cycle and reliable original iOS battery UI have not been verified.

Mali-400 MP4 has an isolated hardware self-test, separate from the iOS renderer.
The phone confirms GPU clears, vertex shaders, triangles, PP0 texture sampling
and updating texels at the same GPU address. GPU30 failed its first alpha blend;
GPU31 corrects RGBA clear-register versus BGRA writeback packing. Host checks
reproduce the old photo's exact pixel and accept the corrected code. GPU31
blending and PP0–3 execution passed on the phone (`gputesto.jpg`: S11/E0,
4096 pixels,16 jobs,12 textured passes, rendered maskf, M0/G1/R1).

**There is no iOS GLES/EAGL backend or GPU-accelerated SpringBoard yet.** Kernel
memory fixes are retained, but the writer behind the QuartzCore slab assertion
has not been proven. This is a development snapshot, not a stable firmware release.

## Build

Use macOS with Apple Command Line Tools, clang with the classic ld64 backend,
Python 3, make and `arm-none-eabi-gcc`/binutils. The development host uses Apple
clang 21.0.0 and GCC 16.2.0. The makefiles find `libclang_rt.cc_kext_ios.a` through
clang. Linux cross-build paths are inherited and unverified; they require a
Mach-O toolchain and an explicit `LD64_WRAPPER` where appropriate.

Clone the companion repositories into sibling directories:

```sh
git clone --branch i9100-source https://github.com/kernel86-64/xnu-i9100.git xnu
git clone --branch i9100 https://github.com/kernel86-64/uniloader.git uniloader
```

From the `xnu` directory, one command builds both:

```sh
python3 ../uniloader/scripts/build-i9100.py --xnu . --jobs 4
```

The default output is `../uniloader/out/zImage`, matching `mach_kernel.sys`,
`assym.s` and `manifest.json`. Optional Android/Odin packages require `--archives`.
The recipe generates a minimal Apple device tree and an empty ramdisk; no Apple
blobs or SDK downloads are needed. It replaces the loader's generated `.config`
with `i9100_defconfig`. Keep the current optimization and cache/mask settings.

Kernel-only build:

```sh
make TARGET_CONFIGS='RELEASE ARM EXYNOS4210_I9100' -j4
```

## Storage and checks

Root filesystem download: [Google Drive](https://drive.google.com/file/d/1KqMwaWaMo_KrEhykoV1BcUsQpSfPAeD3/view?usp=sharing).

MicroSD uses MBR and FAT32, containing `/IOS7/ROOTFS.HFS`: a raw, non-journaled
HFS+ image with separately supplied compatible ARMv7 iOS 7 userspace. Writes
use RAM copy-on-write and disappear at reboot. Small application windows have
a separate userspace launch-profile issue; kernel build tooling does not alter
any root filesystem. No Apple userspace, shared cache, firmware or rootfs is
included in this source snapshot.

Run the host regression batch:

```sh
python3 port-tests/check_i9100.py --log /tmp/i9100-checks.log
```

It requires a host C/C++ compiler, `arm-none-eabi-gcc` and `qemu-system-arm`,
and includes sanitizer models, ARM checks, the retained ref/mod variant and
shader reproducibility. Optional `verify_*_native.py` scripts also require
Unicorn/Capstone and explicit matching symbol paths; userspace verifiers require
external Apple files which are not provided. Host checks cannot verify physical
GPU execution, touch wiring, charging or long-term stability.

See [board notes](docs/GT-I9100.md), [compact overlay](docs/progress/HUD32_COMPACT_OVERLAY_20261101.md)
and [GPU31 analysis](docs/progress/GPU31_CLEAR_PACKING_20261031.md).

Dated development reports and GPU reference manifests: [progress archive](docs/progress/README.md).
