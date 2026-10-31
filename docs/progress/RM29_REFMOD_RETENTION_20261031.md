> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# RM29: сохранение ref/mod при отключении страниц, 31.10.2026

## Результат assertion2.jpg

GPU28 аппаратно прошла: S11 E0 R1 GP0b070101 PPf C133 P1024/1024,
GIRQ000003/0001 M0 G1 T2 V6 J4 B0000:00000000. Подтверждены6 GP VS outputs,
два PP0 triangle image checks, старые clears, guards/MMU и восстановление питания.
Это не iOS GPU UI acceleration. Фото/result сохранены diagnostics/gpu28-20261031/.

SpringBoard PID28 снова SIG6 из собственного контекста. Теперь native assertion:
`slab->magic == SLAB_MAGIC (bucket_idx)`, slab_alloc, x-alloc.c:491.
Также есть BBEXIT PID16 SIG6 EXC0. COPY25 и ARGS26 не устранили все вылеты.
Frame0/1 и все native callers согласованы со slide0x02d7a000:

| Phone return | Unslid | Смысл |
| --- | --- | --- |
|3af02fdd|38188fdd|abort после pthread_kill |
|3aee2caf|38168caf|__assert_rtn после abort |
|326724cd|2f8f84cd|slab_alloc assertion path |
|32672313|2f8f8313|внутренний allocator caller |
|3266e343|2f8f4343|QuartzCore small object allocation |
|32a02a05|2fc88a05|UIKit caller |
|32a0273f|2fc8873f|UIKit caller |
|32a02541|2fc88541|UIKit caller |

Конкретный writer/ошибка lifetime страницы не установлены. GPU28 test PASS и
наличие slab assertion до GPU не доказывают полную независимость всех причин.

## Доказанный дефект PMAP

`pmap_disconnect(pa)` вызывает `pmap_page_protect(pa,0)`, затем читает
`pmap_get_refmod(pa)`. Старый page_protect при удалении каждой PV alias очищал
PMAP REFERENCED/MODIFIED. Возвращаемый результат поэтому терял даже уже
установленный dirty flag. Actual old ARM C в QEMU воспроизводит это, exit23.

Отдельно writable short-descriptor PTE позволяет запись без нового fault.
Порт не harvests hardware dirty/access bits и не ставит write/reference traps
после software clear. Старые queries смотрели только physical flags; фактическая
writable alias могла остаться невидимой для VM после clear. Native linked old
_pmap_get_refmod возвращает0 при такой alias; новый возвращает REF|MOD.

VM vm_pageout.c:2456 использует результат disconnect, чтобы обновить m->dirty
перед веткой освобождения clean page. Неверный отрицательный результат может
потерять последнюю запись/данные. Это доказанный контрактный дефект, но не
доказательство, что именно pageout испортил magic в assertion2.jpg. На фото
много свободных страниц; нельзя выдавать общую возможность за найденный writer.

## Исправление только для I9100

- Отдельный helper читает tracked managed PV aliases под прежним PVH exclusion.
  Валидная PTE консервативно означает reference; writable означает possible modify.
  Physical PPN должен совпадать. Query не считает permanent untracked linear
  aliases — иначе вся RAM всегда выглядела бы dirty.
- Публикация PTE, removal/replacement и RW->RO сохраняют старые ref/mod bits.
  Page_protect больше не стирает их до disconnect return.
- get_refmod/is_modified/is_referenced harvest текущие aliases. Explicit clear
  очищает только запрошенные software flags под PVH exclusion. Пока остаётся RW
  alias, следующая query снова сообщает possible modify; при только RO/unmapped
  mappings explicit clear действительно убирает MOD.
- Неподконтрольные физические адреса/MMIO/scanout и preinit не индексируют PV root.
  Остальные flags (wire/cache/noencrypt), PTE permissions, ledgers и VM policy
  не переписываются. Остальные board branches сохранены.

Это консервативный учёт, а не полноценная аппаратная dirty/access emulation:
он может удерживать mapped pages/считать страницы dirty дольше необходимого.
Операции выполняются при PMAP lifecycle/query, без нового per-access hook,
page-fault repair, user memory patching или отключения исходного assert/SIGABRT.
Прежний GPU28 self-test/commands/shaders, Home/touch/power и ARGS26 сохранены.

## Диагностика slab_alloc

Предыдущий collector распознавал только точные slab_dealloc callers. Для
slab_alloc491 дополнительно проверяются четыре native return addresses и общий
page-aligned cache slide. По реальному ARM prologue:

`localSP = align_down((allocatorFP+8)-48,16)-112`

В localSP+36 лежит list-link pointer, в+40 expected magic. В link лежит candidate
slab pointer. Capture читает actual magic именно candidate+16, включая случай
неправильно выровненного candidate; он не подменяется соседней page base.
Всё через bounded copyin в прежней own-task pre-coredump точке после освобождения
signal/proc locks. IRQ/masked/remote/bad stack никогда не запускают чтение.

SLAB/MAGIC строки592/608 теперь появятся и на этом пути. Для alloc OBJ означает
адрес list-link, SLAB — candidate pointer, B — bucket, S1 — complete capture,
S2 — отказ bounded read/validation. На старом dealloc OBJ остаётся object.
Trace ABI и fast renderer не менялись.

## Проверки

23 scripts+4 variants+new/actual-old refmod variants+shader generation PASS.
Actual ARM mapping lifecycle проверяет ledgers/PV promotion, writable-after-clear,
RO cleanliness, hashed aliases, downgrade/removal/replacement retention, MMIO/
bootstrap exclusion и20 reuse cycles. Old control реально исполняет сохранённый
pre-RM29 pmap source и воспроизводит потерю dirty flag.

28 actual linked ARM query/clear cases сравнивают GPU28 и RM29; все4 I/F masks,
preempt nesting, correct public/internal bit conversion, retained unrelated flags,
stale PTE/MMIO/scanout exclusion. RAM/PV/table data modeled, instructions unchanged.

Actual supplied slab_alloc+__assert_rtn prologues: четыре cases (good/bad magic,
оба8/16-byte entry alignments), normal object return vs original assertion и
проверка exact localSP/link/expected/candidate. Apple images read-only, не включены
в source snapshot. Cache SHA cad2df775e122c660238f341e74c163a2ea0ed261e85bfd3190de750cd9c0d2c.
Extended actual stderr/capture helpers ASan/UBSan PASS.

Linked publishers/GPU arena4 masks/touch callbacks и PERF22 counts265200/2800
сохранены. Kernel/loader/raw/embedded/config/DT/whitespace checks PASS.
Ни host model, ни native ARM RAM fixture не являются phone stability proof.

## Выдача

Root raw zImage **RM29**, 7559136 bytes,
SHA256 `11d7028ac0f95b813812869045cbaa329edabeec43d3ebd7890a2e600f5769b8`,
UUID `81777C35-3341-30C4-8222-F5BE1132D035`. Matching sys/assym/manifest/patch/logs/sources:
diagnostics/rm29-20261031/. GPU28 rollback с matching symbols/photo:
backups/rm29-before-20261031/.

Прежняя `heimdall flash --KERNEL zImage`. ROOTFS не менять. GPU success counters
остаются P1024/1024 T2 V6 J4 M0 G1. Проверить обычные действия/повторный запуск;
при вылете нужно фото ABORT/BT/STDERR и SLAB/MAGIC, а не отдельный тест GPU.
RM29 physical result pending; полное устранение вылетов не заявляется.
