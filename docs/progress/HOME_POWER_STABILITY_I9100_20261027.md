> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# I9100 Home, charging and cache maintenance — 2026-10-27

## Device result and recovery point

The user reports much faster boot and a substantially more usable UI after CACHE2, but random complete screen freezes without an observed panic or reboot. This confirms a hardware performance improvement from the cache-policy build, not long-term stability. No device result for POWER3 is available yet.

The exact CACHE2 images, archives, unstripped kernel, dSYM and source originals are preserved in `backups/cache-usable-before-home-power-20261027/`. Keep this checkpoint: it is the last device-reported usable build. The earlier boot/touch checkpoints remain untouched.

## Cache maintenance and freeze diagnostics

Two defects were found in `armv/cpufunc-v7.s`:

1. Whole D-cache operations initialized r1 to zero, but r3 was the level iterator and still contained LoC. They skipped L1 on Cortex-A9.
2. The set/way loop used a non-flag-setting shift before conditional SUBNE/SUBEQ. Once L1 traversal was enabled, these conditions still tested an earlier comparison rather than whether the set index was zero. The I9100 path now uses LSRS and correctly advances ways.

I9100 instruction-range synchronization also cleans D-cache first, then invalidates all VIPT instruction aliases and branch predictors with DSB/ISB. This is necessary for calls outside the executable-page helper corrected in CACHE2. Explicit `platforms.h` inclusion makes board selection available in this assembly file. Other boards retain their previous branches.

`tools/check_i9100_cacheops.py` executes the actual selected assembly under ARM QEMU, replacing CP15 geometry reads and set/way writes with instrumentation. It checks every set/way at 16/32/64KiB, four-way, 32-byte-line geometries for both invalidate and clean/invalidate. The old checkpoint fails this test; the corrected code passes. This validates the traversal, not real Exynos cache coherence. These defects are credible stability issues, but cannot yet be assigned as the cause of the reported freezes.

POWER3 adds an IRQ progress marker when the GUI is active: an 8x8 square at the top right changes color every 100 timer interrupts. After more than about five seconds without another frame, the last diagnostic row shows `LIVE IRQ <hex> PC <hex>`, refreshed from the timer IRQ. The PC is the interrupted context, not proof that this PC caused a stall. An idle screen can also show this row normally. It performs no allocation, I2C, IOKit calls or locking in the IRQ. Small diagnostic writes can coincide with a frame copy. The marker shares the existing FIMD controller, so a display-controller stall can also hide progress.

If the UI freezes again, photograph the whole screen and check whether the square or LIVE IRQ number continues changing. If it changes, IRQ delivery and the panel still work, narrowing investigation toward userspace/workloops or a kernel spin with IRQs enabled. If it does not, this does not alone distinguish masked IRQs, a CPU/bus hang and a panel stall. `i9100perf=0` disables all of this panel instrumentation.

## Physical Home

Samsung's U1 board sources identify Home as GPX3(5), active low, GPIO2 base 0x11000000, bank offset 0xc60. Only this pin's mux and pull fields are modified; unrelated GPIOs, including SD card detect GPX3(4), are preserved.

A second instance of the existing IOHIDEventService publishes a Consumer Control device (usage pair 0x0c/0x01) with a separate queue/client. It emits the physical Home switch as Consumer Menu 0x0c/0x40 using keyboard event type 3. The native queue message is 52 bytes: the existing 28-byte iOS header plus Apple's 24-byte IOHIDKeyboardEventData layout. Touch keeps its own proven 204-byte queue.

Polling is 20ms with a 20ms stable-state debounce. Boot/open while held does not invent a press. Press and release have actual sampled edge timestamps; holds have no fabricated repeat/up. Sixteen retained edges bound queue backpressure while preserving an eventual release. Closed readers discard old transitions. Native copy-event selector 2 returns the proper 52-byte keyboard event for event type 3. Actual Home action, double press and long press still require device verification.

