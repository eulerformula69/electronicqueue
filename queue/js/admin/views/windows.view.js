let ctx;
let windows = [];
let operators = [];
let services = [];
let windowServices = new Map();

const statuses = [
    {value: "online", label: "Работает"},
    {value: "break", label: "Перерыв"},
    {value: "offline", label: "Не работает"}
];

const autoCallModes = [
    {value: "default", label: "По общей настройке"},
    {value: "enabled", label: "Включён"},
    {value: "disabled", label: "Выключен"}
];

export async function mount(context) {
    ctx = context;
    await load();
    render();
}

async function load() {
    const [windowData, operatorData, serviceData] = await Promise.all([
        ctx.api.request("/windows/"),
        ctx.api.request("/operators/"),
        ctx.api.request("/services/?include_hidden=true")
    ]);
    windows = Array.isArray(windowData) ? windowData : [];
    operators = Array.isArray(operatorData) ? operatorData : [];
    services = Array.isArray(serviceData) ? serviceData : [];
    windowServices = new Map();
    await Promise.all(windows.map(async windowItem => {
        const linked = await ctx.api.request(`/window-services/${windowItem.id}`);
        windowServices.set(windowItem.id, Array.isArray(linked) ? linked : []);
    }));
}

function render() {
    const freeOperators = operators.filter(item => !item.window_id);
    const occupiedCount = windows.filter(item => operatorForWindow(item.id)).length;
    ctx.view.innerHTML = `
        <div class="workplaces-summary" aria-label="Состояние рабочих мест">
            ${summaryCard("Рабочих мест", windows.length)}
            ${summaryCard("Занято", occupiedCount, "success")}
            ${summaryCard("Свободно", windows.length - occupiedCount, "warning")}
            ${summaryCard("Без назначения", freeOperators.length, freeOperators.length ? "warning" : "neutral")}
        </div>
        <div class="workplaces-toolbar">
            <p>Оператор назначается на место, но остаётся отдельной учётной записью.</p>
            <div>${ctx.ui.button("Добавить оператора", {action: "create-operator"})}${ctx.ui.button("Добавить рабочее место", {variant: "primary", action: "create-window"})}</div>
        </div>
        <section class="workplaces-section" aria-labelledby="workplaces-title">
            <h2 id="workplaces-title">Рабочие места</h2>
            <div class="workplaces-list">${windows.length ? [...windows].sort(byName).map(renderWindow).join("") : emptyState("Рабочих мест пока нет")}</div>
        </section>
        <section class="workplaces-section" aria-labelledby="unassigned-title">
            <div class="workplaces-section-heading"><h2 id="unassigned-title">Операторы без назначения</h2>${ctx.ui.badge(String(freeOperators.length), freeOperators.length ? "warning" : "neutral")}</div>
            <div class="unassigned-operators">${freeOperators.length ? freeOperators.sort(byName).map(renderFreeOperator).join("") : `<p class="workplaces-empty-inline">Все операторы назначены на рабочие места.</p>`}</div>
        </section>`;
    ctx.view.onclick = handleClick;
    ctx.view.onchange = handleChange;
}

function summaryCard(label, value, tone = "neutral") {
    return `<article class="workplaces-summary-card workplaces-summary-${tone}"><strong>${value}</strong><span>${label}</span></article>`;
}

function renderWindow(windowItem) {
    const operator = operatorForWindow(windowItem.id);
    const linked = windowServices.get(windowItem.id) || [];
    const serviceNames = linked.map(link => services.find(service => service.id === link.service_id)?.name).filter(Boolean);
    return `<article class="workplace-card ${operator ? "is-occupied" : "is-free"} status-${ctx.ui.escapeHtml(windowItem.status)}">
        <div class="workplace-identity"><span class="workplace-status-dot" aria-hidden="true"></span><div><h3>${ctx.ui.escapeHtml(windowItem.name)}</h3><p>${ctx.ui.badge(statusLabel(windowItem.status), statusTone(windowItem.status))}</p></div></div>
        <div class="workplace-services"><span>Услуги</span><strong>${serviceNames.length ? ctx.ui.escapeHtml(serviceNames.join(", ")) : "Не назначены"}</strong></div>
        <div class="workplace-operator"><span>Оператор</span>${operator ? `<strong>${ctx.ui.escapeHtml(operator.name)}</strong><small>${ctx.ui.escapeHtml(operator.login || "")}</small>` : `<select class="admin-input workplace-assign-select" data-action="assign" data-window-id="${windowItem.id}" aria-label="Назначить оператора на ${ctx.ui.escapeHtml(windowItem.name)}"><option value="">Выберите оператора</option>${freeOperatorOptions()}</select>`}</div>
        <div class="workplace-actions">${operator ? ctx.ui.button("Снять", {variant: "ghost", action: "unassign", id: windowItem.id}) : ""}${operator ? ctx.ui.button("Оператор", {variant: "link", action: "edit-operator", id: operator.id}) : ""}${ctx.ui.button("Настроить", {variant: "link", action: "edit-window", id: windowItem.id})}</div>
    </article>`;
}

