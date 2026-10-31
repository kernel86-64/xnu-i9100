> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# ARGS26: повреждение uthread аргументами syscall, 31.10.2026

sbexit4.jpg подтверждает повтор той же native slab_dealloc assertion line567
на COPY25: PID27/SIG6, CTX27:SpringBoard/IRQ0/F4. Все8 адресов согласуются с
shared-cache slide0x0229e000. В этот раз поздние кадры проходят через внутренний
hash table/кэш QuartzCore; утверждать снова CAAnimation dealloc нельзя.
COPY25 partial-page fix не устранила все вылеты; её реальный source fix сохранён.
Значение EXC350618492 (0x14e6037c) нельзя считать подлинным Mach exception type.

## Подтверждённая ошибка

В ARM struct uthread было uu_arg[8] из32-битных слов. unix_syscall копировала
до12 регистров, причём sy_narg трактовался включительно: при count11 писались
индексы0..11. В ARM32 соседние поля лежали так:

| Offset | Старое поле | Что записывал старый loop |
| --- | --- | --- |
|0..31|uu_arg[0..7]|r0..r7|
|32|uu_ap|r8|
|36|uu_rval[0]|r9|
|40|uu_rval[1]|r10|
|44|uu_exception|r11|

Существовавший iOS7 psynch adapter также копировал четыре stack words в
uu_arg[7..10]. Затем dispatcher обнуляла uu_rval[0..1], затирая настоящие
argument words9/10. Это не просто неправильная диагностика: реальные аргументы
вызовов синхронизации менялись до вызова обработчика.

Actual linked sysent содержит440 entries, maximum argument count12.
psynch_cvbroad303, cvsignal304, cvwait305 требуют11words/44bytes. Поэтому
ограничить старую копию восемью словами было бы неверным исправлением.

ARM argument storage увеличен до12words. Новый arm_syscall_store_args сначала
проверяет capacity и регистровый предел12/direct или11/indirect, затем копирует
ровно count words. При ошибке handler не вызывается, возврат идёт обычным errno
путём. Старый psynch stack adapter сохранён; его результат больше не пересекает
return values. Public userspace syscall ABI, signatures/argument order не меняются.
Меняется внутренний layout uthread; связанные BSD objects и экспортированный
user.h пересобраны, включая allocation, dispatch, arm stubs, signal/exit paths.

Старый контроль воспроизводит overwrite uu_ap/uu_rval/uu_exception и потерю
flags/tail words при retval initialization. Новый сохраняет все11words и поля.
Это доказанное исправление kernel argument/metadata corruption. Оно может быть
связано с мусорным EXC и некорректной синхронизацией, но конкретный writer slab
magic на устройстве этим ещё не установлен. Утверждать полное устранение вылетов
до проверки телефона нельзя.

## Исправление diagnostic guard

На sbexit4 допустимый cache slide0x0229e000 превышал старый произвольный предел
32МиБ. Поэтому SLAB/MAGIC не появились. Предел заменён проверкой вместимости
native addresses в user VA<0x40000000; сохранены alignment и совпадение всех4
точных native callers с одним slide. Host test использует адреса sbexit4.
Unrelated stacks по-прежнему отвергаются, дополнительного copyin из IRQ/remote
context нет. Теперь ожидается capture expected/actual magic при повторении.

## Проверки

22 scripts+4 variants PASS. Новая check_i9100_sysargs.py компилирует actual
uthread prefix (только ARM32 pointer моделируется), новый marshaler и прежний
psynch adapter:442 capacity/count/direct/indirect cases ASan/UBSan; все3
psynch tails, EFAULT/EINVAL, retval independence. Old O0 control воспроизводит
intra-object overwrite и возвращает expected23; это намеренный старый UB path,
не sanitizer success старой реализации.

verify_i9100_sysargs_native.py исполняет неизменённый linked ARM marshaler:
1768 exact-buffer cases, все4 I/F masks; читает настоящий sysent и проверяет
11word/44B CV handlers. Dispatcher disassembly передаёт capacity12 и сохраняет
путь psynch stack-tail. Full affected BSD rebuild успешен; exported user.h12.

Native pagecopy320cases + supplied QuartzCore old-assert/new-return PASS:
COPY25 fix сохранена. Native publishers и touch callbacks PASS. PERF22 lookup
по-прежнему265200 instructions/2800 reads в warmed случае; physical FPS не
измерялся. tracing-on ASM/input/cache/VM/Home/power/config/DT не менялись.
Rootfs не менялся. Никаких отключений assertion или SIGABRT не добавлено.

Root raw zImage **ARGS26**, 7543360Б,
SHA256 157fa92bea5bf93753af665ee3fc51058e8be8809497082f9ecd9dd3297dc7e7, UUIDC29DADEF-1AA9-3A26-91D9-7A29B51F8F3A.
Matching kernel/assym/manifest/logs/photo/sources: diagnostics/args26-20261031/.
COPY25 checkpoint: backups/args26-before-20261031/. Phone ARGS26 pending.

Прошивка прежней `heimdall flash --KERNEL zImage`. Проверить случайные действия;
при повторе снять нижнюю половину с SLAB/MAGIC/STDERR/SBEXIT. Rootfs не менять.
