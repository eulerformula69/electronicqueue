/* Медиаплеер для старых LG webOS без современного синтаксиса JavaScript. */
(function () {
    var currentPlaylist = [];
    var playlistIndex = 0;
    var startedAt = new Date().getTime();
    var RELOAD_ON_VIDEO_END_AFTER_MS = 20 * 60 * 1000;
    var HARD_RELOAD_AFTER_MS = 60 * 60 * 1000;
    var NEXT_VIDEO_STORAGE_KEY = "board-media-next-video";
    var VIDEO_AUDIO_ENABLED = !window.BOARD_CONFIG || window.BOARD_CONFIG.videoAudioEnabled !== false;

    function getFileName(path) {
        try {
            return decodeURIComponent(String(path).split("/").pop().split("?")[0]);
        } catch (e) {
            return String(path);
        }
    }

    function playVideo(video) {
        var promise;

        try {
            video.muted = !VIDEO_AUDIO_ENABLED;
            video.volume = VIDEO_AUDIO_ENABLED ? 1.0 : 0;
            promise = video.play();
            if (promise && promise.catch) promise.catch(function () {});
        } catch (e) {}
    }

    function rememberNextVideo(path) {
        try {
            window.sessionStorage.setItem(NEXT_VIDEO_STORAGE_KEY, path);
        } catch (e) {}
    }

    function takeRememberedVideo() {
        var path = "";

        try {
            path = window.sessionStorage.getItem(NEXT_VIDEO_STORAGE_KEY) || "";
            window.sessionStorage.removeItem(NEXT_VIDEO_STORAGE_KEY);
        } catch (e) {}

        return path;
    }

    function reloadPage() {
        window.location.reload();
    }

    function loadPlaylist(isUpdate) {
        var video = document.getElementById("media-video");
        var request;
        var rememberedVideo = takeRememberedVideo();

        if (!video) return;

        request = new XMLHttpRequest();
        request.open("GET", "/queue/media/playlist.json?t=" + new Date().getTime(), true);
        request.onreadystatechange = function () {
            var data;
            var newPlaylist;
            var currentFileName;
            var found = false;
            var i;

            if (request.readyState !== 4 || request.status < 200 || request.status >= 300) return;

            try {
                data = JSON.parse(request.responseText);
            } catch (e) {
                return;
            }

            newPlaylist = Object.prototype.toString.call(data) === "[object Array]" ? data : [];
            currentPlaylist = newPlaylist;

            if (!currentPlaylist.length) {
                video.removeAttribute("src");
                video.load();
                return;
            }

            if (video.currentSrc || video.src) {
                currentFileName = getFileName(video.currentSrc || video.src);
                for (i = 0; i < currentPlaylist.length; i++) {
                    if (getFileName(currentPlaylist[i]) === currentFileName) {
                        playlistIndex = i;
                        found = true;
                        break;
                    }
                }
            } else if (rememberedVideo) {
                currentFileName = getFileName(rememberedVideo);
                for (i = 0; i < currentPlaylist.length; i++) {
                    if (getFileName(currentPlaylist[i]) === currentFileName) {
                        playlistIndex = i;
                        break;
                    }
                }
            }

            if (!found) {
                if (playlistIndex >= currentPlaylist.length) playlistIndex = 0;
                video.src = currentPlaylist[playlistIndex];
                playVideo(video);
            }
        };
        request.send();
    }

    function init() {
        var video = document.getElementById("media-video");
        if (!video) return;

        video.muted = !VIDEO_AUDIO_ENABLED;
        video.volume = VIDEO_AUDIO_ENABLED ? 1.0 : 0;

        video.addEventListener("ended", function () {
            if (!currentPlaylist.length) return;
            playlistIndex = (playlistIndex + 1) % currentPlaylist.length;

            /* Обновляем старый LG WebView только между роликами, не обрывая просмотр. */
            if (new Date().getTime() - startedAt >= RELOAD_ON_VIDEO_END_AFTER_MS) {
                rememberNextVideo(currentPlaylist[playlistIndex]);
                reloadPage();
                return;
            }

            video.src = currentPlaylist[playlistIndex];
            playVideo(video);
        });

        window.addEventListener("ticket-speech-start", function () {
            if (VIDEO_AUDIO_ENABLED) video.volume = 0.2;
        });

        window.addEventListener("ticket-speech-end", function () {
            setTimeout(function () {
                video.volume = VIDEO_AUDIO_ENABLED ? 1.0 : 0;
            }, 6000);
        });

        window.addEventListener("playlist-updated", function () {
            loadPlaylist(true);
        });

        window.initPlaylist = loadPlaylist;
        loadPlaylist(false);

        /* Аварийная страховка на случай очень длинного ролика или зависшего события ended. */
        setTimeout(reloadPage, HARD_RELOAD_AFTER_MS);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
