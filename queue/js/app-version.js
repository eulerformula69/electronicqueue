(function () {
    const STORAGE_KEY = "operatorAppVersion";
    const CHECK_INTERVAL_MS = 60000;
    let checkInProgress = false;
    let pageVersion = null;

    function showUpdateNotification() {
        const notification = document.getElementById("app-update-notification");
        if (notification) {
            notification.style.display = "block";
        }
    }

    async function checkAppVersion() {
        if (checkInProgress || typeof CONFIG === "undefined") return;
        checkInProgress = true;

        try {
            const response = await fetch(`${CONFIG.API_URL}/system/version`, {
                cache: "no-store"
            });
            if (!response.ok) return;

            const data = await response.json();
            const currentVersion = String(data.version || "").trim();
            if (!currentVersion) return;

            if (!pageVersion) {
                pageVersion = currentVersion;
                localStorage.setItem(STORAGE_KEY, currentVersion);
                return;
            }

            if (pageVersion !== currentVersion) {
                showUpdateNotification();
                localStorage.setItem(STORAGE_KEY, currentVersion);
            }
        } catch (error) {
            console.debug("App version check error:", error);
        } finally {
            checkInProgress = false;
        }
    }

    checkAppVersion();
    setInterval(checkAppVersion, CHECK_INTERVAL_MS);
})();
