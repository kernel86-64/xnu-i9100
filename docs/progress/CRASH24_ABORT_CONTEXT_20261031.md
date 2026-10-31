> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# CRASH24: SIGABRT, stderr и пользовательский стек, 31.10.2026

## Результат телефона

sbexit2.jpg — SB23 по overlay: SBEXIT #1 PID17 SIG6 EXIT0 X1,
EXC0 CODE00000000 SUB00000000 FREE163667 (около639.3МиБ свободных страниц).
SBREQ unavailable ожидаемо: SB23 записывала только15/9. Это не доказательство
отсутствия запроса сигнала. На фото BBEXIT не отображается. Новый случай —
SIGABRT, а не прежний SIGTERM15. Сам номер6/X1 не доказывает self-abort и не
указывает конкретное исключение, assert, повреждение heap или отправителя.

В штатном локальном libsystem_c abort0x38188f90 вызывает pthread_self, затем
pthread_kill(...,6) на0x38188fd8. Native __assert_rtn выводит сообщение в fd2
через _simple_dprintf перед abort; libc++abi fatal helper0x374b7c8c пишет stderr
через fwrite/vfprintf/fputc перед abort. Эти пути проверены по supplied cache,
а не угаданы по одному номеру сигнала. Старый rootfs монтировался read-only.
Точная причина конкретного вылета остаётся неизвестной.

## Изменение

Signal request observer теперь принимает6,15,9 и имеет три независимых slots.
Существующие delivery calls сохранены. CTX — контекст запроса, не автоматически
доказанный отправитель. Kernel K и saved user U/LR помогают установить путь.

Для точного SpringBoard stderr fd2 сохраняется ограниченная копия намерения
записи, после штатной проверки FWRITE в write_nocancel/wr_uio. Writev читает
существующие iovecs без сдвига, максимум8 векторов/512Б за вызов; copyin кусками
до128Б. Ошибка наблюдения не меняет I/O/retval/errno. Это не доказательство
успешной записи в консоль. Перехват не затрагивает чужие процессы/stdout.

RAM ring512Б хранит хвост. Streaming match через фрагменты сохраняет первую
строку с uncaught exception/assertion failed/malloc: (без учёта регистра), до240Б,
чтобы следующий стек или footer её не затёр. Если строки нет — последние240Б.
PID+task смена сбрасывает pending stderr; snapshot переживает respawn.

После proc_signalend/proc_unlock в default SIGABRT postsig и перед исходным
coredump сохраняются PC/LR/SP/FP и до8 Thumb/r7 frame return addresses. Только
свой текущий task, user mode, IRQ не активен и interrupts enabled. Бounded
copyin, alignment/user boundary/64КиБ/monotonic checks, ошибки дают partial E.
В proc_prepareexit copyin не добавлялся: там lifecycle уже запрещает новое
потенциальное блокирование. Нет heap, printf, файловых записей в publishers,
изменения signal/abort/coredump policy, подавления исключений или исправления
пользовательской памяти. Header/store scalar copies, raw CPSR guard сохраняет I/F.

Новые строки448–576 после matching retained SIG6:

- ABORT PID/PC/LR; SP/FP/N/E;
- BT0 и BT4 (8 адресов); это frame-chain snapshot, не полный validated unwind;
- STDERR diagnostic line / last240 bytes / unavailable, четыре строки текста.

Прежние BBEXIT624/640, SBREQ656/672, TCH688, SBEXIT704/720 сохранены.
При сборе фото захватить всю нижнюю половину экрана.

PERF22 lookup C, tracing-on ASM/input, CACHE16/VM/Home/power и config/DT сохранены.
Новая прошивка не является исправлением причины SIG6 и не обещает новый FPS.

## Проверки

20 host/ARM scripts +4 variants PASS. check_i9100_abort.py компилирует actual
write_nocancel/wr_uio/helpers/header с ASan/UBSan (halt on error): исходные
permission/retval/UIO semantics, fragmentation, first diagnostic retention,
ring wrap/task mismatch, remote/IRQ/masked/bad-pointer exclusions, bounded
frame chain и formatter. Наблюдения SIG6/9/15 проходят existing process check.

Actual linked ARM publishers в Unicorn проходят реальные MRS/CPSID/MSR и4
I/F masks, split stderr + independent6 slot + retained snapshot. В проверенном
32-byte append сценарии максимум8184 instructions; это не измерение времени
на Exynos. Native touch callbacks и warmed observers сохраняют прежние
265200 instructions/2800 table reads. Kernel/loader/embedded/config checks PASS.
Телефон CRASH24 ещё не проверялся.

## Артефакт

Root raw zImage CRASH24: 7543360Б, SHA256 4d25df922d5f867128ab6d8ee8836c5d700a14225d12da1888dc54da91814e88,
UUID 20A7F401-9F09-3248-BAAC-EC456CC2D5E3. Matching symbols/assym/manifest/logs/photo/sources:
diagnostics/crash24-20261031/. SB23 raw+matching kernel/config/sources:
backups/crash24-before-20261031/. Rootfs не менялся.

Следующий шаг — прежняя `heimdall flash --KERNEL zImage`, затем после вылета
фото нижней половины: ABORT/BT/STDERR и SBREQ/SBEXIT. Не объявлять неизвестное
Objective-C exception или heap corruption установленной причиной.
