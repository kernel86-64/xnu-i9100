> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# MALI34: register the Mali smoke client in the cached launch job list

Date: 2026-11-01. Rootfs-only correction; the MALI33 kernel is unchanged.
Full iOS UI/GLES/EAGL acceleration remains in development.

## Finding

The user reports `U0/0` and confirms installing both MALI33 files. The supplied
U0.jpg duplicates the earlier gputesto.jpg byte for byte, so the new counter is
recorded from the user's message, not inferred from that image.

MALI33 installed a signed client and a disk LaunchDaemon plist but did not add
its entry to the embedded XPC LaunchDaemons cache. The supplied cache contains
192 jobs and lacks `/System/Library/LaunchDaemons/org.i9100.mali-smoke.plist`.
The installed launchctl contains the cache path/section and cache-selection
boot flag strings. Apple's [launchctl source](https://github.com/apple-oss-distributions/launchd/blob/main/support/launchctl.c)
shows default cached bootstrap with no disk-plist fallback in that mode.
This establishes a missing registration; whether it completely explains the
reported counter still requires the phone test.

## Correction

`userland/mali/launch_cache.py` finds the embedded `__xpcd_cache` section in the
legacy ARMv7 dyld cache and adds exactly the original one-shot job. Existing
jobs, root metadata and bytes outside that section are preserved. No launcher
instructions, global code-signing settings or boot flags are patched. Caches
with a declared code signature are rejected. Cache permissions are restored.

The binary plist remains exactly 155340 bytes at cache offset487732. Unused
space is inserted before its offset table; the final trailer and offset-table
pointer remain valid. All 192 existing jobs are preserved, total193. The client,
disk job, launchd, launchctl and SpringBoard are byte-identical to MALI33.
The installer accepts a matching existing job, rejects conflicts, and operates
only on a new output image. Both original rootfs images are preserved.

## Validation

- Synthetic cache: exact patch window, old-job/metadata preservation,
  signed/missing/conflicting/overflow rejection and repeat registration.
- Actual supplied cache: old and new binary plists parse with Python plistlib
  and native CoreFoundation; all old jobs and metadata compare equal.
- Actual installed image: every cache byte outside the section unchanged;
  original cache mode retained, and critical executable/job bytes unchanged.
- New image fsck_hfs repair/check passes. Kernel and input image SHA256 unchanged.
- No kernel changes, so no new kernel build or claim of new device execution.

## Artifacts and phone step

`ROOTFS.MALI34.HFS`:939524096 bytes, SHA256
`91c975933924f266cc8f3953640abe5e69f5977b03e19a7fe1aeed790dfaf371`.

Copy only this image to the card as `/IOS7/ROOTFS.HFS`. Keep the existing
MALI33 `zImage` (SHA256
`30dc2f8e20d9778e53607c30b9c0b56eb74c330fde613da609d7a5e9e745949d`).
Expected counter after the one-shot test is `U3/0`; final userspace comparison
is in `/var/log/i9100-mali-smoke.log` (volatile on this port). Device validation
is pending. This private16x16 transport is not SpringBoard acceleration.

Private logs and manifests are retained in diagnostics/mali34-20261101;
Apple cache/rootfs contents are excluded from the source repositories.
