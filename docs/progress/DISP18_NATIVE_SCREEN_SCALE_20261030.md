> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# DISP18 — исправление screen scale для приложений, 30.10.2026

**Последующий результат телефона:** AssistiveTouch появился, Настройки остались
маленькими. Продолжение — APP19_FULLSCREEN_LAUNCH_20261030.md: отдельный ROOTFS.HFS
с native480x800 launch profiles; ядро DISP18 и scale1 сохранены.

Пользователь прислал старое `appexample.jpg` (видимый label CACHE2) и сообщил,
что симптом сохраняется: SpringBoard заполняет экран, приложения открываются
маленьким прямоугольником с чёрными полями. Затем разрешил исправление.
Это отдельная задача после HOME17; действие физической Home ещё не подтверждено.

## Найденное нарушение

Текущий `uniloader/blob/dtb` содержал только root model/compatible и chosen
name/firmware-version/debug-enabled. Обязательное для native iOS7 screen query
свойство `/chosen/display-scale` отсутствовало. Генератор
`tools/github-prepare-payloads.py` тоже его не создавал.

В локальном iOS7 rootfs проверен оригинальный dyld shared cache:
`cad2df775e122c660238f341e74c163a2ea0ed261e85bfd3190de750cd9c0d2c`. Read-only mount, userspace не изменялся.
По original ARM code установлена цепочка:

1. GraphicsServices запрашивает MGCopyAnswer(`screen-dimensions`).
2. MobileGestalt получает pixel size через IOMobileFramebuffer, затем читает
   IODeviceTree:/chosen `display-scale` как **OSData длиной4 байта**, native uint32.
3. При отсутствующем свойстве default равен0; MobileGestalt публикует float scale0.
4. GSMainScreenPointSize делит pixel width/height на этот ноль и получает Inf/Inf.
5. С корректным integer1 native query выдаёт480x800 points и scale1.

Это доказанное нарушение контракта. Маленькое окно на фото согласуется с неверной
геометрией, но конкретная downstream fallback-ветвь UIKit, создающая его, не
выполнялась в проверке. Что исправление устраняет весь device symptom, подтвердит
телефон. Первоначальная гипотеза о различии parent logical320x533 и физических
480x800 была предварительной: само различие не является доказанной ошибкой.
Физические480x800 и нормализованный touch сохранены.

Дополнительное подтверждение требования найдено в BOOT-MAP исходного комплекта
(Downloads/Telegram Lite/ios7), CurrentNative.DisplayScale067: chosen/display-scale,
OSData native uint32,4 bytes, Value1, RawHex01000000. Наш минимальный loader DT
утратил это свойство при адаптации. Исходный комплект не доказывает текущую
геометрию телефона; decisive evidence здесь — реальные native screen routines.

## Исправление

Генератор добавляет только `/chosen/display-scale = 01 00 00 00`. Это **целое1**,
не строка, не один байт и не IEEE float1.0 (`00 00 80 3f`). DT вырос340→380 байт;
проверено, что кроме chosen property count и этих40 байт старое содержимое
побайтно сохранено. Добавлен `--dt-only` для сохранения existing ramdisk при
обновлении рабочего loader. Экспортированный loader build использует тот же
исправленный generator. Тестовая копия generator включается в XNU port-tests,
чтобы host checks не зависели от наличия sibling loader checkout.

В ядре меняются только две видимые строки HOME17→DISP18, чтобы различать образ
по фото. Реализации cache/VM/preemption/touch/Home/power не изменены. Ни framework
patching, ни принудительного растяжения готового изображения, ни переопределения
UIKit windows/bounds здесь нет. Rootfs на карте менять не нужно.

## Проверки

- `check_i9100_display.py` запускает production generator CLI и независимо
  разбирает Apple tree: exact uint32 scale1, counts/padding, прежние board
  properties, DT-only сохранение ramdisk и прежний default empty-ramdisk flow.
  Старый generator падает на отсутствии обязательного scale.
- `verify_i9100_screen_native.py` выполняет оригинальные MG/GS ARM инструкции в
  Unicorn2.1.4. Native cache identity проверяется SHA256 до исполнения.
  Реальны static-info routine3723e990, param conversion3723ed98,
  screen-dimensions dictionary builder3723a1a8 и GS screen query3229f1f4.
  IOKit и CoreFoundation object storage моделируются; framebuffer query
  возвращает480x800 как текущий production selector8. Phone product variant
  моделируется как phone. Dot pitch/class остаются unknown; они не выдуманы.
  Native helper фактически читает bytes из выбранного DT через IORegistry shim.
  UIKit runtime/композиция/реальное hardware этим тестом не подтверждены.
- Старый DT: native MG scale0, GS point size Inf/Inf. Новый реальный DT:
  native MG scale1, GS point size480/800. Никакие Apple bytes не патчатся.
- Все17 host/ARM scripts плюс locktrace --unknown/--block PASS. Kernel/loader
  builds PASS. Prepared source display check тоже PASS.
- В финальном raw zImage ровно один exact kernel blob и один exact380B DT,
  присутствуют DISP18 и i9100home=1, нет Home0/power0. Config сохранён.

Для повторения native эксперимента (после read-only mount локального rootfs):

```sh
python3 tools/verify_i9100_screen_native.py --cache /path/to/dyld_shared_cache_armv7 \
  --dtb uniloader/blob/dtb \
  --before backups/display18-before-20261030/uniloader/blob/dtb
```

Нужен Unicorn2.x. В supplied cache конкретные функции привязаны к указанному
SHA; неизвестный cache отклоняется и требует нового address audit. Apple cache
и извлечённые framework binaries не включены в source export или diagnostics.

## Артефакты и телефон

- Root raw `zImage`: 7530912 bytes.
- SHA256: `fbd22076ce1bd25390ef0a25fa9d30a7b4620c620166962b57da0cb7d218cebb`.
- Kernel UUID: `F2FC01E5-35A9-33FD-B19A-9A113B72598D`.
- Matching symbols/DT/manifest/patch/logs: `diagnostics/disp18-20261030/`.
- Предыдущий HOME17 с symbols и старым DT: `backups/display18-before-20261030/`.

Пользователь прошивает root raw zImage прежней командой. Открыть Настройки или
другое приложение и проверить заполнение экрана и попадание тача по элементам.
На полосе должен быть DISP18. Если окно осталось маленьким, фото всего экрана
зафиксирует device result для исследования UIKit/CADisplay fallback. Предыдущие
ошибки kernel panic/длительная стабильность и Home не объявляются закрытыми.
