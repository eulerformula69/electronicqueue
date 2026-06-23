// Автоматическая проверка авторизации при загрузке
document.addEventListener("DOMContentLoaded", async () => {
    const savedLogin = localStorage.getItem("terminal_credential_login");
    const savedPass = localStorage.getItem("terminal_credential_pass");

    if (savedLogin && savedPass) {
        // Если данные есть, пробуем войти в фоне
        await performTerminalLogin(savedLogin, savedPass, true);
    } else {
        // Если данных нет, показываем окно входа
        document.getElementById("terminal-auth-overlay").style.display = "flex";
    }
});

// Функция входа
async function performTerminalLogin(login, password, isAuto = false) {
    const errorEl = document.getElementById("term-auth-error");
    try {
        const response = await fetch(`${CONFIG.API_URL}/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ login, password })
        });

        const data = await response.json();

        // Проверяем, что это именно терминал
        if (response.ok && data.role === "terminal") {
            // Сохраняем сессию для текущей работы
            localStorage.setItem("session_id", data.session_id);          
            // Сохраняем логин/пароль "навечно" для авто-входа
            localStorage.setItem("terminal_credential_login", login);
            localStorage.setItem("terminal_credential_pass", password);          
            // Скрываем окно и загружаем данные терминала
            document.getElementById("terminal-auth-overlay").style.display = "none" 
            // Стандартные функции инициализации
            loadServices();
            loadTerminalSettings();
        } else {
            throw new Error(data.detail || "Доступ запрещен или это не терминал");
        }
    } catch (err) {
        console.error("Auth error:", err);
        if (isAuto) {
            // Если авто-вход не сработал (например, пароль изменили), сбрасываем и просим ввод
            localStorage.removeItem("terminal_credential_login");
            localStorage.removeItem("terminal_credential_pass");
        }
        document.getElementById("terminal-auth-overlay").style.display = "flex";
        errorEl.textContent = err.message;
    }
}

// Вызывается при нажатии на кнопку в форме
async function handleTerminalManualLogin() {
    const login = document.getElementById("term-login").value;
    const pass = document.getElementById("term-password").value;
    const btn = document.getElementById("vkb-login-btn") || document.getElementById("term-auth-btn");
    
    if (btn) btn.disabled = true;
    await performTerminalLogin(login, pass);
    if (btn) btn.disabled = false;
}


function connectSocket() {
    // Используем URL из конфига
    const socket = new WebSocket(CONFIG.WS_TERMINAL_URL);
    socket.onopen = () => console.log("WS connected");
    socket.onclose = () => {
        console.log("WS reconnecting...");
        // Используем интервал из конфига
        setTimeout(connectSocket, CONFIG.RECONNECT_INTERVAL);
    };

    socket.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type === "services_updated") {
            loadServices();
            loadTerminalSettings();
        }
        if (data.type === "settings_updated") {
            loadTerminalSettings();
        }
    };

    return socket;
}

let socket = connectSocket();
let terminalSettings = {
    print_ticket: true,
    show_print_badge: true,
    ticket_notice_duration_printed_seconds: 7,
    ticket_notice_duration_unprinted_seconds: 45,
    ticket_notice_printed_text: "Ваш номер: <number>",
    ticket_notice_unprinted_text: "Пожалуйста, запомните свой номер:\n<number>"
};

const TERMINAL_SERVICE_GESTURE = {
    corners: ["top-left", "top-right", "bottom-right", "bottom-left"],
    hitSize: 120,
    timeoutMs: 6000,
    step: 0,
    startedAt: 0
};

function detectTerminalCorner(event) {
    const point = event.changedTouches ? event.changedTouches[0] : event;
    const x = point.clientX;
    const y = point.clientY;
    const width = window.innerWidth;
    const height = window.innerHeight;
    const hit = TERMINAL_SERVICE_GESTURE.hitSize;

    if (x <= hit && y <= hit) return "top-left";
    if (x >= width - hit && y <= hit) return "top-right";
    if (x >= width - hit && y >= height - hit) return "bottom-right";
    if (x <= hit && y >= height - hit) return "bottom-left";
    return null;
}

function resetTerminalServiceGesture() {
    TERMINAL_SERVICE_GESTURE.step = 0;
    TERMINAL_SERVICE_GESTURE.startedAt = 0;
}

function handleTerminalServiceGesture(event) {
    if (document.getElementById("terminal-service-overlay")?.style.display === "flex") {
        return;
    }

    const corner = detectTerminalCorner(event);
    if (!corner) {
        resetTerminalServiceGesture();
        return;
    }

    const now = Date.now();
    const expected = TERMINAL_SERVICE_GESTURE.corners[TERMINAL_SERVICE_GESTURE.step];

    if (
        TERMINAL_SERVICE_GESTURE.step > 0 &&
        now - TERMINAL_SERVICE_GESTURE.startedAt > TERMINAL_SERVICE_GESTURE.timeoutMs
    ) {
        resetTerminalServiceGesture();
    }

    if (corner === TERMINAL_SERVICE_GESTURE.corners[0] && TERMINAL_SERVICE_GESTURE.step === 0) {
        TERMINAL_SERVICE_GESTURE.startedAt = now;
        TERMINAL_SERVICE_GESTURE.step = 1;
        return;
    }

    if (corner !== expected) {
        resetTerminalServiceGesture();
        return;
    }

    TERMINAL_SERVICE_GESTURE.step += 1;

    if (TERMINAL_SERVICE_GESTURE.step >= TERMINAL_SERVICE_GESTURE.corners.length) {
        resetTerminalServiceGesture();
        openTerminalServiceModal();
    }
}

function ensureTerminalServiceModal() {
    let overlay = document.getElementById("terminal-service-overlay");
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = "terminal-service-overlay";
    overlay.className = "terminal-service-overlay";
    overlay.style.display = "none";
    overlay.innerHTML = `
        <div class="terminal-service-modal" role="dialog" aria-modal="true">
            <h2>\u0421\u0435\u0440\u0432\u0438\u0441\u043d\u043e\u0435 \u043c\u0435\u043d\u044e</h2>
            <div class="terminal-service-actions">
                <button type="button" class="terminal-service-refresh">\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u0432\u043a\u043b\u0430\u0434\u043a\u0443</button>
                <button type="button" class="terminal-service-cancel">\u041e\u0442\u043c\u0435\u043d\u0430</button>
            </div>
        </div>
    `;

    overlay.querySelector(".terminal-service-refresh").addEventListener("click", () => {
        window.location.reload();
    });
    overlay.querySelector(".terminal-service-cancel").addEventListener("click", closeTerminalServiceModal);
    overlay.addEventListener("click", (event) => {
        if (event.target === overlay) closeTerminalServiceModal();
    });

    document.body.appendChild(overlay);
    return overlay;
}

function openTerminalServiceModal() {
    const overlay = ensureTerminalServiceModal();
    overlay.style.display = "flex";
}

function closeTerminalServiceModal() {
    const overlay = document.getElementById("terminal-service-overlay");
    if (overlay) overlay.style.display = "none";
}

document.addEventListener("pointerup", handleTerminalServiceGesture, true);

function renderPrintModeBadge() {
    const badge = document.getElementById("print-mode-badge");
    if (!badge) return;

    if (!terminalSettings.show_print_badge) {
        badge.style.display = "none";
        return;
    }

    badge.style.display = "block";
    if (terminalSettings.print_ticket) {
        badge.textContent = "Печать: ВКЛ";
        badge.style.background = "rgba(40, 167, 69, 0.92)";
    } else {
        badge.textContent = "Печать: ВЫКЛ";
        badge.style.background = "rgba(108, 117, 125, 0.92)";
    }
}

async function loadTerminalSettings() {
    try {
        const res = await fetch(`${CONFIG.API_URL}/settings/public`);
        if (!res.ok) {
            renderPrintModeBadge();
            return;
        }
        const data = await res.json();
        terminalSettings.print_ticket = data.print_ticket !== false;
        terminalSettings.show_print_badge = data.show_print_badge !== false;
        terminalSettings.ticket_notice_duration_printed_seconds =
            Number(data.ticket_notice_duration_printed_seconds) || 7;
        terminalSettings.ticket_notice_duration_unprinted_seconds =
            Number(data.ticket_notice_duration_unprinted_seconds) || 45;
        terminalSettings.ticket_notice_printed_text =
            data.ticket_notice_printed_text || "Ваш номер: <number>";
        terminalSettings.ticket_notice_unprinted_text =
            data.ticket_notice_unprinted_text || "Пожалуйста, запомните свой номер:\n<number>";
        renderPrintModeBadge();
    } catch (error) {
        console.warn("Не удалось загрузить публичные настройки терминала:", error);
        renderPrintModeBadge();
    }
}

// --- Загрузка услуг ---
async function loadServices() {
    try {
        console.log("Loading services from:", `${CONFIG.API_URL}/services/`);
        const res = await fetch(`${CONFIG.API_URL}/services/`);
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        
        const services = await res.json();
        const container = document.getElementById("services");
        container.innerHTML = "";

        if (services.length === 0) {
            container.innerHTML = "<p>Нет доступных услуг</p>";
            return;
        }

        services.forEach(service => {
            const btn = document.createElement("button");
            btn.classList.add("service-btn");

            if (service.status === "inactive") {
                btn.textContent = `${service.name} (сейчас не активна)`;
                btn.classList.add("unavailable");
                btn.onclick = () => {
                    showNotice("В данный момент нет доступных специалистов. Услуга недоступна", CONFIG.NOTICE_DURATION);
                };
            } else {
                btn.textContent = service.name;
                btn.onclick = () => {
                    if (service.operator_choice_enabled) {
                        chooseOperator(service.id, service.name);
                    } else {
                        createTicket(service.id, service.name);
                    }
                };
            }
            container.appendChild(btn);
        });

    } catch (error) {
        console.error("Ошибка загрузки услуг:", error);
        const container = document.getElementById("services");
        container.innerHTML = `<p style="color: red;">Ошибка загрузки услуг (ОШИБКА: ${error.message})</p>`;
    }
}

function ensureOperatorChoiceModal() {
    let overlay = document.getElementById("operator-choice-overlay");
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = "operator-choice-overlay";
    overlay.className = "operator-choice-overlay";
    overlay.style.display = "none";

    overlay.innerHTML = `
        <div class="operator-choice-modal">
            <button type="button" class="operator-choice-close" onclick="closeOperatorChoiceModal()" aria-label="Закрыть">×</button>
            <h2>Выберите оператора</h2>
            <div id="operator-choice-service" class="operator-choice-service"></div>
            <select id="operator-choice-select" class="operator-choice-select"></select>
            <div id="operator-choice-error" class="operator-choice-error"></div>
            <div id="operator-choice-list" class="operator-choice-list"></div>
            <div class="operator-choice-actions">
                <button type="button" class="operator-choice-confirm" onclick="confirmOperatorChoice()">Подтвердить</button>
                <button type="button" class="operator-choice-cancel" onclick="closeOperatorChoiceModal()">Отмена</button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);
    return overlay;
}

function closeOperatorChoiceModal() {
    const overlay = document.getElementById("operator-choice-overlay");
    if (overlay) overlay.style.display = "none";
    window.pendingOperatorChoice = null;
    window.selectedOperatorWindowId = null;
}

async function chooseOperator(serviceId, serviceName) {
    const currentSession = localStorage.getItem("session_id");

    if (!currentSession) {
        showNotice("Ошибка: Сессия не найдена. Войдите заново.", 5);
        document.getElementById("terminal-auth-overlay").style.display = "flex";
        return;
    }

    const overlay = ensureOperatorChoiceModal();
    const select = document.getElementById("operator-choice-select");
    const errorEl = document.getElementById("operator-choice-error");
    const serviceEl = document.getElementById("operator-choice-service");
    const list = document.getElementById("operator-choice-list");
    const confirmBtn = overlay.querySelector(".operator-choice-confirm");

    window.pendingOperatorChoice = { serviceId, serviceName };
    window.selectedOperatorWindowId = null;
    serviceEl.textContent = serviceName;
    errorEl.textContent = "";
    list.innerHTML = "";
    select.innerHTML = `<option value="">Загрузка операторов...</option>`;
    select.disabled = true;
    confirmBtn.disabled = true;
    overlay.style.display = "flex";

    try {
        const res = await fetch(`${CONFIG.API_URL}/services/${serviceId}/operators`, {
            headers: { "session-id": currentSession }
        });

        const operators = await res.json().catch(() => []);

        if (!res.ok) {
            errorEl.textContent = operators.detail || "Не удалось загрузить операторов";
            select.innerHTML = `<option value="">Нет доступных операторов</option>`;
            return;
        }

        if (!Array.isArray(operators) || operators.length === 0) {
            errorEl.textContent = "Нет доступных операторов для этой услуги";
            select.innerHTML = `<option value="">Нет доступных операторов</option>`;
            return;
        }

list.innerHTML = "";
select.innerHTML = "";
select.style.display = "none";

confirmBtn.disabled = true;

operators.forEach(operator => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "operator-choice-card";
    card.textContent = `${operator.operator_name} — ${operator.window_name}`;

    card.onclick = () => {
        list.querySelectorAll(".operator-choice-card").forEach(el => {
            el.classList.remove("selected");
        });

        card.classList.add("selected");
        confirmBtn.disabled = false;
        window.selectedOperatorWindowId = operator.window_id;
    };

    list.appendChild(card);
});


    } catch (error) {
        console.error("Ошибка загрузки операторов:", error);
        errorEl.textContent = "Сбой связи с сервером.";
        select.innerHTML = `<option value="">Ошибка загрузки</option>`;
    }
}

