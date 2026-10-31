> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# CACHE16: Home re-enabled

The user confirms CACHE16 boot succeeded and explicitly requests physical Home
back after diagnostic disabling. Repeat boots and long-duration stability have
not yet been established.

Rebuilt only uniLoader with `i9100home=1`. The embedded raw kernel was compared
byte-for-byte with the previously delivered CACHE16 payload. Kernel source,
code and UUID remain unchanged; Home uses its existing driver. Touch/power remain
enabled. The generated loader .config retains the explicit Home setting for
future builds. No tar or Android boot image was regenerated.

Root raw zImage SHA256: `fdf034d2b87f10da6ac254d8a36676595919d7b9dbe9700333ea1e04b0410340`.
Kernel UUID: `3C5D41B5-6417-376A-9454-B8823A583B56`.
Artifacts: diagnostics/cache16-home-20261030/. The prior Home-disabled image
and matching artifacts are in backups/cache16-nohome-before-home-20261030/.

Loader build, embedded-payload/boot-argument checks and existing host Home/touch
checks pass. The kernel regression matrix was not rerun for this loader-only
change. Actual Home behavior on the phone is pending. The same UUID now appears
with different Home boot arguments; use the image manifest for variant identity.
