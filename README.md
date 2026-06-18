# Queue

Система управления электронной очередью для Ubuntu Server 24.04 LTS.

## Установка

Перенести всю папку проекта на чистую виртуальную машину и выполнить:

```bash
sudo bash install.sh
```

Установщик настраивает PostgreSQL, приложение, Nginx и Grafana. Рабочая копия размещается в:

```text
/home/queue/queue_project
```

После установки адреса страниц выводятся в терминале. Учётные данные администратора, терминала и Grafana можно посмотреть командой:

```bash
sudo cat /root/queue-credentials.txt
```

## Структура

```text
deploy/             служебные сценарии установки
queue/              веб-интерфейс, модель речи и локальные медиафайлы
install.sh          установка и повторное обновление сервера
main.py             сервер электронной очереди
manageAdmins.py     управление администраторами и терминалами
main.env.example    пример локальной конфигурации
requirements.txt    зависимости Python
statistics.json     дашборд Grafana
update_from_git.py  обновление существующей установки из Git
```

## Учётные записи

Список администраторов и терминалов:

```bash
sudo queue-admin show
```

Создание администратора или терминала (пароль запрашивается скрыто):

```bash
sudo queue-admin add new_admin admin
sudo queue-admin add new_terminal terminal
```

Смена пароля и удаление записи:

```bash
sudo queue-admin change new_admin --password
sudo queue-admin delete new_admin
```
