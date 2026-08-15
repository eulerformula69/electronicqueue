(function () {
    const CHECK_INTERVAL_MS = 60000;
    let checkInProgress = false;
    const pageVersion = document.querySelector('meta[name="app-version"]')?.content?.trim();

    function showUpdateNotification() {
        let notification = document.getElementById("app-release-notification");
        if (!notification) {
            notification = document.createElement("div");
            notification.id = "app-release-notification";
            document.body.appendChild(notification);
        }
        notification.className = "app-version-notification";
        notification.innerHTML = "<span>Доступна новая версия приложения</span>";

        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Обновить";
        button.addEventListener("click", () => window.location.reload());
        notification.appendChild(button);
        notification.style.display = "flex";
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

            if (pageVersion && pageVersion !== currentVersion) {
                showUpdateNotification();
            }
        } catch (error) {
            console.debug("App version check error:", error);
        } finally {
            checkInProgress = false;
        }
    }

    const style = document.createElement("style");
    style.textContent = ".app-version-notification{position:fixed;left:50%;top:16px;transform:translateX(-50%);z-index:10000;align-items:center;gap:12px;padding:12px 16px;border-radius:12px;background:#202124;color:#fff;box-shadow:0 8px 30px rgba(0,0,0,.28);font:600 14px/1.35 system-ui,sans-serif}.app-version-notification button{border:0;border-radius:8px;padding:8px 14px;background:#fff;color:#202124;font:inherit;cursor:pointer}";
    document.head.appendChild(style);

    if (pageVersion) {
        checkAppVersion();
        setInterval(checkAppVersion, CHECK_INTERVAL_MS);
    }
})();
