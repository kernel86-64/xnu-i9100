> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# PERF20 — горячая трассировка и вылеты SpringBoard, 30.10.2026

**Последующий результат:** на телефоне тач отсутствует сразу после загрузки, UI жив.
Оптимизация отозвана в TOUCH21, default trace снова1. Причина не изолирована.
Читать TOUCH21_PERF20_REGRESSION_20261030.md. Статусы pending ниже исторические.

Пользователь сообщает: прежние зависания прекратились, но система сильнее лагает
и SpringBoard иногда вылетает. Симптом есть и со старым rootfs, и с APP19;
новые launch profiles APP19 не объясняют эту регрессию. Длительность наблюдения
и причина завершений SpringBoard пока неизвестны.

## Подтверждённая лишняя работа

После LOCK8/SCOPE10 ядро безусловно собирало владельцев spinlock и каждый
assembly preemption scope. На каждой паре запрета/разрешения вытеснения
сохранялись регистры и вызывались C helpers; в них под raw IRQ/FIQ exclusion
просматривались до16 slots таблиц. C-код production собирается с прежним-O0.
Lock/try/to/unlock дополнительно записывали owner/history records.

Это диагностическая работа в очень частом пути, не механизм синхронизации.
Фактический linked DISP18 содержит10 вызовов collection helpers в семи
проверенных низкоуровневых routines. PERF20 содержит **0** таких вызовов там.
Например, обычный lock/unlock больше не выполняет C lookup в таблицах.
Конкретное ускорение/FPS на телефоне не измерено; не приписывать этому все лаги.

`arm/i9100_trace_config.h` задаёт `I9100_LOCK_TRACE=0` по умолчанию; конфигурация
экспортируется через arm/Makefile для assembler headers других kernel modules.
Специальная диагностическая сборка может определить I9100_LOCK_TRACE=1.
Обычная сборка сохраняет preempt count, lock word semantics, IRQ5 AST/mask fix,
scheduler/lock panic invariants и failed-fault ring. Panic показывает TRACE0;
при нём OWNED0/RAW0 означает отсутствие сбора, а не доказательство отсутствия lock.

**CACHE16 clean-before-invalidate/D-before-I/mask исправления не отменялись.**
Cache traps по-прежнему консервативно обслуживают весь cache. Возможная цена
этого пути остаётся предметом дальнейшего анализа; user range ABI/validation
в этой сборке не меняются. VM/PV/bootstrap, Home52B, touch/power и display-scale1
также сохранены. Глобальный-O0 не менялся.

## Запись о завершении SpringBoard

Причина вылетов не установлена; без сигнала/exception нельзя назвать их watchdog,
ошибкой памяти или последствием замедления. Вместо горячей трассировки добавлен
редкий observer в `proc_prepareexit`, с exact p_comm == SpringBoard.
Он передаёт только скаляры в retained RAM, без printf, файловых записей и изменения
исходного exit flow. Снимок публикуется короткими raw stores с сохранением masks.

После первого завершения две строки над прежним Home status показывают:

```text
SBEXIT #1 PID73 SIG9 EXIT0 X0
EXC0 CODE00000000 SUB00000000 FREE12345
```

SIG — сигнал из wait status, EXIT — нормальный exit code; FREE — свободные
страницы в момент наблюдения (не доказательство OOM). X1 означает, что exit
выполняет поток самого SpringBoard, поэтому доступны его uthread exception fields;
эти поля могут отражать прошлое исключение и не доказывают причину завершения.
При внешнем exit, например jetsam из другого task, X0 и exception/code/subcode
принудительно неизвестны/0: чужие uthread fields не читаются. SIG9 сам по себе
не доказывает watchdog или jetsam. CODE/SUB — младшие32 бита исходных полей.
Кольцо user-fault metadata и полноценные kernel panic reports сохранены отдельно.

Строки появляются после respring и остаются до reboot/следующего завершения;
функция formatter берёт скалярный snapshot с проверкой publication sequence.
Неполный snapshot пропускается без ожидания. При `i9100perf=0` overlay скрыт.

## Проверки и артефакты

- Все18 host/ARM scripts и четыре дополнительных режима: locktrace
  `--unknown`, `--block`, `--light`; preemption `--trace` — PASS.
- `--light` исполняет реальные production assembler paths с реальным default
  config:4000 roundtrips, все четыре I/F masks, nested preemption, try/to,
  r9-based bitlocks; **0 diagnostic records**. Disassembly проверяет отсутствие
  collection calls. Полная tracing-конфигурация отдельно проходит прежние tests.
- Actual __enable_preemption проходит16 mask/nesting/AST cases с collection off
  и on, включая намеренный clobber callback/AST registers.
- `check_i9100_process.py`: actual BSD observer + header publisher/formatter,
  ASan/UBSan. Exact process filtering, normal/signal wait status, remote poisoned
  uthread pointer не читается, unknown exception cleared, bounds/sequence wrap PASS.
- Kernel/loader builds PASS. Production linked image inspection подтверждает
  old10/new0 collection call sites; DT и config побайтно прежние, embedded raw
  kernel и DT встречаются ровно один раз, Home1/power on.
- Prepared XNU sources сверены с pre-edit copies и синхронизированы; relocated
  light/preemption-trace/process tests PASS. Commit/push не выполнялись.

Root **zImage PERF20**,7530912 bytes:
`672acab1283c4821b9742f03dd5ce93faa8d9d4232fba34b9538eeb001c54317`.
Kernel UUID **D2DE639C-A169-35E0-9AED-4302C40A4802**.
Image/matching symbols/DT/manifest/logs в `diagnostics/perf20-20261030/`.
Предыдущий DISP18 с symbols и изменявшимися sources сохранён в
`backups/perf20-before-20261030/`.

User прошивает root raw zImage прежней командой. На полосе должен быть PERF20.
Rootfs в этой работе не менялся: APP19 ROOTFS.HFS SHA остаётся
`cb73747d80a9745506d06c1a270cadfec0854b4a233581cda0c979c137418ec7`.
На телефоне ещё предстоит проверить скорость/отсутствие прежних зависаний;
если SpringBoard вылетит, снять обе строки SBEXIT/EXC. Эта сборка не объявляет
причину вылетов найденной или их устранение подтверждённым.
