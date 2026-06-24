import { fetchJSON, readResponseData } from "./api.js";
import { setActiveTab, setForm, setTable } from "./dom.js";

const API = CONFIG.API_URL;
let services = [];
let openedServices = null;

function resetOpened() {
    openedServices?.remove();
    openedServices = null;
}

//////// УСЛУГИ
export async function loadServices() {
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
    const res = await fetch(`${API}/services?limit=500&include_hidden=true`, {
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
	<th>На терминале</th>
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
	  <td>${s.visible_on_terminal ? "Показана" : "Скрыта"}</td>
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
		<button onclick="toggleTerminalVisibility(${s.id}, ${s.visible_on_terminal ? 0 : 1})">
		  ${s.visible_on_terminal ? "Скрыть на терминале" : "Показать на терминале"}
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

export async function moveService(serviceId, direction) {
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

export function editServiceStatus(id, currentStatus) {
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
export async function toggleOperatorChoice(id, enabled) {
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

export async function toggleTerminalVisibility(id, enabled) {
  const sessionId = sessionStorage.getItem("session_id");

  if (!sessionId) {
    alert("Ошибка: вы не авторизованы как администратор");
    return;
  }

  const res = await fetch(`${API}/services/${id}/terminal-visibility`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "session-id": sessionId
    },
    body: JSON.stringify({
      visible_on_terminal: !!enabled
    })
  });

  if (res.ok) {
    resetOpened();
    loadServices();
  } else {
    const err = await res.json();
    alert("Ошибка: " + (err.detail || "Не удалось обновить отображение на терминале"));
  }
}

export async function saveServiceStatus(id) {
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

export function editService(id, name) {
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

export async function saveService(id) {
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

export async function deleteService(id) {
    if (!confirm("Удалить услугу из работы? Если по ней уже есть билеты, она будет скрыта, но история сохранится.")) return;

    const sessionId = sessionStorage.getItem("session_id"); // Получаем сессию

    const res = await fetch(`${API}/services/${id}`, {
        method: "DELETE",
        headers: {
            "session-id": sessionId // Передаем заголовок
        }
    });

    if (res.ok) {
        const data = await readResponseData(res);
        if (data.message) alert(data.message);
        loadServices(); // Обновляем список, если всё ок
    } else {
        const err = await readResponseData(res);
        alert("Ошибка: " + (err.detail || "Не удалось удалить услугу"));
    }
}

export async function addService() {
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
