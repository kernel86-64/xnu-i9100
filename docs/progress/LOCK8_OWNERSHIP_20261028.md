> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# LOCK8: capture the contended simple-lock call chain

## Device evidence

`LOCK.jpg` shows PANIC7 with matching UUID56497E3F-E751-3777-8F0A-684C40A13D5F.
The pinned header successfully retains the actual panic:

    CALL=800cd058 CAT=0000f101
    hw_lock_lock(): PANIC: Lock 0xc1ce75a0 = 0x00000001

The current BSD process is backboardd, uptime~102.4s. The callsite maps to the
panic wrapper in ARM hw_lock.s. It does not identify the higher-level caller.
The dynamically allocated lock address alone does not identify its object.
This proves that the held-bit path panicked, not which caller violated the
locking contract. It is not evidence of SD data corruption.

## Diagnostic change

LOCK8 records ownership for the I9100 ARM simple/spin lock aliases only.
Successful lock, try-lock and lock-to paths call a bounded observer; unlock and
initialization forget the address. Failure behavior remains terminal. The
observer uses2048 static records (48KiB), hashes by address and probes at most16
slots. A collision miss increments DROPS and leaves ownership explicitly unknown.
It allocates no memory and uses no locks, clock reads or scheduler API.

Raw CPSR exclusion protects only the short diagnostic table access. Hooks
preserve the assembly's volatile arguments, caller LR/frame and the existing
preemption behavior. Busy detection captures the caller before a generic panic
wrapper replaces LR. The panic includes:

- L/V: actual lock address and value.
- ATT/UP: attempting return PC and one validated parent return PC.
- OWNER/UP: acquisition return PC and one validated parent return PC.
- T/IRQ/DEP: thread register, interrupt nesting and acquisition preempt depth.
- KNOWN/MASK/DROPS: whether an owner record exists, attempt entry CPSR and losses.

Parent reads are allowed only for aligned frames fully inside the current
thread kernel stack or current CPU interrupt stack; otherwise UP is zero.
The first panic remains pinned. LOCK8 is an instrumented build, not a claimed
fix for the locking violation. Its extra brief IRQ exclusion changes timing.

## Validation and artifact

`tools/check_i9100_locktrace.py` compiles the actual ARM lock assembly and actual
C observer under QEMU Cortex-A9, using modeled thread/CPU fields. It exercises
init/lock/try/to/unlock, all four I/F masks, preempt balancing, caller ABI,
bounded collisions, lookup after deletion, valid/invalid frame bounds and a
simulated IRQ reentry that verifies both owner and attempt data in the panic.
Panic-renderer and IRQ5 preemption regressions also pass. Kernel/loader builds
and final disassembly pass. The prepared XNU repository receives the same code.

Root raw `zImage` is LOCK8, Home disabled, touch/power enabled. Matching kernel,
UUID, SHA256 manifest, patch, disassembly and logs are in
`diagnostics/lock8-20261028/`. PANIC7 is preserved in
`backups/panic7-before-lock8-20261028/`. No tar/Android image is regenerated.
Device verification is pending. A photo of the completed pinned message is
needed to identify the owning and attempting source paths.
