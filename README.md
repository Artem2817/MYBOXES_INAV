# MYBOXES INAV

Адаптация INAV 10.0.0-rc2 для MYBOX H743 Mini, Mini v2 и Mini v2 Vib. Сборка берёт [зафиксированный коммит INAV](https://github.com/iNavFlight/inav/tree/f1cd5c6f68838227ee4d23e97a44c017849cbb14) и применяет определения плат и правки драйверов из этого репозитория. Лицензия исходного проекта прилагается в [LICENSE](LICENSE).

- [Скачать прошивки](https://artem2817.github.io/MYBOXES_Ardupilot/?firmware=inav)
- [GitHub Releases](https://github.com/Artem2817/MYBOXES_INAV/releases)
- [Локальная сборка и проверка на стенде](README.ru.md)
- [Matek M10Q-3100 и выбор CAN1/CAN2](DRONECAN.ru.md)

При изменениях в `main` и в pull request GitHub Actions собирает все три цели и проверяет целостность HEX, идентификатор платы, границы flash и сектор настроек. Для публикации используйте **Actions → Build MyboxH743 Mini INAV release → Run workflow**. Номер ревизии должен быть новым. К каждому HEX прилагаются манифест и SHA-256.

Все текущие образы публикуются в канале `dev` для стендовой проверки. Vib поддерживает ICM-45686, ICM-42670-P и оба SPA06-003. Приоритет у выносного IMU; ориентация J19 требует проверки на конкретной плате. Моторные выходы настроены на стандартный PWM.

r16: CAN1, 1000 кбит/с, DNA ON, GPS и компас DroneCAN для Matek M10Q-3100. Параметр `dronecan_bus` выбирает CAN1 или CAN2; одновременно активен один интерфейс. Основа — предварительный INAV 10.0.0-rc2, нужен Configurator 10.0.
