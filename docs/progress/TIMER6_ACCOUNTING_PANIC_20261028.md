> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# TIMER6: timer accounting layout and visible panic after graphics

## Device result

`sdox3.jpg` is IRQ5: frame1, battery67%,3564mV,31.8C, USB0/CHG0/R-7,
REV14. It shows LIVE IRQ00000dac and user-space PC3ab5680a, plus ordinary
userspace console output. The user confirms that both the counter and marker
then remain frozen. No panic text is visible. The user-space PC is the last
observed sample and does not identify a faulting process or instruction.
IRQ5's preemption-mask fix is still supported by its ARM regression check,
but it did not resolve the complete device stall.

## Confirmed accounting defect

`kern/timer.h` defines `struct timer` as a 64-bit tstamp followed by low_bits,
high_bits and high_bits_check. The I9100 branch of `arm/etimer.c` cast the start
of this structure to uint64_t in timer_grab and timer_update. Thus reads
returned the timestamp instead of accumulated CPU time; carry updates wrote
the timestamp instead of the accumulator. This can corrupt CPU accounting
and scheduler inputs. It is not established as the sole cause of this freeze.

TIMER6 applies the existing Leo implementation to I9100: read the actual
accumulator with its high/check publication protocol; update check, low and
high fields with barriers. No device-specific Leo observer code is enabled.

`tools/check_i9100_accounting.py` extracts the actual timer structure, board
functions and common kern/timer.c functions. It runs these in privileged ARM
QEMU. The previous source fails the timestamp-versus-accumulator check. The
fixed source passes initialization, carry, timestamp isolation, delta,
stop/switch and 128 repeated intervals crossing the 32-bit low-word boundary.

## Panic visibility

The board's normal panel console is disabled after first graphics present.
Its panic callbacks were stubs, and kern/debug.c forwarded formatted panic
text only for Leo. Therefore a panic after graphics could leave an old image.
This possibility is not proof that the reported stall is a panic.

TIMER6 enables the existing formatted-panic forwarding path for I9100 and
implements its board callbacks. First fatal entry reclaims and clears the
existing framebuffer, prints category, callsite and supplied fault fields,
and disables further graphics/IRQ overlay writes through fatal_active.
Formatted panic text uses the original _doprnt/va_list and original serial
sink, with an extra panel sink. Nested entries do not replace the first owner.
The fatal renderer skips all remapping/allocation paths, even if its earlier
normal-console remap was not completed. It preserves black/white rendering.

`tools/check_i9100_panic.py` runs the actual board renderer with fake MMIO
under ASan/UBSan, checking graphics handover, first ownership, callsite output,
wrapping/scroll bounds, FIMD trigger and no mapping requests with/without an
available framebuffer. It does not prove that a physical panel can display
text after every possible bus/CPU failure.

## Artifact and validation

Root raw `zImage` is TIMER6, Home disabled, power and touch enabled. The kernel
and loader build successfully. Actual final Mach-O disassembly contains the
correct timer fields and I9100 fatal call from panic. The IRQ5 preemption
check still passes. The two new checks also pass from the prepared GitHub
repository. Logs, matching unstripped kernel, patch, UUID and SHA256 manifest
are in `diagnostics/timer6-20261028/`.

IRQ5 is preserved in `backups/irq5-before-timer6-20261028/`. No tar/Android image
was regenerated, following the user's instruction to deliver only raw zImage.
The prepared XNU repository includes these changes and tests. Device testing
of TIMER6 is pending; no stability or successful-boot claim is made.
