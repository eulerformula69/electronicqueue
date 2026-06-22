const API = CONFIG.API_URL;
const GRAFANA = CONFIG.GRAFANA_URL;
// Глобальный WebSocket для админки (используем тот же канал, что и терминалы)
let adminSocket = null;

// Проверка авторизации при загрузке страницы + запуск WebSocket
async function init() {

document.addEventListener("DOMContentLoaded", async () => {
    const sessionId = sessionStorage.getItem("session_id");

    if (!sessionId) {
        // Если токена нет, отправляем на страницу входа
        window.location.href = "login.html";
        return;
    }

    try {
        // Проверяем валидность сессии через эндпоинт, защищенный verify_admin_session
        // Например, попытка загрузить список операторов
		const response = await fetch(`${API}/auth/admin`, {
			method: "GET",
			headers: {
				"session-id": sessionId
			}
		});

        if (!response.ok) {
            // Если сервер вернул 401 или 403, значит сессия не админская или истекла
            throw new Error("Доступ запрещен");
        }
        // Подключаем WebSocket после успешной проверки сессии
        initAdminWebSocket();

    } catch (err) {
        console.error("Auth check failed:", err);
        sessionStorage.removeItem("session_id");
        window.location.href = "login.html";
    }
});

}

init();

function initAdminWebSocket() {
    adminSocket = new WebSocket(CONFIG.WS_TERMINAL_URL);

    adminSocket.onopen = () => {
        console.log("Admin WS connected");
        // Сразу отправляем heartbeat, чтобы сервер быстро привязал session_id к WS
        try {
            const sid = sessionStorage.getItem("session_id");
            if (sid) {
                adminSocket.send(JSON.stringify({ type: "ping", session_id: sid }));
            }
        } catch (e) {
            console.debug("Admin WS initial ping error:", e);
        }
    };

    adminSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "session_expired") {
            // Сервер явно сообщил об истечении сессии
            sessionStorage.clear();
            window.location.replace("login.html");
        }
    };

    adminSocket.onclose = () => {
        console.log("Admin WS closed, will reconnect");
        setTimeout(initAdminWebSocket, CONFIG.RECONNECT_INTERVAL || 2000);
    };
}

let windows=[]
let operators=[]
let services=[]
let openedServices=null

function resetOpened() {
    openedServices = null;
}

async function fetchJSON(url, options = {}) {
    const sessionId = sessionStorage.getItem("session_id");
    // Гарантируем, что заголовки существуют
    options.headers = {
        ...options.headers,
        "session-id": sessionId
    };

    const res = await fetch(url, options);

    if (res.status === 401) {
        alert("Сессия истекла");
        window.location.href = "login.html";
        return;
    }
    // Если это DELETE и статус 200, res.json() может упасть, если сервер шлет пустой ответ
    if (res.status === 204 || (options.method === 'DELETE' && res.ok)) {
        return { status: "ok" };
    }

    return res.json();
}

async function readResponseData(res) {
    const text = await res.text();
    if (!text) return {};

    try {
        return JSON.parse(text);
    } catch {
        return { detail: text };
    }
}

function setTable(html){
document.getElementById("table").innerHTML=html
}

function setForm(html){
document.getElementById("form").innerHTML=html
}

//////// УСЛУГИ
async function loadServices() {
	resetOpened();
	// Показываем форму и таблицу обратно
    document.getElementById("form").style.display = "block";
    document.getElementById("table").style.display = "table";
    // Удаляем блок статистики, чтобы он не мешал
    const statsContainer = document.getElementById("stats-container");
    if (statsContainer) statsContainer.remove();
	setActiveTab('tab-services'); 
    // 1. Берем ID сессии из хранилища браузера
    const sessionId = sessionStorage.getItem("session_id");
    // 2. Делаем запрос с заголовком
    const res = await fetch(`${API}/services?limit=500`, {
        method: "GET",
        headers: {
            "session-id": sessionId // Передаем тот самый ID
        }
    });
    if (res.status === 401) {
        alert("Сессия истекла, войдите снова");
        window.location.href = "login.html";
        return;
    }
    services = await res.json();

  let html = `<tr>
    <th>ID</th>
    <th>Название</th>
    <th>Статус</th>
    <th>Выбор оператора</th>
    <th>Порядок</th>
    <th>Действия</th>
  </tr>`;

  for(let index = 0; index < services.length; index++){
    const s = services[index];
    html += `
    <tr id="service-${s.id}">
      <td>${s.id}</td>
      <td>${s.name}</td>
      <td>${s.status}</td>
      <td>${s.operator_choice_enabled ? "Да" : "Нет"}</td>
      <td>
        <button title="Переместить выше" aria-label="Переместить услугу выше"
          onclick="moveService(${s.id}, -1)" ${index === 0 ? "disabled" : ""}>↑</button>
        <button title="Переместить ниже" aria-label="Переместить услугу ниже"
          onclick="moveService(${s.id}, 1)" ${index === services.length - 1 ? "disabled" : ""}>↓</button>
      </td>
      <td>
        <button onclick="editService(${s.id},'${s.name}')">Название</button>
        <button onclick="editServiceStatus(${s.id}, '${s.status}')">Статус</button>
        <button onclick="toggleOperatorChoice(${s.id}, ${s.operator_choice_enabled ? 0 : 1})">
          ${s.operator_choice_enabled ? "Отключить выбор" : "Включить выбор"}
        </button>
        <button style="background: #ffcccc;" onclick="deleteService(${s.id})">Удалить</button>
      </td>
    </tr>`;
  }

  setTable(html);

  setForm(`
    <div class="form">
      <input id="newServiceName" placeholder="Название услуги">
      <button onclick="addService()">Добавить услугу</button>
    </div>
  `);
}

async function moveService(serviceId, direction) {
  const currentIndex = services.findIndex(service => service.id === serviceId);
  const targetIndex = currentIndex + direction;
  if (currentIndex < 0 || targetIndex < 0 || targetIndex >= services.length) return;

  const reordered = [...services];
  [reordered[currentIndex], reordered[targetIndex]] = [
    reordered[targetIndex], reordered[currentIndex]
  ];

  const result = await fetchJSON(`${API}/services/order`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({service_ids: reordered.map(service => service.id)})
  });

  if (result) loadServices();
}

function editServiceStatus(id, currentStatus) {
  // если уже открыто для этой услуги — закрываем
  if(openedServices && openedServices.dataset.type === "serviceStatus" && openedServices.dataset.serviceId == id){
    openedServices.remove();
    openedServices = null;
    return;
  }
  // закрываем любое другое открытое окно
  openedServices?.remove();
  openedServices = null;

  let row = document.getElementById(`service-${id}`);

  let html = `<tr class="serviceRow" data-service-id="${id}" data-type="serviceStatus">
    <td></td>
    <td></td>
    <td></td>
    <td></td>
    <td></td>
    <td>
      <div class="servicesBox" style="max-width:200px; box-sizing:border-box;">
        <select id="serviceStatus-${id}" style="width:100%; box-sizing:border-box;">
          <option value="active" ${currentStatus === "active" ? "selected" : ""}>active</option>
          <option value="inactive" ${currentStatus === "inactive" ? "selected" : ""}>inactive</option>
        </select>
        <button onclick="saveServiceStatus(${id})">Сохранить</button>
      </div>
    </td>
  </tr>`;

  row.insertAdjacentHTML("afterend", html);
  openedServices = row.nextElementSibling;
}

// функция сохранения статуса через эндпоинт
async function toggleOperatorChoice(id, enabled) {
  const sessionId = sessionStorage.getItem("session_id");

  if (!sessionId) {
    alert("Ошибка: вы не авторизованы как администратор");
    return;
  }

  const res = await fetch(`${API}/services/${id}/operator-choice`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "session-id": sessionId
    },
    body: JSON.stringify({ operator_choice_enabled: !!enabled })
  });

  if (res.ok) {
    resetOpened();
    loadServices();
  } else {
    const err = await res.json();
    alert("Ошибка: " + (err.detail || "Не удалось обновить выбор оператора"));
  }
}

