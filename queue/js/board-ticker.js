(function () {
    function ensureTicker() {
        var ticker = document.getElementById("board-ticker");
        var track;
        var firstText;
        var secondText;

        if (ticker) return ticker;

        ticker = document.createElement("div");
        ticker.id = "board-ticker";
        ticker.className = "board-ticker";
        ticker.hidden = true;

        track = document.createElement("div");
        track.className = "board-ticker__track";

        firstText = document.createElement("span");
        firstText.className = "board-ticker__text";

        secondText = document.createElement("span");
        secondText.className = "board-ticker__text";
        secondText.setAttribute("aria-hidden", "true");

        track.appendChild(firstText);
        track.appendChild(secondText);
        ticker.appendChild(track);
        document.body.appendChild(ticker);

        return ticker;
    }

    window.setBoardTickerText = function (value) {
        var text = String(value || "").trim();
        var ticker = ensureTicker();
        var items = ticker.getElementsByClassName("board-ticker__text");
        var i;

        for (i = 0; i < items.length; i++) {
            items[i].textContent = text;
        }

        ticker.hidden = !text;
        document.body.classList.toggle("has-board-ticker", Boolean(text));
    };
})();
