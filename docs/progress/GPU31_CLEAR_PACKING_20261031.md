> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# GPU31: RGBA clear registers and BGRA writeback

VseSDoli.jpg (GPU30) shows `S10 E-18 R1 P1536/4096` and
`M0 G0 T6 V24 J7 X2 A1 B8080:ff881020`. Both opaque PP0 texture
patterns and the same-VA input update passed; the first blend failed at pixel0.
PP1–3 were not reached. G0 means incomplete verification, not evidence of a
separate guard write. Restore R1 and MMU M0 remain visible.

The background is intended as BGRA word `0xff402010`. PP clear registers use
RGBA bytes instead, as pinned Mesa24.3.4 `lima_draw.c` packs them:
`A<<24 | B<<16 | G<<8 | R`. Writing a BGRA word directly swaps red and blue
in the clear background. Premultiplied red128 then produces **ff881020**, exactly
the photo, instead of **ffa01008**. Earlier white/black clears were invariant
under that swap and hid the error.

GPU31 swaps R/B only when writing PP clear registers, retaining CPU expectations
and texture/writeback BGRA. Clear job2 now uses the asymmetric background to
check this path before any textured draw. The host fixture independently models
the actual RGBA register packing. Running the actual GPU30 C with this fixture
reproduces E-18/J7/P1536/B8080:ff881020; corrected actual C passes all62 modeled
fault/success scenarios under ASan/UBSan. Commands in the local workspace:

```sh
python3 tools/check_i9100_mali.py --source backups/gpu31-before-20261031/xnu/iokit/Drivers/KernelBuiltIn/ARM/AppleARMPlatform/i9100_mali.c --expect-rgba-clear-bug
python3 tools/check_i9100_mali.py
```

In the public XNU snapshot use `port-tests/check_i9100_mali.py`; the local
backup is not distributed. This fixture is not physical Mali execution.
GPU31 still expects16 jobs/4096 pixels/78positions/26triangles/X12/Af, and needs
one phone result. GPU/IRQ masks, power/clock/STOP_BUS handling, pinned64KiB,
input path, prior VM fixes, software iOS renderer and rootfs are retained.

Primary reference: [Mesa24.3.4 lima_draw.c](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-24.3.4/src/gallium/drivers/lima/lima_draw.c),
pinned hashes in GPU30_SOURCES.json. See GPU30_TEXTURES_BLEND_20261031.md for
the fixed-shader and memory layout. Success:

```text
GPU S11 E0 R1 GP0b070101 PPf C133 P4096/4096
GIRQ000003/0001 M0 G1 T26 V78 J16 X12 Af B0000:00000000
```

The GitHub export also now includes new untracked source headers/C/C++, current
documentation and source manifests. Its default build produces raw zImage with
matching symbols. No publishing or flashing occurs automatically. This source
snapshot does not provide an iOS GLES/EAGL backend or stable firmware.

## Delivered image and verification

Root raw `zImage`: **7596064 bytes**, SHA256
`d61e7133e72eed06b5d37a2875411a5b19c1995072b9b607ebe493163ea2df74`.
Kernel UUID **5DABE539-AFF9-344E-859D-54F3FACC6B46**, entry VM `0x800cfa50`
from LC_UNIXTHREAD. Matching sys/assym, image, manifests and logs are archived
locally in `diagnostics/gpu31-20261031/`. Previous GPU30 image, matching symbols,
source and VseSDoli.jpg are preserved in `backups/gpu31-before-20261031/`.

The delivered image uses a full clean build from the exported publication
sources, rather than an incremental kernel. Local incremental builds also pass,
but have a different UUID and must not be used to symbolize this image.
All29 public batch commands pass (23 scripts,4 lock/preempt variants, ref/mod
variant and shader reproducibility). Actual linked exported ARM arena builder
passes4 I/F masks; touch callbacks preserve masks/nesting and the trace observer
retains265200 instructions/2800 reads versus629200/26800 in the old baseline.
No device performance or GPU result is inferred from those host counts.

The raw image contains exactly one matching kernel payload and one380-byte DT
with display-scale1. Home1 is explicit; touch/power/GPU defaults and tracing-on
are retained. No rootfs change or automatic flash is required. Public source
manifests, license notices, completeness, known secret patterns and current
README links were audited separately. Source publication is prepared; combined
binary licensing remains a separate unresolved review.
