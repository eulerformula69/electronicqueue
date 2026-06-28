export async function mount(ctx) {
    window.open(CONFIG.GRAFANA_URL, "_blank", "noopener,noreferrer");
    ctx.view.innerHTML = `
        <div class="admin-loading">Переход в Grafana...</div>
    `;
}
