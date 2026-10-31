> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# HUD32: compact GPU, BAT and LIVE IRQ overlay

The user requested that all other runtime screen diagnostics be hidden and that
the completed changes be committed and pushed to the published branches.

The normal overlay now uses only three 16-pixel rows at the bottom of the
480x800 framebuffer:

| Row | Content |
| --- | --- |
| y752–767 | GPU phase/error/restore, clock, pixels, job, texture passes, rendered PP mask, MMU/guard |
| y768–783 | BAT percent, voltage, temperature, USB/charging/reason/revision |
| y784–799 | LIVE IRQ count and interrupted PC |

Only GPU error adds y736–751 with pixel offset/value, GP/PP IRQ, triangles,
vertices and detected PP mask. Complete GPU31 self-test success is displayed as:

```text
GPU S11 E0 R1 C133 P4096 J16 X12 Af M0 G1
```

The old COPY/GAP/SD/cache, Home/touch, SpringBoard/backboard/signal/abort rows and
top-right flashing square are removed from both the present and IRQ drawing
paths. A shared formatter restores the allowed rows after every full-frame copy,
so LIVE IRQ is not erased or overwritten by an unrelated row between IRQ updates.
BAT/GPU redraw from already published RAM scalars; no I2C, IO allocation or
IOKit calls are introduced in IRQ. The original 100-interrupt display cadence
is retained, including progress during a UI stall.

Only the board renderer changes at runtime. GPU31 driver/shaders, Home/touch,
trace-on configuration, charger policy and previous VM fixes remain intact.
RAM observations and fatal emergency output are retained. `i9100perf=0` hides
the runtime overlay. The rootfs is unchanged; the delivered artifact is raw
zImage with matching archived symbols. Phone confirmation remains pending.

Existing host/ARM regressions, clean kernel/loader build and matching image
checks are recorded in local diagnostics/hud32-20261101/. No iOS GPU acceleration
or new physical Mali result is inferred from this UI change.
