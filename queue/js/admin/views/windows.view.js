let ctx;
let windows = [];
let services = [];
let windowServices = new Map();
let sortState = {key: "name", direction: "asc"};
const sortStorageKey = "admin.windows.sort";

const statuses = [
    {value: "online", label: "online"},
    {value: "break", label: "break"},
    {value: "offline", label: "offline"}
];

export async function mount(context) {
    ctx = context;
    sortState = loadSortState(sortState);
    await load();
    render();
}

async function load() {
    const [windowData, serviceData] = await Promise.all([
        ctx.api.request("/windows/"),
        ctx.api.request("/services/")
    ]);
    windows = Array.isArray(windowData) ? windowData : [];
    services = Array.isArray(serviceData) ? serviceData : [];
    windowServices = new Map();
    await Promise.all(windows.map(async windowItem => {
        const linked = await ctx.api.request(`/window-services/${windowItem.id}`);
        windowServices.set(windowItem.id, Array.isArray(linked) ? linked : []);
    }));
}

function render() {
    const rows = sortWindows(windows).map(windowItem => {
        const linked = windowServices.get(windowItem.id) || [];
        return `
            <tr>
                <td><strong>${ctx.ui.escapeHtml(windowItem.name)}</strong></td>
                <td>${ctx.ui.badge(windowItem.status, windowItem.status === "online" ? "success" : windowItem.status === "break" ? "warning" : "neutral")}</td>
                <td>${linked.length} услуг</td>
                <td>${ctx.ui.button("Редактировать", {variant: "link", action: "edit", id: windowItem.id})}</td>
            </tr>
        `;
    });

    ctx.view.innerHTML = `
        <div class="admin-toolbar">${ctx.ui.button("Добавить рабочее место", {variant: "primary", action: "create"})}</div>
        ${ctx.ui.table([
            ctx.ui.sortHeader("Название", "name", sortState),
            ctx.ui.sortHeader("Статус", "status", sortState),
            ctx.ui.sortHeader("Услуги", "services", sortState),
            "Действия"
        ], rows)}
    `;
    ctx.view.onclick = handleClick;
}

function handleClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    if (button.dataset.action === "sort") {
        setSort(button.dataset.sortKey);
        render();
        return;
    }
    if (button.dataset.action === "create") openDrawer();
    if (button.dataset.action === "edit") openDrawer(windows.find(item => item.id === Number(button.dataset.id)));
}

function setSort(key) {
    sortState = {
        key,
        direction: sortState.key === key && sortState.direction === "asc" ? "desc" : "asc"
    };
    saveSortState(sortState);
}

function sortWindows(items) {
    return [...items].sort((a, b) => {
        const result = compareValues(windowSortValue(a, sortState.key), windowSortValue(b, sortState.key));
        return sortState.direction === "asc" ? result : -result;
    });
}

function windowSortValue(windowItem, key) {
    if (key === "status") return windowItem.status || "";
    if (key === "services") return windowServices.get(windowItem.id)?.length || 0;
    return windowItem.name || "";
}

function compareValues(a, b) {
    if (typeof a === "number" && typeof b === "number") return a - b;
    return String(a ?? "").localeCompare(String(b ?? ""), "ru", {numeric: true, sensitivity: "base"});
}

function loadSortState(fallback) {
    try {
        const parsed = JSON.parse(localStorage.getItem(sortStorageKey) || "null");
        if (parsed && ["name", "status", "services"].includes(parsed.key) && ["asc", "desc"].includes(parsed.direction)) {
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

function openDrawer(windowItem = null) {
    const linked = windowItem ? windowServices.get(windowItem.id) || [] : [];
    const priorities = new Map(linked.map(item => [item.service_id, item.priority ?? 1]));
    ctx.openDrawer(windowItem ? "Редактирование рабочего места" : "Новое рабочее место", `
        <form id="window-form" class="admin-form">
            ${ctx.ui.field("Название", ctx.ui.input("name", windowItem?.name || "", "required"))}
            ${windowItem ? ctx.ui.field("Статус", ctx.ui.select("status", statuses, windowItem.status)) : ""}
            ${windowItem ? `
                <section class="admin-subsection">
                    <h3>Услуги</h3>
                    <p class="admin-muted">Меньшее число означает больший приоритет.</p>
                    <div class="admin-check-list">
                        ${services.map(service => {
                            const checked = priorities.has(service.id);
                            return `
                                <label class="admin-check-row">
                                    <input type="checkbox" name="service_${service.id}" ${checked ? "checked" : ""}>
                                    <span>${ctx.ui.escapeHtml(service.name)}</span>
                                    <input class="admin-input admin-priority-input" type="number" min="1" max="100" name="priority_${service.id}" value="${priorities.get(service.id) || 1}">
                                </label>
                            `;
                        }).join("")}
                    </div>
                </section>
            ` : ""}
        </form>
    `, {
        footer: `
            ${ctx.ui.button("Отмена", {variant: "secondary", action: "cancel"})}
            ${windowItem ? ctx.ui.button("Удалить", {variant: "danger", action: "delete", id: windowItem.id}) : ""}
            ${ctx.ui.button("Сохранить", {variant: "primary", action: "save", id: windowItem?.id ?? ""})}
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
    if (action === "save") await saveWindow(id || null);
    if (action === "delete") await deleteWindow(id);
}

async function saveWindow(id) {
    const form = document.getElementById("window-form");
    const data = Object.fromEntries(new FormData(form).entries());
    const name = data.name?.trim();
    if (!name) return ctx.toast("Введите название рабочего места", "error");

    if (!id) {
        await ctx.api.json("/windows/", {method: "POST", body: {name}});
    } else {
        await ctx.api.json(`/windows/${id}`, {method: "PATCH", body: {name}});
        await ctx.api.json(`/windows/${id}/status`, {method: "PATCH", body: {status: data.status}});
        const linked = services
            .filter(service => data[`service_${service.id}`])
            .map(service => ({
                service_id: service.id,
                priority: Math.max(1, Math.min(100, Number(data[`priority_${service.id}`]) || 1))
            }));
        await ctx.api.json(`/window-services/${id}`, {method: "PUT", body: {services: linked}});
    }

    ctx.closeDrawer();
    await load();
    render();
    ctx.toast("Рабочее место сохранено", "success");
}

async function deleteWindow(id) {
    const linked = await ctx.api.request(`/window-services/${id}`);
    if (Array.isArray(linked) && linked.length) {
        ctx.toast("Сначала удалите услуги, привязанные к рабочему месту", "error");
        return;
    }
    if (!ctx.ui.confirmAction("Удалить рабочее место?")) return;
    await ctx.api.request(`/windows/${id}`, {method: "DELETE"});
    ctx.closeDrawer();
    await load();
    render();
}
