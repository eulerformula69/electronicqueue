let calledTicketTimerInterval = null;
let recallCooldownInterval = null;
const RECALL_COOLDOWN_SECONDS = 10;

function normalizeCalledTicketMinWait(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds)) return 180;
    return Math.max(0, Math.min(3600, Math.trunc(seconds)));
}

function formatTicketDuration(totalSeconds) {
    const safeSeconds = Math.max(0, Math.floor(totalSeconds));
    const hours = Math.floor(safeSeconds / 3600);
    const minutes = Math.floor((safeSeconds % 3600) / 60);
    const seconds = safeSeconds % 60;
    const clock = [minutes, seconds]
        .map(value => String(value).padStart(2, "0"))
        .join(":");
    return hours > 0 ? `${String(hours).padStart(2, "0")}:${clock}` : clock;
}

function calledTicketWaitRemainingSeconds(nowMs = Date.now()) {
    if (!currentTicketId || !currentTicketCalledAt) return 0;
    const waitSeconds = normalizeCalledTicketMinWait(
        operatorSettings.called_ticket_min_wait_seconds
    );
    const availableAt = currentTicketCalledAt.getTime() + waitSeconds * 1000;
    return Math.max(0, Math.ceil((availableAt - nowMs) / 1000));
}

function isCalledTicketWaitActive() {
    return calledTicketWaitRemainingSeconds() > 0;
}

function updateCalledTicketTimers() {
    const finishButton = document.getElementById("finish-btn");
    const serviceTimerContainer = document.getElementById("service-timer");
    const serviceTimer = document.getElementById("service-timer-value");
    const hasServerStartTime = Boolean(currentTicketId && currentTicketCalledAt);

    if (serviceTimerContainer) {
        serviceTimerContainer.hidden = !hasServerStartTime;
    }

    if (serviceTimer) {
        const elapsedSeconds = hasServerStartTime
            ? (Date.now() - currentTicketCalledAt.getTime()) / 1000
            : 0;
        serviceTimer.textContent = formatTicketDuration(elapsedSeconds);
    }

    if (finishButton) {
        const remaining = calledTicketWaitRemainingSeconds();
        finishButton.textContent = remaining > 0
            ? `ЗАВЕРШИТЬ (ЧЕРЕЗ ${formatTicketDuration(remaining)})`
            : "ЗАВЕРШИТЬ";
    }

    refreshOperatorUiState();
}

function syncCalledTicketTimers() {
    if (calledTicketTimerInterval) {
        clearInterval(calledTicketTimerInterval);
        calledTicketTimerInterval = null;
    }
    updateCalledTicketTimers();
    if (currentTicketId && currentTicketCalledAt) {
        calledTicketTimerInterval = setInterval(updateCalledTicketTimers, 1000);
    }
}

function recallCooldownRemainingSeconds(nowMs = Date.now()) {
    if (!currentTicketId) return 0;
    const callTimes = [currentTicketCalledAt, currentTicketLastRecalledAt]
        .filter(Boolean)
        .map(value => value.getTime());
    const latestCallAtMs = callTimes.length ? Math.max(...callTimes) : null;
    if (latestCallAtMs === null) return 0;
    const availableAt = latestCallAtMs + RECALL_COOLDOWN_SECONDS * 1000;
    return Math.max(0, Math.ceil((availableAt - nowMs) / 1000));
}

function updateRecallCooldown() {
    const button = document.getElementById("recall-btn");
    const remaining = recallCooldownRemainingSeconds();
    recallCooldown = remaining > 0;
    if (button) {
        button.textContent = recallCooldown
            ? `Повтор через ${remaining}с`
            : "ПОВТОРИТЬ ВЫЗОВ";
    }
    refreshOperatorUiState();
    if (!recallCooldown && recallCooldownInterval) {
        clearInterval(recallCooldownInterval);
        recallCooldownInterval = null;
    }
}

function syncRecallCooldown() {
    if (recallCooldownInterval) {
        clearInterval(recallCooldownInterval);
        recallCooldownInterval = null;
    }
    updateRecallCooldown();
    if (recallCooldown) {
        recallCooldownInterval = setInterval(updateRecallCooldown, 250);
    }
}