async function saveServiceStatus(id) {
  const select = document.getElementById(`serviceStatus-${id}`);
  const newStatus = select.value;
  // Достаем токен, полученный при авторизации админа
  const sessionId = sessionStorage.getItem("session_id");

  if (!sessionId) {
    alert("Ошибка: вы не авторизованы как администратор");
    return;
  }

  const res = await fetch(`${API}/services/${id}/status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      // Добавляем обязательный заголовок для проверки сессии
      "session-id": sessionId 
    },
    body: JSON.stringify({ status: newStatus })
  });

  if (res.ok) {
    // Если на бэкенде сработал broadcast, 
    // другие клиенты обновятся автоматически через WebSocket
	resetOpened();
    loadServices(); 
  } else {
    const err = await res.json();
    // Обработка случая, если сессия истекла (401)
    if (res.status === 401) {
       alert("Сессия истекла. Пожалуйста, войдите снова.");
       window.location.href = "/login.html"; // пример перенаправления
    } else {
       alert("Ошибка: " + (err.detail || "Не удалось обновить статус"));
    }
  }
}

function editService(id, name) {
  // если уже открыто для этой услуги — закрываем
  if(openedServices && openedServices.dataset.type === "service" && openedServices.dataset.serviceId == id){
    openedServices.remove();
    openedServices = null;
    return;
  }
  // закрываем любое другое открытое окно
  openedServices?.remove();
  openedServices = null;

  let row = document.getElementById(`service-${id}`);
  let html = `<tr class="serviceRow" data-service-id="${id}" data-type="service">
    <td></td>
    <td></td>
    <td></td>
    <td></td>
    <td></td>
    <td>
      <div class="servicesBox" style="max-width:500px; box-sizing:border-box;">
        <input id="serviceInput-${id}" value="${name}" style="width:100%; box-sizing:border-box;">
        <button onclick="saveService(${id})">Сохранить</button>
      </div>
    </td>
  </tr>`;

  row.insertAdjacentHTML("afterend", html);
  openedServices = row.nextElementSibling;
}

async function saveService(id) {
    const input = document.getElementById(`serviceInput-${id}`);
    const name = input.value;
    if (!name) return;

    const sessionId = sessionStorage.getItem("session_id"); // Получаем сессию
    const res = await fetch(`${API}/services/${id}`, {
        method: "PATCH",
        headers: {
            "Content-Type": "application/json",
            "session-id": sessionId // Передаем заголовок
        },
        body: JSON.stringify({ name })
    });

    if (res.ok) {
        // После успешного сохранения просто перезагружаем список
        loadServices();
		resetOpened();
    } else {
        const err = await res.json();
        alert("Ошибка при обновлении: " + (err.detail || "Не удалось сохранить"));
    }
}

async function deleteService(id) {
    if (!confirm("Вы уверены, что хотите удалить эту услугу?")) return;

    const sessionId = sessionStorage.getItem("session_id"); // Получаем сессию

    const res = await fetch(`${API}/services/${id}`, {
        method: "DELETE",
        headers: {
            "session-id": sessionId // Передаем заголовок
        }
    });

    if (res.ok) {
        loadServices(); // Обновляем список, если всё ок
    } else {
        const err = await res.json();
        alert("Ошибка: " + (err.detail || "Не удалось удалить услугу"));
    }
}

async function addService() {
    const nameInput = document.getElementById("newServiceName");
    const name = nameInput.value;
    if (!name) return;

    const sessionId = sessionStorage.getItem("session_id"); // Достаем сессию

    const res = await fetch(`${API}/services`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "session-id": sessionId // Передаем заголовок
        },
        body: JSON.stringify({ name, operator_choice_enabled: false })
    });

    if (res.ok) {
        nameInput.value = ""; // Очищаем поле
        loadServices();       // Обновляем список
    } else {
        const err = await readResponseData(res);
        alert("Ошибка: " + (err.detail || "Не удалось создать услугу"));
    }
}

//////// ОКНА
async function loadWindows() {
	resetOpened();
	// Показываем форму и таблицу обратно
    document.getElementById("form").style.display = "block";
    document.getElementById("table").style.display = "table"; 
    // Удаляем блок статистики, чтобы он не мешал
    const statsContainer = document.getElementById("stats-container");
    if (statsContainer) statsContainer.remove();	
	
	setActiveTab('tab-windows');
    windows = await fetchJSON(`${API}/windows/`);

    let html = `<tr>
        <th>ID</th>
        <th>Название</th>
        <th>Статус</th>
        <th>Действия</th>
    </tr>`;

    for (let w of windows) {
        html += `
        <tr id="window-${w.id}">
            <td>${w.id}</td>
            <td id="windowName-${w.id}">${w.name}</td>
            <td id="windowStatus-${w.id}">${w.status}</td>
            <td>
                <button onclick="editWindow(${w.id},'${w.name}')">Название</button>
                <button onclick="editWindowStatus(${w.id}, '${w.status}')">Статус</button>
				<button onclick="editServices(${w.id})">Услуги</button>
                <button style="background: #ffcccc;" onclick="deleteWindow(${w.id})">Удалить</button>
            </td>
        </tr>`;
    }
    setTable(html);
    setForm(`
    <div class="form">
        <input id="newWindowName" placeholder="Название окна">
        <button onclick="addWindow()">Добавить рабочее место</button>
    </div>
    `);
}

function editWindowStatus(id, currentStatus) {
  // если уже открыто для этого окна — закрываем
  if (openedServices && openedServices.dataset.type === "status" && openedServices.dataset.windowId == id) {
    openedServices.remove();
    openedServices = null;
    return;
  }
  // закрываем любое другое открытое окно/строку статуса
  openedServices?.remove();
  openedServices = null;

  let row = document.getElementById(`window-${id}`);
  let html = `
  <tr class="windowStatusRow" data-window-id="${id}" data-type="status">
    <td></td>
    <td></td>
    <td></td>
    <td>
      <select id="windowStatusSelect-${id}">
        <option value="online" ${currentStatus==="online"?"selected":""}>online</option>
        <option value="break" ${currentStatus==="break"?"selected":""}>break</option>
        <option value="offline" ${currentStatus==="offline"?"selected":""}>offline</option>
      </select>
	  <button onclick="saveWindowStatus(${id})">Сохранить</button>
    </td>
  </tr>
  `;
  row.insertAdjacentHTML("afterend", html);
  openedServices = row.nextElementSibling;
}

async function saveWindowStatus(id) {
  let status = document.getElementById(`windowStatusSelect-${id}`).value;
  // Заменяем fetch на fetchJSON, который автоматически подставит session-id
  let res = await fetchJSON(`${API}/windows/${id}/status`, {
    method: "PATCH",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({status})
  });
  
  if(!res) return; // fetchJSON сам покажет ошибку, если сессия истекла
  
  openedServices.remove();
  resetOpened();
  loadWindows();
}

// Редактирование названия окна на строку ниже
function editWindow(id, name) {
	  // если уже открыто для этого окна — закрываем
	  if(openedServices && openedServices.dataset.type === "window" && openedServices.dataset.windowId == id){
		openedServices.remove();
		openedServices = null;
		return;
	  }
	  // закрываем любое другое открытое окно
	  openedServices?.remove();
	  openedServices = null;
	  
    let row = document.getElementById(`window-${id}`);
	let html = `
	<tr class="windowEditRow" data-window-id="${id}" data-type="window">
	  <td></td>
	  <td></td>
	  <td></td>
	  <td>
		<input id="windowInput-${id}" value="${name}" style="width:10%; box-sizing:border-box;">
		<button onclick="saveWindow(${id})">Сохранить</button>
	  </td>
	</tr>
	`;
    row.insertAdjacentHTML("afterend", html);
    openedServices = row.nextElementSibling;
}

async function saveWindow(id) {
    const inputElement = document.getElementById(`windowInput-${id}`);
    if (!inputElement) return;
    const name = inputElement.value.trim();
    if (!name) return alert("Введите название окна");
    // Используем fetchJSON вместо обычного fetch для автоматической авторизации
    const res = await fetchJSON(`${API}/windows/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name })
    });
    // Если res не определен (undefined), значит fetchJSON перенаправил на логин или выдал ошибку
    if (res) {
        // Опционально: можно добавить уведомление об успехе
        console.log(`Рабочее место ${id} успешно обновлено`);
        resetOpened();
		loadWindows();
		
    }
}
// Добавление окна
async function addWindow() {
    const input = document.getElementById("newWindowName");
    const name = input.value.trim();
    
    if (!name) return alert("Введите название нового окна");
    // Используем fetchJSON для автоматической передачи session-id
    const res = await fetchJSON(`${API}/windows/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name })
    });
    // Если запрос успешен (res не undefined)
    if (res) {
        input.value = ""; // Очищаем поле ввода
        alert("Рабочее место успешно добавлено");
        loadWindows();    // Обновляем список окон
    }
}

// Удаление окна с проверкой на наличие услуг
async function deleteWindow(id) {
    try {
        // 1. Загружаем список услуг, привязанных к этому окну
        // Мы делаем запрос к эндпоинту, который возвращает услуги конкретного окна
        const linkedServices = await fetchJSON(`${API}/window-services/${id}`);
        // 2. Если массив не пустой, значит услуги есть — прерываем удаление
        if (Array.isArray(linkedServices) && linkedServices.length > 0) {
            alert("Нельзя удалить рабочее место: сначала удалите все услуги, привязанные к этому рабочему месту в меню 'Услуги'!");
            return;
        }
        // 3. Если услуг нет, запрашиваем подтверждение
        if (!confirm("Вы уверены, что хотите удалить это рабочее место?")) return;
        // 4. Отправляем запрос на удаление
        const res = await fetchJSON(`${API}/windows/${id}`, {
            method: "DELETE"
        });
        if (res) {
            alert("Рабочее успешно удалено");
            loadWindows(); // Обновляем таблицу
        }
    } catch (e) {
        console.error("Ошибка при проверке или удалении окна:", e);
        alert("Произошла ошибка. Проверьте соединение с сервером.");
    }
}

function getWindowName(id){

let w=windows.find(x=>x.id===id)
return w?w.name:"-"
}

//////// ОПЕРАТОРЫ
async function loadOperators(){
	resetOpened();
	// Показываем форму и таблицу обратно
    document.getElementById("form").style.display = "block";
    document.getElementById("table").style.display = "table";
    // Удаляем блок статистики, чтобы он не мешал
    const statsContainer = document.getElementById("stats-container");
    if (statsContainer) statsContainer.remove();	
	setActiveTab('tab-operators');
    // fetchJSON сам подставит session-id и выкинет на логин при ошибке 401
    windows = await fetchJSON(`${API}/windows/`);
    operators = await fetchJSON(`${API}/operators/`);
    services = await fetchJSON(`${API}/services/`);
    operators.sort((a,b) => a.id - b.id);

    let html = `<tr><th>ID</th><th>Имя</th><th>Рабочее место</th><th>Действия</th></tr>`;

    for(let op of operators){
        html += `
        <tr id="row-${op.id}">
          <td>${op.id}</td>
          <td id="name-${op.id}">${op.name}</td>
          <td id="window-${op.id}">${getWindowName(op.window_id)}</td>
          <td>
            <button onclick="editOperatorName(${op.id},'${op.name}')">Имя</button>
            <button onclick="editOperatorWindow(${op.id},${op.window_id})">Рабочее место</button>
            <button onclick="editLoginPassword(${op.id})">Данные</button>
            <button style="background: #ffcccc;" onclick="deleteOperator(${op.id})">Удалить</button>
          </td>
        </tr>`;
    }

    setTable(html);
    setForm(`
        <div class="form">
          <input id="newOperatorName" placeholder="Имя оператора">
          <input id="newOperatorLogin" placeholder="Логин">
          <input id="newOperatorPassword" placeholder="Пароль">
          <button onclick="addOperator()">Добавить</button>
        </div>
    `);
}

//////// имя оператора
function editOperatorName(id,name){
  // если уже открыто для этого оператора — закрываем
  if(openedServices && openedServices.dataset.type === "name" && openedServices.dataset.operatorId == id){
    openedServices.remove();
    openedServices = null;
    return;
  }
  // закрываем любое другое открытое окно
  openedServices?.remove();
  openedServices = null;

  let row = document.getElementById("row-"+id);

  let html = '<tr class="nameRow" data-operator-id="'+id+'" data-type="name">' +
             '<td></td><td></td><td></td>' +
             '<td><input id="nameInput-'+id+'" value="'+name+'"> ' +
             '<button onclick="saveOperatorName('+id+')">OK</button></td></tr>';

  row.insertAdjacentHTML("afterend", html);
  openedServices = row.nextElementSibling;
}

async function saveOperatorName(id){

let name=document.getElementById(`nameInput-${id}`).value

const res = await fetchJSON(`${API}/operators/${id}`,{
method:"PATCH",
headers:{"Content-Type":"application/json"},
body:JSON.stringify({name})
});

if (!res) return;

loadOperators();
resetOpened();
}

//////// окно оператора
function editOperatorWindow(id,current){
  if(openedServices && openedServices.dataset.type === "window" && openedServices.dataset.operatorId == id){
    openedServices.remove();
    openedServices = null;
    return;
  }
  openedServices?.remove();

  let html = '<tr class="windowRow" data-operator-id="'+id+'" data-type="window">' +
             '<td></td><td></td><td></td>' +
             '<td><select id="windowSelect-'+id+'">';
  html += '<option value="">Нет окна</option>';
  for(let w of windows){
    html += '<option value="'+w.id+'" '+(w.id===current?"selected":"")+'>'+w.name+'</option>';
  }
  html += '</select> <button onclick="saveOperatorWindow('+id+')">OK</button></td></tr>';

  let row = document.getElementById("row-"+id);
  row.insertAdjacentHTML("afterend",html);

  openedServices = row.nextElementSibling;
}

async function saveOperatorWindow(id){

let val=document.getElementById(`windowSelect-${id}`).value
let window_id=val===""?null:parseInt(val)

const r = await fetch(`${API}/operators/${id}`,{
method:"PATCH",
headers:{
    "Content-Type":"application/json",
    "session-id": sessionStorage.getItem("session_id")
},
body:JSON.stringify({window_id})
});

if(!r.ok){
  if (r.status === 401 || r.status === 403) {
    alert("Сессия истекла или недостаточно прав. Войдите снова.");
    window.location.href = "login.html";
    return;
  }
  let err = {};
  try { err = await r.json(); } catch (_) {}
  alert(err.detail || "Не удалось сохранить рабочее место оператора");
  return;
}
loadOperators();
resetOpened();
}


//////// услуги окна
async function editServices(window_id) {
    if (openedServices && openedServices.dataset.windowId == window_id) {
        openedServices.remove();
        openedServices = null;
        return;
    }

    openedServices?.remove();
    openedServices = null;

    let ws = await fetchJSON(`${API}/window-services/${window_id}`);

    let selectedMap = {};
    if (Array.isArray(ws)) {
        ws.forEach(item => {
            selectedMap[item.service_id] = item.priority ?? 1;
        });
    }

    let html = `<tr id="servicesRow" data-window-id="${window_id}">
        <td colspan="4">
            <div class="servicesBoxServices" style="max-width:600px; background:#fff; padding:15px; border:1px solid #ccc; border-radius:8px; margin:10px auto;">
                <b>Настройка услуг (меньше число - выше приоритет)</b><br><br>`;

	if (!services.length) {
    services = await fetchJSON(`${API}/services/`);
}

    for (let s of services) {
        let isActive = selectedMap.hasOwnProperty(s.id);
        let checked = isActive ? "checked" : "";
        let prio = isActive ? selectedMap[s.id] : 1;
        let disabled = isActive ? "" : "disabled";

        html += `
            <div style="margin-bottom:8px; display:flex; align-items:center;">
                <label style="flex:1">
                    <input type="checkbox" class="srv-check" value="${s.id}" ${checked} 
                           onchange="document.getElementById('prio-${s.id}').disabled = !this.checked"> 
                    ${s.name}
                </label>
                <input type="number" id="prio-${s.id}" class="srv-prio" 
                       value="${prio}" min="1" max="100" 
                       style="width:60px" ${disabled}>
            </div>`;
    }

    html += `<br><button onclick="saveServicesWithPriority(${window_id})">Сохранить</button>
            </div>
        </td>
    </tr>`;

    let row = document.getElementById(`window-${window_id}`);
    row.insertAdjacentHTML("afterend", html);
    openedServices = document.getElementById("servicesRow");
}

async function saveServicesWithPriority(windowId) {
    const services = [];

    document.querySelectorAll('.srv-check').forEach(cb => {
        if (cb.checked) {
            const serviceId = parseInt(cb.value);
            const prioInput = document.getElementById(`prio-${serviceId}`);

            services.push({
                service_id: serviceId,
                priority: parseInt(prioInput.value) || 1
            });
        }
    });

    const payload = { services };

    const res = await fetchJSON(`${API}/window-services/${windowId}`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
    });

    if (res) {
        alert("Настройки сохранены");
        loadWindows();
		resetOpened();
    }
}

async function saveServices(window_id) {
    const container = document.getElementById("servicesRow");
    // Находим все чекбоксы услуг
    const checkboxes = container.querySelectorAll(".srv-checkbox");
    
    let servicesToSave = [];
    
    checkboxes.forEach(cb => {
        if (cb.checked) {
            const srvId = parseInt(cb.value);
            // Находим соответствующий инпут приоритета по ID
            const prioInput = document.getElementById(`prio-input-${srvId}`);
            
            servicesToSave.push({
                service_id: srvId,
                priority: parseInt(prioInput.value) || 1
            });
        }
    });

    try {
        // Важно: отправляем объект с ключом "services", как ожидает Pydantic на бэке
		const res = await fetchJSON(`${API}/window-services/${windowId}`, {
			method: "PUT",
			headers: {
				"Content-Type": "application/json"
			},
			body: JSON.stringify(payload)
		});

        alert("Изменения успешно сохранены");
        // Закрываем строку настроек
        openedServices.remove();
        openedServices = null;
    } catch (e) {
        console.error("Save error:", e);
        alert("Ошибка при сохранении приоритетов");
    }
	resetOpened();
}

//////// ДОБАВЛЕНИЕ ОПЕРАТОРА
async function addOperator() {
  const loginInput = document.getElementById("newOperatorLogin");
  const passwordInput = document.getElementById("newOperatorPassword");
  const nameInput = document.getElementById("newOperatorName");

  const login = loginInput.value.trim();
  const password = passwordInput.value.trim();
  const name = nameInput.value.trim();

  if (!login || !password || !name) return alert("Заполните все поля");
  // Используем fetchJSON: он сам добавит header "session-id"
  // и вернет тело ответа (JSON), если статус 200-299.
  // Если случится ошибка (например 400 или 401), fetchJSON сам покажет alert или редиректнет.
  const res = await fetchJSON(`${API}/operators/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ login, password, name, window_id: null })
  });
  // Если res определен, значит запрос прошел успешно
  if (res) {
    // Очистка полей
    loginInput.value = "";
    passwordInput.value = "";
    nameInput.value = "";

    alert("Оператор успешно добавлен");
    loadOperators();
  }
}

