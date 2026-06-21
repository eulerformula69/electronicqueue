/* Дополнительная защита HTML-слоя для старых LG webOS. */
(function () {
    function repaintInterface() {
        var title = document.getElementById("title");
        var boardColumn = document.querySelector(".board-column");

        if (title) title.style.visibility = "visible";
        if (!boardColumn) return;

        boardColumn.style.visibility = "hidden";
        void boardColumn.offsetHeight;
        boardColumn.style.visibility = "visible";
    }

    function init() {
        setInterval(repaintInterface, 60000);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