Some additional aggregate copies exposed the existing ARM compiler's scoped memcpy link problem. Observation/packet copies now call the existing ARM bcopy explicitly; the wire contents remain unchanged. Home serializers initialize fields directly and never add runtime symbol aliases.

## Battery and charger

A new IOPMPowerSource subclass polls hardware on its own workloop once per second. This is real charger control and measurement code, not a fabricated charging flag. Standard capacity, voltage, external-power and charging properties are published, with extra measurement-validity and stop-reason properties. Current draw, remaining minutes, cycle count and calibrated mAh are not invented. Capacity is reported on a relative 0..100 scale. Integration with the original iOS status-bar/power-daemon matching remains a device test.

Wiring is specific to international U1/GT-I9100:

- MAX8997 PMIC: 7-bit 0x66, GPB SDA6/SCL7, GPIO1 base 0x11400000 + 0x40.
- MAX17042 gauge: 0x36, GPY4 SDA0/SCL1, GPIO2 base 0x11000000 + 0x1a0. Gauge access is read-only: version, presence, VCELL and VF SOC. The driver does not rewrite gauge models/configuration or use externally programmed gauge temperature as a battery thermistor.
- Board revision <8: MAX8997 main charger, battery thermistor on ADC6.
- Revision >=8: MAX8922 subcharger, GPL2 enable2/CHG4/POK5, battery thermistor on ADC7. Samsung's GPIO inversion makes a high enable pin select the default USB rate. No 300us high-current programming pulse is generated. Fresh enable has at least a 5ms disable interval, preventing a quick retry from becoming a programming pulse.
- Exynos4210 ADC: 0x13910000, CMU CLK_GATE_IP_PERIL 0xc950 bit15, 12-bit conversions at a 50:1 prescaler. Do not substitute Exynos4412's 0x126c0000 or its PMU ADC PHY setup. Five samples are trimmed by dropping min/max, then interpolated using the Samsung EUR channel-specific thermistor tables. ADC configuration/mux and clock ownership are restored after the read, including timeout.

uniLoader now retains a bounded, well-formed ATAG_REVISION as `i9100rev=0xN`. If absent, the kernel reads stable revision straps GPE1[3:0], only if their mux is already GPIO input. Unknown revision prevents charger control rather than selecting a guessed circuit. The old bootloader text claiming `battery: OK` without a measurement is replaced with a deferred-telemetry message.

The GPIO I2C implementation uses only these two known buses/addresses, open-drain signaling, ACK/NACK, repeated START, little-endian fuel words, bounded stretching and bus recovery. It preserves mux/pull/data fields. Short transactions disable thread preemption while keeping IRQs enabled; there is no timer-IRQ I2C activity. SD's one-time PMIC initialization completes before this service starts. Touch uses a different bus.

Charging policy:

- Both routes are disabled before starting control, and the main charger is kept disabled when using MAX8922.
- Main charger uses 4.2V CV, 450mA fast-current setting, 100mA termination, autonomous termination enabled and a five-hour hardware timer. MAX8922 uses its default USB-rate mode (the MAX8922L datasheet gives 400mA; Samsung calls it the USB/<=450mA path), with no AC-current programming.
- Valid PMIC/gauge readings, battery presence, plausible 2.5..4.3V cell data, valid SOC data and the appropriate thermistor are required. Charging stops at <=0C or >=45C; thermal recovery requires 5..40C.
- Charge ends conservatively at >=4.2V, or full SOC with >=4.15V, or main-chip end-of-charge with >=4.1V. A full latch stays until disconnect. No automatic recharge cycle is added in this first implementation.
- A five-hour software session limit stays latched until disconnect, including time spent paused. MAX8997 also has its hardware timer; no equivalent programmable timer is assumed for MAX8922.
- I/O/measurement failures request charger disable. On the subcharger, GPIO disable is independent of PMIC I2C. A dead PMIC bus can prevent confirmation of a main-charger disable: measurement validity is then false, and the code does not claim a verified hardware state. Invalid measurements do not invent battery removal or erase the last valid capacity.
- `IsCharging`/`CHG` is derived from actual chip status or the CHG/POK pins after control, not merely from cable presence or the enable command.

