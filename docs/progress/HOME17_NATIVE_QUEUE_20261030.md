> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# HOME17 — исправление доставки физической Home, 30.10.2026

Пользователь подтвердил загрузку CACHE16, затем сообщил: Home не работает либо
ничего не делает. Последний loader действительно передавал `i9100home=1`, но
этого было недостаточно: kernel queue отвергала каждый пакет кнопки.

## Доказанная причина

`IOS7LeoHIDQueue::enqueue()` вызывает общую функцию
`leo_touch_queue_enqueue()` из `IOS7LeoTouchQueueProtocol.h`. Её проверка
`bytes!=204U` принимала только пакет digitizer. Home создаёт правильный native
keyboard пакет **52 байта** и вызывает ту же функцию; она возвращала false ещё
до записи entry или изменения tail. `pollHome()` оставлял событие в FIFO16 и
повторял безуспешную доставку. Ни down, ни up не попадали в IOHIDLib.

Старые Home-тесты проверяли debounce/FIFO и сериализацию, но не проводили пакет
через реальную очередь. Поэтому прежний PASS не обнаруживал этот отказ.

Теперь разрешены ровно два имеющихся native размера: **204 и 52**. Нативная
очередь по-прежнему имеет 4096 байт, entry header4, прежние барьеры, wrap/full
правила и уведомления. Home сохраняет отдельный сервис/очередь и Consumer
Control 0c/01, Menu 0c/40; перенос в touch service не понадобился. Тач и
исправления CACHE16/POOL15/VM/preemption сохранены.

Дополнительно GPIO-выражения вынесены в проверяемые helpers с теми же масками.
Изменяется только GPX3(5); соседний SD detect GPX3(4) сохраняется.

## Проверки

Новый `tools/check_i9100_home.py` компилирует **настоящий pollHome()** и
**production queue helper** с fake GPIO/clock/consumer. Проверены down/hold/up,
boot-held suppression, FIFO при заполненной настоящей очереди, сохранение
времён событий, независимое чтение native bytes, все1025 выровненных frontiers
для52B и204B, full/invalid-length отказы, GPIO masks и границы status string.
ASan/UBSan включены. С прежним queue header контроль падает точно на первом
Home enqueue; с исправленным проходит. Отдельные debounce/Atmel/touch tests
тоже проходят.

Все **16** host/ARM scripts плюс locktrace `--unknown`/`--block` PASS.
Kernel/loader builds PASS. Production Thumb disassembly содержит сравнения
`0xcc` (204) и `0x34` (52), ведущие в один путь записи очереди.
Проверены один embedded raw blob, `HOME17`, `i9100home=1`, отсутствие
`i9100home=0`/`i9100power=0`. Логи/patch/disassembly/matching symbols сохранены.

## Диагностика без дополнительной сборки

В существующей нижней полосе, строка y736, выводится:

`HOME E1 P0 O1 D00000002 Q00000002 H0070 T0070`

- E: Home сервис настроен; P: физический GPIO нажат сейчас, даже без HID reader.
- O: userspace открыл именно Home reader.
- D: число debounced transitions, принятых в FIFO; Q: успешно записанные native packets.
- H/T: head/tail отдельной Home очереди, все счётчики/курсоры в hex.

Q и продвижение H не доказывают действие SpringBoard. Строка обновляется при
frame present и раз в наблюдаемую timer-секунду; IRQ читает только diagnostic
RAM, без GPIO, IOKit, locks, allocation или formatting runtime. Счётчики
насыщаются, lifetime не сбрасывается при open/close. `i9100perf=0` скрывает полосу.

## Образ и проверка телефона

- Root raw `zImage`: **7530880** байт.
- SHA256: `d67814cd427a387c7a3cde0ec62d956ab7c33942ee48482e8ac4f993764e1dde`.
- Kernel UUID: `E1BFCDCE-0F2F-317F-B02D-1783432A25EF`.
- Архив: `diagnostics/home17-20261030/`, manifest `artifacts.json`.
- Предыдущий CACHE16 с неработающей Home и matching symbols:
  `backups/home17-before-20261030/`; исходная диагностика CACHE16 сохранена.

Пользователь прошивает raw root zImage прежней командой. Открыть приложение
(например, Настройки) и нажать Home для возврата на рабочий стол. Если реакции
нет, одно фото нижней полосы после нажатия покажет GPIO/reader/enqueue/frontiers.
Физическое действие HOME17, повторные загрузки и длительная стабильность пока
не подтверждены. Host tests не подменяют проверку телефона.

## Сверка native контракта

Локальный rootfs.hfs прочитан через read-only mount и отключён после анализа.
Disassembly его IOKit подтверждает header28 + keyboard24 и обработку 0c/40
в backboardd; формат менять не требовалось. В manifest сохранены хэши образа
ядра, userspace не менялся. Референсы: [Apple IOHIDEventData.h](https://github.com/apple-oss-distributions/IOHIDFamily/blob/IOHIDFamily-503.1.13/IOHIDFamily/IOHIDEventData.h),
[Apple IOHIDEvent.cpp](https://github.com/apple-oss-distributions/IOHIDFamily/blob/IOHIDFamily-503.1.13/IOHIDFamily/IOHIDEvent.cpp),
[Samsung U1 GPIO](https://github.com/CyanogenMod/android_kernel_samsung_smdk4210/blob/cm-10.1/arch/arm/mach-exynos/include/mach/gpio-u1.h).
