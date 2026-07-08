const OperatorQueueSections = (() => {
    const deferReasons = [
        { value: "fills_documents", label: "Заполняет документы" },
        { value: "pays", label: "Оплачивает" },
        { value: "went_for_documents", label: "Пошёл за документами" },
        { value: "missing_document", label: "Нет нужного документа" },
        { value: "other", label: "Другое" }
    ];
    const cancelReasons = [
        { value: "no_show", label: "Клиент не явился" },
        { value: "refused_service", label: "Отказался от услуги" },
        { value: "wrong_ticket", label: "Ошибочный талон" },
        { value: "missing_document", label: "Нет нужного документа" },
        { value: "other", label: "Другое" }
    ];
    const sectionLabels = {
        waiting: "Ожидающие",
        deferred: "Отложенные",
        cancelled: "Отменённые",
        served: "Обслуженные"
    };
    const statusLabels = {
        waiting: "Ожидает",
        called: "В обслуживании",
        deferred: "Отложен",
        cancelled: "Отменён",
        finished: "Завершён"
    };
    const completionReasonLabels = {
        completed: "Обслужен",
        redirected: "Перенаправлен",
        cancelled: "Отменён"
    };

    let selectedSection = "waiting";
    let sections = {
        waiting: [],
        deferred: [],
        cancelled: [],
        served: []
    };

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function deferReasonLabel(reason) {
        return deferReasons.find(item => item.value === reason)?.label
            || cancelReasons.find(item => item.value === reason)?.label
            || completionReasonLabels[reason]
            || reason
            || "";
    }

    function ticketStatusLabel(ticket) {
        if (ticket.status === "finished" && ticket.completion_reason) {
            return completionReasonLabels[ticket.completion_reason] || "Завершён";
        }
        return statusLabels[ticket.status] || ticket.status || "—";
    }

    function ticketMainTime(ticket, section) {
        if (section === "deferred") return ticket.deferred_at || ticket.called_at || ticket.created_at;
        if (section === "served" || section === "cancelled") return ticket.finished_at || ticket.called_at || ticket.created_at;
        return ticket.called_at || ticket.created_at;
    }

    function countsFromSections() {
        return {
            waiting: sections.waiting.length,
            deferred: sections.deferred.length,
            cancelled: sections.cancelled.length,
            served: sections.served.length
        };
    }

    function updateTabs(counts = countsFromSections()) {
        Object.keys(sectionLabels).forEach(section => {
            const counter = document.getElementById(`queue-count-${section}`);
            if (counter) counter.textContent = counts[section] ?? 0;

            const button = document.querySelector(`.queue-column[data-section="${section}"]`);
            if (button) button.classList.toggle("active", section === selectedSection);
        });
    }

    function render() {
        const panel = document.getElementById("queue-list");
        if (!panel) return;

        const tickets = sections[selectedSection] || [];
        if (!tickets.length) {
            const label = sectionLabels[selectedSection] || "Список";
            panel.innerHTML = `<div style='color:var(--text-muted); padding:20px;'>${label}: нет талонов</div>`;
            return;
        }

        panel.innerHTML = tickets.map(ticket => {
            const reason = deferReasonLabel(ticket.defer_reason || ticket.cancel_reason || ticket.completion_reason || ticket.reason);
            const canResume = selectedSection === "deferred";
            const redirected = Boolean(ticket.is_redirected_to_window);
            return `
                <div class="queue-item queue-detail-item ${redirected ? "queue-item-redirected" : ""}">
                    <div class="queue-detail-head">
                        <span>№ ${escapeHtml(ticket.number)}</span>
                        <span>${escapeHtml(ticketMainTime(ticket, selectedSection) || "—")}</span>
                    </div>
                    <div class="queue-service-name">${escapeHtml(ticket.service_name || "Услуга не указана")}</div>
                    <div class="queue-detail-meta">
                        <span>${escapeHtml(ticketStatusLabel(ticket))}</span>
                        <span>Создан: ${escapeHtml(ticket.created_at || "—")}</span>
                        ${ticket.called_at ? `<span>Вызван: ${escapeHtml(ticket.called_at)}</span>` : ""}
                        ${ticket.finished_at ? `<span>Завершён: ${escapeHtml(ticket.finished_at)}</span>` : ""}
                        ${reason ? `<span>Причина: ${escapeHtml(reason)}</span>` : ""}
                    </div>
                    ${redirected ? '<div class="redirect-badge">Перенаправлено</div>' : ''}
                    ${canResume ? `<button class="btn-primary queue-resume-btn" type="button" onclick="resumeDeferredTicket(${Number(ticket.id)})">Вернуть в обслуживание</button>` : ""}
                </div>
            `;
        }).join("");
    }

    function select(section) {
        if (!sectionLabels[section]) return;
        selectedSection = section;
        updateTabs();
        render();
    }

    function setSections(nextSections, counts) {
        sections = nextSections || sections;
        updateTabs(counts || countsFromSections());
        render();
    }

    function selectDeferred() {
        selectedSection = "deferred";
    }

    return {
        deferReasons,
        cancelReasons,
        select,
        selectDeferred,
        setSections
    };
})();

function selectQueueSection(section) {
    OperatorQueueSections.select(section);
}