//////// ОЧЕРЕДЬ
async function loadTickets(){

let tickets=await fetchJSON(`${API}/tickets/`)
let services=await fetchJSON(`${API}/services/`)

let html=`<tr>
<th>Номер</th>
<th>Услуга</th>
<th>Статус</th>
</tr>`

for(let t of tickets){

let service = services.find(s => s.id === t.service_id)

html+=`
<tr>
<td>${t.number}</td>
<td>${service ? service.name : "Unknown"}</td>
<td>${t.status}</td>
</tr>`
}

setTable(html)
setForm("")
}

async function editLoginPassword(operator_id) {
    // Если окно уже открыто для этого оператора — закрываем его
    if (openedServices && openedServices.dataset.operatorId == operator_id) {
        openedServices.remove();
        openedServices = null;
        return;
    }
    // Закрываем любое другое открытое окно
    openedServices?.remove();
    openedServices = null;
    // Получаем данные оператора
    let op = operators.find(o => o.id === operator_id);
    let currentLogin = op.login || "";
    let currentPassword = op.password || ""; // чтобы пароль был виден

let html = `
<tr id="loginPassRow" data-operator-id="${operator_id}">
<td></td>
<td></td>
<td></td>
<td>
<div class="servicesBox">
<b>Сменить логин и пароль</b><br><br>
<label><input id="loginInput-${operator_id}" value="${currentLogin}"></label><br>
<label><input id="passwordInput-${operator_id}" value="${currentPassword}"></label><br><br>
<button onclick="saveLoginPassword(${operator_id})">Сохранить</button>
</div>
</td>
</tr>
`;

    let row = document.getElementById(`row-${operator_id}`);
    row.insertAdjacentHTML("afterend", html);

    openedServices = document.getElementById("loginPassRow");
}

