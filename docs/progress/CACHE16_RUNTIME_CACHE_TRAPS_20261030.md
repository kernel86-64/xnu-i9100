> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# CACHE16: live cache traps discarded dirty kernel data

## Latest phone evidence and historical trigger

noo1.jpg shows the POOL15 label, a black first GUI frame, green marker,
BAT76%/3929mV/T320/USB1/CHG1/R0/REV14, frame1/COPY11425us/GAP0ms/IRQ0,
and LIVE IRQ00001068 PC3a95d0c6. No panic header, UUID or independent CPU/IRQ
state is visible. The user reports a complete freeze. IRQ0 is the first-frame
delta, not proof that no timer interrupts occurred. LIVE PC is a last sampled
user PC, not the established faulting instruction. The panel and marker share
FIMD, so a static image alone cannot localize a CPU, bus, IRQ or panel stall.

The user specifically recalled that early freezes began after an attempt to
repair the earlier1–15-minute desktop freezes. The CACHE2 checkpoint was faster
and usable but not stable. POWER3's patch corrected the cache level iterator
and conditional flags in the whole-cache loops. Those traversal fixes are
correct in isolation, but exposed a pre-existing unsafe runtime caller.

## Confirmed source chain

traps_lo.s dispatches the special cache requests to icache_inv_trap and
dcache_inv_trap. ARM's PC pipeline means selectors0 and1 reach those entries:
the first table branch is the out-of-range fallback, not selector0. The new
harness executes the actual add-to-PC dispatch rather than assuming an index.

The I request called arm_icache_inv_all. Despite its name, that function first
issues DCISW across L1 D-cache, without cleaning, then invalidates I-cache.
The D request called arm_dcache_inv_all, also issuing DCISW without writeback.
At runtime either operation can discard unrelated dirty kernel/user data,
including saved state, lock words, IPC buffers or page-table updates.
That is a source-level data-loss mechanism, not merely a failed panic sink.

The Apple API contract requires sys_dcache_flush to publish modified data and
then invalidate it; sys_icache_invalidate prepares newly written instructions
for execution. See [Apple's archived cache manual](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man3/sys_dcache_flush.3.html).
[Arm Cortex-A9 TRM, cache maintenance table](https://documentation-service.arm.com/static/5e8e264088295d1e18d37ce8)
distinguishes DCISW (invalidate) from DCCISW (clean and invalidate), and defines
the corresponding CP15 encodings. The test's data model follows this distinction.

In CACHE2, the wrong starting level made the D invalidation loop skip L1 on
Cortex-A9. Its I-side helper was already destructive. POWER3 made the D request
actually invalidate all L1 sets/ways, adding another effective data-loss path.
This gives a concrete explanation for why repairing cache loops could worsen
behavior. It also provides a candidate shared cause for diverse later failures.
The phone photo does not prove this trap executed immediately before the stall
or that every earlier panic had this cause. Runtime frequency/last invocation
was not captured on the phone. Keep those conclusions separate.

## Correction

For I9100 only, the I trap calls arm_icache_sync_all and the D trap calls
arm_dcache_wbinv_all. Both save CPSR, mask IRQ/FIQ for the whole-cache operation,
and restore the original control/mask bits before normal exception return.
I9100 arm_idcache_wbinv_all now completes D clean/invalidate before ICIALLU and
BPIALL, followed by DSB/ISB. The old order invalidated I-side before publishing
dirty instructions, permitting a stale refill.

The cold/raw invalidation routines and their boot initialization caller remain
unchanged. They have preconditions appropriate to boot/discard operations and
are no longer selected by these runtime cache traps. The POWER3 traversal fixes
are retained. No global -O0, RAM/scanout policy, CPU1, ACTLR or PL310 configuration
changes were made. Home remains off and touch/power on. All WIRE14/POOL15 fixes
remain. This does not implement or claim new external-L2/cache-coherence support.

The port still performs conservative whole-cache maintenance for these requests;
this change does not implement range-specific cache maintenance or validate a
new user address range. It does not dereference user pointers.

## Reproduction and tests

check_i9100_cachetrap.py compiles the actual trap dispatch, both trap entries,
and the real cache helpers/set-way loops. CP15 reads/writes are instrumented,
while barriers and IRQ/FIQ operations execute on ARM QEMU. An explicit model
holds differing old RAM/new dirty cache values in every set/way, including
unrelated simulated kernel/IPC/lock lines. DCCISW queues writeback and DSB commits
it; DCISW discards dirty contents. I invalidation checks D completion ordering.
QEMU itself does not model physical Cortex-A9 cache coherence.

With saved POOL15 source/traps, both selector0 (I) and1 (D) lose512 modeled dirty
lines in the first16KiB geometry and fail. With CACHE2's cache implementation,
the D request performs no maintenance, fails the API contract and loses no dirty
lines. These negative controls and commands are in diagnostics/cache16-20261030/controls.log.

Corrected requests pass across16/32/64KiB, four-way,32-byte geometries and all
four incoming IRQ/FIQ masks: all dirty values reach modeled RAM, every set/way
is covered once, D clean completes before I invalidation, and masks are restored.
Existing cold-loop coverage remains passing. All15 host/ARM scripts plus locktrace
unknown/block pass, as does the relocated prepared-repo cache-trap test.
Kernel/loader builds pass. Production disassembly confirms the selected call
paths, CPSID/MSR and D-before-I ordering. Embedded image/args/hash checks pass.
These checks do not establish stable hardware operation.

## Artifact

Root raw zImage: **CACHE16**, 7530704 bytes.
UUID: `3C5D41B5-6417-376A-9454-B8823A583B56`.
SHA256: `9ed6ccdad8407e3ea2a0f7e7ed2d1562e67d5c29fefcca0eb7abbb92154de71d`.
Matching image, kernel/symbols, patch, production disassembly and logs:
diagnostics/cache16-20261030/. POOL15 checkpoint:
backups/pool15-before-cache16-20261030/. CACHE2 rollback remains preserved.
Prepared source snapshot synchronized; no commits/publication. No tar/Android
image rebuilt. Next device check is one ordinary raw-zImage flash and boot/UI
result; if it fails, one photo. No successful/stable device result is claimed.
