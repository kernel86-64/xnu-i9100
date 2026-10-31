> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# GT-I9100 storage repair — 2026-10-27

The kernel builds and host regression checks pass. After flashing, the user reported successful boot and provided `BOOTED.jpg`, showing the iOS 7 lock screen on the Galaxy S2. The current archive hashes match the repaired build. A preserved checkpoint with images, unstripped kernel/symbols and the photograph is in `backups/booted-20261027/`.

This records the user’s boot result and the visible interface. Boot logs, touch behavior and stability across repeated cold boots were not supplied with the photo.

## Evidence from the photographs

`codex2.jpg` shows a raw MBR signature of `10af` being labeled “clean”, subsequent reads with different invalid signatures, guessed FAT alignment (`bo=7 bs=7`), and failure to find `IOS7`. The old signature detector returned zero both for clean and unknown data; zero was then logged as clean. Filesystem code searched byte/bit offsets, overwrote signatures, guessed FAT links and transformed all image sectors using one inferred alignment. Such transformations lose boundary data and cannot establish integrity.

`codex1.jpg` contains the tail of a panic, without its first line/fault registers. Its UUID `A9FFCC2D-933B-3B97-92CD-7EED130E75D0` matches the saved pre-change kernel exactly. Symbolization against that kernel gives:

| Address | Actual symbol and offset |
| --- | --- |
| `800cfa34` | `data_abort_crash_in_kernel + 50` |
| `802ebe0b` | `hfs_swap_BTNode + 9a1` |
| `802e1787` | `GetBTreeBlock + 28b` |
| `8031712d` | `GetNode + 5b` |
| `80318329` | `SearchTree + 63` |
| `803146bd` | `BTSearchRecord + 107` |
| `802e4101` | `cat_idlookup + c1` |
| `80307237` | `hfs_MountHFSPlusVolume + f23` |
| `802fc0ff` | `hfs_mountfs + ee3` |
| `802fb0fb` | `hfs_mountroot + 2b` |

Offsets above are hexadecimal. This places the abort in the HFS B-Tree mount path. The photo alone does not identify the precise faulting instruction or prove its cause. Several function names printed on the device are misleading; keep using the matching unstripped kernel for symbolization.

## Source comparison and changes

Reference: [xnu-S2I9100 commit 6ec0eaf](https://github.com/zenkernelsam/xnu-S2I9100/commit/6ec0eaf). Its commit message describes **QEMU smdkc210** verification. This does not establish correct real-device clock, pin or power initialization.

The SD protocol/error path was rebuilt around the same command sequence, with bounded CMD17 transfers and explicit recovery. The old loop could accept CRC/error status when buffer-ready or transfer-complete was simultaneously set: its error check was inside the loop that the completion bit bypassed. Every command/data poll now checks errors first; card R1 errors also fail the request. Failed transfers reset command/data lines and stop the card before retrying. Only completed, error-free sectors reach successful I/O completion. The IOKit adapter uses a fixed 512-byte allocation, checks request arithmetic, and reports completed bytes on partial failure.

Clock configuration was checked against upstream Linux:

- [Exynos4 clock registers](https://github.com/torvalds/linux/blob/v3.0/arch/arm/mach-exynos4/include/mach/regs-clock.h) and [clock routing](https://github.com/torvalds/linux/blob/v3.0/arch/arm/mach-exynos4/clock.c): HSMMC2 gate is CMU `0xC940` bit **7**, not `0xC934` bit 2 (LCD0). `sclk_mmc2` is enabled through `0xC340` bit **8**. Its parent is selected through `0xC240[11:8]`; the pre-divider occupies all eight bits `[15:8]` of `0xC548`.
- [Exynos4 card setup](https://github.com/torvalds/linux/blob/v3.0/arch/arm/mach-exynos4/setup-sdhci.c): select SDHCI base source 2, RX feedback and clock hold; configure the low-frequency delay selects. These settings were absent in the previous driver.
- [Exynos4 GPIO routing](https://github.com/torvalds/linux/blob/v3.4/arch/arm/mach-exynos/setup-sdhci-gpio.c): no pull on CLK/CMD, pull-ups on DAT lines; preserve unrelated pin fields.

The PMIC path now accesses only MAX8997 slave `0x66`, LDO17 register `0x4B`, on the known GPB[7=SCL,6=SDA] bus. It performs open-drain bus recovery, verifies readback, and restores pin configuration. Arbitrary I2C scanning and regulator writes to responding devices were removed. If the PMIC transaction fails, the probe uses inherited slot power and still requires valid raw card reads.

FAT locator and HFS mount/catalog/endian/B-Tree logic were restored from the reference, removing guessed bit fields, hardcoded leaf probes, synthetic root directories and mount retries over partial state. The existing extra record-offset guard in `BTreeNodeOps.c` was retained. Strict mirrored/active FAT and fragmented-image validation remain; root image file size is not hardcoded. The image mapper returns raw sectors, and `exec_activate_image` no longer rewrites Mach-O bytes. RAM COW remains the backing for filesystem writes.

The old handoff incorrectly called `srcOffs[-1]` an out-of-bounds access. In the original internal-node swap routine, `srcOffs` intentionally points one entry after the free-space offset, so index `-1` is valid. Its comment explicitly documents this. The speculative replacement with the end of the buffer weakened bounds checks and was removed.

The old claim that leading zero data makes the SD start bit arrive late is unverified. Clock/configuration bugs and error acceptance are established source-code defects; the exact physical origin of the shifted bytes needs real-device observation after this repair.

## Validation

- `python3 tools/check_i9100_storage.py` passes with AddressSanitizer and UndefinedBehaviorSanitizer.
- The MMIO model covers simultaneous error/completion, command and data CRC failures, retry/recovery, readiness timeout, R1 errors, bounds, unaligned destinations, SDHC/SDSC capacity/addressing, invalid and unstable raw MBRs.
- Sparse FAT32/HFS fixtures cover fragmented extents, mirrored and active FAT, cycles, missing/duplicate directories, shifted/corrupt data rejection, incompatible headers, backend failures, and read/extent limits.
- XNU `RELEASE ARM EXYNOS4210_I9100` and uniLoader build successfully. The build emits existing toolchain warnings, including an `xcodebuild` discovery warning; the make exit status is zero and the kernel links.
- Both tar member names/payloads and Android boot header/kernel payload are checked after packaging.

Host checks do not emulate physical SD timings, PMIC wiring, the complete HFS kernel or a real boot. The intentionally slow (~200 kHz) single-block PIO path can increase boot time.

## Boot diagnostics to retain

The user has now reported a successful boot. The following individual checkpoints still need capture from a device boot log:

1. `i9100 SD: strict PIO v2 clk=8007 ctrl2=c0004120 ctrl3=80808080`
2. `i9100 SD: MBR 55 aa verified 3/3`
3. `fl32: strict FAT32 ...`, then exact `IOS7` / `ROOTFS  HFS` directory matches.
4. `Leo file: validated ...`, followed by the real HFS mount and `/sbin/launchd` execution.

If probing fails, the controller status and return code are printed. No failed probe publishes corrupt media. For another panic, retain the first panic line and fault registers as well as the backtrace. Stable discovery should be checked across repeated cold boots.

## Recovery and artifacts

Original sources, old flash tarballs and the matching unstripped kernel are preserved under `backups/storage-20261027/`. This workspace has no `.git` repository. `storage-repair-20261027.patch` records the source/documentation changes against those saved files. Build/test logs and final hashes are in `diagnostics/storage-20261027/`.
