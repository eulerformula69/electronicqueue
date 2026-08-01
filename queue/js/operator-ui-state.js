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

    const statusToggle = document.getElementById("window-status-toggle");
    if (statusToggle) statusToggle.disabled = busy;

    document.querySelectorAll("[data-call-action]").forEach(button => {
        button.disabled = !online || hasTicket || busy;
    });
    document.querySelectorAll("[data-current-ticket-action]").forEach(button => {
        const waitingBeforeFinish = (
            button.id === "finish-btn" && isCalledTicketWaitActive()
        );
        const waitingBeforeRecall = button.id === "recall-btn" && recallCooldown;
        button.disabled = !online || !hasTicket || busy || (
            waitingBeforeRecall
        ) || waitingBeforeFinish;
        button.classList.toggle(
            "current-ticket-action-inactive",
            waitingBeforeFinish || waitingBeforeRecall
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

}
