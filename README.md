# MYBOXES INAV 9

Рабочая ветка **inav-9** для MYBOX H743 Mini, Mini v2 и Mini v2 Vib.
Основа: **INAV 9.1.0**, INAV Configurator **9.1**.
Текущий опубликованный выпуск: **r15 / INAV 9.1.0 / Stable**.

| Линия | Для чего | Каталог в нашей WSL |
|---|---|---|
| [inav-9](https://github.com/Artem2817/MYBOXES_INAV/tree/inav-9) | Поддержка проверенной INAV 9, основа r15 Stable | ~/inav/mybox |
| [inav-10](https://github.com/Artem2817/MYBOXES_INAV/tree/inav-10) | INAV 10 и DroneCAN, основа r16 Dev | ~/inav-10/mybox |

- [Скачать прошивки](https://artem2817.github.io/MYBOXES_Ardupilot/?firmware=inav)
- [Как работать с двумя версиями и выпускать обновления](BRANCHES.ru.md)
- [Платы, подключение и локальная сборка](README.ru.md)
- [GitHub Releases](https://github.com/Artem2817/MYBOXES_INAV/releases)

В каждом каталоге уже выбрана своя ветка. Обновляйте её и работайте в том же каталоге.
Ветка по умолчанию на GitHub — inav-10; main сохранена для совместимости старых ссылок и больше не используется для сборок.
Проверки выполняются при push и pull request в рабочие ветки. Сборка и упаковка сверяют точный исходный коммит с release-line.json.
Выпуск запускается через Actions с явно выбранной веткой. Новые сборки получают Dev; существующая r15 Stable остаётся без изменений.

Здесь сохранены определения плат, драйверы, SD, DShot, ESC-телеметрия и поворот IMU из r15. Поддержка DroneCAN GPS/компаса добавлена в линии INAV 10. Переименование ветки не меняет уже выпущенный HEX.

- [Запланированные доработки: автоматический резерв IMU только для v2 Vib](ROADMAP.ru.md)
