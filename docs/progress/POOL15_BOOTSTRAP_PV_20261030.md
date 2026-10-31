> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# POOL15: repair the WIRE14 early PV allocation regression

## Device result and responsibility

NOO3.jpg retains the WIRE14 primary panic `pmap mapping PV reserve exhausted`,
source pmap.c:1700, CALL800c76fa. That return address matches leo_node_get+196 in
saved WIRE14 symbols. The UUID/uptime is not visible in the photo. The user reports
panic almost immediately, unlike MAP13's roughly101-second IPC failure.
The lower screen repeatedly enters Debugger("double panic") and ultimately
stops on a secondary data abort. This is a regression introduced by WIRE14,
not evidence of a newly diagnosed hardware failure. The prior lifecycle harness
mocked PV node allocation as available and missed the actual startup contract.

## Startup contract and repair

vm_mem_bootstrap calls pmap_init before vm_mem_init finishes. sched_init,
ipc_bootstrap and ipc_init follow. Only then does startup.c call
mapping_free_prime. thread_call_initialize and mapping_adjust happen later
in kernel_bootstrap_thread. The new tracked mapping path can require a kernel
PV node in the interval after pmap_initialized becomes TRUE and before priming.
The general and kernel lists are both initially empty; leo_node_get therefore
panics without any attempt to allocate a zone node. Moving zone allocation
under the pmap lock would introduce recursive allocation/deadlock.

POOL15 seeds1024 static PV hashed nodes into the ordinary kernel free list at
the end of pmap_init, before publishing pmap_initialized=TRUE and after free-list
locks have been initialized. Static storage requires no allocation and breaks
the self-hosting cycle: growing the PV zone can itself need mapping metadata.
The28KiB reserve follows the same allocation/free-list lifetime as dynamic nodes;
these PV lists recycle nodes, never zfree them. Normal mapping_free_prime still
adds10000 general and50 kernel zone nodes. No counter is forged and no missing
metadata is discarded. The reserve is finite; actual total exhaustion remains
fatal. Host modeling cannot prove its capacity for every device workload.

The real low-water macros also used to attempt thread_call_enter before
mapping_adjust_call existed. The I9100 adjustment helper now requires a non-NULL
callout before acquiring the coalescing flag or enqueueing. This avoids a NULL
call and avoids leaving mappingrecurse set during early boot. Other boards
retain their previous macro behavior. Setup still occurs in mapping_adjust
following thread_call_initialize.

## Reentrant software panic

STOP12 stopped abort recursion, but a software panic in panic's backtrace can
re-enter panic_prologue without taking an abort. In particular a backtrace can
need pmap locks already held at the first panic. On I9100, the same-CPU nested
panic branch now releases the panic lock and calls a raw board one-shot stop
before Debugger. It masks IRQ/FIQ, prints SECONDARY PANIC below the primary
header, and remains in DSB/WFI. A fault or nested entry inside that raw output
cannot keep printing. The primary checks and message are preserved.

## Validation

check_i9100_pvpool.py compiles actual PV free-list macros, leo_node_get, static
seeding and mapping_free_prime. The fixture starts with real empty lists and
models zone backing-page allocations that themselves consume kernel metadata.
It verifies seeding before publication, pre-prime allocation, the full10050-node
dynamic prime, unique node allocation, recycling, NULL-callout protection,
notification coalescing, and fatal behavior after genuine full exhaustion.
With the saved WIRE14 source and --expect-empty-panic, the actual first kernel
request reproduces the retained panic. This is a modeled allocator integration
check, not a full i9100 boot or physical memory test.

The fatal harness also compiles actual panic_prologue and the new board stop
routine. Primary message/state and unlocked panic lock are checked, along with
masked interrupts, no Debugger call and raw-output reentry. An old-branch control
fails by entering Debugger again. Existing abort and ASan backtrace checks remain.

All14 host/ARM scripts plus locktrace unknown/block pass. Prepared-repo relocated
PV-pool and fatal checks pass. Kernel/loader build and embedded blob/boot argument
checks pass. pmap_init is in Mach-O initcode rather than __text: its Thumb bytes
were extracted and disassembled to verify the numeric call to the seed helper.
Production panic_prologue calls the terminal nested-panic helper.

## Artifact and limits

Current raw root zImage: **POOL15**, 7530704 bytes.
UUID: `CC9B0E90-8B7B-3739-989B-5B0148C1292E`.
SHA256: `2baee98cea92ceccf603f5949cab4bd439ba27fbe4f61ca7291cdc25536d7b96`.
Home disabled, touch/power enabled. Matching image, symbols, patch, logs and
production disassembly: diagnostics/pool15-20261030/.
WIRE14 checkpoint: backups/wire14-before-pool15-20261030/.
MAP13 rollback remains in backups/map13-before-wire14-20261030/.
Prepared source snapshot updated; no commits or publication. No tar/Android image
rebuilt and no phone flashing performed by the agent.

WIRE14's target-map translation, per-mapping wiring and ref/mod corrections remain.
The cause of the older IPC header0x140 corruption and device stability are still
unresolved. POOL15 corrects the reproduced early-allocation regression and nested
panic loop; stable device boot is pending. One ordinary raw-image flash is the
next device check; no additional diagnostic variants are requested.
