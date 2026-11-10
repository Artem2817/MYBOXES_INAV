# MYBOXES INAV

Адаптация INAV 9.1.0 для MYBOX H743 Mini, Mini v2 и Mini v2 Vib. Сборка берёт [зафиксированный коммит INAV](https://github.com/iNavFlight/inav/tree/e519b69b02e27c8bdc03b4a0889f1baaae211a54) и применяет определения плат и правки драйверов из этого репозитория. Лицензия исходного проекта прилагается в [LICENSE](LICENSE).

- [Скачать прошивки](https://artem2817.github.io/MYBOXES_Ardupilot/?firmware=inav)
- [GitHub Releases](https://github.com/Artem2817/MYBOXES_INAV/releases)
- [Локальная сборка и проверка на стенде](README.ru.md)

При изменениях в `main` и в pull request GitHub Actions собирает все три цели и проверяет целостность HEX, идентификатор платы, границы flash и сектор настроек. Для публикации используйте **Actions → Build MyboxH743 Mini INAV release → Run workflow**. Номер ревизии должен быть новым. К каждому HEX прилагаются манифест и SHA-256.

Все текущие образы публикуются в канале `dev` для стендовой проверки. Vib использует основной ICM-45686. Поддержка датчиков выносного модуля и DShot требует отдельной проверки.