async function saveLoginPassword(operator_id) {
    let login = document.getElementById(`loginInput-${operator_id}`).value.trim();
    let password = document.getElementById(`passwordInput-${operator_id}`).value.trim();

    if(!login || !password) return alert("Заполните оба поля");
    // Извлекаем токен администратора из хранилища
    const sessionId = sessionStorage.getItem("session_id");

    if (!sessionId) {
        alert("Ошибка: у вас нет прав для выполнения этого действия");
        return;
    }

    let res = await fetch(`${API}/operators/${operator_id}/login`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json",
            // Передаем токен бэкенду
            "session-id": sessionId
        },
        body: JSON.stringify({login, password})
    });

    if(!res.ok){
        // Проверяем, не вызвана ли ошибка отсутствием прав (401 или 403)
        if (res.status === 401 || res.status === 403) {
            return alert("Ошибка доступа: только администратор может менять пароли");
        }
        let err = await res.text();
        return alert("Ошибка при обновлении: " + err);
    }

    alert("Данные входа обновлены");
    // Очистка интерфейса (из вашего исходного кода)
    if (typeof openedServices !== 'undefined' && openedServices) {
        openedServices.remove();
        openedServices = null;
    }
	resetOpened();
    loadOperators();
}

async function loadExtraSettings() {
	resetOpened();
    document.getElementById("form").style.display = "block";
    document.getElementById("table").style.display = "none";
    setTable("");

    const statsContainer = document.getElementById("stats-container");
    if (statsContainer) statsContainer.remove();

    setActiveTab("tab-settings");

    const settings = await fetchJSON(`${API}/admin/settings`);
    if (!settings) return;

    setForm(`
        <div class="form settings-form">
            <h3 class="settings-title">Дополнительные настройки</h3>

            <section class="settings-section">
                <h4 class="settings-section-title">Терминал</h4>
                <label class="settings-checkbox-row">
                    <input type="checkbox" id="setting-print-ticket" ${settings.print_ticket ? "checked" : ""}>
                    Печатать талон на терминале
                </label>

                <label class="settings-checkbox-row">
                    <input type="checkbox" id="setting-show-print-badge" ${settings.show_print_badge ? "checked" : ""}>
                    Показывать режим печати на терминале
                </label>
                <label class="settings-checkbox-row">
                    <input type="checkbox" id="setting-hide-services-without-online" ${settings.hide_services_without_online_operators ? "checked" : ""}>
                    Скрывать услуги на терминале, если по ним нет активных операторов 
                </label>
            </section>

            <section class="settings-section">
                <h4 class="settings-section-title">Оператор</h4>
                <label class="settings-field-row">
                    <span class="settings-label">Статус окна по умолчанию при входе оператора:</span>
                    <select id="setting-default-operator-status" class="settings-select">
                        <option value="online" ${settings.default_operator_status === "online" ? "selected" : ""}>online</option>
                        <option value="break" ${settings.default_operator_status === "break" ? "selected" : ""}>break</option>
                        <option value="offline" ${settings.default_operator_status === "offline" ? "selected" : ""}>offline</option>
                    </select>
                </label>

                <label class="settings-field-row">
                    <span class="settings-label">Если оператор вышел с активным тикетом:</span>
                    <select id="setting-active-ticket-on-logout" class="settings-select settings-select-wide">
                        <option value="return_to_queue" ${settings.active_ticket_on_operator_logout === "return_to_queue" ? "selected" : ""}>Вернуть обратно в очередь</option>
                        <option value="keep_with_operator" ${settings.active_ticket_on_operator_logout === "keep_with_operator" ? "selected" : ""}>Оставить за оператором</option>
					</select>
                </label>
            </section>
			
		<section class="settings-section">
			<h4 class="settings-section-title">Очередь</h4>

			<label class="settings-field-row">
				<span class="settings-label">Режим очереди:</span>
				<select id="setting-queue-mode" class="settings-select settings-select-wide">
					<option value="priority_fifo" ${settings.queue_mode === "priority_fifo" ? "selected" : ""}>
						Приоритет услуг + FIFO
					</option>
					<option value="dynamic_operator_distribution" ${settings.queue_mode === "dynamic_operator_distribution" ? "selected" : ""}>
						Динамическое распределение по операторам
					</option>
				</select>
			</label>
		</section>


        <section class="settings-section">
            <h4 class="settings-section-title">Табло и озвучка</h4>

            <label class="settings-field-row">
                <span class="settings-label">Сообщение вызова / озвучки:</span>
                <input
                    id="setting-call-message-template"
                    class="settings-input settings-input-wide"
                    value="${settings.call_message_template || "Талон <number> подойдите к окну <window>"}"
                >
            </label>

            <small class="settings-hint">
                Можно менять любой текст, но оставьте <b>&lt;number&gt;</b> и <b>&lt;window&gt;</b>.
                Например: <b>Талон &lt;number&gt;, подойдите к окну &lt;window&gt;</b>
            </small>

            <label class="settings-field-row">
                <span class="settings-label">Отображение вызванного талона на табло:</span>
                <input
                    id="setting-board-ticket-template"
                    class="settings-input settings-input-wide"
                    value="${settings.board_ticket_template || "Билет <number> -> окно <window>"}"
                >
            </label>

            <small class="settings-hint">
                Например: <b>&lt;number&gt; → &lt;window&gt;</b> или <b>Билет &lt;number&gt; / окно &lt;window&gt;</b>
            </small>
        </section>

            <div class="settings-actions">
                <button onclick="saveExtraSettings()">Сохранить настройки</button>
            </div>
        </div>
    `);
}

