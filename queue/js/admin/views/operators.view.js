let ctx;
let operators = [];
let windows = [];
let settings = {};
let sortState = {key: "name", direction: "asc"};
const sortStorageKey = "admin.operators.sort";

export async function mount(context) {
    ctx = context;
    sortState = loadSortState(sortState);
    await load();
    render();
}

async function load() {
    const [operatorData, windowData, settingsData] = await Promise.all([
        ctx.api.request("/operators/"),
        ctx.api.request("/windows/"),
        ctx.api.request("/admin/settings")
    ]);
    operators = Array.isArray(operatorData) ? operatorData : [];
    windows = Array.isArray(windowData) ? windowData : [];
    settings = settingsData || {};
}

function render() {
    const rows = sortOperators(operators).map(operator => `
        <tr>
            <td>${operator.id}</td>
            <td><strong>${ctx.ui.escapeHtml(operator.name)}</strong></td>
            <td>${ctx.ui.escapeHtml(operator.login || "-")}</td>
            <td>${ctx.ui.escapeHtml(windowName(operator.window_id))}</td>
            <td>${ctx.ui.escapeHtml(autoCallModeLabel(operator.auto_call_mode))}</td>
            <td>${ctx.ui.button("Редактировать", {variant: "link", action: "edit", id: operator.id})}</td>
        </tr>
    `);

    ctx.view.innerHTML = `
        <div class="operator-top-row">
            <form id="operator-auto-call-form" class="admin-card operator-auto-call-card">
                <strong>Автовызов</strong>
                <div class="operator-auto-call-controls">
                    <label class="operator-auto-call-switch">
                        ${ctx.ui.switchField("auto_call_enabled", settings.auto_call_enabled)}
                        <span>По умолчанию</span>
                    </label>
                    <label class="operator-auto-call-delay">
                        <span>Задержка, сек.</span>
                        <input class="admin-input" name="auto_call_delay_seconds" type="number" min="0" max="600" step="1" value="${ctx.ui.escapeHtml(settings.auto_call_delay_seconds ?? 60)}">
                    </label>
                    ${ctx.ui.button("Сохранить", {variant: "primary", action: "save-auto-call"})}
                </div>
            </form>
            ${ctx.ui.button("Добавить оператора", {variant: "primary", action: "create", className: "operator-add-button"})}
        </div>
        ${ctx.ui.table([
            ctx.ui.sortHeader("ID", "id", sortState),
            ctx.ui.sortHeader("ФИО", "name", sortState),
            ctx.ui.sortHeader("Логин", "login", sortState),
            ctx.ui.sortHeader("Рабочее место", "window", sortState),
            ctx.ui.sortHeader("Автовызов", "auto_call", sortState),
            "Действия"
        ], rows)}
    `;
    ctx.view.onclick = handleClick;
}

async function handleClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    if (button.dataset.action === "sort") {
        setSort(button.dataset.sortKey);
        render();
        return;
    }
    if (button.dataset.action === "save-auto-call") {
        await saveAutoCallSettings();
        return;
    }
    if (button.dataset.action === "create") openDrawer();
    if (button.dataset.action === "edit") openDrawer(operators.find(item => item.id === Number(button.dataset.id)));
}

function setSort(key) {
    sortState = {
        key,
        direction: sortState.key === key && sortState.direction === "asc" ? "desc" : "asc"
    };
    saveSortState(sortState);
}

function sortOperators(items) {
    return [...items].sort((a, b) => {
        const result = compareValues(operatorSortValue(a, sortState.key), operatorSortValue(b, sortState.key));
        return sortState.direction === "asc" ? result : -result;
    });
}

function operatorSortValue(operator, key) {
    if (key === "id") return operator.id ?? 0;
    if (key === "login") return operator.login || "";
    if (key === "window") return windowName(operator.window_id);
    if (key === "auto_call") return autoCallModeLabel(operator.auto_call_mode);
    return operator.name || "";
}

function compareValues(a, b) {
    return String(a ?? "").localeCompare(String(b ?? ""), "ru", {numeric: true, sensitivity: "base"});
}

function loadSortState(fallback) {
    try {
        const parsed = JSON.parse(localStorage.getItem(sortStorageKey) || "null");
        if (parsed && ["id", "name", "login", "window", "auto_call"].includes(parsed.key) && ["asc", "desc"].includes(parsed.direction)) {
            return parsed;
        }
    } catch (error) {
        return fallback;
    }
    return fallback;
}

