> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# GPU28: вершинный шейдер и треугольники Mali-400, 31.10.2026

GPUtest1.jpg впервые подтвердил выполнение GPU27 на телефоне:
`GPU S11 E0 R1 GP0b070101 PPf C133 P512/512`
`GIRQ000002/0001 M0 G1 BAD0000:00000000`.
Это GP PLBU/PP0 two-color readback, неповреждённые защитные области и успешное
восстановление rail/clock/domain на133МГц. Экран блокировки виден. Фото и
машиночитаемый результат сохранены в diagnostics/gpu27-20261031/.
VS/geometry, PP1..3 rendering, UI acceleration и длительная стабильность
этим фото не подтверждены. Старый SpringBoard slab assertion не закрыт.

## Изменения GPU28

После двух сохранённых16x16 clear jobs запускаются ещё два16x16 draw jobs:
красный треугольник в левой верхней половине и зелёный в правой нижней.

- GP VS загружает три vec4 атрибута и двумя MUL-by-one инструкциями пишет
  post-viewport x/y/z/reciprocal-w. Все48байт output и padding страницы
  проверяются отдельно перед PP. CPU пишет в output только sentinel.
- GP PLBU получает настоящий triangle draw, RSW, viewport/scissor/depth range,
  vertex-output pointer и VS/PLBU semaphores. Требуются оба completion bits и
  отсутствие active status; IRQ без записи вершин не является успехом.
- PP0 fragment shader возвращает RGBA constant red/green. Это фиксированные
  тестовые программы, а не GLSL compiler. Начальный фон black. CPU не рисует
  треугольник и не заполняет ожидаемыми цветами output.
- Точно проверяются interior, exterior, alpha/channel constraints на краях,
  output padding, read-only pages и unmapped guards после каждого job.
  На краевой полосе допускается antialiasing в единственном ожидаемом канале;
  P1024 означает512 clear pixels и512 triangle pixels с этими правилами.
- GP output получает отдельную RW page10 в том же prepared NC64КиБ arena.
  Pages0/1 доступны только walker; commands/shaders page2 RO; pages3..10 RW;
  pages11..15 unmapped. Живой framebuffer/IOSurface не является DMA target.
- Питание, clocks<=160МГц, MMU init, IRQ masks0/polling, ограниченные waits,
  STOP_BUS и pinned lifetime сохранены из GPU27. Job ничего не оставляет
  постоянно исполняться. Общие PLL/CPU/DDR/display не перенастраиваются.

`tools/generate_i9100_mali_shaders.py` воспроизводит header с программами по
MIT Mesa24.3.4 GP/PP bit layouts; `--check` сравнивает точные bytes.
Штатные GP/PP дизассемблеры того же Mesa прочитали их как четыре attribute MOV
через GP MUL units и single PP MOV constant/stop. Вывод mesa-shaders.dis в
архиве. Полного Mesa NIR/GLSL compiler и iOS GL backend здесь ещё нет.

## Проверка телефона

Нужен только root raw zImage, прежняя команда:

```sh
heimdall flash --KERNEL zImage
```

ROOTFS не менять. assertion2.jpg подтвердила успешный GPU28 на133МГц с
P1024/1024, T2 V6 J4, M0 G1 R1. При этом SpringBoard снова упал
в slab_alloc491; это отдельное открытое расследование RM29. Успешные строки:

`GPU S11 E0 R1 GP0b070101 PPf C133 P1024/1024`
`GIRQ000003/0001 M0 G1 T2 V6 J4 B0000:00000000`

Частота может отличаться в пределах160МГц. T — прошедшие triangle checks,
V — проверенные vertices, J — номер текущего/последнего job (1/2 clear,
3/4 triangle). Старые phase/error значения — в GPU27 report. Новое E-17:
VS output или его padding не совпали, B — byte offset и actual word.
E-13 при J3/4 означает image/padding mismatch; E-11 GP/VS/PLBU fault/timeout.
R2 требует сохранения power/pages при неподтверждённом STOP_BUS/restore.
Достаточно фото обеих строк. Сами маленькие треугольники рисуются в private
memory и на экран не выводятся. SpringBoard остаётся software-rendered.

## Проверки и границы результата

23 host scripts+4 variants+generator check PASS. Actual C49 cases с ASan/UBSan:
power/clock/MMU/readback/rollback и новые no-VS/bad-VS/padding, missing completion,
active VS, empty triangle, wrong/stale FS, triangle MMU/PP timeout/table damage.
Fixture разбирает команды и фиксированные shader fields, моделирует запись
вершин/triangle rasterization только для проверки CPU validation/error paths.
Это ограниченная host model, не аппаратный Mali emulator и не physical PASS.

Actual linked ARM builder с4 I/F masks проверяет guards/PD/PT/commands/shaders;
actual linked touch callbacks/masks/nesting и PERF22 observer counts265200/2800
сохранены. Kernel/loader/raw/embedded/DT/config checks PASS. Physical VS, PLBU
geometry/rasterization/PP shaders проверятся только на телефоне.

## Артефакты

- Root raw zImage: 7559136 bytes.
- SHA256: `d841cbd24e103f2e3d9cc3d68c3b3877de962a3f4b3a0614cbe1623d5b35951e`.
- UUID: `22598D13-71FC-3517-A08C-818A410F1C93`.
- Matching symbols/assym/manifest/patch/logs/sources: diagnostics/gpu28-20261031/.
- Подтверждённый GPU27 rollback: backups/gpu28-before-20261031/.
- Источники и SHA: GPU28_SOURCES.json; base registers/rails — GPU27 report.

Первичные shader layouts: [GP codegen](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-24.3.4/src/gallium/drivers/lima/ir/gp/codegen.h),
[PP codegen](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-24.3.4/src/gallium/drivers/lima/ir/pp/codegen.h),
[draw packets/state](https://gitlab.freedesktop.org/mesa/mesa/-/blob/mesa-24.3.4/src/gallium/drivers/lima/lima_draw.c).
MIT notices сохранены. Apple images/cache не экспортируются.

После geometry PASS следующий этап — validated buffer/context/submit/fence
interface и Darwin winsys, затем Mesa Lima compiler/GLES/EAGL/IOSurface boundary.
Одного снятия CA_ENABLE_OGL=0 недостаточно: в supplied cache SGX535 backend.
