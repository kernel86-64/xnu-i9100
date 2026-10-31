> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# GPU30: текстуры, прозрачность и четыре PP, 31.10.2026

**Результат телефона:** VseSDoli.jpg подтверждает два opaque PP0 texture jobs и
same-VA update, затем E-18/J7/B8080:ff881020 на первом blend. Причина — RGBA
clear register против BGRA writeback. Исправлено в GPU31_CLEAR_PACKING_20261031.md;
blend и PP1..3 ждут повторной физической проверки. Остальной текст ниже — отчёт
о подготовке GPU30 до этой фотографии.

Текущая инструкция пользователя: сосредоточиться на GPU. Расследование
SpringBoard/VM не продолжалось; RM29/COPY25/ARGS26/PERF22 сохранены как есть.
GPU27 clear/readback и GPU28 VS/triangles подтверждены на телефоне. GPU30
ещё не опробована на устройстве. iOS GLES/EAGL/ускоренный SpringBoard пока нет.

## Что добавлено

Одна one-shot последовательность из16 render jobs (каждый GP затем PP):

1. Прежние два16x16 clear и два triangle jobs GPU28.
2. Для каждого PP0..3: полноэкранный16x16 quad из двух triangles, UV из второго
   GP attribute/varying, выборка линейной2x2 BGRA8888 texture nearest/clamp mip0.
3. Повтор с другими четырьмя texels по тому же GPU VA, чтобы заметить stale input.
4. Третий pattern с premultiplied alpha128 поверх непрозрачного цветного фона:
   source-over ONE/INV_SRC_ALPHA для RGB и alpha. Pixel-kill отключён для blend.

Всего4096 image pixels,78 exact position vertices,72 UV pairs,26 triangles,
12 texture draws (из них4 blend), successful textured PP maskf. CPU пишет
texture input и output sentinel, но не генерирует готовое изображение в output.
Opaque result проверяется точно, blend RGB допускает±1 из-за округления, alpha255
и все padding/guards — точные. Старые edge-channel rules сохранены только для
двух GPU28 triangles; textured quad проверяет каждый пиксель.

GP UV shader — три128-bit инструкции (position.xy/zw и uv.xy). PP shader —
один bundle: varying vec2 -> sampler0 -> MOV texture to color0, sync/stop.
Это фиксированные тестовые программы, не GLSL compiler. Они прочитаны штатными
Mesa24.3.4 GP/PP disassemblers. Descriptor bytes дополнительно совпали с
unmodified Mesa lima_tex_desc C layout и присвоениями его полей.

Descriptor normalized2D, format0x16/noRBswap, dimensions2x2x1, linear layout0,
stride64B, nearest min/mag, clamp edges, min/max LOD0, vendor Mesa nearest
bias8/16. Texels расположены в private VA0x0100b400, второй ряд+64. Между jobs
повторно загружаются только четыре входных texels; следующий job reset cores и
flush L2. Это проверяет данный upload/reset/flush path; не заявляет корректность
произвольного concurrent texture update.

## Память и запуск

Тот же physically contiguous prepared NC64КиБ с CPU PTE proof. GPU VA:
PD/PT pages0/1 walker-only; page2 shaders/commands RO; pages3..10 job data RW;
page11 descriptors/blend commands/input texture RO; pages12..15 unmapped guards.
Position/UV readback, whole output padding и protected checksum выполняются
после каждого job. После контролируемого CPU input upload baseline checksum
обновляется. Live framebuffer/IOSurface не являются DMA targets.

PP registers выбираются по core base8000/a000/c000/e000; MMU каждого PP уже
получает собственный initialized walker block с тем же private PD. Jobs идут
последовательно, без конкуренции за tile heap/stack/output. Маски GPU IRQ0,
bounded polling/timeouts, STOP_BUS ACK и прежний restore/pinned lifetime
сохранены. PLL/CPU/DDR/display/charger policy не менялись.

