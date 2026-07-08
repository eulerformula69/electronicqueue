(function () {
    const CHANGELOG_URL = "/queue/changelog/operator.json";
    const STORAGE_KEY = "operatorChangelogVersion";

    function isValidChangelog(data) {
        return data
            && typeof data.version === "string"
            && data.version.trim()
            && Array.isArray(data.changes)
            && data.changes.every(item => typeof item === "string" && item.trim());
    }

    function closeOperatorChangelog(overlay, version) {
        overlay.remove();
        localStorage.setItem(STORAGE_KEY, version);
    }

    function showOperatorChangelog(data) {
        const version = data.version.trim();
        const existing = document.querySelector(".operator-changelog-overlay");
        if (existing) existing.remove();

        const overlay = document.createElement("div");
        overlay.className = "operator-changelog-overlay";

        const modal = document.createElement("div");
        modal.className = "operator-changelog-modal";
        modal.setAttribute("role", "dialog");
        modal.setAttribute("aria-modal", "true");
        modal.setAttribute("aria-labelledby", "operator-changelog-title");

        const title = document.createElement("h2");
        title.id = "operator-changelog-title";
        title.textContent = data.title || "Что изменилось для оператора";

        const list = document.createElement("ul");
        data.changes.forEach(change => {
            const item = document.createElement("li");
            item.textContent = change;
            list.appendChild(item);
        });

        const actions = document.createElement("div");
        actions.className = "operator-changelog-actions";

        const closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.className = "btn-primary";
        closeButton.textContent = "Понятно";
        closeButton.addEventListener("click", () => closeOperatorChangelog(overlay, version));

        actions.appendChild(closeButton);
        modal.appendChild(title);
        modal.appendChild(list);
        modal.appendChild(actions);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
    }

    async function loadOperatorChangelog() {
        try {
            const response = await fetch(`${CHANGELOG_URL}?t=${Date.now()}`, {
                cache: "no-store"
            });
            if (!response.ok) return;

            const data = await response.json();
            if (!isValidChangelog(data)) return;

            const version = data.version.trim();
            if (localStorage.getItem(STORAGE_KEY) === version) return;

            showOperatorChangelog(data);
        } catch (error) {
            console.debug("Operator changelog load error:", error);
        }
    }

    loadOperatorChangelog();
})();
