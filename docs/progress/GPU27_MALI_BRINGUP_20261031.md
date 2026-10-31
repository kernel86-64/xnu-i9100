> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# GPU27: аппаратный bring-up Mali-400, 31.10.2026

По запросу пользователя начат GPU bring-up. Реализованы IOS7I9100Mali и
изолированный GP PLBU -> PP0 -> private-memory self-test. Физический результат получен: `GPUtest1.jpg` показывает
`S11 E0 R1 GP0b070101 PPf C133 P512/512`, `M0 G1 BAD0000:00000000`.
GP PLBU/PP0 two-color и восстановление питания прошли на телефоне. UIKit/QuartzCore продолжают software rendering; ускорение
SpringBoard пока не заявляется. ARGS26/COPY25/PERF22/cache/VM/Home/touch/power
сохранены; результат стабильности ARGS26 на телефоне отдельно не сообщён.

## Обнаруженный userspace и граница этой выдачи

В порте ранее не было Mali driver: IOSurface CPU backing и FIMD present работают
через CPU. В supplied shared cache найдены IMGSGX535GLDriver (0x2c20d000),
OpenGLES (0x2f701000), GLEngine и IOAccelerator. Cache SHA
cad2df775e122c660238f341e74c163a2ea0ed261e85bfd3190de750cd9c0d2c.
Их SGX535 shader/command ABI не является Mali ABI. Нужен отдельный iOS
OpenGLES/EAGL backend, затем интеграция QuartzCore. Одного CA_ENABLE_OGL мало.
Rootfs и launch environment здесь не менялись. GPU27 — отдельный IOService,
без IOAccelerator/OpenGLBundleName, Apple GPU impersonation и fake rendering.

## Реализовано

AppleARMPE регистрирует GPU после display/storage/power/HID. Собственный
workloop и one-shot timer20мс; один self-test, затем только RAM diagnostics.
Default включён, boot arg `i9100gpu=0` отключает GPU probe.

| Блок | Exynos4210 / Samsung U1 |
| --- | --- |
| Mali |0x13000000,64КиБ; GP,4PP,5MMU |
| CMU |0x10030000; G3D source0xc22c/div0xc52c/status0xc62c/gate0xc92c |
| MPLL |4210 CON0=0x14108, source CPU mux0x14200 bit8, xtal24МГц |
| PMU |0x10020000, G3D conf0x3c60/status+4 |
| Rail |MAX8997 BUCK3 CTRL0x2a/DVSTV0x2b; BUCK4 — camera rail |
| PMIC bus |Existing GPB6/7 GPIO1=0x11400000, same UP exclusion as power driver |

MPLL декодируется, G3D divider выбирается с потолком160МГц. Общие PLL, CPU,
DDR/display clocks не перенастраиваются. Cold rail —1100мВ, допустимое уже
включённое состояние950–1200мВ сохраняется. Это сверено с vendor startup и
Linux OPP. Исходные rail/source/div/gate/domain fields сохраняются; посторонние
bits не меняются. Перед вмешательством проверяется отсутствие inherited active
GPU job. Charging policy/регистры не меняются.

Private64КиБ: IOBuffer physically contiguous, prepared/wired, Normal-NC.
Перед hardware test явно устанавливаются NC attributes и проверяются CPU PTE
каждого4КиБ page, включая physical address. Ошибка — E-16, без старта DMA.
GPU VA0x01000000 использует собственные PD/PT: сами таблицы GPU-VA не mapped,
commands/shader RO, job pages RW, trailing guards unmapped. Framebuffer,
IOSurface и userspace не являются DMA targets. GP/PP/MMU interrupt masks=0,
raw status polling, GIC не меняется; все waits ограничены.

Проверяются GP family0x0b07 и PP0..3 family0xcd07, reset, L2 и5MMU. GP PLBU
head/end создаёт один tile; PP0 пишет16x16 BGRA8888 сначала white0xffffffff,
затем black0xff000000. CPU записывает только другой sentinel и проверяет512
пикселей, padding и protected checksums после каждого job. IRQ без DMA не PASS.
PP1..3 пока определяются/reset/MMU-init; rendering проверяется только на PP0.
VS/triangle, arbitrary shader programs, GL contexts и UI acceleration не готовы.

Перед отключением domain GP+4PP должны подтвердить STOP_BUS. Затем domain off,
восстановление clock/rail/domain fields. R1 не означает восстановление полного
command-processor context. Если STOP_BUS не ACK — R2, power/clock остаются,
private pages не освобождаются. Если power-off не ACK после bus stop — R2,
G3D clock gated, rail сохраняется. Arena удерживается весь boot lifetime во всех
случаях: неизвестное DMA state не превращается в DMA-after-free. Нет бесконечного
retry, global cache trap, heap repair или подавления panic/assertions.

## Проверка телефона