function renderFreeOperator(operator) {
    return `<article class="unassigned-operator-card"><div><strong>${ctx.ui.escapeHtml(operator.name)}</strong><small>${ctx.ui.escapeHtml(operator.login || "")}</small></div>${ctx.ui.button("Изменить", {variant: "link", action: "edit-operator", id: operator.id})}</article>`;
}

function emptyState(message) {
    return `<div class="admin-card admin-empty-state">${ctx.ui.escapeHtml(message)}</div>`;
}

function freeOperatorOptions() {
    return operators.filter(item => !item.window_id).sort(byName).map(item => `<option value="${item.id}">${ctx.ui.escapeHtml(item.name)}</option>`).join("");
}

function operatorForWindow(windowId) {
    return operators.find(item => item.window_id === windowId);
}

function byName(a, b) {
    return String(a.name || "").localeCompare(String(b.name || ""), "ru", {numeric: true, sensitivity: "base"});
}

function statusLabel(status) {
    return statuses.find(item => item.value === status)?.label || status;
}

function statusTone(status) {
    return status === "online" ? "success" : status === "break" ? "warning" : "neutral";
}

async function handleChange(event) {
    if (event.target.dataset.action !== "assign" || !event.target.value) return;
    event.target.disabled = true;
    await assignOperator(Number(event.target.dataset.windowId), Number(event.target.value));
}

async function handleClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button || button.matches("select")) return;
    const id = Number(button.dataset.id);
    if (button.dataset.action === "create-window") openWindowDrawer();
    if (button.dataset.action === "edit-window") openWindowDrawer(windows.find(item => item.id === id));
    if (button.dataset.action === "create-operator") openOperatorDrawer();
    if (button.dataset.action === "edit-operator") openOperatorDrawer(operators.find(item => item.id === id));
    if (button.dataset.action === "unassign") await assignOperator(id, null);
}

async function assignOperator(windowId, operatorId) {
    await ctx.api.json(`/windows/${windowId}/operator`, {method: "PUT", body: {operator_id: operatorId}});
    await refresh(operatorId ? "Оператор назначен" : "Оператор снят с рабочего места");
}

function openWindowDrawer(windowItem = null) {
    const linked = windowItem ? windowServices.get(windowItem.id) || [] : [];
    const priorities = new Map(linked.map(item => [item.service_id, item.priority ?? 1]));
    ctx.openDrawer(windowItem ? "Настроить рабочее место" : "Новое рабочее место", `<form id="window-form" class="admin-form">
        ${ctx.ui.field("Название", ctx.ui.input("name", windowItem?.name || "", "required"))}
        ${windowItem ? ctx.ui.field("Состояние", ctx.ui.select("status", statuses, windowItem.status)) : ""}
        ${windowItem ? `<section class="admin-subsection"><h3>Услуги</h3><p class="admin-muted">Меньшее число означает больший приоритет.</p><div class="admin-check-list">${services.map(service => { const checked = priorities.has(service.id); return `<label class="admin-check-row"><input type="checkbox" name="service_${service.id}" ${checked ? "checked" : ""}><span>${ctx.ui.escapeHtml(service.name)}</span><input class="admin-input admin-priority-input" type="number" min="1" max="100" name="priority_${service.id}" value="${priorities.get(service.id) || 1}"></label>`; }).join("")}</div></section>` : ""}
    </form>`, {footer: drawerFooter("window", windowItem?.id)});
    document.getElementById("admin-drawer").onclick = handleDrawerClick;
}

