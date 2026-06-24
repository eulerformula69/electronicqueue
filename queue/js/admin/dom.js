export function resetOpened() {
    if (typeof window.resetOpened === "function") {
        window.resetOpened();
    }
}

export function setTable(html) {
    document.getElementById("table").innerHTML = html;
}

export function setForm(html) {
    document.getElementById("form").innerHTML = html;
}

export function setActiveTab(tabId) {
    document.querySelectorAll(".tabs button").forEach(btn => {
        btn.classList.remove("active");
    });

    document.getElementById(tabId)?.classList.add("active");
}