function confirmOperatorChoice() {
    const pending = window.pendingOperatorChoice;
    const errorEl = document.getElementById("operator-choice-error");

    if (!pending) return;

    const windowId = window.selectedOperatorWindowId;
    if (!windowId) {
        errorEl.textContent = "Выберите оператора";
        return;
    }

    closeOperatorChoiceModal();
    createTicket(pending.serviceId, pending.serviceName, Number(windowId));
}

// --- Создание талона ---
async function createTicket(serviceId, serviceName, windowId = null) {
    const buttons = document.querySelectorAll(".service-btn");
    buttons.forEach(btn => btn.disabled = true);
    // Достаем токен сессии
	const currentSession = localStorage.getItem("session_id");

    if (!currentSession) {
        showNotice("Ошибка: Сессия не найдена. Войдите заново.", 5);
        document.getElementById("terminal-auth-overlay").style.display = "flex";
        return;
    }

    try {
        const response = await fetch(`${CONFIG.API_URL}/tickets`, {
            method: "POST",
            headers: { 
                "Content-Type": "application/json",
                "session-id": currentSession
            },
            body: JSON.stringify({
                service_id: serviceId,
                window_id: windowId
            })
        });

        const data = await response.json();
        // Обработка ошибок 
        if (!response.ok) {
            if (response.status === 401) {
                showNotice("Сессия истекла. Требуется повторный вход.", 5);
                // Можно вызвать логаут или показать форму входа
                return;
            }
            const errorMsg = data.detail || data.error || "Ошибка создания талона";
            showNotice(errorMsg, 3);
            return; 
        }
        // Настройка форматирования даты
        const dateOptions = { 
            weekday: 'long', 
            day: 'numeric', 
            month: 'long', 
            year: 'numeric', 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit' 
        };

        const formattedDate = new Date().toLocaleString('ru-RU', dateOptions).replace(' г.', 'г.');
        // Заполнение данными для печати
        document.getElementById("receipt-number").textContent = data.number;
        document.getElementById("receipt-service").textContent = data.service_name || serviceName;
        document.getElementById("receipt-date").textContent = formattedDate;

        const waitEl = document.getElementById("receipt-wait-count");
        if (waitEl) {
            waitEl.textContent = data.waiting_before > 0 
                ? `ПЕРЕД ВАМИ В ОЧЕРЕДИ: ~ ${data.waiting_before} ЧЕЛ.` 
                : "ВЫ СЛЕДУЮЩИЙ В ОЧЕРЕДИ!";
        }
        // Печать, если включена в админке
        if (terminalSettings.print_ticket) {
            printTicket();
        }      
        // Уведомляем другие модули через сокет
        if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "queue_updated" }));
        }
        if (terminalSettings.print_ticket) {
            showNotice(
                renderTicketNoticeText(terminalSettings.ticket_notice_printed_text, data.number),
                terminalSettings.ticket_notice_duration_printed_seconds
            );
        } else {
            showNotice(
                renderTicketNoticeText(terminalSettings.ticket_notice_unprinted_text, data.number),
                terminalSettings.ticket_notice_duration_unprinted_seconds
            );
        }

    } catch (error) {
        console.error("Ошибка при создании билета:", error);
        showNotice("Сбой связи с сервером.", 4);
    } finally {
        // Разблокировка кнопок
        buttons.forEach(btn => {
            if (!btn.classList.contains("unavailable")) {
                btn.disabled = false;
            }
        });
    }
}

