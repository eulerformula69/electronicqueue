let ctx;
let schedule;

const DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

export async function mount(context) {
    ctx = context;
    schedule = await ctx.api.request("/admin/close-day-schedule");
    render();
}

function render() {
    const selectedDays = new Set(schedule.weekdays || []);
    ctx.view.innerHTML = `
        <form id="close-day-schedule-form" class="admin-scheduler-form">
            <section class="admin-card admin-form admin-scheduler-card">
                <div class="admin-scheduler-heading">
                    <div>
                        <h2>Автоматическое закрытие смены</h2>
                        <p>Работает на сервере — держать админку открытой не нужно.</p>
                    </div>
                    <label class="admin-scheduler-enabled">
                        <span>Включено</span>
                        ${ctx.ui.switchField("enabled", schedule.enabled)}
                    </label>
                </div>

                <fieldset class="admin-scheduler-days">
                    <legend>Дни недели</legend>
                    <div>${DAYS.map((day, index) => `
                        <label class="admin-day-toggle">
                            <input type="checkbox" name="weekday" value="${index}" ${selectedDays.has(index) ? "checked" : ""}>
                            <span>${day}</span>
                        </label>`).join("")}</div>
                </fieldset>

                <div class="admin-scheduler-grid">
                    ${ctx.ui.field("Время закрытия (Иркутск)", ctx.ui.input("run_time", schedule.run_time, 'type="time" required'))}
                    ${ctx.ui.field("Статус операторов", ctx.ui.select("operator_action", [
                        {value: "offline", label: "Выход — офлайн и завершить сессии"},
                        {value: "offline_keep_session", label: "Офлайн — сессию оставить"},
                        {value: "break", label: "Перерыв — сессию оставить"}
                    ], schedule.operator_action))}
                    ${ctx.ui.field("Политика талонов", ctx.ui.select("ticket_action", [
                        {value: "cancel", label: "Отменить все открытые"},
                        {value: "finish", label: "Завершить обслуживаемые, остальные отменить"}
                    ], schedule.ticket_action))}
                </div>
                <div class="admin-scheduler-actions">
                    ${ctx.ui.button("Сохранить расписание", {variant: "primary", action: "save-schedule", type: "submit"})}
                </div>
            </section>
        </form>`;
    ctx.view.querySelector("form").addEventListener("submit", save);
}

async function save(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const weekdays = [...form.querySelectorAll('[name="weekday"]:checked')].map(input => Number(input.value));
    if (!weekdays.length) {
        ctx.toast("Выберите хотя бы один день недели", "error");
        return;
    }
    const submit = form.querySelector('[data-action="save-schedule"]');
    submit.disabled = true;
    try {
        schedule = await ctx.api.json("/admin/close-day-schedule", {
            method: "PUT",
            body: {
                enabled: form.elements.enabled.checked,
                weekdays,
                run_time: form.elements.run_time.value,
                operator_action: form.elements.operator_action.value,
                ticket_action: form.elements.ticket_action.value
            }
        });
        ctx.toast("Расписание сохранено", "success");
        render();
    } finally {
        submit.disabled = false;
    }
}
