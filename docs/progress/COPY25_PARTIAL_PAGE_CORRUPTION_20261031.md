> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# COPY25: исправление смещения partial-page VM copy, 31.10.2026

## Что установлено по sbexit3.jpg

CRASH24: PID17 SIG6/EXC0; STDERR diagnostic line:
`Assertion failed: (slab->magic == SLAB_MAGIC (bucket_idx)), function slab_dealloc,
file /SourceCache/QuartzCore/QuartzCore-330.1.25/util/x-alloc.c, line 567.`

SBREQ CTX17:SpringBoard IRQ0 F4 и matching kernel call __pthread_kill ->
psignal_uthread, плюс native stack, устанавливают SIGABRT из этого процесса.
Сам по себе предыдущий X1 этого не доказывал. Это конкретная native assertion,
не kernel panic и не установленный Objective-C exception. Исходный неверный
writer/allocator-lifetime event на телефоне ещё не найден.

Shared-cache slide0x005d7000 согласует все8 return addresses:

| Телефон (Thumb LR) | Без slide (Thumb LR) | Проверенный смысл |
| --- | --- | --- |
|3875ffdd|38188fdd|abort, возврат после pthread_kill|
|3873fcaf|38168caf|__assert_rtn, возврат после abort|
|2feefb0b|2f918b0b|slab_dealloc, native assert call|
|2fee0d4f|2f909d4f|освобождение bucket-list|
|2fedd34b|2f90634b|recycle освобождённых блоков|
|2fed249f|2f8fb49f|внутренний free-list path|
|2fed571b|2f8fe71b|освобождение внутреннего property-list|
|2fedaacb|2f903acb|-[CAAnimation dealloc]|

Native slab_dealloc берёт page base как object&~4095, читает magic в+0x10,
сравнивает с0xdeafbe00|bucket_idx. Несовпадение может означать перезапись,
неверный pointer/bucket или повторное использование; одно assert этого не различает.
Совпадение базы/cache проверялось на supplied dyld cache SHA
cad2df775e122c660238f341e74c163a2ea0ed261e85bfd3190de750cd9c0d2c.
Rootfs монтировался read-only, не менялся. Disassembly сохранён в diagnostics.

## Подтверждённая ошибка ядра

ARM pmap_copy_part_page игнорировала dst_offset:

```c
// Было:
ovbcopy(src_base + src_offset, dst_base + src_offset, len);
// Стало:
ovbcopy(src_base + src_offset, dst_base + dst_offset, len);
```

Реальный путь vm_fault_copy partial branch -> vm_page_part_copy передаёт два
независимых offset. Когда они различаются, старый код пишет вне запрошенного
диапазона назначения. Исправлена одна переменная адреса в generic ARM helper;
copy lengths, page assertions, overlap-capable ovbcopy и VM policy сохранены.

Host regression исполняет actual branch из vm_fault.c, actual wrapper из
vm_resident.c и actual helper из pmap.c. Пример src_offset16/dst_offset256/len4
стирает guard magic destination+16 в старом варианте; после fix guard сохраняется.
28548 offset/boundary/same-page-overlap сценариев проверяют весь RAM buffer,
с ASan/UBSan. Old control возвращает ожидаемый failure23.

Native regression исполняет настоящий linked ARM helper и его bcopy из старого
CRASH24 и нового COPY25, без замены инструкций. Контролируемый copy должен менять
+512, а старый меняет+16. Получившуюся страницу получает original QuartzCore
slab_dealloc: старый результат magic0xdeadf00d -> та же assertion; новый
magic0xdeafbe01 -> нормальный return.320 native cases проверяют offsets/overlap,
все4 I/F masks и whole-buffer guards. RAM/linear mapping и import boundary
__assert_rtn моделируются. Это подтверждённый механизм повреждения, но не
доказательство, что именно этот copy был writer в конкретном sbexit3.jpg.

## Дополнительное наблюдение в той же сборке

Если совпадают точные4 native return addresses abort/assert/slab/list с одним
page-aligned slide, observer извлекает saved r8/r5 из assert frame (FP-16/FP-4),
читает descriptor+8 -> object -> slab+0x10. Всё через ограниченные copyin в уже
существующей own-task pre-coredump точке, без новых чтений в IRQ/remote context.
Original native assertion prologue исполнен отдельно: offsets saved registers
подтверждены. Unrelated assertions не проходят адресный guard. При отказе чтения
S2, при полном capture S1; поля только наблюдаются, сигналы/asserts не подавляются.

Строки592/608 показывают SLAB/OBJ/bucket/status и expected/actual MAGIC.
Прежние ABORT/BT/STDERR, BBEXIT и SBREQ/SBEXIT сохранены. Это позволит при
повторении увидеть значения сразу, без отдельной прошивки ради missing magic.

## Проверки и артефакт

21 scripts +4 variants PASS. Native partial-copy + supplied slab assertion
old-fail/new-pass, actual saved-register prologue, extended slab collector
ASan/UBSan, linked publishers4 masks и touch transfer callbacks PASS.
PERF22 lookup и tracing-on ASM/input/control path не менялись; native warmed
observer case по-прежнему265200 instructions/2800 reads. Kernel/loader,
embedded raw/DT380B/scale1, boot Home/power, unchanged config и delta checks PASS.
Это не измерение физического FPS/cache coherence и не phone stability result.

Root raw zImage COPY25: 7543360Б,
SHA256 cfa0d0aa0cd96bde7c6926f090217d57153de71897b3b899ec7458759004cd46, UUID 8FAA2989-08D6-35C7-9ADC-04BCD71CF1A6.
Matching symbols/assym/manifest/logs/photo/sources: diagnostics/copy25-20261031/.
CRASH24 image+matching kernel/assym/config/sources: backups/copy25-before-20261031/.
Rootfs не менялся. Использовать прежнюю `heimdall flash --KERNEL zImage`.

На телефоне проверить случайные действия/анимации. Если вылет повторится,
сфотографировать нижнюю половину с STDERR, SLAB/MAGIC и SBREQ/SBEXIT.
Не объявлять все SpringBoard exits исправленными до результата телефона;
старый SIGTERM15 также не получил доказанного объяснения.