function renderTicketNoticeText(template, ticketNumber) {
    return String(template || "<number>").replaceAll("<number>", String(ticketNumber));
}

function showNotice(message, duration) {
    const notice = document.getElementById("ticket-notice");
    const timerEl = document.getElementById("ticket-timer");
    const messageEl = document.getElementById("ticket-message");
    // Останавливаем предыдущие таймеры, если они были
    if (window.noticeInterval) clearInterval(window.noticeInterval);

    messageEl.textContent = message;
    let secondsLeft = duration;
    
    timerEl.textContent = secondsLeft;
    notice.style.display = "flex";

    window.noticeInterval = setInterval(() => {
        secondsLeft--;
        timerEl.textContent = secondsLeft;

        if (secondsLeft <= 0) {
            clearInterval(window.noticeInterval);
            notice.style.display = "none";
        }
    }, 1000);
}

function closeNotice() {
    if (window.noticeInterval) {
        clearInterval(window.noticeInterval);
        window.noticeInterval = null;
    }
    document.getElementById("ticket-notice").style.display = "none";
}

document.getElementById("ticket-notice-close").addEventListener("click", closeNotice);

// Оставляем только ОДНУ функцию printTicket
function printTicket() {
    const receipt = document.getElementById("print-receipt");  
    // Делаем видимым для корректного захвата браузером
    receipt.style.display = "block";
    // Вызов системного диалога печати
    window.print();
    // Скрываем обратно
    receipt.style.display = "none";
}

