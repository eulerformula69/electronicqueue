#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="queue"
APP_HOME="/home/${APP_NAME}"
APP_DIR="${APP_HOME}/queue_project"
APP_USER="queue"
DB_NAME="queue"
DB_USER="queue_app"
GRAFANA_DB_USER="queue_grafana"
SERVICE_NAME="queue.service"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FIRST_INSTALL=0

log() {
    printf '\n\033[1;34m[QUEUE]\033[0m %s\n' "$1"
}

fail() {
    printf '\n\033[1;31m[QUEUE] Ошибка:\033[0m %s\n' "$1" >&2
    exit 1
}

if [[ ${EUID} -ne 0 ]]; then
    fail "запустите установщик командой: sudo ./install.sh"
fi

if [[ ! -f "${SOURCE_DIR}/main.py" || ! -d "${SOURCE_DIR}/queue" ]]; then
    fail "рядом с install.sh должны находиться main.py и папка queue"
fi

if [[ ! -f /etc/os-release ]]; then
    fail "поддерживается Ubuntu 24.04 LTS"
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ ${ID:-} != "ubuntu" ]]; then
    fail "поддерживается Ubuntu 24.04 LTS (обнаружено: ${PRETTY_NAME:-неизвестно})"
fi

export DEBIAN_FRONTEND=noninteractive

log "Устанавливаю системные компоненты"
apt-get update
apt-get install -y python3 python3-venv python3-pip postgresql nginx rsync curl wget gpg

if ! id "${APP_USER}" >/dev/null 2>&1; then
    useradd --create-home --home-dir "${APP_HOME}" --shell /bin/bash "${APP_USER}"
fi

install -d -o "${APP_USER}" -g "${APP_USER}" "${APP_DIR}"
install -d -o "${APP_USER}" -g "${APP_USER}" "${APP_DIR}/deploy"

if [[ ! -f "${APP_DIR}/main.env" ]]; then
    FIRST_INSTALL=1
fi

log "Копирую приложение"
install -m 0644 "${SOURCE_DIR}/main.py" "${APP_DIR}/main.py"
install -m 0644 "${SOURCE_DIR}/requirements.txt" "${APP_DIR}/requirements.txt"
install -m 0644 "${SOURCE_DIR}/deploy/bootstrap_users.py" "${APP_DIR}/deploy/bootstrap_users.py"
install -d -o "${APP_USER}" -g "${APP_USER}" "${APP_DIR}/queue"
rsync -a --delete \
    --exclude 'media/' \
    --exclude 'tts/cache/' \
    "${SOURCE_DIR}/queue/" "${APP_DIR}/queue/"
install -d -o "${APP_USER}" -g "${APP_USER}" \
    "${APP_DIR}/queue/media" "${APP_DIR}/queue/tts/cache"

systemctl enable --now postgresql

if [[ ${FIRST_INSTALL} -eq 1 ]]; then
    log "Создаю локальную базу данных"
    DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    GRAFANA_DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"

    if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1; then
        runuser -u postgres -- psql -v ON_ERROR_STOP=1 \
            -c "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}'"
    else
        runuser -u postgres -- psql -v ON_ERROR_STOP=1 \
            -c "ALTER ROLE ${DB_USER} PASSWORD '${DB_PASSWORD}'"
    fi

    if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
        runuser -u postgres -- createdb --owner="${DB_USER}" "${DB_NAME}"
    fi
    runuser -u postgres -- psql -v ON_ERROR_STOP=1 \
        -c "ALTER DATABASE ${DB_NAME} OWNER TO ${DB_USER}"

    SERVER_IP="$(hostname -I | awk '{print $1}')"
    [[ -n "${SERVER_IP}" ]] || SERVER_IP="127.0.0.1"

    cat > "${APP_DIR}/main.env" <<EOF
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@127.0.0.1:5432/${DB_NAME}
GRAFANA_DB_PASSWORD=${GRAFANA_DB_PASSWORD}
CORS_ORIGINS=http://${SERVER_IP},http://localhost,http://127.0.0.1
SESSION_TIMEOUT_SECONDS=300
PIPER_PATH=${APP_DIR}/venv/bin/piper
PIPER_MODEL=queue/tts/ru_RU-irina-medium.onnx
TTS_CACHE_DIR=queue/tts/cache
TTS_LENGTH_SCALE=1.25
TTS_NOISE_SCALE=0.65
TTS_NOISE_W_SCALE=0.75
EOF
    chmod 0600 "${APP_DIR}/main.env"

    ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
    TERMINAL_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
    install -m 0600 /dev/null /root/queue-credentials.txt
    cat > /root/queue-credentials.txt <<EOF
