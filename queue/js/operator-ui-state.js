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
        const waitingBeforeFinish = (
            button.id === "finish-btn" && isCalledTicketWaitActive()
        );
        button.disabled = !online || !hasTicket || busy || (
            button.id === "recall-btn" && recallCooldown
        ) || waitingBeforeFinish;
        button.classList.toggle(
            "current-ticket-action-inactive",
            waitingBeforeFinish
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
