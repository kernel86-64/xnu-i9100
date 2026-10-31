> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# SB23: источник SIGTERM и завершения UI-служб, 30.10.2026

PERF22 проверена пользователем: тач снова работает; общее ускорение небольшое,
перелистывание страниц SpringBoard заметно плавнее. SpringBoard по-прежнему
может вылететь при случайном действии, без постоянного сценария.

## Что показывает SBEXIT.jpg

PERF22, SBEXIT #3 PID32 SIG15 EXIT0 X1; EXC0 CODE00000000 SUB00000000
FREE173214 (около676.6МиБ свободных страниц по4КиБ).
Это завершение по SIGTERM. X1 означает, что proc_prepareexit исполняется потоком
целевого task; оно не доказывает самостоятельный вызов завершения. EXC0 означает
отсутствие записанного uthread exception. Нельзя вывести отправителя, watchdog,
или точную первопричину из этих строк. FREE не выглядит как исчерпание свободных
страниц, но не исключает прочие memory policy. #3 — sequence observer, не
проверенный счётчик трёх уникальных аварий.

## Проверенные пути

В локальном XNU kill()/group kill отправляют сигнал после permission check.
proc_terminate() выбирает SIGKILL для clean tracked task, SIGTERM — иначе.
Штатный launchd из исходного локального rootfs действительно вызывает
proc_terminate (Thumb call0x74e2); другой kill call0x135ec принимает signum из XPC.
Поэтому один номер15 не доказывает watchdog timeout. Исследовались локальные
исходники и native userspace, сетевые сведения для этого не нужны.

Original Downloads rootfs монтировался только read-only. В нём SpringBoard
загружает ios7lab-observer061.dylib, backboardd — без этого injector. Strings
observer описывают ограниченный pending launch watchdog extension для отдельных
приложений. Статические imports не содержат kill. Это не доказывает ни его
виновность, ни полную непричастность: новый образ rootfs не создавался.

## Изменение SB23

Перед всеми четырьмя psignal wrappers записывается запрос SIGTERM/SIGKILL к
точному SpringBoard. Существующие calls в psignal_internal сохраняются.
Сохраняются PID/task цели, context PID/name, kernel caller PC, saved user PC/LR,
IRQ и flavor. CTX — текущий контекст, не автоматически доказанный отправитель;
сопоставлять K с matching kernel, U/LR с соответствующим userspace. В IRQ или
kernel task пользовательские регистры не читаются, context PID0/kernel. Нет
stack walk, copyin, heap, printf, файловых записей или изменения signal policy.
Чтение user registers производится только у своего текущего user task через
find_user_regs, с проверкой saved user mode.

Два независимых pending slots сохраняют15 и9, чтобы поздний SIGKILL не затёр
происхождение SIGTERM. При выходе совпадают PID+task+signal; копия остаётся на
экране после respawn и не заменяется запросами нового SpringBoard. Отсутствие
совпадения показывается явно. Это наблюдение запроса, не гарантия delivery/причины.

proc_prepareexit отдельно сохраняет последний backboardd exit: он может быть
первичным событием перед respring. Это пока гипотеза, а не установленная цепочка.
При remote termination чужой uthread по-прежнему не разыменовывается.

Overlay после события:

- 624/640: BBEXIT + EXC/CODE/SUB/FREE, если backboardd завершалась;
- 656/672: SBREQ SIG… CTX… IRQ… F… и K… U… LR…;
- 704/720: прежние SBEXIT/EXC/CODE/SUB/FREE.

PERF22 bounded lookup C сохранён byte-for-byte; tracing-on ASM, input driver,
cache/VM/Home/power и DT380B/scale1 сохранены. Эти правки сами по себе не являются
исправлением причины вылетов и не обещают дополнительного прироста скорости.

## Проверки

19 host/ARM scripts +4 variants PASS. Последняя версия actual exit/signal hooks,
actual board publisher C и formatter проходит ASan/UBSan: exact process filter,
SIG15/9 slots, task mismatch, respawn retention, poisoned pointers в IRQ/kernel/
null context, remote uthread exclusion, все4 masks, bounded names/text, wrap.

verify_i9100_process_native.py исполняет неизменённые linked ARM publishers с
реальными MRS/CPSID/MSR, всеми4 I/F masks, ARM stack arguments и независимым
backboardd status. RAM/thread/CPU моделируются; delivery не эмулируется.
verify_i9100_trace_native.py: те же265200 instructions/2800 table reads для400
observer roundtrips; linked touch callbacks сохраняют masks/nesting.
Disassembly всех4 psignal wrappers сохраняет delivery call и caller LR capture.
Kernel/loader build, точный embedded raw kernel/DT, boot args и config PASS.
Это не тест физического тача/стабильности новой SB23 на телефоне.

## Выдача

Root raw zImage SB23:7535120B, SHA256 0c71a63c0e8a95d13239013e75413f567a22b0f0c67a4382b4eeb2b5e2e3baf7,
UUID 6C33708D-F150-35ED-8CCA-7CCCC99C2EBE. Matching kernel/assym/manifest/logs и исходное
фото: diagnostics/sb23-20261030/. PERF22 checkpoint:
backups/sb23-before-20261030/ (raw image + matching kernel/config/sources).

Прошить прежней командой `heimdall flash --KERNEL zImage`. Rootfs менять не нужно.
После следующего вылета сфотографировать нижние строки с SBREQ/K/U/LR и SBEXIT;
если появятся BBEXIT — захватить их тоже. Поведение SIGTERM не подавлять.
