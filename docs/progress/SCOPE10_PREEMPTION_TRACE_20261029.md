> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# SCOPE10: attribute the remaining preemption scope

`tikto.jpg` matches PV9 UUID64699340-EC34-35D2-9BE5-031423E9E18C. The retained
panic shows PL1, IRQ0, OWNED0, L0/L1 zero, SPIN_DROPS0; current context is
backboardd, uptime~105.09s. PV9 did not resolve the device failure. Its reproduced
mapping-exclusion defect remains a valid source correction, but the lower
observed count in this different boot is not proof that it caused that panic.
The observer has no active spin-lock record or loss for this context; it does
not identify an ordinary preemption scope or mutex interlock.

SCOPE10 records every I9100 IncrementPreemptLevel expansion, including ordinary
__disable_preemption, simple locks, mutex interlocks and the r9-based bitlock.
Before generic __enable_preemption decrements, it forgets the record at that
thread's current depth. A1024-slot static table records thread/depth, caller LR,
a validated parent LR and an instruction address inside the increment site.
Lookups probe at most16 slots; misses increment a separate loss counter.
There are no allocations, scheduler calls, clock reads or locks in the tracker.
Short raw CPSR exclusion protects the diagnostic metadata only.

Assembly hooks preserve volatile registers, r9/r12, callee state, eight-byte
stack alignment and the flags set by the original increment. Generic enable
retains IRQ5's I/F restoration. Other boards select the original macro. The
scheduler's fatal invariant remains; no count is reset and no lock is released.
The fatal report adds RAW/PC/UP/SITE/DROP for the depth1 record. RAW1 identifies
a recorded outstanding scope, not by itself a proven erroneous source line.
RAW0/DROP0 would require investigating untracked assignments or state corruption.

The two board diagnostic panic helpers now call `(panic)(...)` directly. The
inherited panic macro stringified the concatenated format and made the prior
header show literal quotes and backslash-n sequences. The original panic
formatter/control flow is retained; new fields use real newlines.

ARM QEMU checks pass for all16 I/F/nesting/AST return cases, including a hook
that deliberately clobbers volatile state; actual assembly lock paths plus the
actual C trackers; nested raw-scope enter/leave; scope removal after unlock;
r9-based bitlock/r12 mask preservation; and ownership/scope data in terminal
panic arguments. A harness alignment issue found while adding the bitlock test
was corrected to match EnterARM's production alignment. Panic-renderer
ASan/UBSan checks and the relocated repository check pass. Kernel/loader build
and final Mach-O disassembly pass. These are host/instruction checks, not proof
of physical stability; the instrumentation also changes timing and adds20KiB BSS.

Root raw `zImage` is SCOPE10, Home disabled, touch/power enabled. Its matching
unstripped kernel, SHA256, UUID, patch, disassembly and logs are under
`diagnostics/scope10-20261029/`. PV9 is preserved in
`backups/pv9-before-scope10-20261029/`. No tar/Android image was regenerated.
Prepared XNU publication sources include these changes. Device confirmation
and identification of the remaining outstanding scope are pending; the next
photo should include the RAW/PC/UP/SITE line in the pinned panic header.
