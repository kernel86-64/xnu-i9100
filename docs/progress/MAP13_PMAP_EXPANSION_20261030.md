> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# MAP13: preserve a competing L2 installation

## Phone result and confirmed limits

`please.jpg` matches STOP12 UUID AA4A7545-72A6-3CA7-A738-8159264AEE16.
The first panic, at uptime107.671904166s in backboardd context, is a kernel
write data abort. FAR/R0=d1ef327c, R1=df113840, length R2=0x5c (92 bytes),
PC=800ca6d0, LR=800149e3, CPSR40000113, DFSR00000807.
The instruction is `streq r5,[r0],#4` inside memcpy (unaligned-to16, aligned-to4
forward-copy preparation). LR is ipc_kmsg_get_from_kernel after copying to
kmsg->ikm_header. The upper call chain is mach_exception_raise,
exception_deliver, exception_triage, doexception, sleh_abort and user prefetch
entry. Thus another user prefetch failure led to exception-message delivery,
which itself faulted writing an IPC buffer. The photo does not give the
original user PC or identify why that kernel buffer lacked a usable mapping.
Do not blame memcpy merely because the faulting store is there.

STOP12's terminal policy worked: scrolling stopped. The secondary exception
is PC800c3018, LR800c3009, TYPE3, FSR2, PSR600001b3, FAR0. Matching disassembly
locates `bkpt #0` in Debugger. This explains the observed secondary exception;
it is separate from the primary missing kernel-memory mapping.

## Deterministic source defect and correction

pmap_enter_options drops the pmap lock before requesting expansion.
pmap_grab_page may wait or schedule. The old pmap_expand computed its TTE,
allocated a fresh zeroed L2, then locked the map and unconditionally replaced
the descriptor. If another thread completed expansion and populated that
same region during the wait, the resumed thread discarded the existing
mappings by publishing its empty table.

The new check_i9100_expand.py compiles the actual ARM pmap_expand. Its modeled
allocator injects a second call to the actual function while the first call
is blocked, then installs a populated PTE in the winner. Old STOP12 source
fails because its descriptor no longer equals the winner. The corrected
source passes for both kernel and user pmaps.

I9100 pmap_expand now checks under the pmap lock before allocation, releases
the lock to allocate, refetches and rechecks after allocation, and retains a
competing installed table. It releases the unused wired page through
VM_PAGE_FREE under its owning object's lock, outside the pmap spinlock,
and balances inuse_ptepages_count. Allocation count remains cumulative.
Repeated expansion is idempotent and an unexpected nonzero descriptor causes
a fatal invariant failure instead of being overwritten.

Also reject user addresses >=0x40000000, matching pmap_pte's TTBR split rule.
The previous > comparison admitted the boundary even though pmap_pte always
returned0 there, making its expansion loop unable to complete. Existing
pmap_enter tests now cover both boundary and above-boundary rejection.

The expansion race is a proven source defect that can lose kernel mappings.
Its responsibility for this phone panic, the prior ownerless locks and
preemption failures is not proven. MAP13 is a repair candidate, not a claim
of stable boot. No lock is forced open and no preemption count is reset.

## Fewer manual cycles

The competing-thread scenario is now reproducible without a phone. The full
available13-script host/ARM regression matrix plus locktrace unknown/block
runs as one batch:

```sh
python3 tools/check_i9100.py --log /tmp/i9100-tests.log
```

The runner has no phone access and does not flash anything. It discovers
check_i9100_*.py beside itself and stops on the first failure. Both targeted
controls and the complete batch passed for MAP13, including storage, touch,
timing, cache policy/cacheops, power, preemption, accounting, pmap enter/expand,
locktrace, fatal gate and renderer. No claim of physical cache/GPIO/charging
validation follows from those modeled checks. Kernel/loader build, embedded
blob/boot arguments and targeted production disassembly pass.

## Delivered artifact

Root raw zImage: MAP13, 7424160 bytes.
SHA256: `90ef84b4732ff296f8a35ef37198c9664fa4af5e5df0fed91ea025290cebb275`.
UUID: `6BC75085-0DA4-3F04-9FC3-0414C7A9BE23`.
Home disabled, touch/power enabled. Artifacts and symbols:
diagnostics/map13-20261030/. STOP12 backup:
backups/stop12-before-map13-20261030/. Prepared XNU source snapshot updated.
No tar or Android boot image regenerated. No phone flashing was performed.

The only next user action is the usual single raw-zImage flash and a report
whether boot/interface survives. If it panics, one photo containing the pinned
header is sufficient; avoid requesting multiple new diagnostic variants.
