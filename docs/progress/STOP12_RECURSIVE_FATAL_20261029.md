> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# STOP12: stop secondary abort recursion after panic

`deadlock.jpg` shows the FAULT11 label and addresses matching its saved kernel;
its UUID is not visible in the photo. The retained first panic is:

```text
hw_lock busy L=8057bb68 V=00000001
ATT=80041c87 UP=00000000 T=c1dc9a38 IRQ=1
OWNER=00000000 UP=00000000 T=00000000 IRQ=0 DEP=0
KNOWN=0 MASK=000001d2 DROPS=0
FAULT=0 TYPE=0 RET=0
H0=0 ... H1=0 ...
```

In FAULT11 symbols, L is `thread_call_lock_data`; ATT is a return LR in
`thread_call_delayed_timer` after its spin-lock call. This is an IRQ-context
attempt with no recorded owner or tracker loss, not the previous BSD log lock.
FAULT0 means no retained failed user fault for this thread. H0/H1 are zero
because only bsd_log_spinlock was watched. Neither proves absence of a fault.

The lower display repeatedly prints `Fatal exception: sleh_abort: recursive
abort`, register state and debugger frames. FAULT11 return addresses
800c8f91 (sleh_abort + b5), 800c8ec3 (sleh_fatal_exception +14d),
800d0b00 (prefetch_abort_in_kernel +50), and visible LR800c2ff3
(Debugger +8f) corroborate secondary exceptions in the panic/debugger path.
The exact first secondary PC/FSR is cut off; do not claim a particular fault
instruction. The handler calls Debugger again, which can fault again before
reaching Halt_system. The top primary header remains frozen while repeated
secondary output scrolls the lower area.

## Changes

At I9100 sleh_abort entry, before abort-count checks, VM or exception delivery,
call a board fatal gate. Ordinary faults return immediately. Once a primary
fatal report is active, mask IRQ/FIQ, close a one-shot gate, print the saved
secondary PC/LR/FAR/FSR/CPSR/reason directly through board sinks, then remain in
a DSB/WFI loop. If those sinks themselves fault, the closed gate halts without
another print, printf, Debugger or vm_fault call. The original pinned header
is retained. This is a terminal panic policy; debugger-generated aborts after
panic also terminate here. Normal pre-panic exception/debugger handling remains.

Separately, panic_arm_backtrace stores at most32 addresses but walks up to48
frames and previously passed frame_index directly to kmod_panic_dump. Clamp
that count to the initialized array capacity. The actual old function produces
an ASan stack-buffer-overflow with48 frames; the corrected function passes
both48-frame and short-frame tests. This source bug is confirmed, but the photo
does not prove it caused the first secondary abort.

No initial lock/scheduler invariant is removed, no count is reset and no lock
is force-released. The primary ownerless thread-call lock failure remains
unresolved. This build corrects fatal reporting; device behavior is pending.

## Verification and artifact

Actual ARM fatal-gate tests cover ordinary return, IRQ/FIQ masks, complete saved
secondary fields, terminal transfer and recursive failure inside output. Actual
backtrace code is tested under ASan/UBSan with a failing old-code control.
Renderer, locktrace --unknown/--block, preemption and relocated fatal tests pass.
Kernel and loader builds pass. Production disassembly verifies gate placement
before VM and its final CPSID/DSB/WFI path. Embedded image/variant/arguments match.

Current raw root zImage is **STOP12**, Home disabled, touch/power enabled.
UUID: `AA4A7545-72A6-3CA7-A738-8159264AEE16`.
SHA256: `938b3c108f5e2532a270c5afac63f4a979b41bbb52796eeeae7b45f4507ddc8f`.
Size: 7424160 bytes.
Artifacts: diagnostics/stop12-20261029/. Previous image and matching kernel:
backups/fault11-before-stop12-20261029/. No tar or Android image regenerated.

Next phone report: whole pinned header plus the last SECONDARY ABORT lines,
if present. The stopped secondary PC/FSR should distinguish a debugger trap
from an actual invalid fetch or memory access; primary lock ownership still
requires separate investigation.
