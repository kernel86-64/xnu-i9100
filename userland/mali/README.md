# MALI33 userspace transport

This is the first bounded userspace-to-Mali rendering path. It is **not an
OpenGL ES/EAGL implementation and does not accelerate SpringBoard yet**.
The native iOS renderer remains enabled while this transport is validated.

`IOS7I9100Mali` accepts one pointer-free 32-byte request through selector0 and
returns a 1040-byte reply: ABI version, error/restore/pixel count and a16x16 BGRA
image. Operations are clear, opaque nearest2x2 expansion and premultiplied2x2
source-over. The kernel constructs every command/shader/page-table address;
no raw GPU commands, registers, user pointers or DMA mappings are exposed.
A kernel mutex serializes boot and user jobs. Any rendering failure disables
further requests until reboot. The arena remains pinned, including after an
unconfirmed STOP_BUS/restore. The returned pixels undergo GPU readback checks.

Build the original ARMv7 iOS7 executable on the same macOS toolchain:

```sh
python3 userland/mali/build.py
```

The script creates symbol-only link stubs, links against the installed iOS
IOKit/libSystem paths, and adds an ad-hoc signature including a primary SHA1
CodeDirectory understood by this XNU. Stubs contain declarations, not Apple
implementation code. No SDK or binary is included in Git. The transport follows
[IOKitUser907.1.13](https://github.com/apple-oss-distributions/IOKitUser/blob/IOKitUser-907.1.13/IOKitLib.h).

Run `/usr/local/libexec/i9100-mali-smoke` on the phone to submit three jobs and
independently verify each256-pixel image from userspace. For automatic boot testing,
create a new rootfs copy with its one-shot launch job:

```sh
python3 userland/mali/install.py /path/to/ROOTFS.HFS /path/to/ROOTFS.MALI33.HFS
```

The input is preserved. The installer changes only its new copy, adds the client
and launch plist, and fixes their HFS+ BSD uid/gid/mode offline. This avoids
accidentally shipping a launch job owned by the macOS user on a noowners mount.
The rootfs must be raw, non-journaled HFS+/HFSX with its catalog in primary extents.
The installer runs fsck_hfs on the new copy, including any HFSX folder-count
metadata upgraded by the macOS write mount. Installer errors must be resolved
before using the output. Proprietary rootfs
contents are never copied into the source repository.

After boot with matching MALI33 kernel and rootfs, the GPU row adds `U3/0` if
all three user requests completed; the process also verifies all image pixels
and writes `/var/log/i9100-mali-smoke.log`. U3 alone proves kernel completion,
not that the userspace pixel comparison succeeded: inspect that log for final
`MALI USER: PASS`. The client retries a missing/not-yet-ready service only for a
bounded interval; it does not remain as a background rendering loop.

The remaining work for UI acceleration is a full-size render-target/buffer and
context/fence interface, a Mali shader compiler/GL state driver, and integration
with the supplied native EAGL/CoreAnimation ABI. Mesa Lima is a relevant source
for the Mali backend, but its Linux DRM userspace is not a drop-in iOS driver:
[upstream Lima documentation](https://docs.mesa3d.org/drivers/lima.html).
