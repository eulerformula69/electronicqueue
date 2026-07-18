const activeOperatorRequests = new Set();

function beginOperatorRequest(key) {
    if (activeOperatorRequests.size > 0) return false;
    activeOperatorRequests.add(key);
    refreshOperatorUiState();
    return true;
}

function endOperatorRequest(key) {
    activeOperatorRequests.delete(key);
    refreshOperatorUiState();
}

function refreshOperatorUiState() {
    const online = currentWindowStatus === "online";
    const hasTicket = Boolean(currentTicketId);
    const busy = activeOperatorRequests.size > 0;

    document.querySelectorAll("[data-call-action]").forEach(button => {
        button.disabled = !online || hasTicket || busy;
    });
    document.querySelectorAll("[data-current-ticket-action]").forEach(button => {
        button.disabled = !online || !hasTicket || busy || (
            button.id === "recall-btn" && recallCooldown
        );
    });
    document.querySelectorAll(".queue-resume-btn").forEach(button => {
        button.disabled = !online || hasTicket || busy;
    });

    const displayZone = document.querySelector(".display-zone");
    if (displayZone) {
        displayZone.classList.toggle("current-ticket-actions-inactive", !hasTicket);
        displayZone.classList.toggle("operator-work-disabled", !online);
        displayZone.dataset.ticketStatus = currentTicketStatus || "none";
    }

    const autoCallNow = document.getElementById("auto-call-now-btn");
    const autoCallDecline = document.getElementById("auto-call-decline-btn");
    const autoCallInteractive = online && !hasTicket && !busy && operatorSettings.auto_call_enabled;
    if (autoCallNow) autoCallNow.disabled = !autoCallInteractive;
    if (autoCallDecline) autoCallDecline.disabled = !autoCallInteractive || !autoCallTimer;
}
