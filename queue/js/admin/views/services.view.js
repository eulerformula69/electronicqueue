let ctx;
let services = [];
let groups = [];
let draggedServiceId = null;
let sortState = {key: "name", direction: "asc"};

const statusOptions = [
    {value: "active", label: "active"},
    {value: "inactive", label: "inactive"}
];

export async function mount(context) {
    ctx = context;
    await load();
    render();
}

async function load() {
    const [serviceData, groupData] = await Promise.all([
        ctx.api.request("/services?limit=500&include_hidden=true"),
        ctx.api.request("/service-groups/")
    ]);
    services = Array.isArray(serviceData) ? serviceData : [];
    groups = Array.isArray(groupData) ? groupData : [];
}

function render() {
    const activeCount = services.filter(item => item.status === "active").length;
    const inactiveCount = services.filter(item => item.status !== "active").length;
    const hiddenCount = services.filter(item => !item.visible_on_terminal).length;

    ctx.view.innerHTML = `
        <div class="admin-toolbar">
            ${ctx.ui.button("Добавить услугу", {variant: "primary", action: "create-service"})}
            <div class="admin-inline-form admin-service-group-create">
                ${ctx.ui.input("inline_group_name", "", "placeholder=\"Название группы\"")}
                ${ctx.ui.button("Добавить группу", {variant: "secondary", action: "add-inline-group"})}
            </div>
        </div>
        <div class="admin-stats-grid">
            ${ctx.ui.statCard("Всего услуг", services.length, "blue")}
            ${ctx.ui.statCard("Активных", activeCount, "green")}
            ${ctx.ui.statCard("Отключенных", inactiveCount, "red")}
            ${ctx.ui.statCard("Скрытых", hiddenCount, "orange")}
        </div>
        <section class="admin-service-board">
            ${renderGroupSections()}
        </section>
    `;

    ctx.view.onclick = handleClick;
    ctx.view.ondragstart = handleDragStart;
    ctx.view.ondragover = handleDragOver;
    ctx.view.ondrop = handleDrop;
    ctx.view.ondragend = handleDragEnd;
}

function renderGroupSections() {
    const sections = [
        ...groups.map(group => ({
            id: group.id,
            name: group.name,
            isSystem: false,
            items: sortServices(services.filter(service => service.service_group_id === group.id))
        })),
        {
            id: "",
            name: "Без группы",
            isSystem: true,
            items: sortServices(services.filter(service => service.service_group_id === null || service.service_group_id === undefined))
        }
    ];

    return sections.map((section, index) => `
        <article class="admin-service-group" data-group-id="${section.id}">
            <header class="admin-service-group-header">
                <div>
                    <h2>${ctx.ui.escapeHtml(section.name)}</h2>
                    <span>${section.items.length} услуг</span>
                </div>
                ${section.isSystem ? "" : `
                    <div class="admin-service-group-actions">
                        ${ctx.ui.button("↑", {variant: "icon", action: "group-up", id: section.id, disabled: index === 0, title: "Группу выше"})}
                        ${ctx.ui.button("↓", {variant: "icon", action: "group-down", id: section.id, disabled: index === groups.length - 1, title: "Группу ниже"})}
                        ${ctx.ui.button("Имя", {variant: "secondary", action: "rename-group", id: section.id})}
                        ${ctx.ui.button("Удалить", {variant: "danger", action: "delete-group", id: section.id})}
                    </div>
                `}
            </header>
            ${renderServiceSortHeader()}
            <div class="admin-service-dropzone" data-group-id="${section.id}">
                ${section.items.length ? section.items.map(renderServiceCard).join("") : `
                    <div class="admin-service-empty">Перетащите сюда услугу</div>
                `}
            </div>
        </article>
    `).join("");
}

function renderServiceSortHeader() {
    return `
        <div class="admin-service-sort-row">
            <span></span>
            ${renderServiceSortButton("Название", "name")}
            ${renderServiceSortButton("Статус", "status")}
            ${renderServiceSortButton("Терминал", "visible")}
            ${renderServiceSortButton("Выбор", "choice")}
            <span></span>
        </div>
    `;
}

function renderServiceSortButton(label, key) {
    const direction = sortState.key === key ? sortState.direction : null;
    return `
        <button class="admin-sort-header" type="button" data-action="sort" data-sort-key="${ctx.ui.escapeHtml(key)}">
            <span>${ctx.ui.escapeHtml(label)}</span>
            <span class="admin-sort-indicator" aria-hidden="true">${direction === "asc" ? "↑" : direction === "desc" ? "↓" : ""}</span>
        </button>
    `;
}