async function saveExtraSettings() {
	const payload = {
		print_ticket: document.getElementById("setting-print-ticket").checked,
		show_print_badge: document.getElementById("setting-show-print-badge").checked,
		default_operator_status: document.getElementById("setting-default-operator-status").value,
		active_ticket_on_operator_logout: document.getElementById("setting-active-ticket-on-logout").value,
		hide_services_without_online_operators: document.getElementById("setting-hide-services-without-online").checked,
		queue_mode: document.getElementById("setting-queue-mode").value,

		call_message_template: document.getElementById("setting-call-message-template").value.trim(),
		board_ticket_template: document.getElementById("setting-board-ticket-template").value.trim()
	};

    if (!payload.call_message_template.includes("<number>") || !payload.call_message_template.includes("<window>")) {
        alert("Шаблон озвучки должен содержать <number> и <window>");
        return;
    }

    if (!payload.board_ticket_template.includes("<number>") || !payload.board_ticket_template.includes("<window>")) {
        alert("Шаблон табло должен содержать <number> и <window>");
        return;
    }

    const res = await fetchJSON(`${API}/admin/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });

    if (res) {
        alert("Настройки сохранены");
        loadExtraSettings();
    }
}

function loadStats() {
    // Открываем Grafana в новой вкладке вместо embedded-режима.
    window.open(GRAFANA, "_blank", "noopener,noreferrer");
    setActiveTab('tab-stats');
}

//////// КАРТА
let officeMap = {version: 1, width: 1200, height: 700, objects: []};
let selectedMapObjectId = null;
let mapWindows = [];
let mapOperators = [];
let mapServices = [];
let mapWindowServices = {};
let mapDirty = false;
let mapZoom = 1;
let mapWorldWidth = 6000;
let mapWorldHeight = 4000;
const MAP_GRID_SIZE = 20;
let mapSnapEnabled = localStorage.getItem("map_snap_enabled") === "true";

async function mapRequest(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: {
            ...options.headers,
            "session-id": sessionStorage.getItem("session_id")
        }
    });
    const data = await readResponseData(response);
    if (!response.ok) throw new Error(data.detail || "Ошибка работы с картой");
    return data;
}

async function loadMapEditor() {
    resetOpened();
    document.getElementById("form").style.display = "block";
    document.getElementById("table").style.display = "none";
    setTable("");
    document.getElementById("stats-container")?.remove();
    setActiveTab("tab-map");

    setForm(`<div class="map-loading">Загрузка карты...</div>`);
    try {
        [officeMap, mapWindows, mapOperators, mapServices] = await Promise.all([
            mapRequest(`${API}/admin/map`),
            fetchJSON(`${API}/windows/?limit=500`),
            fetchJSON(`${API}/operators/?limit=500`),
            fetchJSON(`${API}/services/?limit=500`)
        ]);
        if (!Array.isArray(mapWindows)) mapWindows = [];
        if (!Array.isArray(mapOperators)) mapOperators = [];
        if (!Array.isArray(mapServices)) mapServices = [];
        mapWindowServices = {};
        mapWorldWidth = Math.max(6000, officeMap.width);
        mapWorldHeight = Math.max(4000, officeMap.height);
        mapZoom = 1;
        selectedMapObjectId = null;
        mapDirty = false;
        renderMapEditor();
    } catch (error) {
        setForm(`<div class="map-error">${escapeMapHtml(error.message)}</div>`);
    }
}

function renderMapEditor() {
    setForm(`
        <div class="map-editor">
            <div class="map-toolbar">
                <button class="map-tool-room" onclick="addMapObject('room')">Добавить помещение</button>
                <button class="map-tool-workplace" onclick="addMapObject('workplace')">Добавить физический стол</button>
                <div class="map-zoom-controls">
                    <button title="Отдалить" onclick="changeMapZoom(-0.15)">−</button>
                    <button id="map-zoom-value" class="map-zoom-value" title="Вернуть масштаб 100%" onclick="resetMapZoom()">100%</button>
                    <button title="Приблизить" onclick="changeMapZoom(0.15)">+</button>
                </div>
                <label class="map-snap-toggle">
                    <input type="checkbox" ${mapSnapEnabled ? "checked" : ""}
                        onchange="toggleMapSnap(this.checked)">
                    <span>Привязка к сетке</span>
                </label>
                <span class="map-toolbar-spacer"></span>
                <span id="map-save-state" class="map-save-state">Все изменения сохранены</span>
                <button class="map-save-button" onclick="saveOfficeMap()">Сохранить карту</button>
            </div>
            <div class="map-editor-body">
                <div id="map-viewport" class="map-canvas-scroll">
                    <div id="map-canvas-stage" class="map-canvas-stage">
                        <div id="map-canvas" class="map-canvas"></div>
                    </div>
                </div>
                <aside id="map-properties" class="map-properties"></aside>
            </div>
        </div>
    `);

    const canvas = document.getElementById("map-canvas");
    initializeMapViewport();
    renderMapObjects();
    renderMapProperties();
    updateMapSaveState();
}

function initializeMapViewport() {
    updateMapSurfaceSize();
    const viewport = document.getElementById("map-viewport");
    const canvas = document.getElementById("map-canvas");

    viewport.addEventListener("wheel", event => {
        event.preventDefault();
        setMapZoom(mapZoom + (event.deltaY < 0 ? 0.12 : -0.12), event.clientX, event.clientY);
    }, {passive: false});

    viewport.addEventListener("pointerdown", event => {
        const panRequested = event.button === 1 || (event.button === 0 && event.target === canvas);
        if (!panRequested) return;
        event.preventDefault();
        if (event.button === 0) selectMapObject(null);
        const startX = event.clientX;
        const startY = event.clientY;
        const startLeft = viewport.scrollLeft;
        const startTop = viewport.scrollTop;
        viewport.classList.add("panning");
        viewport.setPointerCapture(event.pointerId);

        const move = moveEvent => {
            viewport.scrollLeft = startLeft - (moveEvent.clientX - startX);
            viewport.scrollTop = startTop - (moveEvent.clientY - startY);
        };
        const stop = () => {
            viewport.classList.remove("panning");
            viewport.removeEventListener("pointermove", move);
        };
        viewport.addEventListener("pointermove", move);
        viewport.addEventListener("pointerup", stop, {once: true});
        viewport.addEventListener("pointercancel", stop, {once: true});
    });
}

function updateMapSurfaceSize() {
    const canvas = document.getElementById("map-canvas");
    const stage = document.getElementById("map-canvas-stage");
    if (!canvas || !stage) return;
    canvas.style.width = `${mapWorldWidth}px`;
    canvas.style.height = `${mapWorldHeight}px`;
    canvas.style.transform = `scale(${mapZoom})`;
    stage.style.width = `${mapWorldWidth * mapZoom}px`;
    stage.style.height = `${mapWorldHeight * mapZoom}px`;
    const value = document.getElementById("map-zoom-value");
    if (value) value.textContent = `${Math.round(mapZoom * 100)}%`;
}

function setMapZoom(value, clientX, clientY) {
    const viewport = document.getElementById("map-viewport");
    const stage = document.getElementById("map-canvas-stage");
    if (!viewport || !stage) return;
    const nextZoom = Math.max(0.25, Math.min(2.5, Math.round(value * 100) / 100));
    if (nextZoom === mapZoom) return;

    const rect = viewport.getBoundingClientRect();
    const anchorX = clientX === undefined ? viewport.clientWidth / 2 : clientX - rect.left;
    const anchorY = clientY === undefined ? viewport.clientHeight / 2 : clientY - rect.top;
    const worldX = (viewport.scrollLeft + anchorX - stage.offsetLeft) / mapZoom;
    const worldY = (viewport.scrollTop + anchorY - stage.offsetTop) / mapZoom;
    mapZoom = nextZoom;
    updateMapSurfaceSize();
    viewport.scrollLeft = stage.offsetLeft + worldX * mapZoom - anchorX;
    viewport.scrollTop = stage.offsetTop + worldY * mapZoom - anchorY;
}

function changeMapZoom(delta) {
    setMapZoom(mapZoom + delta);
}

function resetMapZoom() {
    setMapZoom(1);
}

function toggleMapSnap(enabled) {
    mapSnapEnabled = enabled;
    localStorage.setItem("map_snap_enabled", String(enabled));
}

function snapMapValue(value) {
    return mapSnapEnabled ? Math.round(value / MAP_GRID_SIZE) * MAP_GRID_SIZE : value;
}

function renderMapObjects() {
    const canvas = document.getElementById("map-canvas");
    if (!canvas) return;
    canvas.innerHTML = "";

    const objects = [...officeMap.objects].sort((a, b) =>
        (a.type === "room" ? 0 : 1) - (b.type === "room" ? 0 : 1)
    );

    for (const object of objects) {
        const element = document.createElement("div");
        element.className = `map-object map-${object.type}`;
        if (object.id === selectedMapObjectId) element.classList.add("selected");
        element.dataset.objectId = object.id;
        element.style.left = `${object.x}px`;
        element.style.top = `${object.y}px`;
        element.style.width = `${object.width}px`;
        element.style.height = `${object.height}px`;

        const title = document.createElement("span");
        title.className = "map-object-title";
        title.textContent = mapObjectTitle(object);
        element.appendChild(title);

        const resizeHandle = document.createElement("span");
        resizeHandle.className = "map-resize-handle";
        resizeHandle.title = "Изменить размер";
        resizeHandle.addEventListener("pointerdown", event => startMapResize(event, object));
        element.appendChild(resizeHandle);

        element.addEventListener("pointerdown", event => startMapDrag(event, object));
        canvas.appendChild(element);
    }
}

function mapObjectTitle(object) {
    if (object.type === "room") return object.label || "Помещение";
    const windowItem = mapWindows.find(item => item.id === object.window_id);
    return object.label || windowItem?.name || "Физический стол";
}

function addMapObject(type) {
    const sameTypeCount = officeMap.objects.filter(item => item.type === type).length;
    const isRoom = type === "room";
    const width = isRoom ? 420 : 100;
    const height = isRoom ? 260 : 70;
    const offset = (sameTypeCount * 24) % 240;
    const object = {
        id: createMapObjectId(),
        type,
        x: snapMapValue(Math.min(40 + offset, mapWorldWidth - width)),
        y: snapMapValue(Math.min(40 + offset, mapWorldHeight - height)),
        width,
        height,
        label: `${isRoom ? "Помещение" : "Физический стол"} ${sameTypeCount + 1}`,
        window_id: null
    };
    officeMap.objects.push(object);
    selectedMapObjectId = object.id;
    markMapDirty();
    renderMapObjects();
    renderMapProperties();
}

function createMapObjectId() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    return `map-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function selectMapObject(id) {
    selectedMapObjectId = id;
    renderMapObjects();
    renderMapProperties();
}

function startMapDrag(event, object) {
    if (event.button !== 0 || event.target.classList.contains("map-resize-handle")) return;
    event.preventDefault();
    selectMapObjectFromPointer(object.id);
    const startX = event.clientX;
    const startY = event.clientY;
    const originalX = object.x;
    const originalY = object.y;
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);

    const move = moveEvent => {
        object.x = clampMapValue(
            snapMapValue(originalX + (moveEvent.clientX - startX) / mapZoom),
            0,
            mapWorldWidth - object.width
        );
        object.y = clampMapValue(
            snapMapValue(originalY + (moveEvent.clientY - startY) / mapZoom),
            0,
            mapWorldHeight - object.height
        );
        ensureMapWorldSpace(object);
        target.style.left = `${object.x}px`;
        target.style.top = `${object.y}px`;
        markMapDirty();
    };
    const stop = () => {
        target.removeEventListener("pointermove", move);
        renderMapProperties();
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", stop, {once: true});
    target.addEventListener("pointercancel", stop, {once: true});
}

function startMapResize(event, object) {
    event.preventDefault();
    event.stopPropagation();
    selectMapObjectFromPointer(object.id);
    const startX = event.clientX;
    const startY = event.clientY;
    const originalWidth = object.width;
    const originalHeight = object.height;
    const baseMinWidth = object.type === "room" ? 180 : 70;
    const baseMinHeight = object.type === "room" ? 120 : 50;
    const minWidth = mapSnapEnabled
        ? Math.ceil(baseMinWidth / MAP_GRID_SIZE) * MAP_GRID_SIZE
        : baseMinWidth;
    const minHeight = mapSnapEnabled
        ? Math.ceil(baseMinHeight / MAP_GRID_SIZE) * MAP_GRID_SIZE
        : baseMinHeight;
    const target = event.currentTarget;
    const objectElement = target.parentElement;
    target.setPointerCapture(event.pointerId);

    const move = moveEvent => {
        object.width = clampMapValue(
            snapMapValue(originalWidth + (moveEvent.clientX - startX) / mapZoom),
            minWidth,
            mapWorldWidth - object.x
        );
        object.height = clampMapValue(
            snapMapValue(originalHeight + (moveEvent.clientY - startY) / mapZoom),
            minHeight,
            mapWorldHeight - object.y
        );
        ensureMapWorldSpace(object);
        objectElement.style.width = `${object.width}px`;
        objectElement.style.height = `${object.height}px`;
        markMapDirty();
    };
    const stop = () => {
        target.removeEventListener("pointermove", move);
        renderMapProperties();
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", stop, {once: true});
    target.addEventListener("pointercancel", stop, {once: true});
}

function selectMapObjectFromPointer(id) {
    selectedMapObjectId = id;
    document.querySelectorAll(".map-object").forEach(element => {
        element.classList.toggle("selected", element.dataset.objectId === id);
    });
    renderMapProperties();
}

function clampMapValue(value, min, max) {
    return Math.round(Math.max(min, Math.min(max, value)));
}

function ensureMapWorldSpace(object) {
    let expanded = false;
    if (object.x + object.width > mapWorldWidth - 500 && mapWorldWidth < 50000) {
        mapWorldWidth = Math.min(50000, mapWorldWidth + 2000);
        expanded = true;
    }
    if (object.y + object.height > mapWorldHeight - 500 && mapWorldHeight < 50000) {
        mapWorldHeight = Math.min(50000, mapWorldHeight + 2000);
        expanded = true;
    }
    if (expanded) updateMapSurfaceSize();
}

function renderMapProperties() {
    const panel = document.getElementById("map-properties");
    if (!panel) return;
    const object = officeMap.objects.find(item => item.id === selectedMapObjectId);
    if (!object) {
        panel.innerHTML = `
            <h3>Карта</h3>
            <p>Добавьте или выберите объект, чтобы изменить его параметры.</p>
            <p class="map-properties-hint">Объекты можно перетаскивать и растягивать за угол.</p>
        `;
        return;
    }

    const windowOptions = mapWindows.map(item =>
        `<option value="${item.id}" ${item.id === object.window_id ? "selected" : ""}>${escapeMapHtml(item.name)}</option>`
    ).join("");
    const windowSettings = object.type === "workplace" && object.window_id
        ? renderMapWindowSettings(object.window_id)
        : "";
    panel.innerHTML = `
        <h3>${object.type === "room" ? "Помещение" : "Физический стол"}</h3>
        <label class="map-property-field">
            <span>Название</span>
            <input id="map-object-label" maxlength="100" value="${escapeMapHtml(object.label)}">
        </label>
        ${object.type === "workplace" ? `
            <label class="map-property-field">
                <span>Рабочее место</span>
                <select id="map-object-window">
                    <option value="">Не привязано</option>
                    ${windowOptions}
                </select>
                <button class="map-inline-create" onclick="createMapWindowForSelected()">Создать рабочее место</button>
            </label>
        ` : ""}
        <div class="map-object-size">${object.width} × ${object.height}, позиция ${object.x} × ${object.y}</div>
        ${windowSettings}
        <button class="map-delete-button" onclick="deleteSelectedMapObject()">Удалить объект</button>
    `;

    document.getElementById("map-object-label").addEventListener("input", event => {
        object.label = event.target.value;
        const title = document.querySelector(`[data-object-id="${object.id}"] .map-object-title`);
        if (title) title.textContent = mapObjectTitle(object);
        markMapDirty();
    });
    document.getElementById("map-object-window")?.addEventListener("change", event => {
        object.window_id = event.target.value ? Number(event.target.value) : null;
        renderMapObjects();
        markMapDirty();
        renderMapProperties();
    });

    panel.querySelectorAll(".map-service-check").forEach(checkbox => {
        checkbox.addEventListener("change", event => {
            const priority = panel.querySelector(`[data-priority-for="${event.target.dataset.serviceId}"]`);
            if (priority) priority.disabled = !event.target.checked;
        });
    });

    if (object.window_id && mapWindowServices[object.window_id] === undefined) {
        loadMapWindowServices(object.window_id, object.id);
    }
}

function renderMapWindowSettings(windowId) {
    const windowItem = mapWindows.find(item => item.id === windowId);
    const assignedOperator = mapOperators.find(operator => operator.window_id === windowId);
    const operatorOptions = mapOperators.map(operator => {
        const otherWindow = operator.window_id && operator.window_id !== windowId
            ? mapWindows.find(item => item.id === operator.window_id)
            : null;
        const disabled = otherWindow ? "disabled" : "";
        const selected = assignedOperator?.id === operator.id ? "selected" : "";
        const suffix = otherWindow ? ` — ${otherWindow.name}` : "";
        return `<option value="${operator.id}" ${selected} ${disabled}>${escapeMapHtml(operator.name + suffix)}</option>`;
    }).join("");

    const linkedServices = mapWindowServices[windowId];
    let servicesHtml = `<div class="map-window-loading">Загрузка услуг...</div>`;
    if (Array.isArray(linkedServices)) {
        const priorities = new Map(linkedServices.map(item => [item.service_id, item.priority ?? 1]));
        servicesHtml = mapServices.length ? mapServices.map(service => {
            const checked = priorities.has(service.id);
            return `
                <div class="map-service-row">
                    <label class="map-service-checkbox" title="Включить услугу">
                        <input class="map-service-check" type="checkbox" data-service-id="${service.id}" ${checked ? "checked" : ""}>
                    </label>
                    <button class="map-service-name" title="Изменить название услуги"
                        onclick="renameMapService(${service.id})">${escapeMapHtml(service.name)}</button>
                    <input class="map-service-priority" type="number" min="1" max="100"
                        data-priority-for="${service.id}" value="${priorities.get(service.id) ?? 1}" ${checked ? "" : "disabled"}>
                </div>
            `;
        }).join("") : `<div class="map-window-loading">Услуг пока нет</div>`;
    }

    return `
        <section class="map-window-settings">
            <h4>Настройка рабочего места</h4>
            <label class="map-settings-field">
                <span>Название рабочего места в БД</span>
                <input id="map-window-name" value="${escapeMapHtml(windowItem?.name || "")}" placeholder="Название">
            </label>
            <label class="map-settings-field">
                <span>Статус</span>
            <select id="map-window-status">
                <option value="online" ${windowItem?.status === "online" ? "selected" : ""}>online</option>
                <option value="break" ${windowItem?.status === "break" ? "selected" : ""}>break</option>
                <option value="offline" ${windowItem?.status === "offline" ? "selected" : ""}>offline</option>
            </select>
            </label>
            <button onclick="saveMapWindow(${windowId})">Сохранить рабочее место</button>
        </section>
        <section class="map-window-settings">
            <h4>Оператор окна</h4>
            <select id="map-window-operator">
                <option value="">Не назначен</option>
                ${operatorOptions}
            </select>
            <button onclick="saveMapWindowOperator(${windowId})">Сохранить оператора</button>
            ${assignedOperator ? `
                <div class="map-entity-editor">
                    <input id="map-operator-name" value="${escapeMapHtml(assignedOperator.name)}" placeholder="Имя">
                    <input id="map-operator-login" value="${escapeMapHtml(assignedOperator.login || "")}" placeholder="Логин">
                    <input id="map-operator-password" type="password" placeholder="Новый пароль (необязательно)">
                    <button onclick="saveMapOperator(${assignedOperator.id})">Сохранить данные оператора</button>
                </div>
            ` : ""}
            <details class="map-create-details">
                <summary>Создать оператора</summary>
                <input id="map-new-operator-name" placeholder="Имя">
                <input id="map-new-operator-login" placeholder="Логин">
                <input id="map-new-operator-password" type="password" placeholder="Пароль">
                <button onclick="createMapOperator(${windowId})">Создать и назначить</button>
            </details>
        </section>
        <section class="map-window-settings">
            <h4>Услуги окна</h4>
            <div class="map-services-list">${servicesHtml}</div>
            ${Array.isArray(linkedServices) ? `<button onclick="saveMapWindowServices(${windowId})">Сохранить услуги</button>` : ""}
            <details class="map-create-details">
                <summary>Создать услугу</summary>
                <input id="map-new-service-name" placeholder="Название услуги">
                <button onclick="createMapService()">Создать услугу</button>
            </details>
        </section>
    `;
}

async function createMapWindowForSelected() {
    const object = officeMap.objects.find(item => item.id === selectedMapObjectId);
    if (!object || object.type !== "workplace") return;
    const name = prompt("Название рабочего места:", object.label || "Новое рабочее место")?.trim();
    if (!name) return;
    try {
        const windowItem = await mapRequest(`${API}/windows/`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name})
        });
        mapWindows.push(windowItem);
        object.window_id = windowItem.id;
        markMapDirty();
        renderMapObjects();
        renderMapProperties();
    } catch (error) {
        alert(error.message);
    }
}

