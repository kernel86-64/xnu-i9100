> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# PERF22 — ускорение диагностики с сохранением пути ввода

Пользователь справедливо указал, что TOUCH21 возвращает и тяжёлую диагностику,
поэтому откат PERF20 не решает лаги. TOUCH21 была временным rollback после
немедленного отказа тача на PERF20; результат TOUCH21 с телефона ещё не получен.
Прямой механизм отказа PERF20 не установлен.

## Изменение

В PERF22 сохранены I9100_LOCK_TRACE=1, все прежние assembler wrappers/callbacks,
raw IRQ/FIQ exclusion, lock words, preemption counters и panic invariants.
Меняется только реализация двух C lookup functions в диагностике: раньше при
создании записи они всегда просматривали16 ячеек, даже при пустой таблице.

Для каждого исходного hash bucket хранится максимальное расстояние когда-либо
выделенного slot. Поиск просматривает этот префикс; при необходимости вставки
расширяет его до первого свободного slot, максимум16. Удаление не уменьшает
границу. Поэтому дырка не скрывает существующую запись с тем же hash, и после
удаления/повторной вставки выбирается тот же первый свободный slot, что раньше.
При коллизиях сохраняются прежний предел16 и отказ вместо перезаписи чужой записи.
Границы ограничены16 даже при завышенном byte. Дополнительные static arrays:
2048+1024 bytes, без heap. Доступ защищён прежними raw masks; target — UP.

Таким образом, исключён лишний поиск, а не выполнение защитных функций вокруг
touch I²C. Глобальный-O0, startup/protocol/GPIO/HID code, CPSR masks/AST,
CACHE16/VM/Home/scale и редкие TCH/SBEXIT observers не менялись. Rootfs не менялся.

## Проверки

- `check_i9100_trace_lookup.py` исполняет actual production lookup functions и
  сравнивает **точные выбранные slots** с прежним bounded policy.420000 mixed
  insert/find/delete operations,17 colliding keys, дырки, повторная вставка,
  wrap через конец массива, full bucket и завышенные bounds — PASS под ASan/UBSan.
- Все19 host/ARM scripts + locktrace unknown/block/experimental-light и
  preemption trace — PASS. Default tracing-on проверяется отдельно от отозванного
  collection-off experiment; последний не возвращён в production.
- `verify_i9100_trace_native.py` загружает original linked TOUCH21/PERF22
  Mach-O segments и исполняет реальные ARM/Thumb observer functions в Unicorn.
  Сами kernel instructions не патчатся; thread/CPU/stack RAM моделируется по
  matching assym.s, TPIDRPRW инициализируется настоящим MCR. Никаких function hooks
  для подмены observer behavior нет. Проверены400 warmed roundtrips по четырём
  I/F masks; lock word и preempt count наблюдатели не изменяют.
- Дополнительно исполняются actual linked Clang Thumb beginTouchTransfer/
  endTouchTransfer через actual ARM disable/enable_preemption и C observers:
  четыре I/F masks и исходная вложенность0/1 в обоих ядрах — PASS.
  Сам GPIO/I²C обмен и контроллер этим тестом не моделируются.

Для повторного исполнения (Unicorn2.x):

```sh
python3 tools/verify_i9100_trace_native.py \
  --before diagnostics/touch21-20261030/mach_kernel.sys \
  --kernel diagnostics/perf22-20261030/mach_kernel.sys \
  --assym diagnostics/perf22-20261030/assym.s
```

Измеренный сценарий — один warmed noncolliding thread/depth и lock,400 повторов
enter/leave/acquired/forget. Результат **инструкций наблюдателей**:

| Метрика | TOUCH21 | PERF22 |
| --- | ---: | ---: |
| Выполненные инструкции | 629200 | 265200 |
| Чтения diagnostic record arrays | 26800 | 2800 |

Это **−57.9% instructions / −89.6% table reads в данном сценарии**. Не FPS и не
общее ускорение iOS; на Exynos не измерено. При тяжёлых коллизиях поиск по-прежнему
до16, относительный выигрыш меньше. Оставшаяся стоимость callbacks, parent check,
full-cache traps и software rendering этой правкой не устранена.

Kernel/loader builds PASS; generated DT и loader config побайтно прежние.
Exact kernel blob и DT встречаются в raw image по одному, Home1/power on/scale1.
Prepared source-only copies сверены с baseline и синхронизированы; relocated lookup
и tracing checks PASS. Commit/push не выполнялись.

## Готовый образ и границы результата

Root **zImage PERF22**,7535120 bytes:
`6dfeca45458247f94d54bd20986ee6f205c61f0692d81550521a6d22dc9e780e`.
UUID **2E6168E8-C402-31A4-95CC-3256F8B96AAE**.
Matching symbols/assym/manifest/logs: diagnostics/perf22-20261030/.
TOUCH21 с symbols/source сохранена в backups/perf22-before-20261030/.

Прошить root raw zImage прежней командой; TOUCH21 промежуточно не требуется.
Rootfs менять не нужно. На телефоне ещё нужно проверить **и тач, и скорость**.
При отказе — строка TCH; при вылете SpringBoard — SBEXIT/EXC. Эти device symptoms
не объявляются исправленными по host/native emulation PASS.
