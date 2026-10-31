> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# IRQ5: restore interrupt masks after enabling preemption

## Device report

`Hang228.jpg` is from the DIAG4 image with `i9100home=0` (root zImage SHA256
7bb77995b0b4613e079996c8e45748c3e681eb0de945b2c6ffd621b373772046).
It still stops on black frame1. The photo shows LIVE IRQ00000af0,
PC800cfcf5, battery64%,3721mV,38.6C,USB0,CHG0,R-7,REV14. R-7 is the
expected offline/cable-absent reason. No panic is visible.

The photographed PC lies in the `ml_set_interrupts_enabled` enable/return
sequence of the matching DIAG4 unstripped kernel. It is the last observed
interrupted PC, not necessarily the faulting instruction.

## Established source defect

`osfmk/arm/machine_routines_asm.s` had the corrected preemption return only for
the Leo board. I9100 took the old path: CPSID IF, then MRS CPSR, then test I.
That test necessarily sees IRQ masked. When the preemption count falls to zero,
the function returns without restoring the caller's IRQ/FIQ masks and skips
pending scheduler AST handling. Short GPIO I2C transfers use this path, as do
other kernel callers. A later explicit IRQ enable could temporarily hide the
fault, so its effects need not occur at the same visible point each boot.

IRQ5 enables the existing corrected path for I9100 in both the mask capture
and AST return branches. It captures CPSR before CPSID, restores the caller's
I/F masks, and retains that state across a C AST call that can clobber r3.
Other boards' selected paths are unchanged. The overlay label becomes IRQ5.

## Validation

`tools/check_i9100_preemption.py` extracts the actual ARM function and runs it
in privileged mode on QEMU Cortex-A9. It uses real CPSR instructions and modeled
thread/CPU fields; the AST stub deliberately clobbers r3. All16 combinations of
entry I/F masks, count1/2, and pending/no AST pass. The pre-fix source fails the
same check. This checks instruction behavior, not physical Exynos scheduling.

The XNU and uniLoader builds pass. Final Mach-O disassembly confirms MRS occurs
before CPSID and that the AST return restores CPSR. Logs, the source patch,
matching unstripped kernel, UUID and hashes are in `diagnostics/irq5-20261028/`.
No physical success is claimed until the user tests IRQ5.

## Device artifact

The raw `/path/to/workspace/zImage` is IRQ5, with Home still disabled
and touch/power enabled. Its hash is recorded in the artifact manifest. It is
also saved as `diagnostics/irq5-20261028/zImage`. Use the user's existing raw
zImage flashing command. Earlier tar/Android images have not been regenerated
for IRQ5, per the user's raw-image-only instruction.

The previous root zImage, source and kernel are preserved in
`backups/diag4-before-irq5-20261028/`; the older CACHE2 backup is untouched.
The prepared XNU source repository is updated with the fix and the new check.
