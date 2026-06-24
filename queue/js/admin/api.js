const API = CONFIG.API_URL;

export async function fetchJSON(url, options = {}) {
    const sessionId = sessionStorage.getItem("session_id");
    options.headers = {
        ...options.headers,
        "session-id": sessionId
    };

    const res = await fetch(url, options);

    if (res.status === 401) {
        alert("?????? ???????");
        window.location.href = "login.html";
        return;
    }

    if (res.status === 204 || (options.method === "DELETE" && res.ok)) {
        return { status: "ok" };
    }

    return res.json();
}

export async function readResponseData(res) {
    const text = await res.text();
    if (!text) return {};

    try {
        return JSON.parse(text);
    } catch {
        return { detail: text };
    }
}
