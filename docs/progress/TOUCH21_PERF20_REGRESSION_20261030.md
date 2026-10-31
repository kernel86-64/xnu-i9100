> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# TOUCH21 — откат PERF20 после отказа тача

Пользователь сообщает: после PERF20 тач не работает сразу после загрузки,
при этом интерфейс/часы/анимации продолжают работать. Это device regression;
host PASS PERF20 не подтвердили работу физического ввода.

Прямой механизм отказа пока не изолирован. PERF20 не меняла Atmel protocol,
GPIO pins или native HID packet, но изменила общий lock/preemption path, который
использует touch I²C transfer. Нельзя утверждать, что доказана конкретная ошибка
контроллера, частоты I²C, таймера или очереди.

TOUCH21 **отзывает collection-off оптимизацию PERF20**: I9100_LOCK_TRACE=1 снова
по умолчанию. Семь linked routines побайтно и по адресам совпадают с сохранённой
DISP18, где тач работал: hw_lock_init/lock/unlock/try/to, disable_preemption,
enable_preemption. В них возвращены прежние10 collection call sites.
Логи проверки: diagnostics/touch21-20261030/restored-bytes.log.
Это консервативный rollback, не доказанный root-cause repair. Оптимизация лагов
остаётся незавершённой; тяжёлая диагностическая нагрузка снова присутствует.

CACHE16 dirty-data/writeback/order/mask fix, VM/PV/bootstrap, Home52B,
touch protocol, питание и scale1 сохранены. Редкий SBEXIT observer из PERF20
сохранён. Rootfs не менялся.

## Видимая строка состояния ввода

Добавлен маленький scalar RAM snapshot из уже существующего publishSnapshot
touch service. Отдельные ready/init/stage/open/poll/report/queue/error counters
не меняют контроллер или очередь. Дисплей/IRQ читают только RAM; нет новых MMIO,
I²C, locks, allocation или queue consumption в reader.
На row688 после boot видно, например:

```text
TCH R1 I00000000 S5 O1 P0123 N0004 Q0004 H0340 T0340 E0000
```

- R — controller ready; I — исходный init result, hex32 (отрицательный код в two's complement).
- S — transport stage; O — native reader opened service.
- P — число polls, N — real decoded reports, Q — successful queue enqueues.
- H/T — фактические native shared queue cursors; E — transport error count.
- P/N/Q/H/T/E показывают low16 bits, сами по себе не доказывают BackBoard/UI action.

R0/I!=0 указывает на failed startup; R1 с растущим P, но N0 локализует путь до
real reports; Q/T растут, H стоит — native queue не потребляется. Отдельные scalar
reads могут относиться к соседним публикациям, snapshot не объявляется атомарным.
Не делать ложный вывод о причине ошибки по одному счётчику.

## Проверки и образ

Все18 host/ARM scripts и четыре дополнительных режима PASS. Default tracing-on
проверяется без command-line override; --light теперь явно выбирает отозванный
PERF20 experiment и не называется production. Native mask/nesting/AST/bitlock
tests PASS. Atmel/GPIO/native204B/52B, touch status canaries/negative result/low16
и ASan/UBSan PASS. Exact linked old/current bytes проверены отдельно.
Kernel/loader builds, exact embedded kernel/DT, Home1/power on PASS.

**Root zImage TOUCH21**,7535120 bytes:
`675dafad6725d386fffceae745db55d043bfdfac378e4a4cad8d26f41b9a383d`.
UUID **3E0DDE1F-08DA-3117-BE39-80D22A1863B9**.
Manifest/matching symbols/logs: diagnostics/touch21-20261030/.
Предыдущий PERF20 с symbols/source сохранён: backups/touch21-before-20261030/.

Прошить обычный root zImage прежней командой. Rootfs менять не требуется.
Телефонное восстановление тача в TOUCH21 ещё не подтверждено. При сохранении
отказа нужен экран со строкой TCH; при respring также SBEXIT/EXC. Причина
SpringBoard exits и усиление лагов остаются открытыми.