// Запуск "тишины" для предотвращения сна
function startAntiSleepAudio() {
    const audio = document.getElementById('silentAudio');
    if (audio) {
        audio.play().then(() => {
            console.log("Anti-sleep audio started");
        }).catch(err => {
            console.warn("Audio play blocked, waiting for user interaction");
        });
    }
}

// Запускаем при первом клике в любом месте страницы
document.addEventListener('click', () => {
    startAntiSleepAudio();
}, { once: true });

// Клавиатура активации //
let vkbActiveField = 'term-login';
let vkbShift = false;
let vkbCaps = false;

const VKB_LAYOUT = [
    ['1','2','3','4','5','6','7','8','9','0','-','='],
    ['q','w','e','r','t','y','u','i','o','p','[',']'],
    ['a','s','d','f','g','h','j','k','l',';','\''],
    ['z','x','c','v','b','n','m',',','.','/']
];

const VKB_SHIFT_MAP = {
    '1':'!','2':'@','3':'#','4':'$','5':'%','6':'^','7':'&','8':'*','9':'(','0':')',
    '-':'_','=':'+',
    '[':'{',']':'}',
    ';':':','\'':'"',
    ',':'<','.':'>','/':'?'
};

function setActiveField(fieldId) {
    vkbActiveField = fieldId;
    // Подсветить активное поле
    ['term-login','term-password'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.borderColor = id === fieldId ? '#00aaff' : '#e2e8f0';
    });
}

