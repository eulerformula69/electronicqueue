(function () {
    var tickerText = "";
    var resizeTimer = null;
    var resizeListenerAttached = false;

    function ensureTicker() {
        var ticker = document.getElementById("board-ticker");
        var track;

        if (ticker) return ticker;

        ticker = document.createElement("div");
        ticker.id = "board-ticker";
        ticker.className = "board-ticker";
        ticker.hidden = true;

        track = document.createElement("div");
        track.className = "board-ticker__track";

        ticker.appendChild(track);
        document.body.appendChild(ticker);

        return ticker;
    }

    function createTextItem(text, hidden) {
        var item = document.createElement("span");
        item.className = "board-ticker__text";
        item.textContent = text;
        if (hidden) item.setAttribute("aria-hidden", "true");
        return item;
    }

    function formatTickerText(value) {
        var messages = String(value || "")
            .split(/\r?\n/)
            .map(function (line) {
                return line.trim();
            })
            .filter(Boolean);

        if (messages.length <= 1) return messages[0] || "";
        return messages.join("   |   ") + "   |   ";
    }

    function renderTickerText() {
        var text = tickerText;
        var ticker = ensureTicker();
        var track = ticker.getElementsByClassName("board-ticker__track")[0];
        var tickerWidth;
        var itemWidth;
        var repeatCount;
        var distance;
        var i;

        ticker.hidden = !text;
        document.body.classList.toggle("has-board-ticker", Boolean(text));

        track.innerHTML = "";

        if (!text) return;

        track.appendChild(createTextItem(text, false));
        tickerWidth = ticker.clientWidth || window.innerWidth || 1920;
        itemWidth = track.firstChild.offsetWidth || tickerWidth;
        repeatCount = Math.max(2, Math.ceil(tickerWidth / itemWidth) + 2);
        distance = itemWidth * repeatCount;

        track.innerHTML = "";
        for (i = 0; i < repeatCount * 2; i++) {
            track.appendChild(createTextItem(text, i >= repeatCount));
        }

        track.style.setProperty("--board-ticker-distance", distance + "px");
        track.style.setProperty("--board-ticker-duration", Math.max(18, Math.round(distance / 80)) + "s");
    }

    function scheduleRender() {
        if (resizeTimer) clearTimeout(resizeTimer);
        resizeTimer = setTimeout(renderTickerText, 100);
    }

    window.setBoardTickerText = function (value) {
        tickerText = formatTickerText(value);
        renderTickerText();

        if (!resizeListenerAttached) {
            window.addEventListener("resize", scheduleRender);
            resizeListenerAttached = true;
        }
    };
})();
