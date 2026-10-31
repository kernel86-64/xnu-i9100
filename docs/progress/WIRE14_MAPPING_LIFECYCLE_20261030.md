> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# WIRE14: target-map translation and per-mapping wiring

The user explicitly authorized repairs after the panic333 VM audit.
MAP13 and matching artifacts/sources were preserved in
backups/map13-before-wire14-20261030/ before changes.

## Corrections

I9100 pmap_extract now walks the requested map under its pmap lock. It validates
L1 bounds/type and L2 type, returns0 for an absent mapping, retains the offset
for sections/large/small pages, and rejects the user TTBR split range. It no
longer obtains a target process's PA from active CPU translation/PAR. Unsupported
supersections fail explicitly rather than producing a truncated physical address.

I9100 now selects the existing shared ARM mapping implementation previously
selected only for QSD8250_LEO. The legacy non-Leo branches remain for other boards
but are not the I9100 production path. PV rooted and hashed entries have the same
mapping_wired prefix; root promotion copies this field. Each managed alias has
its own state. Unmanaged MMIO/scanout mappings have hash-only records, without
indexing RAM PV roots. The physical WIRED flag is refreshed as the OR of managed
aliases, while each mapping contributes exactly once to its pmap count/ledger.

Entry, same-page update, change_wiring, replacement, remove_range and page_protect
now use the same lifecycle. Repeated wire/unwire is idempotent. Replacing or
removing one wired alias debits only that alias. Replacement breaks the old PTE
before publishing the new one. User PV allocation retries happen outside pmap/PVH
exclusion; the existing kernel reserve policy remains, with explicit exhaustion
panic rather than ignored metadata loss.

Bootstrap mappings use exact VA/PA provenance and remain outside tracked-mapping
statistics until adopted. This is not physical VM wire_count. The initial direct
mapping is validated against arm_vm_init, including its sectionOffset tail.
Runtime adoption transfers a known bootstrap mapping to accounted PV metadata.
The I9100 pair capacity is8192 (32MiB of individual bootstrap mappings) to cover
metadata initialization for1GiB RAM; exhaustion is explicit. Range capacity remains64.
No missing PV is silently treated as an arbitrary bootstrap mapping.

I9100 descriptor cache cleaning/barriers and executable D/I cache synchronization
are retained in the shared publication path, including same-page and bootstrap
writes. Removal and break-before-make stores are also cleaned. Other boards retain
their prior selection/policy.

pmap_clear_refmod now converts VM_MEM_MODIFIED/REFERENCED to the corresponding
physical attribute bits. The old direct mask could clear WIRED when asked to
clear modified. Tests prove WIRED survives both operations.

## Validation

Replaced the narrow pmap-enter harness with actual production mapping functions,
actual PV hash insertion/unlink/removal, and actual provenance routines under ARM
QEMU, with modeled VM allocators, page tables, ledgers and cache sinks. Covers:

- First/repeated wire/unwire and same-page enter changes.
- Two aliases in one map and across maps, preserving the remaining alias.
- Root-to-hash promotion and page_protect removal/read protection, including kernel aliases.
- RAM/MMIO replacement in both directions; independent hash-only MMIO aliases.
- Balanced resident/wired ledgers and PV node allocation/free counts.
- Unlocked allocation retry, including retry after old mapping removal.
- Bootstrap entry/adoption/removal, exact direct-map seeding with nonzero
  sectionOffset, range split/replacement and wrong-PPN rejection.
- Distinct target-map L1/L2 tables; absent/small-XN/large/section mappings;
  bounds and user split rejection; ref/mod conversion.
- Descriptor/executable synchronization sinks.

All13 available host/ARM regression scripts plus locktrace unknown/block passed.
Final extended mapping cases and relocated prepared-repo mapping check pass.
Kernel and loader builds pass. Production disassembly confirms pmap_enter_options
and pmap_change_wiring select the shared helpers and extract does not issue ATS.
Embedded kernel, boot arguments and image identity checks pass.

These are instruction/source/model checks; they do not establish physical cache
coherence or stable phone boot. The writer/lifetime error that produced IPC
header0x140 in panic333 remains unidentified. No IPC cleanup is skipped, no
corrupted message is discarded, no lock is forced open and no preemption counter
is reset. Device results must decide whether these source fixes affect that panic.

## Delivered image

Root raw zImage: **WIRE14**, 7502032 bytes.
UUID: `53524443-F06E-3C33-BA17-67B6994EF515`.
SHA256: `cd5d2f3d1ddfdeeafdb1a184f29d0c1c87913dd0c8c665f24aa0dd3ababbbc42`.
Home disabled, touch/power enabled. Matching symbols, image, patch, disassembly,
build/test logs and manifest: diagnostics/wire14-20261030/.
Prepared XNU source/test snapshot updated; no commits or publication performed.
No tar or Android boot image regenerated. Next user step: one normal flash and
report boot/interface outcome, or one pinned-header photo if panic occurs.
