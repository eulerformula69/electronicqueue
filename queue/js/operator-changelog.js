(function () {
    const CHANGELOG_URL = "/queue/changelog/operator.json";
    const STORAGE_KEY = "operatorChangelogVersion";

    function isValidChangelog(data) {
        return data
            && typeof data.version === "string"
            && data.version.trim()
            && typeof data.date === "string"
            && data.date.trim()
            && Array.isArray(data.changes)
            && data.changes.every(item => typeof item === "string" && item.trim());
    }

    function getPreviousEntries(data) {
        if (!Array.isArray(data.previous)) return [];

        return data.previous.filter(isValidChangelog);
    }

    function formatOperatorChangelogTitle(data, version) {
        return `Обновление от ${data.date.trim()}, версия ${version}`;
    }

    function closeOperatorChangelog(overlay, version, saveVersion) {
        overlay.remove();
        if (saveVersion) {
            localStorage.setItem(STORAGE_KEY, version);
        }
    }

    function appendChangelogEntry(container, entry) {
        const version = entry.version.trim();
        const section = document.createElement("section");
        section.className = "operator-changelog-entry";

        const heading = document.createElement("h3");
        heading.textContent = formatOperatorChangelogTitle(entry, version);

        const list = document.createElement("ul");
        entry.changes.forEach(change => {
            const item = document.createElement("li");
            item.textContent = change;
            list.appendChild(item);
        });

        section.appendChild(heading);
        section.appendChild(list);
        container.appendChild(section);
    }

    function showOperatorChangelog(data, options = {}) {
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
        title.textContent = options.includePrevious
            ? "Обновления"
            : formatOperatorChangelogTitle(data, version);

        const content = document.createElement("div");
        content.className = "operator-changelog-content";
        appendChangelogEntry(content, data);

        if (options.includePrevious) {
            getPreviousEntries(data).forEach(entry => appendChangelogEntry(content, entry));
        }

        const actions = document.createElement("div");
        actions.className = "operator-changelog-actions";

        const closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.className = "btn-primary";
        closeButton.textContent = "Понятно";
        closeButton.addEventListener(
            "click",
            () => closeOperatorChangelog(overlay, version, options.saveVersion !== false)
        );

        actions.appendChild(closeButton);
        modal.appendChild(title);
        modal.appendChild(content);
        modal.appendChild(actions);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
    }

    async function loadOperatorChangelog(options = {}) {
        try {
            const response = await fetch(`${CHANGELOG_URL}?t=${Date.now()}`, {
                cache: "no-store"
            });
            if (!response.ok) return;

            const data = await response.json();
            if (!isValidChangelog(data)) return;

            const version = data.version.trim();
            if (!options.force && localStorage.getItem(STORAGE_KEY) === version) return;

            showOperatorChangelog(data, options);
        } catch (error) {
            console.debug("Operator changelog load error:", error);
        }
    }

    window.openOperatorChangelogHistory = function () {
        loadOperatorChangelog({
            force: true,
            includePrevious: true,
            saveVersion: false
        });
    };

    loadOperatorChangelog();
})();
