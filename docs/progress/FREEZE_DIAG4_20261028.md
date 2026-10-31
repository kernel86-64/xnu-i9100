> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# DIAG4 boot-stall investigation, 2026-10-28

## Device evidence

`deadbat.jpg` shows POWER3 frame1, copy14124us, GAP0/IRQ0, SD divider2,
94435KiB/73593ms, E0, C1, and battery13%,3696mV,37.7C,USB1,CHG1,R0,REV14.
The user reports that the top-right marker becomes green, then white, and
remains white. LIVE IRQ never appears. No panic or reboot was reported.

The first-frame IRQ delta is zero by definition. CHG1 is the controller's
sampled charging status; a successful full charge cycle is not established.
The stopped marker is consistent with lost timer progress, a stuck timer
callback, IRQ masking, or a panel/update failure. The photograph does not
identify a root cause. POWER3 must not be called stable or device-verified.

## Diagnostic changes

- DIAG4 prints LIVE IRQ/PC every100 timer IRQs after graphics handover, including
  the first5 seconds. POWER3 hid that row until5 seconds without a new frame.
- The observer runs before `rtclock_intr`, so a stuck `etimer_intr` callback
  cannot hide the IRQ that entered it. The marker still shares the framebuffer
  and FIMD trigger with other display paths; it is not an independent watchdog.
- `i9100home=0` skips only Home publication, preserving the touch service.
- `i9100power=0` skips the new power service. XNU does not then configure/control
  charging; the bootloader's previous hardware state is not changed by this switch.

No fix for the physical stall is claimed. Cache, SD, touch and charger policy
logic are unchanged from POWER3.

## Artifacts and first test

Root `boot.tar` and `zImage.tar` are normal DIAG4 with both new services enabled.
`diagnostics/freeze-20261028/nohome/` contains DIAG4 with Home disabled.
`diagnostics/freeze-20261028/nopower/` contains DIAG4 with kernel power disabled.
Each directory contains both tar choices plus their raw images; flash one image
at a time using the existing procedure. Start with the nohome variant, since
it preserves the new charging control. If the same stop remains, test nopower
briefly with an adequately charged battery. Report whether it reaches the lock
screen and capture LIVE IRQ/PC if it stops. A different outcome narrows the
search; it does not by itself establish an electrical or software root cause.

`backups/power3-before-freeze-20261028/` preserves POWER3 artifacts, unstripped
kernel and changed sources. The earlier usable CACHE2 checkpoint is untouched.
Logs and SHA256 manifests are in `diagnostics/freeze-20261028/`.

## GitHub preparation

`github-ready/xnu/` and `github-ready/uniloader/` are independent source snapshots,
with Git indexes prepared but no commits or remotes. Original notices and
provenance are preserved. They include curated README/build/board notes and
portable checks rather than stale local handoff history. The uniLoader recipe
creates the minimal Apple device tree and an empty ramdisk from source, then
builds XNU and packages flash archives. Device binaries, Apple userspace/rootfs,
backups, photos, local logs, SDKs and toolchains are not staged.

Read `github-ready/PUBLISH.md` for first-commit and GitHub commands. The workspace
has no global Git author identity, so the user must choose their author name
and email before the first commit. Nothing was uploaded.

## Validation result

The original workspace kernel build and all three loader variants passed.
Boot arguments, tar contents and Android payloads were checked. The independent
exported sources also built XNU and uniLoader from a clean BUILD directory via
the published build recipe. Its generated Apple DT is byte-identical to the
existing working DT. All six existing driver/cache/timing/HID checks pass after
relocation into port-tests. Build outputs remain ignored by the prepared Git
indexes. This verifies preparation and host builds, not resolution of the
physical boot stall.
