/* LG webOS watchdog for the lite2 board page.
   Older TV WebViews can stop repainting HTML overlays after long playback.
   Keep the DOM changing and refresh the page before that state usually starts. */
(function () {
    var REPAINT_INTERVAL_MS = 10000;
    var VIDEO_CHECK_INTERVAL_MS = 30000;
    var HARD_RELOAD_AFTER_MS = 10 * 60 * 1000;
    var startedAt = new Date().getTime();
    var repaintTick = 0;
    var screenWakeLock = null;

    if (!document.body || document.body.dataset.boardProfile !== "media") return;

    function ensureHeartbeatElement() {
        var el = document.getElementById("lg-lite2-heartbeat");

        if (!el) {
            el = document.createElement("div");
            el.id = "lg-lite2-heartbeat";
            el.setAttribute("aria-hidden", "true");
            el.style.position = "fixed";
            el.style.left = "0";
            el.style.bottom = "0";
            el.style.width = "3px";
            el.style.height = "3px";
            el.style.zIndex = "2147483647";
            el.style.pointerEvents = "none";
            el.style.background = "#ffffff";
            el.style.borderRadius = "3px";
            document.body.appendChild(el);
        }

        return el;
    }

    function repaintInterface() {
        var title = document.getElementById("title");
        var wrapper = document.querySelector(".board-wrapper");
        var heartbeat = ensureHeartbeatElement();

        if (title) title.style.visibility = "visible";
        if (wrapper) wrapper.style.visibility = "visible";

        repaintTick = repaintTick + 1;
        heartbeat.style.left = repaintTick % 2 ? "0" : "6px";
        heartbeat.style.bottom = repaintTick % 2 ? "0" : "6px";
        heartbeat.style.opacity = repaintTick % 2 ? "0.15" : "0.08";
        heartbeat.setAttribute("data-tick", String(repaintTick));

        if (wrapper) {
            wrapper.style.webkitTransform = "translateZ(0)";
            wrapper.style.transform = "translateZ(0)";
        }
    }

    function keepVideoPlaying() {
        var video = document.getElementById("media-video");
        var promise;

        if (!video) return;

        if (video.paused && (video.currentSrc || video.src)) {
            try {
                promise = video.play();
                if (promise && promise.catch) promise.catch(function () {});
            } catch (e) {}
        }

        if (window.initPlaylist) {
            try {
                window.initPlaylist(true);
            } catch (e2) {}
        }
    }

    function requestWakeLock() {
        var wakeLock;

        if (screenWakeLock) return;
        if (!navigator.wakeLock || !navigator.wakeLock.request) return;

        try {
            wakeLock = navigator.wakeLock.request("screen");
            if (wakeLock && wakeLock.then) {
                wakeLock.then(function (lock) {
                    screenWakeLock = lock;

                    if (screenWakeLock && screenWakeLock.addEventListener) {
                        screenWakeLock.addEventListener("release", function () {
                            screenWakeLock = null;
                        });
                    }
                }).catch(function () {});
            }
        } catch (e) {}
    }

    function hardReloadBeforeWebOsStalls() {
        var url;

        if (window.BOARD_DISABLE_FORCED_RELOAD) return;
        if (new Date().getTime() - startedAt < HARD_RELOAD_AFTER_MS) return;

        url = window.location.pathname + "?lgLiteReload=" + new Date().getTime();
        window.location.replace(url);
    }

    function init() {
        repaintInterface();
        keepVideoPlaying();
        requestWakeLock();

        setInterval(repaintInterface, REPAINT_INTERVAL_MS);
        setInterval(keepVideoPlaying, VIDEO_CHECK_INTERVAL_MS);
        setInterval(hardReloadBeforeWebOsStalls, 30000);

        document.addEventListener("visibilitychange", function () {
            if (!document.hidden) {
                requestWakeLock();
                keepVideoPlaying();
                repaintInterface();
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
