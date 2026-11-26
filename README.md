# MYBOXES INAV 9

Рабочая линия **inav-9**, основа **9.1.0**, Configurator **9.1**.

| Плата | INAV 9.1 Stable | INAV 9.1 Dev | INAV 10 Dev |
|---|---|---|---|
| Mini | r15 | r15 | r17 |
| Mini v2 | r15 | r15 | r17 |
| Mini v2 Vib | r15 | r16 | r18 |

Новые r16 для INAV 9 и r18 для INAV 10 относятся только к Mini v2 Vib: автоматический переход на резервную IMU включён по умолчанию. Подробнее: [IMU-FAILOVER.ru.md](IMU-FAILOVER.ru.md).

[Скачать прошивки](https://artem2817.github.io/MYBOXES_Ardupilot/?firmware=inav&line=9) · [Релизы](https://github.com/Artem2817/MYBOXES_INAV/releases)

- [Подключение, параметры и сборка](README.ru.md)
- [Работа с ветками и выпуск обновления](BRANCHES.ru.md)
- [Текущие планы](ROADMAP.ru.md)
- [MyboxDiag](https://github.com/Artem2817/MYBOXES_Diag)

Источник истины — файлы этой ветки: target/, board-support.patch, release-line.json и tools/. Полные исходники закреплены точным коммитом из release-line.json. Исторические дополнительные патчи находятся в archive/legacy-patches/ и не участвуют в текущей сборке.

В WSL проект находится в /home/osas/inav/mybox; полные исходники — /home/osas/inav-9-failover. Отдельные диагностические checkout не заменяют релизные исходники. Ветка main заморожена для старых ссылок.

Разработка ведётся от Artem2817 с помощью AI. Опубликованные HEX и теги сохраняются без изменений; новые исправления получают новый выпуск.