function saveSortState(state) {
    try {
        localStorage.setItem(sortStorageKey, JSON.stringify(state));
    } catch (error) {
        // Ignore storage failures; sorting still works for the current render.
    }
}

function windowName(id) {
    return windows.find(item => item.id === id)?.name || "Не назначено";
}

function windowOptions(selectedId) {
    return [
        {value: "", label: "Не назначено"},
        ...windows.map(item => ({value: item.id, label: item.name}))
    ];
}

function autoCallModeOptions() {
    return [
        {value: "default", label: "По общей настройке"},
        {value: "enabled", label: "Включён"},
        {value: "disabled", label: "Выключен"}
    ];
}

function autoCallModeLabel(mode) {
    return autoCallModeOptions().find(item => item.value === mode)?.label || "По общей настройке";
}

function openDrawer(operator = null) {
    const isEdit = Boolean(operator);
    ctx.openDrawer(isEdit ? "Редактирование оператора" : "Новый оператор", `
        <form id="operator-form" class="admin-form">
            ${ctx.ui.field("ФИО", ctx.ui.input("name", operator?.name || "", "required"))}
            ${ctx.ui.field("Логин", ctx.ui.input("login", operator?.login || "", "required"))}
            ${ctx.ui.field("Пароль", ctx.ui.input("password", "", `${isEdit ? "placeholder=\"Оставьте пустым, чтобы не менять\"" : "required"} type="password"`))}
            ${ctx.ui.field("Рабочее место", ctx.ui.select("window_id", windowOptions(operator?.window_id), operator?.window_id ?? ""))}
            ${ctx.ui.field("Автовызов", ctx.ui.select("auto_call_mode", autoCallModeOptions(), operator?.auto_call_mode || "default"))}
        </form>
    `, {
        footer: `
            ${ctx.ui.button("Отмена", {variant: "secondary", action: "cancel"})}
            ${isEdit ? ctx.ui.button("Удалить", {variant: "danger", action: "delete", id: operator.id}) : ""}
            ${ctx.ui.button("Сохранить", {variant: "primary", action: "save", id: operator?.id ?? ""})}
        `
    });
    document.getElementById("admin-drawer").onclick = handleDrawerClick;
}

async function handleDrawerClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    const id = Number(button.dataset.id);
    if (action === "cancel") ctx.closeDrawer();
    if (action === "save") await saveOperator(id || null);
    if (action === "delete") await deleteOperator(id);
}

async function saveOperator(id) {
    const data = Object.fromEntries(new FormData(document.getElementById("operator-form")).entries());
    const name = data.name?.trim();
    const login = data.login?.trim();
    const password = data.password?.trim();
    const window_id = data.window_id ? Number(data.window_id) : null;
    const auto_call_mode = data.auto_call_mode || "default";

    if (!name || !login || (!id && !password)) {
        ctx.toast("Заполните имя, логин и пароль", "error");
        return;
    }

    if (!id) {
        await ctx.api.json("/operators/", {method: "POST", body: {name, login, password, window_id, auto_call_mode}});
    } else {
        const current = operators.find(item => item.id === id);
        if (current && login !== current.login && !password) {
            ctx.toast("Для смены логина укажите новый пароль", "error");
            return;
        }
        await ctx.api.json(`/operators/${id}`, {method: "PATCH", body: {name, window_id, auto_call_mode}});
        if (password) {
            await ctx.api.json(`/operators/${id}/login`, {method: "PUT", body: {login, password}});
        }
    }

    ctx.closeDrawer();
    await load();
    render();
    ctx.toast("Оператор сохранён", "success");
}

async function saveAutoCallSettings() {
    const form = document.getElementById("operator-auto-call-form");
    const data = Object.fromEntries(new FormData(form).entries());
    const auto_call_delay_seconds = Number(data.auto_call_delay_seconds);

    if (!Number.isInteger(auto_call_delay_seconds) || auto_call_delay_seconds < 0 || auto_call_delay_seconds > 600) {
        ctx.toast("Задержка автовызова должна быть целым числом от 0 до 600 секунд", "error");
        return;
    }

    settings = await ctx.api.json("/admin/settings", {
        method: "PUT",
        body: {
            ...settings,
            auto_call_enabled: Boolean(data.auto_call_enabled),
            auto_call_delay_seconds
        }
    });
    ctx.toast("Настройки автовызова сохранены", "success");
    render();
}

async function deleteOperator(id) {
    if (!ctx.ui.confirmAction("Удалить оператора?")) return;
    await ctx.api.request(`/operators/${id}`, {method: "DELETE"});
    ctx.closeDrawer();
    await load();
    render();
}
