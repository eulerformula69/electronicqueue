#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Запустите через sudo: sudo bash deploy/configure_grafana_embed.sh" >&2
  exit 1
fi

NGINX_SITE="/etc/nginx/sites-available/queue"
DROPIN_DIR="/etc/systemd/system/grafana-server.service.d"
DROPIN="${DROPIN_DIR}/queue.conf"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="/var/backups/queue-grafana-embed/${STAMP}"
SERVER_IP="${QUEUE_SERVER_IP:-$(hostname -I | awk '{print $1}')}"

if [[ -z "${SERVER_IP}" ]]; then
  echo "IP не определён. Укажите QUEUE_SERVER_IP=10.0.1.132." >&2
  exit 1
fi
if [[ ! -f "${NGINX_SITE}" ]]; then
  echo "Не найден конфиг Nginx: ${NGINX_SITE}" >&2
  exit 1
fi

mkdir -p "${BACKUP_DIR}" "${DROPIN_DIR}"
cp -a "${NGINX_SITE}" "${BACKUP_DIR}/nginx-queue"
[[ ! -f "${DROPIN}" ]] || cp -a "${DROPIN}" "${BACKUP_DIR}/grafana-queue.conf"

cat > "${DROPIN}" <<EOF
[Service]
Environment="GF_SECURITY_ALLOW_EMBEDDING=true"
Environment="GF_AUTH_ANONYMOUS_ENABLED=true"
Environment="GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer"
Environment="GF_USERS_DEFAULT_THEME=light"
Environment="GF_SERVER_DOMAIN=${SERVER_IP}"
Environment="GF_SERVER_ROOT_URL=https://${SERVER_IP}/grafana/"
Environment="GF_SERVER_SERVE_FROM_SUB_PATH=true"
EOF

python3 - "${NGINX_SITE}" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()
begin = "# BEGIN QRONION GRAFANA PROXY"
end = "# END QRONION GRAFANA PROXY"
block = """        # BEGIN QRONION GRAFANA PROXY
        location /grafana/ {
            proxy_pass http://127.0.0.1:3000;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-Prefix /grafana;
            proxy_hide_header X-Frame-Options;
        }
        # END QRONION GRAFANA PROXY

"""

if begin in text and end in text:
    pattern = re.compile(
        r"^[ \t]*# BEGIN QRONION GRAFANA PROXY.*?"
        r"^[ \t]*# END QRONION GRAFANA PROXY\s*",
        re.MULTILINE | re.DOTALL,
    )
    text, count = pattern.subn(block, text, count=1)
    if count != 1:
        raise SystemExit("Не удалось обновить блок Grafana в Nginx")
elif re.search(r"location\s+(?:\^~\s+)?/grafana/", text):
    raise SystemExit("В Nginx уже есть ручной location /grafana/. Нужна ручная проверка.")
else:
    marker = re.search(r"^(\s*)location\s+/\s*\{", text, re.MULTILINE)
    if not marker:
        raise SystemExit("Не найден основной location / в конфиге Nginx")
    text = text[:marker.start()] + block + text[marker.start():]

path.write_text(text)
PY

if ! nginx -t; then
  cp -a "${BACKUP_DIR}/nginx-queue" "${NGINX_SITE}"
  echo "Исходный конфиг Nginx восстановлен." >&2
  exit 1
fi

systemctl daemon-reload
if ! systemctl restart grafana-server; then
  if [[ -f "${BACKUP_DIR}/grafana-queue.conf" ]]; then
    cp -a "${BACKUP_DIR}/grafana-queue.conf" "${DROPIN}"
  else
    rm -f "${DROPIN}"
  fi
  systemctl daemon-reload
  systemctl restart grafana-server || true
  echo "Grafana не запустилась. Предыдущая настройка восстановлена." >&2
  exit 1
fi

systemctl reload nginx
for _ in {1..30}; do
  if curl -kfsS "https://${SERVER_IP}/grafana/api/health" >/dev/null; then
    echo "Готово: https://${SERVER_IP}/grafana/"
    echo "Резервная копия: ${BACKUP_DIR}"
    exit 0
  fi
  sleep 1
done

echo "Настройки применены, но Grafana не ответила на проверку." >&2
echo "Резервная копия: ${BACKUP_DIR}" >&2
exit 1