GPU/GIRQ на строках416/432 остаются видимыми и при crash dump448–608.
Ожидаемый успех:

`GPU S11 E0 R1 GP0b07.... PPf C160 P512/512`
`GIRQ000002/0001 M0 G1 BAD0000:00000000`

C — частота теста, может быть ниже160МГц. PPf — обнаружены4PP, P512 — два
readback теста PP0. После них исходное питание/тактирование восстанавливаются;
GPU не оставляется постоянно занятой. Это hardware test, а не UI acceleration.

Phase1 allocation/maps;2 rail;3 clock;4 domain;5 IDs;6 reset/L2;7 MMU;
8 GP;9 PP;10 readback;11 successful completion+restore.
R0 — ещё не менялось/в процессе; R1 restore OK; R2 quiescence/restore не подтверждены.

| E | Причина |
| --- | --- |
|-1|mapping/allocation/contiguous arena |
|-2|MAX8997 I/O/readback |
|-3|исходное rail state |
|-4|MPLL/mux/divider |
|-5|domain state/transition |
|-6|GP/PP ID |
|-7|inherited active job |
|-8|reset |
|-9|MMU reset/enable |
|-10|L2 command |
|-11|GP error/fault/timeout |
|-12|PP error/fault/timeout |
|-13|pixel/padding mismatch, BAD offset/value |
|-14|protected checksum |
|-15|otherwise-successful test failed restoration |
|-16|CPU NC/physical PTE check |

Одна прежняя `heimdall flash --KERNEL zImage`, затем фото двух строк GPU/GIRQ.
Rootfs менять не нужно. При panic — полный header/UUID и matching GPU27 symbols.

## Проверки

23 host/ARM scripts+4 variants PASS. Actual portable C с ASan/UBSan:38 явных
power/clock/MMU/job/DMA/failure cases, private GPU page walk/permissions,
two-color readback, no-DMA false-success rejection, pixels/padding/protected-page
corruption, PMIC failure до/после записи, bounded timeouts и STOP_BUS quarantine.
Это register/DMA model, не Mali emulator и не physical pass.

Actual linked ARM arena builder:4 I/F masks, buffer guards, PD/PT permissions,
GP/PP packets, RSW и Mesa clear shader. Mali ISA не исполняется. C++ wrapper
собрана; long-call targets setter/PTE/selftest и NC comparison проверены в
disassembly. Native touch callbacks/PERF22 counts265200/2800 сохранены.
Kernel/loader/embedded/config/DT checks PASS. MMIO, rail, GPU execution и physical
cache coherency требуют телефона.

## После аппаратного подтверждения

1. Исправить failing hardware stage, если он проявится; затем VS/triangle.
2. Buffers/contexts, validated submit/fences/timeout recovery и IOKit user client;
   Darwin winsys для Mesa Lima вместо Linux DRM.
3. ARMv7 Darwin Mesa Lima compiler/GLES backend и реальная EAGL/GL-driver/
   IOSurface boundary; исследовать GLEngine ABI, не пересылать SGX commands в Mali.
4. После correctness/geometry/synchronization подключать QuartzCore и снимать
   software-only flags; UI performance измерять отдельно от hardware self-test.

## Артефакты и первичные источники

Manifest/symbols/assym/logs/patch/sources: diagnostics/gpu27-20261031/.
ARGS26 rollback image и matching kernel/config: backups/gpu27-before-20261031/.
Root zImage GPU27,7554992Б, SHA256
a5b38d97ce3c928f72c07280fa78a7da1aa385947818e2e98f7f9a596032d524,
UUID AD5FC668-D2EB-385E-8FF6-46D8AB3D75CB. Rootfs/config/DT неизменны.

Exact reference URLs/SHA: GPU27_SOURCES.json и archive references.json.

- [Mesa Lima](https://docs.mesa3d.org/drivers/lima.html).
- [Mesa24.3.4 packets](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-24.3.4/src/gallium/drivers/lima/lima_job.c), [clear shader](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-24.3.4/src/gallium/drivers/lima/lima_screen.h).
- [Linux6.12 Lima registers](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/lima/lima_regs.h), [Exynos4210 DT](https://github.com/torvalds/linux/blob/v6.12/arch/arm/boot/dts/samsung/exynos4210.dtsi).
- [Pinned Samsung U1](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/a0346556698e62405a04b010c4f4197bdc9fec06/arch/arm/mach-exynos/mach-u1.c), [Mali platform](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/a0346556698e62405a04b010c4f4197bdc9fec06/drivers/media/video/samsung/mali/platform/orion-m400/mali_platform.c).

MIT notices Mesa/Linux Lima (MIT option) сохранены в i9100_mali.c. Vendor
Android driver не импортирован; он служил сверке board registers/rails.
Apple images/cache/compiler не включаются в prepared source snapshot.
