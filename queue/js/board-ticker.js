(function () {
    var tickerMessages = [];
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

    function createTextItem(text, isSegmentEnd, hidden) {
        var item = document.createElement("span");
        item.className = "board-ticker__text" + (isSegmentEnd ? " board-ticker__text--segment-end" : "");
        item.textContent = text;
        if (hidden) item.setAttribute("aria-hidden", "true");
        return item;
    }

    function parseTickerMessages(value) {
        return String(value || "")
            .split(/\s+\|\s+|\r?\n/)
            .map(function (line) {
                return line.trim();
            })
            .filter(Boolean);
    }

    function appendMessageSet(track, messages, hidden) {
        var i;

        for (i = 0; i < messages.length; i++) {
            track.appendChild(createTextItem(messages[i], i === messages.length - 1, hidden));
        }
    }

    function renderTickerMessages() {
        var messages = tickerMessages;
        var ticker = ensureTicker();
        var track = ticker.getElementsByClassName("board-ticker__track")[0];
        var tickerWidth;
        var setWidth;
        var repeatCount;
        var distance;
        var i;

        ticker.hidden = !messages.length;
        document.body.classList.toggle("has-board-ticker", Boolean(messages.length));

        track.innerHTML = "";

        if (!messages.length) return;

        appendMessageSet(track, messages, false);
        tickerWidth = ticker.clientWidth || window.innerWidth || 1920;
        setWidth = track.scrollWidth || tickerWidth;
        repeatCount = Math.max(2, Math.ceil(tickerWidth / setWidth) + 2);
        distance = setWidth * repeatCount;

        track.innerHTML = "";
        for (i = 0; i < repeatCount * 2; i++) {
            appendMessageSet(track, messages, i >= repeatCount);
        }

        track.style.setProperty("--board-ticker-distance", distance + "px");
        track.style.setProperty("--board-ticker-duration", Math.max(18, Math.round(distance / 80)) + "s");
    }

    function scheduleRender() {
        if (resizeTimer) clearTimeout(resizeTimer);
        resizeTimer = setTimeout(renderTickerMessages, 100);
    }

    window.setBoardTickerText = function (value) {
        tickerMessages = parseTickerMessages(value);
        renderTickerMessages();

        if (!resizeListenerAttached) {
            window.addEventListener("resize", scheduleRender);
            resizeListenerAttached = true;
        }
    };
})();
