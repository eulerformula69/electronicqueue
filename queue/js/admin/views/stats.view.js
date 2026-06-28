export async function mount(ctx) {
    window.location.href = CONFIG.GRAFANA_URL;
    ctx.view.innerHTML = `
        <div class="admin-loading">Переход в Grafana...</div>
    `;
}