function renderServiceCard(service) {
    return `
        <div class="admin-service-item" draggable="true" data-service-id="${service.id}">
            <span class="admin-drag-handle" title="Перетащить">☰</span>
            <strong>${ctx.ui.escapeHtml(service.name)}</strong>
            ${ctx.ui.badge(service.status, service.status === "active" ? "success" : "neutral")}
            ${service.visible_on_terminal ? ctx.ui.badge("Показывается", "success") : ctx.ui.badge("Скрыта", "warning")}
            <span>${service.operator_choice_enabled ? "Выбор: да" : "Выбор: нет"}</span>
            <span class="admin-service-actions">${ctx.ui.button("Редактировать", {variant: "link", action: "edit", id: service.id})}</span>
        </div>
    `;
}

async function handleClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    if (button.dataset.action === "sort") {
        setSort(button.dataset.sortKey);
        render();
        return;
    }
    const id = Number(button.dataset.id);

    if (button.dataset.action === "create-service") openServiceDrawer();
    if (button.dataset.action === "add-inline-group") await addInlineGroup();
    if (button.dataset.action === "edit") openServiceDrawer(services.find(item => item.id === id));
    if (button.dataset.action === "rename-group") await renameGroup(id);
    if (button.dataset.action === "delete-group") await deleteGroup(id);
    if (button.dataset.action === "group-up") await moveGroup(id, -1);
    if (button.dataset.action === "group-down") await moveGroup(id, 1);
}

function setSort(key) {
    sortState = {
        key,
        direction: sortState.key === key && sortState.direction === "asc" ? "desc" : "asc"
    };
}

function sortServices(items) {
    return [...items].sort((a, b) => {
        const result = compareValues(serviceSortValue(a, sortState.key), serviceSortValue(b, sortState.key));
        return sortState.direction === "asc" ? result : -result;
    });
}

function serviceSortValue(service, key) {
    if (key === "status") return service.status || "";
    if (key === "visible") return service.visible_on_terminal ? 1 : 0;
    if (key === "choice") return service.operator_choice_enabled ? 1 : 0;
    return service.name || "";
}

function compareValues(a, b) {
    if (typeof a === "number" && typeof b === "number") return a - b;
    return String(a ?? "").localeCompare(String(b ?? ""), "ru", {numeric: true, sensitivity: "base"});
}

function groupOptions(selectedId) {
    return [
        {value: "", label: "Без группы"},
        ...groups.map(group => ({value: group.id, label: group.name}))
    ];
}

function openServiceDrawer(service = null) {
    const isEdit = Boolean(service);
    ctx.openDrawer(isEdit ? "Редактирование услуги" : "Новая услуга", `
        <form id="service-form" class="admin-form">
            ${ctx.ui.field("Название", ctx.ui.input("name", service?.name || "", "required"))}
            ${ctx.ui.field("Группа", ctx.ui.select("service_group_id", groupOptions(service?.service_group_id), service?.service_group_id ?? ""))}
            ${isEdit ? ctx.ui.field("Статус", ctx.ui.select("status", statusOptions, service.status)) : ""}
            ${ctx.ui.field("Показывать на терминале", ctx.ui.switchField("visible_on_terminal", service?.visible_on_terminal ?? true))}
            ${ctx.ui.field("Выбор оператора", ctx.ui.switchField("operator_choice_enabled", service?.operator_choice_enabled ?? false))}
        </form>
    `, {
        footer: `
            ${ctx.ui.button("Отмена", {variant: "secondary", action: "close-service"})}
            ${isEdit ? ctx.ui.button("Удалить", {variant: "danger", action: "delete-service", id: service.id}) : ""}
            ${ctx.ui.button("Сохранить", {variant: "primary", action: "save-service", id: service?.id ?? ""})}
        `
    });

    document.getElementById("admin-drawer").onclick = handleDrawerClick;
}

async function handleDrawerClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    const id = Number(button.dataset.id);

    if (action === "close-service") ctx.closeDrawer();
    if (action === "save-service") await saveService(id || null);
    if (action === "delete-service") await deleteService(id);
}

