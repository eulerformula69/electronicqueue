function closeReprintTicketPanel() {
    const panel = document.getElementById("terminal-reprint-panel");
    if (panel) panel.remove();

    const actions = document.querySelector("#terminal-service-overlay .terminal-service-actions");
    if (actions) actions.style.display = "";
}

function openReprintTicketPanel() {
    const overlay = document.getElementById("terminal-service-overlay");
    if (!overlay) return;

    const actions = overlay.querySelector(".terminal-service-actions");
    const modal = overlay.querySelector(".terminal-service-modal");
    if (!actions || !modal) return;

    actions.style.display = "none";
    closeReprintTicketPanel();
    actions.style.display = "none";

    const panel = document.createElement("div");
    panel.id = "terminal-reprint-panel";
    panel.style.display = "grid";
    panel.style.gap = "12px";
    panel.innerHTML = `
        <input
            id="terminal-reprint-number"
            type="number"
            min="1"
            step="1"
            inputmode="numeric"
            autocomplete="off"
            placeholder="\u041d\u043e\u043c\u0435\u0440 \u0442\u0430\u043b\u043e\u043d\u0430"
            style="font-size:1.1rem; padding:14px 16px; border:2px solid #e2e8f0; border-radius:10px;"
        >
        <div id="terminal-reprint-error" style="min-height:22px; color:#dc3545; font-weight:700;"></div>
        <div class="terminal-service-actions">
            <button type="button" class="terminal-reprint-submit">\u041f\u0435\u0447\u0430\u0442\u044c</button>
            <button type="button" class="terminal-service-cancel terminal-reprint-cancel">\u041d\u0430\u0437\u0430\u0434</button>
        </div>
    `;

    panel.querySelector(".terminal-reprint-submit").addEventListener("click", reprintIssuedTicket);
    panel.querySelector(".terminal-reprint-cancel").addEventListener("click", closeReprintTicketPanel);
    panel.querySelector("#terminal-reprint-number").addEventListener("keydown", (event) => {
        if (event.key === "Enter") reprintIssuedTicket();
    });

    modal.appendChild(panel);
    panel.querySelector("#terminal-reprint-number").focus();
}

async function reprintIssuedTicket() {
    const input = document.getElementById("terminal-reprint-number");
    const errorEl = document.getElementById("terminal-reprint-error");
    const submitBtn = document.querySelector("#terminal-reprint-panel .terminal-reprint-submit");
    const number = Number(input?.value);

    if (!Number.isInteger(number) || number <= 0) {
        errorEl.textContent = "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043f\u043e\u043b\u043e\u0436\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0439 \u043d\u043e\u043c\u0435\u0440 \u0442\u0430\u043b\u043e\u043d\u0430";
        return;
    }

    const currentSession = localStorage.getItem("session_id");
    if (!currentSession) {
        errorEl.textContent = "\u0421\u0435\u0441\u0441\u0438\u044f \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430";
        document.getElementById("terminal-auth-overlay").style.display = "flex";
        return;
    }

    errorEl.textContent = "";
    if (submitBtn) submitBtn.disabled = true;

    try {
        const response = await fetch(`${CONFIG.API_URL}/tickets/reprint/${number}`, {
            headers: { "session-id": currentSession }
        });
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            errorEl.textContent = data.detail || "\u0422\u0430\u043b\u043e\u043d \u0437\u0430 \u0441\u0435\u0433\u043e\u0434\u043d\u044f \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d";
            return;
        }

        fillTicketReceipt(data);
        printTicket();
        closeReprintTicketPanel();
        closeTerminalServiceModal();
        showNotice("\u0422\u0430\u043b\u043e\u043d \u043d\u0430\u043f\u0435\u0447\u0430\u0442\u0430\u043d \u043f\u043e\u0432\u0442\u043e\u0440\u043d\u043e", 3);
    } catch (error) {
        console.error("Reprint ticket error:", error);
        errorEl.textContent = "\u0421\u0431\u043e\u0439 \u0441\u0432\u044f\u0437\u0438 \u0441 \u0441\u0435\u0440\u0432\u0435\u0440\u043e\u043c";
    } finally {
        if (submitBtn) submitBtn.disabled = false;
    }
}
