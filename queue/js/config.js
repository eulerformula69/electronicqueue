const WS_PROTOCOL = window.location.protocol === "https:" ? "wss:" : "ws:";

const CONFIG = {
    API_URL: window.location.origin,
    WS_TERMINAL_URL: `${WS_PROTOCOL}//${window.location.host}/ws/terminal`,
    WS_BOARD_URL: `${WS_PROTOCOL}//${window.location.host}/ws/board`,
    NOTICE_DURATION: 7,
    RECONNECT_INTERVAL: 2000,
    OPERATOR_POLL_INTERVAL_MS: 7000,
    GRAFANA_URL: `http://${window.location.hostname}:3000/d/queue-statistics/queue-statistics`,
    MEDIA_IDLE_DELAY: 15
};