Панель администратора: admin
Пароль администратора: ${ADMIN_PASSWORD}

Терминал: terminal
Пароль терминала: ${TERMINAL_PASSWORD}
EOF
fi

GRAFANA_DB_PASSWORD="$(sed -n 's/^GRAFANA_DB_PASSWORD=//p' "${APP_DIR}/main.env")"
if [[ -z "${GRAFANA_DB_PASSWORD}" ]]; then
    GRAFANA_DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    printf 'GRAFANA_DB_PASSWORD=%s\n' "${GRAFANA_DB_PASSWORD}" >> "${APP_DIR}/main.env"
fi
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${GRAFANA_DB_USER}'" | grep -q 1; then
    runuser -u postgres -- psql -v ON_ERROR_STOP=1 \
        -c "CREATE ROLE ${GRAFANA_DB_USER} LOGIN PASSWORD '${GRAFANA_DB_PASSWORD}'"
else
    runuser -u postgres -- psql -v ON_ERROR_STOP=1 \
        -c "ALTER ROLE ${GRAFANA_DB_USER} PASSWORD '${GRAFANA_DB_PASSWORD}'"
fi

log "Устанавливаю Python-зависимости"
if [[ ! -x "${APP_DIR}/venv/bin/python" ]]; then
    python3 -m venv "${APP_DIR}/venv"
fi
"${APP_DIR}/venv/bin/python" -m pip install --upgrade pip
"${APP_DIR}/venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"

chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 0600 "${APP_DIR}/main.env"

log "Настраиваю автоматический запуск"
cat > "/etc/systemd/system/${SERVICE_NAME}" <<EOF
[Unit]
Description=Electronic queue
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

log "Создаю начальные учётные записи"
if [[ -f /root/queue-credentials.txt ]]; then
    ADMIN_PASSWORD="$(sed -n 's/^Пароль администратора: //p' /root/queue-credentials.txt)"
    TERMINAL_PASSWORD="$(sed -n 's/^Пароль терминала: //p' /root/queue-credentials.txt)"
else
    ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
    TERMINAL_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
fi

QUEUE_ADMIN_PASSWORD="${ADMIN_PASSWORD}" QUEUE_TERMINAL_PASSWORD="${TERMINAL_PASSWORD}" \
    runuser -u "${APP_USER}" -- "${APP_DIR}/venv/bin/python" "${APP_DIR}/deploy/bootstrap_users.py"

log "Устанавливаю и настраиваю Grafana"
install -d -m 0755 /etc/apt/keyrings
wget -q -O - https://apt.grafana.com/gpg.key \
    | gpg --dearmor --yes -o /etc/apt/keyrings/grafana.gpg
cat > /etc/apt/sources.list.d/grafana.list <<'EOF'
deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main
EOF
apt-get update
apt-get install -y grafana

runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" <<EOF
GRANT CONNECT ON DATABASE ${DB_NAME} TO ${GRAFANA_DB_USER};
GRANT USAGE ON SCHEMA public TO ${GRAFANA_DB_USER};
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ${GRAFANA_DB_USER};
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO ${GRAFANA_DB_USER};
ALTER DEFAULT PRIVILEGES FOR ROLE ${DB_USER} IN SCHEMA public
    GRANT SELECT ON TABLES TO ${GRAFANA_DB_USER};
EOF

install -d -m 0755 /etc/grafana/provisioning/datasources
install -d -m 0755 /etc/grafana/provisioning/dashboards
install -d -m 0755 /var/lib/grafana/dashboards

cat > /etc/grafana/provisioning/datasources/queue.yaml <<EOF
apiVersion: 1
datasources:
  - name: Queue PostgreSQL
    uid: queue-postgres
    type: postgres
    access: proxy
    url: 127.0.0.1:5432
    user: ${GRAFANA_DB_USER}
    secureJsonData:
      password: ${GRAFANA_DB_PASSWORD}
    jsonData:
      database: ${DB_NAME}
      sslmode: disable
      postgresVersion: 1600
      timescaledb: false
    isDefault: true
    editable: false
EOF
chmod 0640 /etc/grafana/provisioning/datasources/queue.yaml
chown root:grafana /etc/grafana/provisioning/datasources/queue.yaml

cat > /etc/grafana/provisioning/dashboards/queue.yaml <<'EOF'
apiVersion: 1
providers:
  - name: Queue
    orgId: 1
    folder: Queue
    type: file
    disableDeletion: true
    updateIntervalSeconds: 30
    options:
      path: /var/lib/grafana/dashboards