async function saveService(id) {
    const form = document.getElementById("service-form");
    const data = Object.fromEntries(new FormData(form).entries());
    const name = data.name?.trim();
    if (!name) return ctx.toast("Введите название услуги", "error");
    const service_group_id = data.service_group_id ? Number(data.service_group_id) : null;

    if (!id) {
        await ctx.api.json("/services", {
            method: "POST",
            body: {name, operator_choice_enabled: Boolean(data.operator_choice_enabled), service_group_id}
        });
    } else {
        await ctx.api.json(`/services/${id}`, {method: "PATCH", body: {name}});
        await ctx.api.json(`/services/${id}/group`, {method: "PATCH", body: {service_group_id}});
        await ctx.api.json(`/services/${id}/status`, {method: "PATCH", body: {status: data.status}});
        await ctx.api.json(`/services/${id}/terminal-visibility`, {method: "PATCH", body: {visible_on_terminal: Boolean(data.visible_on_terminal)}});
        await ctx.api.json(`/services/${id}/operator-choice`, {method: "PATCH", body: {operator_choice_enabled: Boolean(data.operator_choice_enabled)}});
    }

    ctx.closeDrawer();
    await load();
    render();
    ctx.toast("Услуга сохранена", "success");
}

async function deleteService(id) {
    if (!ctx.ui.confirmAction("Удалить услугу? Если по ней уже есть билеты, она будет скрыта, история сохранится.")) return;
    const data = await ctx.api.request(`/services/${id}`, {method: "DELETE"});
    if (data.message) ctx.toast(data.message, "info");
    ctx.closeDrawer();
    await load();
    render();
}

async function addInlineGroup() {
    const input = ctx.view.querySelector('[name="inline_group_name"]');
    const name = input.value.trim();
    if (!name) return;
    await ctx.api.json("/service-groups", {method: "POST", body: {name}});
    await load();
    render();
}

async function renameGroup(id) {
    const group = groups.find(item => item.id === id);
    const name = prompt("Название группы", group?.name || "")?.trim();
    if (!name) return;
    await ctx.api.json(`/service-groups/${id}`, {method: "PATCH", body: {name}});
    await load();
    render();
}

async function deleteGroup(id) {
    if (!ctx.ui.confirmAction("Удалить группу? Услуги останутся без группы.")) return;
    await ctx.api.request(`/service-groups/${id}`, {method: "DELETE"});
    await load();
    render();
}

async function moveGroup(id, direction) {
    const index = groups.findIndex(item => item.id === id);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= groups.length) return;
    const reordered = [...groups];
    [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
    await ctx.api.json("/service-groups/order", {method: "PUT", body: {group_ids: reordered.map(item => item.id)}});
    await load();
    render();
}

function handleDragStart(event) {
    const item = event.target.closest(".admin-service-item");
    if (!item) return;
    draggedServiceId = Number(item.dataset.serviceId);
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(draggedServiceId));
    item.classList.add("dragging");
}

function handleDragOver(event) {
    const dropzone = event.target.closest(".admin-service-dropzone");
    if (!dropzone || !draggedServiceId) return;
    event.preventDefault();
    const dragged = ctx.view.querySelector(`.admin-service-item[data-service-id="${draggedServiceId}"]`);
    if (!dragged) return;
    const afterElement = getDragAfterElement(dropzone, event.clientY);
    if (afterElement) {
        dropzone.insertBefore(dragged, afterElement);
    } else {
        dropzone.appendChild(dragged);
    }
}

async function handleDrop(event) {
    const dropzone = event.target.closest(".admin-service-dropzone");
    if (!dropzone || !draggedServiceId) return;
    event.preventDefault();
    await persistDraggedOrder();
}

function handleDragEnd() {
    ctx.view.querySelectorAll(".admin-service-item.dragging").forEach(item => item.classList.remove("dragging"));
    draggedServiceId = null;
}

function getDragAfterElement(container, y) {
    const elements = [...container.querySelectorAll(".admin-service-item:not(.dragging)")];
    return elements.reduce((closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) {
            return {offset, element: child};
        }
        return closest;
    }, {offset: Number.NEGATIVE_INFINITY, element: null}).element;
}

async function persistDraggedOrder() {
    const groupUpdates = [];
    const orderedIds = [];

    ctx.view.querySelectorAll(".admin-service-group").forEach(groupEl => {
        const groupValue = groupEl.dataset.groupId;
        const groupId = groupValue ? Number(groupValue) : null;
        groupEl.querySelectorAll(".admin-service-item").forEach(item => {
            const serviceId = Number(item.dataset.serviceId);
            orderedIds.push(serviceId);
            const service = services.find(current => current.id === serviceId);
            if (service && (service.service_group_id ?? null) !== groupId) {
                groupUpdates.push(ctx.api.json(`/services/${serviceId}/group`, {
                    method: "PATCH",
                    body: {service_group_id: groupId}
                }));
            }
        });
    });

    if (orderedIds.length !== services.length) {
        await load();
        render();
        return;
    }

    await Promise.all(groupUpdates);
    await ctx.api.json("/services/order", {method: "PUT", body: {service_ids: orderedIds}});
    await load();
    render();
    ctx.toast("Порядок услуг сохранён", "success");
}
