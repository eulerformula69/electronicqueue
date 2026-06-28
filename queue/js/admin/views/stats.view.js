export async function mount(ctx) {
    ctx.view.innerHTML = `
        <div class="admin-card admin-empty-state">
            <h2>Статистика</h2>
            <p>Текущая статистика остаётся в Grafana. Логика не изменяется.</p>
            <a class="admin-btn admin-btn-primary" href="${ctx.ui.escapeHtml(CONFIG.GRAFANA_URL)}" target="_blank" rel="noopener noreferrer">
                Открыть статистику
            </a>
        </div>
    `;
}
