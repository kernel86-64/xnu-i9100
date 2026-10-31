> Historical workspace report. Local photos, backups and binary artifacts are not included.
> Commands below use the original workspace layout; use the [repository README](../../README.md) for this snapshot.

# APP19 — полноэкранный запуск приложений, 30.10.2026

Результат DISP18 с телефона: система запускается, AssistiveTouch теперь появляется,
но Настройки по-прежнему открываются маленьким окном. Scale1 сохраняется.
Новая правка находится в **ROOTFS.HFS**, kernel/loader остаются DISP18.

## Причина и проверенная цепочка

В supplied iPhone4 rootfs у всех21 обычных phone apps отсутствуют UILaunchImages
и height-qualified launch resources. Native SpringBoard трактует экран выше480
points без соответствующего launch profile как основание для classic mode.
UIDeviceFamily1/2 само по себе не объявляет tall-phone поддержку.

Оригинальные ARM routines текущего SpringBoard (SHA256
`203507844fe39bd5f024ade40779b3902ced6f8f243ff194b047bf4d89835028`):

1. `_imageNamesFromInfoDictionary:` `0x001be044` разбирает UILaunchImages,
   проверяет NSString types, orientation и minimum OS, группирует profiles.
2. `_calculateSupportedTypesLazilyIfNecessary` `0x0003e704` при phone height>480
   вызывает `_infoplist_defaultPNGCalculateContainsCorgiImage` `0x001bf398`.
   Этот helper сравнивает UILaunchImageSize с реальным UIScreen size, а не
   требует именно568. Для валидного480x800 profile ставится supportedTypes bit4.
3. `-[SBApplication isClassic]` `0x0003e8b8` возвращает1 без этого bit4.
4. UIKit `-[UIScreen _computeMetrics]` `0x2fce7fcc` при classic main screen
   выбирает оригинальную320x480 константу вместо GSMainScreenPointSize.

Это отдельная воспроизведённая причина маленьких окон, которую прежний MG/GS
scale-тест не покрывал. Наличие live CADisplay в процессе приложения пока не
измерено: UIKit также имеет fallback320x480 при отсутствующем CADisplay.
Результат всего UI на реальном телефоне остаётся pending.

## Изменение

`tools/prepare_i9100_fullscreen_rootfs.py` создаёт отдельную копию supplied image.
Для21 `/Applications/*.app` с UIDeviceFamily1 добавляет четыре штатных launch
profiles: Portrait, PortraitUpsideDown, LandscapeLeft, LandscapeRight;
UILaunchImageSize `{480, 800}`, minimum OS7.0. Старые plist keys/profiles сохранены.
Добавлены две нейтральные чёрные PNG заставки на приложение:480x800 portrait
и800x480 landscape. Размер profile описывает UIScreen, независимо от ориентации.
Во время запуска до появления UI может быть виден чёрный экран.

Ни новый injector, ни runtime override bounds, ни binary/cache patch не добавлены.
Все Mach-O, shared cache, launchd jobs и прежние observers сохранены побайтно.
SpringBoard/AssistiveTouch bundles не меняются. Новые установленные приложения
не обрабатываются автоматически; для них отдельно нужна такая же launch support.

## Проверки

`verify_i9100_app_geometry_native.py` исполняет **неизменённые** ARM инструкции
парсера, classifier/helper/support-bit и UIKit metrics в Unicorn2.x.
Objective-C containers/runtime, phone identity, resource lookup и GS queries
смоделированы на границах вызовов. Main CADisplay моделируется доступным.
Старый rootfs не содержит568h resources; fullscreen-specific resource lookup
возвращает отсутствие совпадения. Это явно заданная граница, не полный файловый
или Objective-C runtime. При scale1 GS dimensions задаются480x800, отдельно
подтверждёнными прежним native MG/GS тестом.

- Старые реальные Info.plist всех21 apps: supportedTypes1, classic1,
  UIKit bounds320x480 — PASS baseline/control.
- Новые реальные Info.plist из **готового mounted ROOTFS.HFS**: native parser
  принимает profiles, supportedTypes5, classic0, UIKit bounds480x800 — PASS.
- Native parser controls: size480x799 и minimum OS99.0 снова дают classic1 и320x480.
- Phone320x480 по-прежнему nonclassic с320x480 — PASS.
- Полное сравнение файлов original/new: **7110 прежних файлов неизменны**,
  только21 Info.plist изменён,42 PNG добавлены, удалений нет. PNG CRC/dimensions/
  decoded bytes проверены; остальные plist fields равны исходным.
- Actual patcher idempotence — PASS; второй запуск не меняет bytes.
- Raw HFSX, journalInfoBlock0 и journaled flag0 сохранены. Образ cleanly detached.
- Input SHA до/после равен; root zImage SHA равен исходному DISP18.

Пример воспроизведения (нужен supplied rootfs, Apple files не входят в source export):

```sh
python3 tools/prepare_i9100_fullscreen_rootfs.py /path/to/original/rootfs.hfs \
  /path/to/new/ROOTFS.HFS --report /path/to/report.json
python3 tools/verify_i9100_app_geometry_native.py --root /readonly/mount/original --expect classic
python3 tools/verify_i9100_app_geometry_native.py --root /readonly/mount/new --expect fullscreen
```

Два native scripts и file audit не проверяют live compositor, input coordinates,
app-specific layout assumptions или длительную стабильность телефона.
Kernel17 checks в APP19 повторно не запускались: kernel/loader sources и bytes
не менялись. Повторная сборка ядра не нужна.

## Готовый файл и применение

- **`/path/to/workspace/ROOTFS.HFS`**,939524096 bytes (896MiB).
- SHA256 **`cb73747d80a9745506d06c1a270cadfec0854b4a233581cda0c979c137418ec7`**.
- Original supplied image сохранён в
  `/path/to/separately-supplied/rootfs.hfs`, SHA
  `c9b9080de2a1de00707c6c282650b61608405a7dbc8fe2c0bced475705fb9fea`.
- Logs, source scripts, manifest и filesystem diff:
  `diagnostics/app19-20261030/`. Apple image хранится только локально в root,
  не копируется в prepared GitHub repositories.
- Kernel остаётся **DISP18**, UUID `F2FC01E5-35A9-33FD-B19A-9A113B72598D`,
  zImage SHA `fbd22076ce1bd25390ef0a25fa9d30a7b4620c620166962b57da0cb7d218cebb`.

Пользователю нужно **заменить один файл на MicroSD: `/IOS7/ROOTFS.HFS`** готовым
ROOTFS.HFS из корня проекта, безопасно извлечь карту и загрузить телефон.
Повторная Heimdall-прошивка zImage не применит APP19 и не требуется.
Проверить Настройки, края экрана/тач и AssistiveTouch. Панель останется DISP18;
APP19 определяется SHA rootfs, а не новым kernel label. На момент подготовки
карта телефона не была доступна, файл на ней агент не заменял.
