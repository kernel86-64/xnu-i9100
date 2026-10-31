> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# panic333: IPC corruption and deeper VM audit

## Device evidence

panic333.jpg matches MAP13 UUID6BC75085-0DA4-3F04-9FC3-0414C7A9BE23.
At uptime101.101501125s in backboardd context:
PC80014506, LR800144e7, FAR/R0=00000140, CPSRa0000133, DFSR7.
Exact symbols/disassembly: PC is `ldr r0,[r0]` in ipc_kmsg_clean,
immediately after loading kmsg->ikm_header; LR is ipc_kmsg_reap_delayed+23.
The header value used for reading message bits is invalid. The photo does not
identify the actual kmsg address, whether the object or queue is corrupt, the
writer responsible, or whether its lifetime has ended.
Secondary abort is again Debugger BKPT; it terminates under STOP12's gate.
MAP13 did not establish stable operation or resolve the device failures.

Earlier please.jpg failed while writing an exception IPC buffer. This result
fails while cleaning a deferred IPC message. Together they justify examining
object lifetime, thread/queue state and VM, rather than merely suppressing
these individual IPC faults. They do not establish one common cause.

## Actual ARM memory primitives

Executed current bcopy.s and bzero.s in Cortex-A9 QEMU, with a separate byte
reference and whole-buffer comparisons: memcpy source alignment0..7,
destination0..15, lengths0..259; bcopy overlap offsets-32..32; memset/bzero
destination0..31 and lengths0..259; memcpy/memset return values.
All66820 scenarios passed. This narrows the search but does not test physical
cache coherence, interrupt interference or all possible memory accesses.
Reproducer/log: diagnostics/panic333-audit-20261030/audit_memops.py and
memops-audit.log; run the script from the workspace root.

## Confirmed VM source defects

Extracted the actual pmap_extract and pmap_change_wiring functions into an ARM
harness with modeled maps, PTE, ledger/physical flags and PAR. Artifacts:
diagnostics/panic333-audit-20261030/wiring-audit.c, start.S, wiring-audit.log.
This is an audit reproduction of known failures, not a passing regression or
a physical-MMU test.

1. ARMv7 pmap_extract does not walk or switch to the supplied pmap. It only
   uses pmap==kernel_pmap to choose privileged vs user translation. Two distinct
   user pmaps therefore issue identical translation operations for the same VA.
   In a PAR model representing the currently active pmap, asking for the other
   pmap returns the active map's PA. The code has no means to distinguish them.
   pmap_change_wiring is one caller that can pass a particular pmap.
2. pmap_change_wiring has inverted/non-idempotent bookkeeping. Starting with an
   unwired physical page and wired_count0, requesting wired=TRUE runs the else
   (unwire) branch and changes count0 to-1. Starting with wired_count1 and an
   already-set flag, repeated TRUE credits another page, changing1 to2.
   Repeated FALSE on an unwired page also decrements0 to-1. These failures were
   reproduced from the actual function, with RELEASE assertions inactive.
   vm_fault.c calls this routine during wiring changes.

These are concrete VM contract/accounting violations. They are not yet proven
to cause panic333, the earlier IPC fault, ownerless locks, or preemption leak.
In particular a wrong wired counter alone does not prove a wired page was
physically reclaimed: VM also maintains its own wire accounting.

A correct repair must identify wiring per mapping. The current non-Leo code
uses a physical-wide WIRED bit shared by aliases. Merely flipping the condition
would still let one alias clear another alias's status. The next implementation
should provide correct target-map translation and per-mapping wire transitions,
with tests for aliasing, repeated calls, replacement/removal and ledger balance.
Do not suppress IPC cleanup, discard corrupted messages, reset counters, or
claim this audit identifies the writer that produced header0x140.

## Delivered state

No kernel sources or zImage changed during this audit. Root raw image remains
MAP13 with SHA25690ef84b4732ff296f8a35ef37198c9664fa4af5e5df0fed91ea025290cebb275.
No extra phone flash is requested for this audit. Preserve existing source
changes and MAP13 symbols. The known-failure audit is kept separate from the
all-green check_i9100.py suite; earlier green checks did not cover change_wiring.
