> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# MALI33: first bounded userspace-to-Mali rendering transport

Requested goal: userspace image acceleration. **Full UI/GLES/EAGL acceleration
is not delivered by this checkpoint.** The required first userspace transport
is implemented and prepared for phone validation before a general backend is
connected to native CoreAnimation.

The supplied cache contains the SGX535 GL driver, not a Mali backend. Its
`gldInitializeLibrary`, device/context dispatch and framebuffer entry points
are hardware-specific. Mesa Lima supports Mali-400, but its DRM winsys is not
an iOS integration. The existing CPU IOSurface/FIMD display path remains active.
See [Mesa Lima](https://docs.mesa3d.org/drivers/lima.html) and the locally inspected
cache identified in GPU27_MALI_BRINGUP_20261031.md.

## Implemented transport

- `IOS7I9100Mali` publishes a user client with one selector accepting an exact
  32-byte value-only ABI1 request and returning1040 bytes, including256 pixels.
- Three fixed private16x16 operations: clear, nearest opaque2x2 texture expansion
  and premultiplied2x2 source-over. Arbitrary addresses/commands/shaders and DMA
  mappings are not accepted. Reserved/version/op/alpha constraints are validated
  before MMIO, with local request capture.
- The kernel builds all commands using the physically tested GPU31 programs.
  Requests reuse the prepared64KiB Normal-NC arena and serialize with the boot
  test. Every output/padding/protected page is checked; waits and restoration
  remain bounded. A failed user draw disables further requests until reboot;
  pinned DMA storage is never reused for unrelated allocations after failure.
- The original iOS7 ARMv7 client uses IOKit to submit three different requests
  and independently checks returned images. Native Mach-O import signatures
  match IOKitUser907.1.13. Symbol-only linker stubs contain no Apple code.
- The executable is ad-hoc signed with primary SHA1 plus alternate SHA256.
  This is significant: this XNU's ubc_subr.c validates primary SHA1 page hashes.
- A separate rootfs copy receives the executable and a one-shot launch job.
  HFS+/HFSX catalog BSD uid/gid/modes are fixed offline to root ownership, rather
  than trusting macOS noowners stat. No CA/OpenGLES/cache binaries are patched.
- The GPU row retains boot status and adds `U<completed>/<error>`; expect `U3/0`
  when the boot job has made all three kernel submissions. This is completion,
  not a secure userspace attestation. Final independent validation is logged to
  `/var/log/i9100-mali-smoke.log`; filesystem writes are volatile on this port.

## Validation and limits

Actual C core tests retain the62 existing fault cases and add120 arbitrary
user clear/copy/blend requests,6 malformed requests rejected before PMIC/MMIO,
and6 injected user DMA/timeout/guard/restore failures. The actual user-client
selector gate runs under ASan/UBSan with poisoned rejected pointers. The actual
userspace C client runs against the original C driver through mock IOKit with
success/retry/missing/open/fault/pixel-error cases. These are host fixtures.

The linked ARMv7 executable also runs unmodified under Unicorn with mocked IOKit
imports: seven success/error/retry branches, actual32-bit wire sizes and stack
arguments, return-pixel validation and close behavior. Primary CodeDirectory
SHA1/page hashes are checked. This is not native iOS/dyld or physical GPU proof.

Phone confirmation of the new user path is required. The previous HUD32 image
and matching symbols remain in backups/mali33-before-20261101/. The original
ROOTFS.HFS remains intact; ROOTFS.MALI33.HFS is a separate copy to install as
/IOS7/ROOTFS.HFS. Neither rootfs nor binary client is published in source repos.

After transport validation, remaining work includes full-size render targets,
user buffers/contexts and real completion fences, a shader compiler/GL state
backend, IOSurface sharing and EAGL/CoreAnimation ABI integration. A16x16
request demo is not a performance optimization and is not routed into the live
UI. The working software renderer remains the fallback.
