import * as api from "./api.js";
import * as ui from "./ui.js";
import { mount as mountServices } from "./views/services.view.js";
import { mount as mountWindows } from "./views/windows.view.js";
import { mount as mountOperators } from "./views/operators.view.js";
import { mount as mountMedia } from "./views/media.view.js";
import { mount as mountSettings } from "./views/settings.view.js";
import { mount as mountStats } from "./views/stats.view.js";
import { mount as mountMap, unmount as unmountMap } from "./views/map.view.js";

const routes = {
    services: {
        label: "Услуги",
        description: "Управление услугами, доступными на терминалах",
        icon: "▦",
        mount: mountServices
    },
    windows: {
        label: "Рабочие места",
        description: "Рабочие места, статусы и назначенные услуги",
        icon: "▣",
        mount: mountWindows
    },
    operators: {
        label: "Операторы",
        description: "Доступ операторов и привязка к рабочим местам",
        icon: "◎",
        mount: mountOperators
    },
    map: {
        label: "Карта",
        description: "Редактор карты офиса",
        icon: "▥",
        mount: mountMap,
        unmount: unmountMap
    },
    media: {
        label: "Медиафайлы",
        description: "Загрузка и управление роликами для табло",
        icon: "▤",
        mount: mountMedia
    },
    settings: {
        label: "Настройки",
        description: "Реальные параметры терминала, очереди и табло",
        icon: "⚙",
        mount: mountSettings
    },
    stats: {
        label: "Статистика",
        description: "Переход к текущей статистике Grafana",
        icon: "↗",
        mount: mountStats
    }
};

let currentRoute = null;
let adminSocket = null;
let heartbeatTimer = null;
let reconnectTimer = null;

const root = document.getElementById("admin-root");

function renderShell() {
    root.innerHTML = `
        <div class="admin-shell">
            <aside class="admin-sidebar">
                <nav class="admin-nav">
                    ${Object.entries(routes).map(([key, route]) => `
                        <a href="#${key}" class="admin-nav-link" data-route="${key}">
                            <span>${route.icon}</span>
                            ${route.label}
                        </a>
                    `).join("")}
                </nav>
            </aside>
            <main class="admin-main">
                <header class="admin-header">
                    <button class="admin-menu-button" type="button" aria-label="Меню">☰</button>
                    <div>
                        <h1 id="admin-title">Администрирование</h1>
                        <p id="admin-description"></p>
                    </div>
                    <div class="admin-header-spacer"></div>
                    ${ui.button("Выйти", {variant: "ghost", action: "logout"})}
                </header>
                <section id="admin-view" class="admin-view"></section>
            </main>
        </div>
        <aside id="admin-drawer" class="admin-drawer" aria-hidden="true"></aside>
        <div id="admin-toast-host" class="admin-toast-host"></div>
    `;

    root.addEventListener("click", event => {
        const action = event.target.closest("[data-action]")?.dataset.action;
        if (action === "logout") api.logout();
        if (event.target.closest(".admin-menu-button")) {
            document.body.classList.toggle("admin-sidebar-collapsed");
        }
    });
}

function setHeader(routeKey) {
    const route = routes[routeKey];
    document.getElementById("admin-title").textContent = route.label;
    document.getElementById("admin-description").textContent = route.description;
    document.querySelectorAll(".admin-nav-link").forEach(link => {
        link.classList.toggle("active", link.dataset.route === routeKey);
    });
}

function getView() {
    return document.getElementById("admin-view");
}

function openDrawer(title, content, options = {}) {
    const drawer = document.getElementById("admin-drawer");
    drawer.innerHTML = `
        <div class="admin-drawer-header">
            <h2>${ui.escapeHtml(title)}</h2>
            ${ui.button("×", {variant: "icon", action: "close-drawer", title: "Закрыть"})}
        </div>
        <div class="admin-drawer-body">${content}</div>
        ${options.footer ? `<div class="admin-drawer-footer">${options.footer}</div>` : ""}
    `;
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
    drawer.querySelector('[data-action="close-drawer"]')?.addEventListener("click", closeDrawer);
}

function closeDrawer() {
    const drawer = document.getElementById("admin-drawer");
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    drawer.innerHTML = "";
}

async function navigate() {
    const routeKey = (location.hash || "#services").slice(1);
    const key = routes[routeKey] ? routeKey : "services";
    const route = routes[key];

    closeDrawer();
    if (currentRoute && routes[currentRoute]?.unmount) routes[currentRoute].unmount();
    currentRoute = key;
    setHeader(key);

    const ctx = {
        api,
        ui,
        routes,
        view: getView(),
        setHeader,
        openDrawer,
        closeDrawer,
        toast: ui.showToast
    };

    getView().innerHTML = `<div class="admin-loading">Загрузка...</div>`;
    try {
        await route.mount(ctx);
    } catch (error) {
        if (error?.name === "ApiError") return;
        console.error(error);
        getView().innerHTML = `<div class="admin-error">${ui.escapeHtml(error.message || "Не удалось загрузить раздел")}</div>`;
    }
}

function startWebSocket() {
    clearTimeout(reconnectTimer);
    adminSocket = new WebSocket(CONFIG.WS_TERMINAL_URL);

    adminSocket.onopen = () => sendHeartbeat();
    adminSocket.onmessage = event => {
        const data = JSON.parse(event.data);
        if (data.type === "session_expired") api.redirectToLogin();
    };
    adminSocket.onclose = () => {
        reconnectTimer = setTimeout(startWebSocket, CONFIG.RECONNECT_INTERVAL || 2000);
    };

    clearInterval(heartbeatTimer);
    heartbeatTimer = setInterval(sendHeartbeat, 5000);
}

function sendHeartbeat() {
    const sid = api.getSessionId();
    if (!sid || !adminSocket || adminSocket.readyState !== WebSocket.OPEN) return;
    adminSocket.send(JSON.stringify({type: "ping", session_id: sid}));
}

async function bootstrap() {
    const sessionId = api.getSessionId();
    if (!sessionId) {
        api.redirectToLogin();
        return;
    }

    renderShell();
    await api.request("/auth/admin");
    startWebSocket();

    window.addEventListener("hashchange", navigate);
    if (!location.hash) location.hash = "#services";
    await navigate();
}

document.addEventListener("DOMContentLoaded", () => {
    bootstrap().catch(error => {
        if (error?.name === "ApiError") return;
        console.error(error);
        api.redirectToLogin();
    });
});