function openOperatorDrawer(operator = null) {
    const isEdit = Boolean(operator);
    ctx.openDrawer(isEdit ? "Редактирование оператора" : "Новый оператор", `<form id="operator-form" class="admin-form">
        ${ctx.ui.field("ФИО", ctx.ui.input("name", operator?.name || "", "required"))}
        ${ctx.ui.field("Логин", ctx.ui.input("login", operator?.login || "", "required"))}
        ${ctx.ui.field("Пароль", ctx.ui.input("password", "", `${isEdit ? "placeholder=\"Оставьте пустым, чтобы не менять\"" : "required"} type="password"`))}
        ${ctx.ui.field("Автовызов", ctx.ui.select("auto_call_mode", autoCallModes, operator?.auto_call_mode || "default"))}
        ${isEdit ? `<p class="admin-muted">Назначение меняется на основном экране.</p>` : ""}
    </form>`, {footer: drawerFooter("operator", operator?.id)});
    document.getElementById("admin-drawer").onclick = handleDrawerClick;
}

function drawerFooter(type, id) {
    return `${ctx.ui.button("Отмена", {variant: "secondary", action: "cancel"})}${id ? ctx.ui.button("Удалить", {variant: "danger", action: `delete-${type}`, id}) : ""}${ctx.ui.button("Сохранить", {variant: "primary", action: `save-${type}`, id: id || ""})}`;
}

async function handleDrawerClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const id = Number(button.dataset.id) || null;
    if (button.dataset.action === "cancel") ctx.closeDrawer();
    if (button.dataset.action === "save-window") await saveWindow(id);
    if (button.dataset.action === "delete-window") await deleteWindow(id);
    if (button.dataset.action === "save-operator") await saveOperator(id);
    if (button.dataset.action === "delete-operator") await deleteOperator(id);
}

async function saveWindow(id) {
    const data = Object.fromEntries(new FormData(document.getElementById("window-form")).entries());
    const name = data.name?.trim();
    if (!name) return ctx.toast("Введите название рабочего места", "error");
    if (!id) await ctx.api.json("/windows/", {method: "POST", body: {name}});
    else {
        await ctx.api.json(`/windows/${id}`, {method: "PATCH", body: {name}});
        await ctx.api.json(`/windows/${id}/status`, {method: "PATCH", body: {status: data.status}});
        const linked = services.filter(service => data[`service_${service.id}`]).map(service => ({service_id: service.id, priority: Math.max(1, Math.min(100, Number(data[`priority_${service.id}`]) || 1))}));
        await ctx.api.json(`/window-services/${id}`, {method: "PUT", body: {services: linked}});
    }
    await refresh("Рабочее место сохранено");
}

async function saveOperator(id) {
    const data = Object.fromEntries(new FormData(document.getElementById("operator-form")).entries());
    const name = data.name?.trim();
    const login = data.login?.trim();
    const password = data.password?.trim();
    if (!name || !login || (!id && !password)) return ctx.toast("Заполните имя, логин и пароль", "error");
    if (!id) await ctx.api.json("/operators/", {method: "POST", body: {name, login, password, window_id: null, auto_call_mode: data.auto_call_mode}});
    else {
        const current = operators.find(item => item.id === id);
        if (current && login !== current.login && !password) return ctx.toast("Для смены логина укажите новый пароль", "error");
        await ctx.api.json(`/operators/${id}`, {method: "PATCH", body: {name, auto_call_mode: data.auto_call_mode}});
        if (password) await ctx.api.json(`/operators/${id}/login`, {method: "PUT", body: {login, password}});
    }
    await refresh("Оператор сохранён");
}

async function refresh(message) {
    ctx.closeDrawer();
    await load();
    render();
    ctx.toast(message, "success");
}

async function deleteWindow(id) {
    if (operatorForWindow(id)) return ctx.toast("Сначала снимите оператора с рабочего места", "error");
    if ((windowServices.get(id) || []).length) return ctx.toast("Сначала удалите услуги рабочего места", "error");
    const item = windows.find(windowItem => windowItem.id === id);
    if (!ctx.ui.confirmAction(`Удалить рабочее место «${item?.name || ""}»?`)) return;
    await ctx.api.request(`/windows/${id}`, {method: "DELETE"});
    await refresh("Рабочее место удалено");
}

async function deleteOperator(id) {
    const item = operators.find(operator => operator.id === id);
    if (!ctx.ui.confirmAction(`Удалить оператора ${item?.name || ""}? История обслуживания сохранится.`)) return;
    await ctx.api.request(`/operators/${id}`, {method: "DELETE"});
    await refresh("Оператор удалён");
}