async function saveMapWindow(windowId) {
    const name = document.getElementById("map-window-name")?.value.trim();
    const status = document.getElementById("map-window-status")?.value;
    if (!name) return alert("Введите название рабочего места");
    try {
        await mapRequest(`${API}/windows/${windowId}`, {
            method: "PATCH",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name})
        });
        await mapRequest(`${API}/windows/${windowId}/status`, {
            method: "PATCH",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({status})
        });
        const windowItem = mapWindows.find(item => item.id === windowId);
        if (windowItem) Object.assign(windowItem, {name, status});
        renderMapObjects();
        renderMapProperties();
    } catch (error) {
        alert(error.message);
    }
}

async function loadMapWindowServices(windowId, objectId) {
    mapWindowServices[windowId] = null;
    try {
        const data = await mapRequest(`${API}/window-services/${windowId}`);
        mapWindowServices[windowId] = Array.isArray(data) ? data : [];
        if (selectedMapObjectId === objectId) renderMapProperties();
    } catch (error) {
        mapWindowServices[windowId] = [];
        if (selectedMapObjectId === objectId) renderMapProperties();
        alert(error.message);
    }
}

async function saveMapWindowOperator(windowId) {
    const select = document.getElementById("map-window-operator");
    const operatorId = select?.value ? Number(select.value) : null;
    try {
        await mapRequest(`${API}/windows/${windowId}/operator`, {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({operator_id: operatorId})
        });
        mapOperators.forEach(operator => {
            if (operator.window_id === windowId) operator.window_id = null;
            if (operator.id === operatorId) operator.window_id = windowId;
        });
        renderMapProperties();
    } catch (error) {
        alert(error.message);
    }
}