This implements charging while XNU is running. There is no standalone powered-off charger/recovery mode yet. Hardware current, temperature calibration, termination, sustained charging and original iOS UI reporting require validation on the phone. Autonomous chip voltage/thermal behavior is retained; software thermal supervision necessarily stops if the CPU completely hangs.

## Panel values and testing

`POWER3` identifies the build. Existing COPY/GAP/SD diagnostics remain. The third row shows:

`BAT <percent>% <mV>mV T<deci-C>/10C USB<connected> CHG<actual charging> R<reason> REV<revision>`

`BAT unknown` means no valid complete measurement. Stop reasons: 0 healthy control; -1 I/O or invalid measurement; -2 unknown revision; -3 temperature; -4 full; -5 timeout; -6 battery absent; -7 no input power. USB1 alone is not proof of charging. For a charging test, photograph values after cable insertion and removal, and compare voltage/percentage after several minutes. Do not infer measured current from the configured current setting.

All host checks pass: existing storage, touch, cache policy and timing/frame bounds, plus Home debounce/hold/backpressure/native ABI, 16 revision selections, both charger paths, thermal/full/timeout behavior, absent battery, invalid gauge/ADC data, and injected I/O failures. GPIO-edge slave models test the actual I2C code, exact buses/addresses, endian order, ACK/NACK, pin restoration and timeouts. ADC and charger GPIO register models check masks, clocks and configuration restoration. These mocks are not hardware validation.

ARM kernel and uniLoader are rebuilt, with existing toolchain warnings. Root `boot.tar` and `zImage.tar` contain this build. Logs, assembly inspection and artifact hashes are under `diagnostics/home-power-20261027/`. Reviewable changes are in `home-power-stability-i9100-20261027.patch`.

## Primary source references

- [Samsung U1 gpio-u1.h](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/cm-10.1/arch/arm/mach-exynos/include/mach/gpio-u1.h), [mach-u1.c](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/cm-10.1/arch/arm/mach-exynos/mach-u1.c): Home, board wiring and thermistor tables.
- [Samsung sec_battery_u1.h](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/cm-10.1/include/linux/power/sec_battery_u1.h), [sec_battery_u1.c](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/cm-10.1/drivers/power/sec_battery_u1.c): EUR revision threshold and ADC channel selection.
- [MAX8997 U1 driver](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/cm-10.1/drivers/power/max8997_charger_u1.c), [MAX8922 U1 driver](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/cm-10.1/drivers/power/max8922_charger_u1.c), [MAX17042 U1 driver](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/cm-10.1/drivers/power/max17042_fuelgauge_u1.c).
- [Samsung map-exynos4.h](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/cm-10.1/arch/arm/mach-exynos/include/mach/map-exynos4.h), [clock-exynos4.c](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/cm-10.1/arch/arm/mach-exynos/clock-exynos4.c), [ADC driver](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/cm-10.1/arch/arm/plat-samsung/adc.c).
- [Apple IOHIDEventData.h, IOHIDFamily-503.1.13](https://github.com/apple-oss-distributions/IOHIDFamily/blob/IOHIDFamily-503.1.13/IOHIDFamily/IOHIDEventData.h), [IOHIDEvent.cpp](https://github.com/apple-oss-distributions/IOHIDFamily/blob/IOHIDFamily-503.1.13/IOHIDFamily/IOHIDEvent.cpp): native keyboard event layout.
- [MAX8922L manufacturer datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/max8922l.pdf): default current, enable programming, charge status and autonomous protection. GPIO polarity follows the Samsung board driver, not the chip pin in isolation.