## Что проверить на телефоне

Только root raw zImage, прежняя команда `heimdall flash --KERNEL zImage`.
ROOTFS не менять. Нужна одна фотография GPU/GIRQ после загрузки.

`GPU S11 E0 R1 GP0b070101 PPf C133 P4096/4096`
`GIRQ000003/0001 M0 G1 T26 V78 J16 X12 Af B0000:00000000`

Частота может быть другой<=160МГц. T — triangles, V — exact position vertices,
J — последний/текущий render job, X — прошедшие textured draws, A — bitmap
PPs с успешно проверенным textured result. PPf выше — обнаруженные cores,
A подтверждает execution этого нового пути. Отдельное property VerifiedBlendPasses
должно быть4, VerifiedTexturePasses12, RenderedPPMask15. Диагностическая строка
55 символов/440pixels помещается в480 и остаётся над старым abort dump.

J1/2 clears, J3/4 GPU28 triangles. Для J>=5:
`core=(J-5)/3`, `pattern=(J-5)%3` (0first,1updated,2blend).
E-17 — position/UV output/padding; новое E-18 — texture/blend image mismatch,
B — byte offset и actual word. E-11 GP/VS/PLBU, E-12 PP/fault/timeout,
E-14 protected-memory checksum, R2 restore/quiescence not confirmed.
Полная старая error/phase legend — GPU27/GPU28 reports. Self-test заканчивается
и восстанавливает питание; это ещё не постоянно работающий iOS renderer.

## Проверки

23 host scripts+4 variants+retained refmod variant+generator check PASS.
Actual C62 cases ASan/UBSan: старые power/clock/MMU/VS/readback/restore cases и
новые no-texture-DMA, UV damage, RB/XY swap, stale texture, RO input/descriptor
corruption, disabled/wrong blending, PP1 image fault, PP2 timeout, PP3 MMU fault,
empty textured quad. Fixture walks PD/PT and fixed shader fields, barycentrically
interpolates actual GP UV output и samples descriptor/input only for validation
of CPU checks/error paths. Это ограниченная host model, не Mali emulator или
physical GPU execution. PP-specific failures должны отвергаться и на поздних jobs.

Actual linked ARM arena builder4 I/F masks проверяет PD/PT permissions,
quad/UV/shaders/descriptor/list/RSW/blend data, unmapped/RO guards. Mesa official
disassembly и descriptor layout output сохранены. Native touch callbacks/masks
и trace265200/2800 сохранены. Kernel/loader/raw/DT/config/delta checks PASS.
Physical texture unit, blending и PP1..3 execution требуют телефона.

## Артефакты и следующий этап

Root raw **GPU30**, 7559200bytes,
SHA256 `bf236692d6d44deb6e76b886f3cfa1c22841b24514d667a4038bce83089df435`,
UUID `7E1F851D-9B97-3347-81C4-97E7F930C166`. Matching sys/assym/logs/source patch:
diagnostics/gpu30-20261031/. RM29 rollback backups/gpu30-before-20261031/;
физически опробованный GPU28 остаётся backups/rm29-before-20261031/.
Exact primary refs/SHA — GPU30_SOURCES.json. Mesa MIT notices сохранены.

- [Mesa Lima](https://docs.mesa3d.org/drivers/lima.html).
- [Texture descriptor](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-24.3.4/src/gallium/drivers/lima/lima_texture.h), [descriptor setup](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-24.3.4/src/gallium/drivers/lima/lima_texture.c).
- [PP encoding](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-24.3.4/src/gallium/drivers/lima/ir/pp/codegen.c), [render state](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-24.3.4/src/gallium/drivers/lima/lima_draw.c).

После hardware PASS — reusable buffer/context/validated-submit/fence interface,
Darwin winsys и compiler/GLES/EAGL/IOSurface integration. SGX535 userspace ABI
не подменяется Mali командами; software-only iOS flags пока сохранены.