async function saveMapOperator(operatorId) {
    const operator = mapOperators.find(item => item.id === operatorId);
    const name = document.getElementById("map-operator-name")?.value.trim();
    const login = document.getElementById("map-operator-login")?.value.trim();
    const password = document.getElementById("map-operator-password")?.value;
    if (!name || !login) return alert("Заполните имя и логин оператора");
    if (operator && login !== operator.login && !password) {
        return alert("Для смены логина укажите новый пароль");
    }
    try {
        await mapRequest(`${API}/operators/${operatorId}`, {
            method: "PATCH",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name})
        });
        if (password) {
            await mapRequest(`${API}/operators/${operatorId}/login`, {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({login, password})
            });
        }
        if (operator) Object.assign(operator, {name, login});
        renderMapProperties();
    } catch (error) {
        alert(error.message);
    }
}

async function createMapOperator(windowId) {
    const name = document.getElementById("map-new-operator-name")?.value.trim();
    const login = document.getElementById("map-new-operator-login")?.value.trim();
    const password = document.getElementById("map-new-operator-password")?.value;
    if (!name || !login || !password) return alert("Заполните данные нового оператора");
    try {
        const operator = await mapRequest(`${API}/operators/`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name, login, password, window_id: null})
        });
        await mapRequest(`${API}/windows/${windowId}/operator`, {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({operator_id: operator.id})
        });
        mapOperators.forEach(item => {
            if (item.window_id === windowId) item.window_id = null;
        });
        mapOperators.push({...operator, login, window_id: windowId});
        renderMapProperties();
    } catch (error) {
        alert(error.message);
    }
}

async function saveMapWindowServices(windowId) {
    const panel = document.getElementById("map-properties");
    const linkedServices = [];
    panel.querySelectorAll(".map-service-check:checked").forEach(checkbox => {
        const priority = panel.querySelector(`[data-priority-for="${checkbox.dataset.serviceId}"]`);
        linkedServices.push({
            service_id: Number(checkbox.dataset.serviceId),
            priority: Math.max(1, Math.min(100, Number(priority?.value) || 1))
        });
    });
    try {
        await mapRequest(`${API}/window-services/${windowId}`, {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({services: linkedServices})
        });
        mapWindowServices[windowId] = linkedServices;
        renderMapProperties();
    } catch (error) {
        alert(error.message);
    }
}

async function createMapService() {
    const input = document.getElementById("map-new-service-name");
    const name = input?.value.trim();
    if (!name) return alert("Введите название услуги");
    try {
        const service = await mapRequest(`${API}/services`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name, operator_choice_enabled: false})
        });
        mapServices.push(service);
        renderMapProperties();
    } catch (error) {
        alert(error.message);
    }
}

