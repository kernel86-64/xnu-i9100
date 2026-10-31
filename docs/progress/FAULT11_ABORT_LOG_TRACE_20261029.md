> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# FAULT11: failed user-abort and BSD log-lock witnesses

`Death12.jpg` matches SCOPE10 UUID `704256D1-2F8C-3967-8DA5-347A3D8EB2E9`.
At uptime 125.098594625 s, in backboardd context, the retained panic is:

```text
hw_lock busy L=8057af14 V=00000001
ATT=800c141f UP=8002cfbb T=c1e79a38 IRQ=0
OWNER=00000000 UP=00000000 T=00000000 IRQ=0 DEP=0
KNOWN=0 MASK=00000193 DROPS=0
```

Matching symbols identify `L` as `bsd_log_spinlock`, ATT as the return LR
in `usimple_lock` after `lck_spin_lock`, and UP as the return LR in
`bsd_log_lock`. Lower backtrace return `800c92b7` is inside `sleh_abort`
after the first printf reporting a failed **user data abort** vm_fault;
`800d0b40` is after the sleh_abort call from data_abort_crash_in_usermode.
The printf return at 800c92b6 follows a branch reached only when vm_fault
returned neither KERN_SUCCESS nor KERN_ABORTED. This is not the earlier
user-prefetch exception-delivery scheduler panic. Names printed by the phone
such as dsmos_page_transform_hook and hibernate_vm_unlock are nearest-symbol
misattributions, not those functions actually executing.

The lock word is busy without an owner record and with zero recorded drops.
This does not prove ordinary recursive acquisition, memory corruption,
a cache failure or an observer failure. Nor does it resolve the PV9
preemption issue. No RAW line is expected from this different fatal path.

## Implementation

FAULT11 retains all SCOPE10 hooks and scheduler/lock invariants. It adds:

- Scalar entry snapshot before vm_fault in sleh_abort: thread, reason,
  PC/LR/SP, FAR/FSR/CPSR. Both failed user-data and user-prefetch paths publish
  the entry snapshot and vm_fault return before diagnostic printf.
- A 16-entry failed-fault ring, protected by short raw CPSR exclusion. Fatal
  lock and scheduler reports show the newest retained failed fault for that
  thread. FAULT=0 means no retained match; it does not mean no fault occurred.
  Records are historical and bounded; eviction and thread-address reuse limit
  attribution. Publication occurs after vm_fault returns an error, so a panic
  inside vm_fault itself does not publish this pending fault.
- A separate 16-entry history for bsd_log_spinlock alone, selected before its
  initialization in printf_init. Existing assembly init/unlock hooks now pass
  caller, operation and thread; successful acquisitions already provide them.
  H0/H1 show the last two completed hook observations for this lock.
  OP=1 acquired, OP=2 unlocked, OP=3 initialized; V is the sampled word.
  These hooks follow the store: an exception between the store and hook is
  still a possible observation gap, not an atomic transition trace.
- The pinned report includes FAULT/TYPE/RET, PC/LR/SP, FAR/FSR/PSR and H0/H1.
  TYPE=3 prefetch, TYPE=4 data. H*=0 means no applicable retained event.

No lock is cleared by diagnostics, no preemption count is repaired, and no
printf or exception path is suppressed. No new allocations, timing calls or
scheduler/lock calls occur inside the observers. The build remains UP-only.
The diagnostics change timing; physical stability is pending.

## Validation and artifact

Actual ARM/QEMU lock paths pass normal, --unknown and --block modes,
including ownerless busy-word reporting, assembly init/acquire/unlock history,
ring wrap/eviction, immutable snapshot values, and fault fields in both fatal
reports. Existing mask/nesting/AST preemption tests pass. The actual panel
renderer passes ASan/UBSan, including complete FAULT11 witness visibility and
header preservation after 20K debugger characters. Kernel/loader builds pass;
production disassembly verifies both pre-printf publication calls, and embedded
kernel/argument/variant checks pass. These do not establish device stability.

Root raw `zImage` is FAULT11, 7424160 bytes, SHA256
`ba7765c89758ae7b87b897cbc76c9f1bebde407aed52b9a5b6b6907fd1180d76`.
Kernel UUID: `27B1A035-B199-3199-8763-855CFF06BE5B`.
Home remains disabled; touch and power enabled. Matching unstripped kernel,
image, disassembly, build/test logs and manifest are under
`diagnostics/fault11-20261029/`. SCOPE10 is preserved under
`backups/scope10-before-fault11-20261029/`. No tar/Android image was rebuilt.

The next device photo should include the entire pinned header. Decode its
FAULT/RET/FAR/PC first, then H0/H1 and owner/scope fields against this exact
UUID. Do not equate a changed panic or a lower preemption level with a fix.
