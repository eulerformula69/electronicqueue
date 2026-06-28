let ctx;
let mediaProcessingWatchActive = false;
let mediaLastUploadMessage = "";

export async function mount(context) {
    ctx = context;
    await render();
}

async function render() {
    const data = await ctx.api.request("/admin/media/files");
    const items = data.items || (data.files || []).map(filename => ({filename, status: "ready"}));
    const playlist = data.playlist || [];
    const hasProcessing = items.some(item => item.status === "pending" || item.status === "processing");

    if (mediaProcessingWatchActive && !hasProcessing) {
        mediaLastUploadMessage = "Обработка завершена. Файл готов.";
        mediaProcessingWatchActive = false;
    }

    const rows = items.map(item => {
        const webPath = `/queue/media/${item.filename}`;
        const included = playlist.includes(webPath);
        const ready = (item.status || "ready") === "ready";
        return `
            <tr>
                <td><strong>${ctx.ui.escapeHtml(item.filename)}</strong>${item.compression_label ? `<small>${ctx.ui.escapeHtml(item.compression_label)}</small>` : ""}</td>
                <td>${ctx.ui.badge(statusText(item, included), statusTone(item.status, included))}</td>
                <td>
                    ${ready ? `<a class="admin-btn admin-btn-secondary" href="${ctx.ui.escapeHtml(webPath)}" target="_blank" rel="noopener">Предпросмотр</a>` : ""}
                    ${ready ? ctx.ui.button(included ? "Исключить" : "Включить", {variant: included ? "secondary" : "primary", action: "toggle", id: item.filename}) : ""}
                    ${item.status === "error" && item.job_id ? ctx.ui.button("Повторить", {variant: "secondary", action: "retry", id: item.job_id}) : ""}
                    ${ready ? ctx.ui.button("Удалить", {variant: "danger", action: "delete", id: item.filename}) : ""}
                </td>
            </tr>
        `;
    });

    ctx.view.innerHTML = `
        <div class="admin-toolbar">
            <form id="media-upload-form" class="admin-upload-form">
                <label class="admin-file-picker">
                    <input class="admin-file-input" type="file" name="file" accept=".mp4,.webm,.mov,.mkv,.avi,.m4v,.wmv,.mpg,.mpeg,.3gp,video/*">
                    <span class="admin-btn admin-btn-secondary">Выбрать файл</span>
                    <span class="admin-file-name" data-file-name>Файл не выбран</span>
                </label>
                <label class="admin-checkbox"><input type="checkbox" name="process_video" checked> Обрабатывать видео</label>
                <select class="admin-input" name="compression_mode">
                    <option value="normal" selected>Обычное качество</option>
                    <option value="high">Высокое качество</option>
                    <option value="compact">Максимальное сжатие</option>
                </select>
                ${ctx.ui.button("Загрузить файл", {variant: "primary", action: "upload"})}
            </form>
            <div id="uploadStatus" class="admin-upload-status">${ctx.ui.escapeHtml(mediaLastUploadMessage)}</div>
        </div>
        ${ctx.ui.table(["Файл", "Статус", "Действия"], rows)}
    `;

    ctx.view.onclick = handleClick;
    ctx.view.onchange = event => {
        if (event.target.name === "file") {
            updateSelectedFileName(event.target);
        }
        if (event.target.name === "process_video") {
            document.querySelector('[name="compression_mode"]').disabled = !event.target.checked;
        }
    };

    if (hasProcessing) {
        setTimeout(() => {
            if (location.hash === "#media") render();
        }, 5000);
    }
}

function updateSelectedFileName(input) {
    const label = input.closest(".admin-file-picker");
    const fileName = label?.querySelector("[data-file-name]");
    if (!fileName) return;
    fileName.textContent = input.files[0]?.name || "Файл не выбран";
}

function statusText(item, included) {
    if (item.status === "pending") return "Ожидает обработки";
    if (item.status === "processing") return "Обработка";
    if (item.status === "error") return `Ошибка${item.error ? `: ${item.error}` : ""}`;
    return included ? "В плейлисте" : "Исключен";
}

function statusTone(status, included) {
    if (status === "pending" || status === "processing") return "warning";
    if (status === "error") return "danger";
    return included ? "success" : "neutral";
}

async function handleClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    const id = button.dataset.id;
    if (action === "upload") await upload();
    if (action === "toggle") await toggle(id);
    if (action === "delete") await deleteFile(id);
    if (action === "retry") await retry(id);
}

async function upload() {
    const form = document.getElementById("media-upload-form");
    const file = form.elements.file.files[0];
    const status = document.getElementById("uploadStatus");
    if (!file) return ctx.toast("Выберите файл", "error");
    if (file.size > 300 * 1024 * 1024) return ctx.toast("Файл слишком большой (> 300MB)", "error");

    const payload = new FormData();
    payload.append("file", file);
    payload.append("process_video", form.elements.process_video.checked ? "true" : "false");
    payload.append("compression_mode", form.elements.compression_mode.value || "normal");
    status.textContent = "Загрузка...";

    const response = await ctx.api.formData("/admin/media/upload", payload, {method: "POST"});
    if (response.status === "ready") {
        mediaLastUploadMessage = "Загружено без обработки. Файл готов.";
        mediaProcessingWatchActive = false;
    } else {
        mediaLastUploadMessage = "Загружено. Видео обрабатывается...";
        mediaProcessingWatchActive = true;
    }
    await render();
}

async function toggle(filename) {
    const data = await ctx.api.request("/admin/media/files");
    const playlist = data.playlist || [];
    const path = `/queue/media/${filename}`;
    await ctx.api.json("/admin/media/playlist", {
        method: "POST",
        body: {path, action: playlist.includes(path) ? "delete" : "add"}
    });
    await render();
}

async function deleteFile(filename) {
    if (!ctx.ui.confirmAction(`Удалить файл ${filename} с сервера навсегда?`)) return;
    await ctx.api.request(`/admin/media/file/${encodeURIComponent(filename)}`, {method: "DELETE"});
    await render();
}

async function retry(jobId) {
    await ctx.api.request(`/admin/media/job/${encodeURIComponent(jobId)}/retry`, {method: "POST"});
    await render();
}
