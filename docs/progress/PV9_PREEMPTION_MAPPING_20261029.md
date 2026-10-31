> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# PV9: balance mapping exclusion on RAM/MMIO replacement

## Device evidence and symbolization

`Lol.jpg` matches LOCK8 UUID2E1FBA85-9CF2-3927-9360-EA0A66AD4DEE. It shows:

    thread_invoke: preemption_level 2, possible cause: blocking
    while holding a spinlock, or within interrupt context

The panic caller0x80031e4c is thread_invoke. Matching return addresses identify
exception_triage (0x8002292d), doexception (0x800c861d), sleh_abort
(0x800c906f) and the user prefetch-abort vector (0x800cf99c). The current BSD
process is backboardd. Several symbol names printed by the device backtracer
were misleading nearest exports; the matching unstripped nm/disassembly was
used instead. This is a failed scheduling invariant during exception delivery,
not an OWNER/ATT panic from the lock observer.

## Confirmed mapping defect

The regular I9100 pmap_enter_options path locked the old physical PV entry,
then tested whether the *new* physical page was managed. On RAM-to-MMIO/scanout
replacement it jumped to EnterPte before removing the old PV or balancing its
preemption exclusion. Its resident ledger was also credited without removing
the old mapping's charge. Conversely, an old unmanaged mapping could be treated
as a managed PV entry. These are confirmed source defects. Multiple leaked
exclusion levels are consistent with the observed positive depth; a common
cause for all previous device panics is not established.

PV9 makes I9100 distinguish old/new managed pages, removes the old managed PV
before installing an unmanaged replacement, balances its old exclusion on all
completion paths, and avoids using PV storage for unmanaged pages. It debits
the replaced resident mapping independently of the new page type. Accounting
checks also caught a wired mapping credit going to phys_mem instead of wired_mem;
that credit is corrected. An already-wired same-page update is idempotent.
Unwiring still uses pmap_change_wiring; the inherited physical-wide wired bit
cannot, by itself, identify an individual alias's wired state. This change
does not redesign the full alias wiring model or the entire ARM pmap.

## Regression and remaining diagnostic

`tools/check_i9100_enter.py` runs the actual production pmap_enter_options
function under ARM QEMU, with modeled page-table/PV/allocator/ledger hooks.
The previous source fails depth balancing on the first RAM-to-MMIO case.
PV9 passes RAM/MMIO/reserved-scanout replacements, removal of old PV ownership,
map exclusion balance, resident ledger, covered wiring cases and allocation
retry with locks released. Existing cache/alias-policy checks also pass.
These tests do not emulate the entire VM fault stack or physical cache behavior.

The scheduler's nonzero-preemption invariant is retained. Its I9100 fatal path
now adds current thread/IRQ and up to two matching active spin-lock records
(L0/L1 PC/UP), along with total OWNED and SPIN_DROPS. OWNED0 with a positive
level means the bounded observer has no matching active spin record; it is not
proof that no untracked preemption scope exists. The real ARM owner observer
check and an additional scheduler-panic case pass, including actual CPU thread
register lookup. No forced unlock or preemption-count reset is introduced.

## Artifact

Root raw `zImage` is PV9, Home disabled, touch/power enabled. Kernel/loader builds
pass. Its matching unstripped kernel, UUID, SHA256 manifest, patch, disassembly
and logs are in `diagnostics/pv9-20261028/` (work began October28 and completed
October29). LOCK8 is preserved in `backups/lock8-before-pv9-20261028/`. No tar or
Android image was regenerated. The prepared XNU repository includes the changes
and the relocated ARM checks pass. Device validation and a successful UI boot
with PV9 remain pending.
