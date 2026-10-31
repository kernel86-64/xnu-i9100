> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# PANIC7: retain the primary panic message

`iOS7200.jpg` confirms a real kernel panic on TIMER6, with matching kernel UUID
F254E03D-48E3-3DDF-A25E-3AD35D5A1641. It shows current BSD process backboardd,
uptime105804379166ns (~105.8s), and a KDP wait. This process association alone
does not establish the cause. The photo contains the end of the dump: the
primary panic format, expanded arguments and kernel caller scrolled offscreen.
Neither the shown user stack addresses nor KDP wait identifies that cause.

PANIC7 preserves the existing panic/control flow and captures the first768
formatted bytes in fixed board BSS. At formatter completion, it draws category,
actual panic callsite, optional context reason and the bounded formatted text
in the upper256 pixel rows. Very long text is visibly marked truncated. Later
normal debugger output scrolls only in rows256..799. The complete original
formatter output still goes to the existing serial sink. First-panic ownership,
black/white display and allocation-free fatal handling remain intact.

The normal boot console still scrolls over its full height before a panic.
Touch, charger, storage, scheduler and IRQ5/TIMER6 fixes are unchanged. This is
a diagnostic improvement; the physical panic cause has not been read or fixed.

`tools/check_i9100_panic.py` uses the actual board functions under ASan/UBSan.
It now checks bounded capture and preservation of all pinned framebuffer pixels
after20,000 subsequent debugger characters, scrolling, carriage returns/tabs,
and a cursor reset. Frame guards, null framebuffer and no IO allocation checks
also pass. Kernel and loader builds pass.

Root raw `zImage` is PANIC7, with Home disabled and touch/power enabled. Its
matching kernel, UUID, SHA256 manifest and logs are in
`diagnostics/panic7-20261028/`; TIMER6 is preserved in
`backups/timer6-before-panic7-20261028/`. No tar/Android image was regenerated.
Device verification of the pinned header is pending. The next device photo
should include the top of the completed panic screen.
