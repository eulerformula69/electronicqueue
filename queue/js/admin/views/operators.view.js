let ctx;
let operators = [];
let windows = [];

export async function mount(context) {
    ctx = context;
    await load();
    render();
}

async function load() {
    const [operatorData, windowData] = await Promise.all([
        ctx.api.request("/operators/"),
        ctx.api.request("/windows/")
    ]);
    operators = Array.isArray(operatorData) ? operatorData.sort((a, b) => a.id - b.id) : [];
    windows = Array.isArray(windowData) ? windowData : [];
}

function render() {
    const rows = operators.map(operator => `
        <tr>
            <td>${operator.id}</td>
            <td><strong>${ctx.ui.escapeHtml(operator.name)}</strong></td>
            <td>${ctx.ui.escapeHtml(operator.login || "-")}</td>
            <td>${ctx.ui.escapeHtml(windowName(operator.window_id))}</td>
            <td>${ctx.ui.button("Редактировать", {variant: "link", action: "edit", id: operator.id})}</td>
        </tr>
    `);

    ctx.view.innerHTML = `
        <div class="admin-toolbar">${ctx.ui.button("Добавить оператора", {variant: "primary", action: "create"})}</div>
        ${ctx.ui.table(["ID", "ФИО", "Логин", "Рабочее место", "Действия"], rows)}
    `;
    ctx.view.onclick = handleClick;
}

function handleClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    if (button.dataset.action === "create") openDrawer();
    if (button.dataset.action === "edit") openDrawer(operators.find(item => item.id === Number(button.dataset.id)));
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

function openDrawer(operator = null) {
    const isEdit = Boolean(operator);
    ctx.openDrawer(isEdit ? "Редактирование оператора" : "Новый оператор", `
        <form id="operator-form" class="admin-form">
            ${ctx.ui.field("ФИО", ctx.ui.input("name", operator?.name || "", "required"))}
            ${ctx.ui.field("Логин", ctx.ui.input("login", operator?.login || "", "required"))}
            ${ctx.ui.field("Пароль", ctx.ui.input("password", "", `${isEdit ? "placeholder=\"Оставьте пустым, чтобы не менять\"" : "required"} type="password"`))}
            ${ctx.ui.field("Рабочее место", ctx.ui.select("window_id", windowOptions(operator?.window_id), operator?.window_id ?? ""))}
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

    if (!name || !login || (!id && !password)) {
        ctx.toast("Заполните имя, логин и пароль", "error");
        return;
    }

    if (!id) {
        await ctx.api.json("/operators/", {method: "POST", body: {name, login, password, window_id}});
    } else {
        const current = operators.find(item => item.id === id);
        if (current && login !== current.login && !password) {
            ctx.toast("Для смены логина укажите новый пароль", "error");
            return;
        }
        await ctx.api.json(`/operators/${id}`, {method: "PATCH", body: {name, window_id}});
        if (password) {
            await ctx.api.json(`/operators/${id}/login`, {method: "PUT", body: {login, password}});
        }
    }

    ctx.closeDrawer();
    await load();
    render();
    ctx.toast("Оператор сохранён", "success");
}

async function deleteOperator(id) {
    if (!ctx.ui.confirmAction("Удалить оператора?")) return;
    await ctx.api.request(`/operators/${id}`, {method: "DELETE"});
    ctx.closeDrawer();
    await load();
    render();
}