EOF

DASHBOARD_SOURCE="${SOURCE_DIR}/Статистика для очереди 2-1776781181260.json"
if [[ ! -f "${DASHBOARD_SOURCE}" ]]; then
    DASHBOARD_SOURCE="$(find "${SOURCE_DIR}" -maxdepth 1 -type f -name 'Статистика для очереди*.json' -print -quit)"
fi
[[ -n "${DASHBOARD_SOURCE}" && -f "${DASHBOARD_SOURCE}" ]] \
    || fail "не найден JSON-дашборд Grafana в папке проекта"
python3 - "${DASHBOARD_SOURCE}" /var/lib/grafana/dashboards/queue-statistics.json <<'PY'
import json
import sys

source, destination = sys.argv[1:]
with open(source, encoding="utf-8") as file:
    dashboard = json.load(file)

old_datasource_uids = {"cffzz1xb8ay9sa", "bfjh7wvbqibcwd"}


def replace_datasource_uid(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "uid" and item in old_datasource_uids:
                value[key] = "queue-postgres"
            else:
                replace_datasource_uid(item)
    elif isinstance(value, list):
        for item in value:
            replace_datasource_uid(item)


replace_datasource_uid(dashboard)
dashboard["id"] = None
dashboard["uid"] = "queue-statistics"
dashboard["title"] = "Статистика очереди"
with open(destination, "w", encoding="utf-8") as file:
    json.dump(dashboard, file, ensure_ascii=False, indent=2)
PY
chown -R grafana:grafana /var/lib/grafana/dashboards

install -d -m 0755 /etc/systemd/system/grafana-server.service.d
cat > /etc/systemd/system/grafana-server.service.d/queue.conf <<'EOF'
[Service]
Environment=GF_SECURITY_ALLOW_EMBEDDING=true
Environment=GF_AUTH_ANONYMOUS_ENABLED=true
Environment="GF_AUTH_ANONYMOUS_ORG_NAME=Main Org."
Environment=GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
Environment=GF_AUTH_DISABLE_LOGIN_FORM=true
Environment=GF_USERS_DEFAULT_THEME=light
EOF

systemctl daemon-reload
systemctl enable --now grafana-server
systemctl restart grafana-server

log "Настраиваю веб-доступ"
cat > /etc/nginx/sites-available/queue <<'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 55m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
    }
}
EOF

rm -f /etc/nginx/sites-enabled/default
ln -sfn /etc/nginx/sites-available/queue /etc/nginx/sites-enabled/queue
nginx -t
systemctl enable --now nginx
systemctl reload nginx

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q '^Status: active'; then
    ufw allow 'Nginx HTTP'
    ufw allow 3000/tcp
fi

log "Проверяю запуск"
for _ in {1..30}; do
    if curl --fail --silent --output /dev/null http://127.0.0.1:8000/queue/login.html; then
        break
    fi
    sleep 1
done

if ! curl --fail --silent --output /dev/null http://127.0.0.1:8000/queue/login.html; then
    journalctl -u "${SERVICE_NAME}" -n 30 --no-pager >&2
    fail "приложение не ответило. Выше показан журнал ошибки"
fi

for _ in {1..30}; do
    if curl --fail --silent --output /dev/null http://127.0.0.1:3000/api/health; then
        break
    fi
    sleep 1
done

if ! curl --fail --silent --output /dev/null http://127.0.0.1:3000/api/health; then
    journalctl -u grafana-server -n 30 --no-pager >&2
    fail "Grafana не ответила. Выше показан журнал ошибки"
fi

SERVER_IP="$(hostname -I | awk '{print $1}')"
[[ -n "${SERVER_IP}" ]] || SERVER_IP="127.0.0.1"

printf '\n\033[1;32mУстановка завершена.\033[0m\n'
printf 'Вход:       http://%s/queue/login.html\n' "${SERVER_IP}"
printf 'Терминал:   http://%s/queue/terminal.html\n' "${SERVER_IP}"
printf 'Табло:      http://%s/queue/board-media.html\n' "${SERVER_IP}"
printf 'Статистика: http://%s:3000/d/queue-statistics/queue-statistics\n' "${SERVER_IP}"
if [[ ${FIRST_INSTALL} -eq 1 ]]; then
    printf 'Пароли:     /root/queue-credentials.txt\n'
else
    printf 'Настройки и пользовательские данные сохранены.\n'
fi