function vkbPress(char) {
    const el = document.getElementById(vkbActiveField);
    if (!el) return;

    el.value += char;

    if (vkbShift && !vkbCaps) {
        vkbShift = false;
        renderVkbKeys();
    }
}

function vkbBackspace() {
    const el = document.getElementById(vkbActiveField);
    if (el) el.value = el.value.slice(0, -1);
}

function vkbToggleShift() {
    vkbShift = !vkbShift;
    renderVkbKeys();
}

function vkbToggleCaps() {
    vkbCaps = !vkbCaps;
    renderVkbKeys();
}

function vkbSpace() {
    const el = document.getElementById(vkbActiveField);
    if (el) el.value += ' ';
}

function vkbTab() {
    // Переключить между полями
    vkbActiveField = vkbActiveField === 'term-login' ? 'term-password' : 'term-login';
    setActiveField(vkbActiveField);
}

function renderVkbKeys() {
    const isUpper = vkbShift || vkbCaps;

    // --- РЯД 1 ---
    const numRow = document.getElementById('vkb-row-num');
    numRow.innerHTML = '';

    VKB_LAYOUT[0].forEach(k => {
        const btn = document.createElement('button');
        btn.className = 'vkb-key';

        let char = k;
        if (vkbShift && VKB_SHIFT_MAP[k]) {
            char = VKB_SHIFT_MAP[k];
        }

        btn.textContent = char;
        btn.onclick = () => vkbPress(char);
        numRow.appendChild(btn);
    });

    const bs = document.createElement('button');
    bs.className = 'vkb-key action-dark';
    bs.textContent = '⌫';
    bs.onclick = vkbBackspace;
    numRow.appendChild(bs);

    // --- РЯД 2 ---
    const qRow = document.getElementById('vkb-row-q');
    qRow.innerHTML = '';

    const tab = document.createElement('button');
    tab.className = 'vkb-key action-dark';
    tab.textContent = 'Tab';
    tab.onclick = vkbTab;
    qRow.appendChild(tab);

    VKB_LAYOUT[1].forEach(k => {
        const btn = document.createElement('button');
        btn.className = 'vkb-key';
        btn.textContent = isUpper ? k.toUpperCase() : k;
        btn.onclick = () => vkbPress(btn.textContent);
        qRow.appendChild(btn);
    });

    // --- РЯД 3 ---
    const aRow = document.getElementById('vkb-row-a');
    aRow.innerHTML = '';

    const caps = document.createElement('button');
    caps.className = 'vkb-key' + (vkbCaps ? ' shift-active' : '');
    caps.textContent = 'Caps';
    caps.onclick = vkbToggleCaps;
    aRow.appendChild(caps);

    VKB_LAYOUT[2].forEach(k => {
        const btn = document.createElement('button');
        btn.className = 'vkb-key';
        btn.textContent = isUpper ? k.toUpperCase() : k;
        btn.onclick = () => vkbPress(btn.textContent);
        aRow.appendChild(btn);
    });

    // --- РЯД 4 ---
    const zRow = document.getElementById('vkb-row-z');
    zRow.innerHTML = '';

    const shift = document.createElement('button');
    shift.className = 'vkb-key' + (vkbShift ? ' shift-active' : '');
    shift.textContent = 'Shift';
    shift.onclick = vkbToggleShift;
    zRow.appendChild(shift);

    VKB_LAYOUT[3].forEach(k => {
        const btn = document.createElement('button');
        btn.className = 'vkb-key';

        let char = k;
        if (vkbShift && VKB_SHIFT_MAP[k]) {
            char = VKB_SHIFT_MAP[k];
        }

        btn.textContent = isUpper ? char.toUpperCase() : char;
        btn.onclick = () => vkbPress(btn.textContent);
        zRow.appendChild(btn);
    });

	// --- РЯД 5: ПРОБЕЛ ---
	const spaceRow = document.getElementById('vkb-row-space');
	spaceRow.innerHTML = '';

	const space = document.createElement('button');
	space.className = 'vkb-key';
	space.textContent = 'Пробел';
	space.onclick = vkbSpace;

	spaceRow.appendChild(space);

	// --- РЯД 6: ДЕЙСТВИЯ ---
	const actionRow = document.getElementById('vkb-row-actions');
	actionRow.innerHTML = '';

	const clear = document.createElement('button');
	clear.className = 'vkb-key danger';
	clear.textContent = 'Очистить';
	clear.onclick = () => {
		document.getElementById(vkbActiveField).value = '';
	};

	const login = document.createElement('button');
	login.className = 'vkb-key action-green';
	login.textContent = 'Войти';
	login.onclick = handleTerminalManualLogin;

	actionRow.append(clear, login);
}

// Инициализируем клавиатуру при первой загрузке
document.addEventListener('DOMContentLoaded', () => {
    renderVkbKeys();
    setActiveField('term-login');

    // Поддержка физической клавиатуры
    document.addEventListener('keydown', (e) => {
        const overlay = document.getElementById('terminal-auth-overlay');
        if (!overlay || overlay.style.display === 'none') return;

        if (e.key === 'Backspace') {
            e.preventDefault();
            vkbBackspace();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            handleTerminalManualLogin();
        } else if (e.key === 'Tab') {
            e.preventDefault();
            vkbTab();
        } else if (e.key.length === 1) {
            e.preventDefault();
            const el = document.getElementById(vkbActiveField);
            if (el) el.value += e.key;
        }
    });
});

// --- Инициализация ---
loadTerminalSettings();
loadServices();