async function renameMapService(serviceId) {
    const service = mapServices.find(item => item.id === serviceId);
    if (!service) return;
    const name = prompt("Название услуги:", service.name)?.trim();
    if (!name || name === service.name) return;
    try {
        await mapRequest(`${API}/services/${serviceId}`, {
            method: "PATCH",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name})
        });
        service.name = name;
        renderMapProperties();
    } catch (error) {
        alert(error.message);
    }
}

function deleteSelectedMapObject() {
    if (!selectedMapObjectId) return;
    officeMap.objects = officeMap.objects.filter(item => item.id !== selectedMapObjectId);
    selectedMapObjectId = null;
    markMapDirty();
    renderMapObjects();
    renderMapProperties();
}

function markMapDirty() {
    mapDirty = true;
    updateMapSaveState();
}

function updateMapSaveState(text) {
    const state = document.getElementById("map-save-state");
    if (!state) return;
    state.textContent = text || (mapDirty ? "Есть несохранённые изменения" : "Все изменения сохранены");
    state.classList.toggle("dirty", mapDirty);
}

async function saveOfficeMap() {
    updateMapSaveState("Сохранение...");
    try {
        officeMap.width = mapWorldWidth;
        officeMap.height = mapWorldHeight;
        officeMap = await mapRequest(`${API}/admin/map`, {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(officeMap)
        });
        mapDirty = false;
        updateMapSaveState();
    } catch (error) {
        updateMapSaveState("Не удалось сохранить");
        alert(error.message);
    }
}

function escapeMapHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function setActiveTab(tabId) {
    // Убираем класс active у всех кнопок
    document.querySelectorAll('.tabs button').forEach(btn => {
        btn.classList.remove('active');
    });
    // Добавляем класс нужной кнопке
    document.getElementById(tabId).classList.add('active');
}

async function deleteOperator(id) {
    if (!confirm("Вы уверены?")) return;

    try {
        // Заменяем fetch на fetchJSON
        const res = await fetchJSON(`${API}/operators/${id}`, {
            method: "DELETE"
        });
        // Если запрос прошел (res не undefined), обновляем список
        if (res) {
            alert("Оператор удален");
            loadOperators();
        }
    } catch (e) {
        console.error("Ошибка удаления:", e);
        alert("Не удалось удалить оператора");
    }
}

// основной обработчик закрытия страницы
window.addEventListener("beforeunload", function () {
    // если это обновление страницы — ничего не делаем
    if (isClosingTab || sessionStorage.getItem("refresh")) {
        return;
    }
    // если вкладку закрывают
    if (sessionId) {
		
		ExitPage();

    }

});

async function ExitPage() {
    const sessionId = sessionStorage.getItem("session_id");
    if (!sessionId) return;

    try {
        // Используем fetch, так как нам не важен ответ (мы всё равно закрываем страницу)
        await fetch(`${API}/logout`, {
            method: "POST",
            headers: { "session-id": sessionId }
        });
    } catch (err) {
        console.error("Ошибка при выходе:", err);
    } finally {
        // чищаем данные сессии на клиенте
        sessionStorage.removeItem("session_id");
        location.href = "login.html"; // Перенаправляем на вход
    }
}

/// MEDIA FILES 
// In admin.js
async function loadMedia() {
	resetOpened();
	// Показываем форму и таблицу обратно
    document.getElementById("form").style.display = "block";
    document.getElementById("table").style.display = "table";
 
    setActiveTab('tab-media');
    // Удаляем блок статистики, чтобы он не мешал
    const statsContainer = document.getElementById("stats-container");
    if (statsContainer) statsContainer.remove();	
	
    const sessionId = sessionStorage.getItem("session_id");

    try {
        // 1. Get both the physical files AND the playlist status
        const response = await fetch(`${API}/admin/media/files`, {
            headers: { "session-id": sessionId }
        });
        const data = await response.json();    
        // Ensure we are working with arrays
        const files = data.files || [];
        const playlist = data.playlist || [];

        let html = `<tr>
            <th>Файл</th>
            <th>Статус</th>
            <th>Действия</th>
        </tr>`;

        files.forEach(filename => {
            const webPath = `/queue/media/${filename}`;
            const isIncluded = playlist.includes(webPath);
            
            html += `<tr>
                <td>${filename}</td>
                <td><b style="color: ${isIncluded ? 'var(--success)' : 'var(--text-muted)'}">
                    ${isIncluded ? 'В плейлисте' : 'Исключен'}
                </b></td>
                <td>
                    <a href="${webPath}" target="_blank" style="text-decoration: none;">
                        <button style="background: var(--accent); color: white;">Предпросмотр</button>
                    </a>
                    <button onclick="toggleMedia('${filename}', ${isIncluded})" 
                            style="background: ${isIncluded ? '#ffcc00' : 'var(--success)'}; color: white; margin-left: 5px;">
                        ${isIncluded ? 'Исключить' : 'Включить'}
                    </button>
                    <button onclick="deletePhysicalFile('${filename}')" 
                            style="background: var(--danger); color: white; margin-left: 5px;">
                        Удалить
                    </button>
                </td>
            </tr>`;
        });

        setTable(html);
        setForm(`
            <div class="form">
                <h3>Загрузить видео (MP4, Max 50MB)</h3>
                <input type="file" id="videoFileInput" accept="video/mp4">
                <button onclick="uploadVideoFile()">Начать загрузку</button>
                <div id="uploadStatus"></div>
            </div>
        `);
    } catch (e) {
        console.error("Ошибка загрузки медиа:", e);
        setTable("<tr><td>Ошибка связи с сервером</td></tr>");
    }
}

async function toggleMedia(filename, isCurrentlyIncluded) {
    const webPath = `/queue/media/${filename}`;
    const action = isCurrentlyIncluded ? "delete" : "add";

    await fetchJSON(`${API}/admin/media/playlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
            path: webPath, 
            action: action 
        })
    });

    loadMedia(); // Refresh table
}

// Logic to delete the file from the disk
async function deletePhysicalFile(filename) {
    if (!confirm(`Удалить файл ${filename} с сервера навсегда?`)) return;

    const response = await fetch(`${API}/admin/media/file/${filename}`, {
        method: "DELETE",
        headers: { "session-id": sessionStorage.getItem("session_id") }
    });

    if (response.ok) {
        loadMedia();
    }
}

// Logic for the "Include/Exclude" toggle
async function toggleInPlaylist(filename, currentlyIncluded) {
    const action = currentlyIncluded ? "delete" : "add";
    const path = `/queue/media/${filename}`;

    const res = await fetchJSON(`${API}/admin/media/playlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: path, action: action })
    });
    if (res) loadMedia();
}

// Logic for physical deletion
async function deleteFromServer(filename) {
    if (!confirm(`Вы уверены, что хотите полностью удалить ${filename} с сервера?`)) return;

    const sessionId = sessionStorage.getItem("session_id");
    const response = await fetch(`${API}/admin/media/file/${filename}`, {
        method: "DELETE",
        headers: { "session-id": sessionId }
    });

    if (response.ok) {
        alert("Файл удален");
        loadMedia();
    }
}

async function uploadVideoFile() {
    const fileInput = document.getElementById('videoFileInput');
    const status = document.getElementById('uploadStatus');
    const file = fileInput.files[0];

    if (!file) return;

    if (file.size > 50 * 1024 * 1024) {
        alert("Файл слишком большой (> 50MB)");
        return;
    }

    const formData = new FormData();
    formData.append("file", file);
    status.textContent = "Загрузка...";

    const response = await fetch(`${API}/admin/media/upload`, {
        method: "POST",
        headers: { "session-id": sessionStorage.getItem("session_id") },
        body: formData
    });

    if (response.ok) {
        status.textContent = "Загружено!";
        loadMedia();
    } else {
        const err = await response.json();
        status.textContent = "Ошибка: " + err.detail;
    }
}

async function addMedia() {
    const path = document.getElementById("newVideoPath").value;
    if (!path) return;

    const res = await fetchJSON(`${API}/admin/media/playlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: path, action: "add" })
    });

    if (res) loadMedia();
}

async function deleteMedia(index) {
    if (!confirm("Удалить это видео из плейлиста?")) return;

    const res = await fetchJSON(`${API}/admin/media/playlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index: index, action: "delete" })
    });

    if (res) loadMedia();
}

// Логика фонового heartbeat для админа через WebSocket (вместо HTTP /ping)
setInterval(() => {
    const sid = sessionStorage.getItem("session_id");
    if (!sid) return;
    if (!adminSocket || adminSocket.readyState !== WebSocket.OPEN) return;

    try {
        adminSocket.send(JSON.stringify({
            type: "ping",
            session_id: sid
        }));
    } catch (e) {
        console.debug("Admin WS ping error:", e);
    }
}, 5000);
