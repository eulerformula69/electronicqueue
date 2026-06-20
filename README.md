# Queue

Система управления электронной очередью для Ubuntu Server 24.04 LTS.

## Установка

Перенесите всю папку проекта на чистую виртуальную машину и выполните:

```bash
sudo bash install.sh
```

Установщик настраивает PostgreSQL, приложение, Nginx, HTTP + HTTPS и Grafana. Рабочая копия размещается в:

```text
/home/queue/queue_project
```

После установки адреса страниц выводятся в терминале. Учётные данные администратора, терминала и Grafana можно посмотреть командой:

```bash
sudo cat /root/queue-credentials.txt
```

Основной IPv4 определяется автоматически. При необходимости его можно указать явно:

```bash
sudo QUEUE_SERVER_IP=192.168.0.20 bash install.sh
```

## HTTPS

Установщик создаёт локальный центр сертификации `mkcert`, выпускает сертификат для IP сервера и одновременно оставляет доступными HTTP и HTTPS без перенаправления.

Корневой сертификат для клиентских устройств находится на сервере:

```text
/root/queue-rootCA.pem
```

Скопировать его в домашний каталог пользователя сервера можно командой:

```bash
sudo cp /root/queue-rootCA.pem ~/queue-rootCA.pem
sudo chown "$USER:$USER" ~/queue-rootCA.pem
```

На Windows сертификат устанавливается из PowerShell администратора:

```powershell
certutil -addstore -f Root "C:\путь\к\queue-rootCA.pem"
```

На Raspberry Pi или другом Linux:

```bash
sudo cp queue-rootCA.pem /usr/local/share/ca-certificates/queue-mkcert.crt
sudo update-ca-certificates
```

После установки сертификата браузер необходимо полностью перезапустить. Файл `rootCA-key.pem` с сервера переносить нельзя.

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

## Локальные файлы

Следующие данные не публикуются в Git:

- `main.env`;
- `dump.sql`;
- `PostgreSQL/`;
- `queue/media/`;
- `queue/tts/cache/`;
- `__pycache__/`.

Они могут содержать пароли, рабочие данные или локальные установочные файлы.
