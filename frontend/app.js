const loginView = document.querySelector("#login-view");
const dashboardView = document.querySelector("#dashboard-view");
const loginForm = document.querySelector("#login-form");
const loginError = document.querySelector("#login-error");
const loadError = document.querySelector("#load-error");
const opportunityList = document.querySelector("#opportunity-list");
const emptyState = document.querySelector("#empty-state");
const reminderList = document.querySelector("#reminder-list");
const reminderEmpty = document.querySelector("#reminder-empty");
const statusFilter = document.querySelector("#status-filter");
const serviceTools = document.querySelector("#service-tools");
const setupRestricted = document.querySelector("#setup-restricted");
const dashboardTabs = [...document.querySelectorAll('[role="tab"]')];
const whatsappState = document.querySelector("#whatsapp-state");
const whatsappQrPanel = document.querySelector("#whatsapp-qr-panel");
const whatsappQr = document.querySelector("#whatsapp-qr");
const startWhatsAppButton = document.querySelector("#start-whatsapp-button");
const testChannelButton = document.querySelector("#test-channel-button");
const siteList = document.querySelector("#site-list");
let whatsappPoll = null;
let dashboardRefresh = null;

function activateTab(tab, focus = false) {
  for (const candidate of dashboardTabs) {
    const selected = candidate === tab;
    candidate.setAttribute("aria-selected", String(selected));
    candidate.tabIndex = selected ? 0 : -1;
    document.querySelector(`#${candidate.getAttribute("aria-controls")}`)
      .classList.toggle("hidden", !selected);
  }
  if (focus) tab.focus();
}

for (const tab of dashboardTabs) {
  tab.addEventListener("click", () => activateTab(tab));
}

document.querySelector('[role="tablist"]').addEventListener("keydown", (event) => {
  const index = dashboardTabs.indexOf(document.activeElement);
  if (index < 0) return;
  const next = event.key === "ArrowRight"
    ? (index + 1) % dashboardTabs.length
    : event.key === "ArrowLeft"
    ? (index - 1 + dashboardTabs.length) % dashboardTabs.length
    : event.key === "Home"
    ? 0
    : event.key === "End"
    ? dashboardTabs.length - 1
    : -1;
  if (next < 0) return;
  event.preventDefault();
  activateTab(dashboardTabs[next], true);
});

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 401) throw new Error("Please sign in again.");
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "The request could not be completed.");
  }
  return response.status === 204 ? null : response.json();
}

function showLogin() {
  dashboardView.classList.add("hidden");
  loginView.classList.remove("hidden");
}

async function showDashboard(user) {
  document.querySelector("#account-email").textContent = user.email;
  loginView.classList.add("hidden");
  dashboardView.classList.remove("hidden");
  serviceTools.classList.toggle("hidden", !user.can_manage_services);
  setupRestricted.classList.toggle("hidden", user.can_manage_services);
  activateTab(dashboardTabs[0]);
  await Promise.all([loadOpportunities(), loadReminders()]);
  if (dashboardRefresh) clearInterval(dashboardRefresh);
  dashboardRefresh = setInterval(() => {
    loadOpportunities();
    loadReminders();
  }, 30000);
  if (user.can_manage_services) {
    await Promise.all([refreshWhatsAppStatus(), loadSites()]);
  }
}

function formatDeadline(value) {
  if (!value) return "Deadline not specified";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Deadline not specified"
    : `Deadline ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date)}`;
}

function escapeText(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function renderOpportunities(items) {
  opportunityList.replaceChildren();
  emptyState.classList.toggle("hidden", items.length > 0);
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "opportunity-card";
    const safeUrl = /^https?:\/\//i.test(item.canonical_url) ? item.canonical_url : "#";
    const isArticle = item.record_type === "article";
    card.innerHTML = `
      <div class="card-top">
        <h3 class="card-title"><a href="${escapeText(safeUrl)}" target="_blank" rel="noopener noreferrer">${escapeText(item.title)}</a></h3>
        <span class="badge ${escapeText(isArticle ? "article" : item.status)}">${escapeText(isArticle ? "article" : item.status)}</span>
      </div>
      <p class="card-summary">${escapeText(item.summary)}</p>
      <div class="meta-row">
        <span>${item.record_type === "article" ? "Article" : escapeText(item.category)}</span>
        <span>${escapeText(item.organization || "Organization not specified")}</span>
        <span>${escapeText(formatDeadline(item.deadline))}</span>
        ${item.matched_recipient ? `<span>For ${escapeText(item.matched_recipient)}</span>` : ""}
      </div>
      <div class="card-actions">
        ${isArticle ? "" : `<label class="filter-label">Status
          <select data-status-id="${item.id}" aria-label="Update status for ${escapeText(item.title)}">
            ${["active", "completed", "withdrawn", "expired"].map((status) =>
              `<option value="${status}" ${status === item.status ? "selected" : ""}>${status}</option>`
            ).join("")}
          </select>
        </label>`}
        <a class="source-link" href="${escapeText(safeUrl)}" target="_blank" rel="noopener noreferrer">Open source ↗</a>
      </div>`;
    opportunityList.append(card);
  }
}

function formatSchedule(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Schedule time unavailable"
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function renderReminders(items) {
  reminderList.replaceChildren();
  reminderEmpty.classList.toggle("hidden", items.length > 0);
  for (const item of items) {
    const completed = item.opportunity_status === "completed";
    const status = completed ? "completed" : item.status;
    const card = document.createElement("article");
    card.className = "reminder-card";
    const details = document.createElement("div");
    details.className = "reminder-details";
    const link = document.createElement("a");
    link.href = /^https?:\/\//i.test(item.canonical_url) ? item.canonical_url : "#";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = item.title;
    const schedule = document.createElement("span");
    schedule.textContent = `${item.offset_days}-day reminder · ${formatSchedule(item.scheduled_at)}`;
    details.append(link, schedule);
    const badge = document.createElement("span");
    badge.className = `reminder-status ${escapeText(status)}`;
    badge.textContent = status;
    card.append(details, badge);
    reminderList.append(card);
  }
}

async function loadReminders() {
  const error = document.querySelector("#reminder-error");
  error.textContent = "";
  try {
    const data = await api("/api/reminders");
    renderReminders(data.items);
  } catch (requestError) {
    error.textContent = requestError.message;
    if (requestError.message.includes("sign in")) showLogin();
  }
}

async function loadOpportunities() {
  loadError.textContent = "";
  try {
    const status = statusFilter.value;
    const data = await api(`/api/opportunities${status ? `?status=${encodeURIComponent(status)}` : ""}`);
    document.querySelector("#total-count").textContent = data.counts.total;
    document.querySelector("#active-count").textContent = data.counts.active;
    document.querySelector("#upcoming-count").textContent = data.counts.upcoming;
    renderOpportunities(data.items);
  } catch (error) {
    loadError.textContent = error.message;
    if (error.message.includes("sign in")) showLogin();
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";
  const formData = new FormData(loginForm);
  try {
    await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: formData.get("email"),
        password: formData.get("password"),
      }),
    });
    loginForm.reset();
    await showDashboard(await api("/api/auth/me"));
  } catch (error) {
    loginError.textContent = error.message;
  }
});

document.querySelector("#logout-button").addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST" });
    if (whatsappPoll) clearInterval(whatsappPoll);
    if (dashboardRefresh) clearInterval(dashboardRefresh);
    showLogin();
  } catch (error) {
    loadError.textContent = error.message;
  }
});

function updateWhatsAppState(data) {
  if (typeof data.target_group === "string" && data.target_group) {
    document.querySelector("#whatsapp-target-group").textContent = data.target_group;
  }
  if (typeof data.target_channel === "string" && data.target_channel) {
    document.querySelector("#whatsapp-target-channel").textContent = data.target_channel;
  }
  const messages = {
    stopped: "WhatsApp Web has not been started.",
    starting: "Starting WhatsApp Web…",
    qr: "Ready to pair. Scan this QR code from WhatsApp on your phone.",
    connecting: "QR scanned. Connecting your WhatsApp account…",
    connected: data.error
      ? data.error
      : data.target_group_found === false
      ? `Connected, but ${data.target_group || "the configured group"} was not found in this account.`
      : data.target_channel_found === false
      ? `Connected, but ${data.target_channel || "the configured channel"} was not found in this account.`
      : data.target_channel_found === true
      ? `Connected. Listening in ${data.target_group || "the configured group"} and monitoring ${data.target_channel}.`
      : "Connected. Checking for configured WhatsApp sources…",
    reconnecting: "Connection lost. Trying to reconnect…",
    disconnected: "Disconnected. Start WhatsApp Web to reconnect.",
    error: data.error || "WhatsApp could not start. Try again.",
  };
  whatsappState.textContent = messages[data.state] || "Checking WhatsApp connection…";
  document.querySelector("#whatsapp-error").textContent =
    data.error && data.state !== "error" ? data.error : "";
  const qr = typeof data.qr === "string" && data.qr.startsWith("data:image/png;base64,")
    ? data.qr
    : null;
  whatsappQrPanel.classList.toggle("hidden", !qr);
  if (qr) whatsappQr.src = qr;
  startWhatsAppButton.disabled = ["starting", "qr", "connecting", "connected", "reconnecting"].includes(data.state);
  testChannelButton.disabled = data.state !== "connected" || data.target_channel_found !== true;
  startWhatsAppButton.textContent = data.state === "connected" ? "WhatsApp is connected" : "Start WhatsApp Web";
  if (
    data.state === "connected"
    && data.target_group_found !== null
    && data.target_group_found !== undefined
    && data.target_channel_found !== null
    && data.target_channel_found !== undefined
    && whatsappPoll
  ) {
    clearInterval(whatsappPoll);
    whatsappPoll = null;
  }
}

async function refreshWhatsAppStatus() {
  try {
    updateWhatsAppState(await api("/api/whatsapp/status"));
  } catch (error) {
    whatsappState.textContent = "WhatsApp service is not available.";
    document.querySelector("#whatsapp-error").textContent = error.message;
    startWhatsAppButton.disabled = false;
  }
}

startWhatsAppButton.addEventListener("click", async () => {
  startWhatsAppButton.disabled = true;
  document.querySelector("#whatsapp-error").textContent = "";
  whatsappState.textContent = "Starting WhatsApp Web…";
  try {
    updateWhatsAppState(await api("/api/whatsapp/start", { method: "POST" }));
    if (!whatsappPoll) {
      whatsappPoll = setInterval(refreshWhatsAppStatus, 2000);
    }
    await refreshWhatsAppStatus();
  } catch (error) {
    whatsappState.textContent = "WhatsApp service is not available.";
    document.querySelector("#whatsapp-error").textContent = error.message;
    startWhatsAppButton.disabled = false;
  }
});

testChannelButton.addEventListener("click", async () => {
  const resultElement = document.querySelector("#channel-test-result");
  testChannelButton.disabled = true;
  resultElement.textContent = "Reading up to 10 recent posts and sending supported media to Gemini…";
  try {
    const result = await api("/api/whatsapp/channel/test-last-10", { method: "POST" });
    const lines = result.items.map((item) => item.error
      ? `Post could not be processed`
      : `${item.title || "Post"} — ${item.record_type || "processed"}${item.duplicate ? " (already tracked)" : ""}`);
    resultElement.textContent = `Scanned ${result.scanned}; processed ${result.processed}.\n${lines.join("\n")}`;
    await Promise.all([loadOpportunities(), loadReminders()]);
  } catch (error) {
    resultElement.textContent = error.message;
  } finally {
    testChannelButton.disabled = false;
    await refreshWhatsAppStatus();
  }
});

async function loadSites() {
  siteList.replaceChildren();
  try {
    const data = await api("/api/sites");
    if (!data.items.length) {
      const empty = document.createElement("p");
      empty.className = "site-empty";
      empty.textContent = "No websites added yet.";
      siteList.append(empty);
      return;
    }
    for (const site of data.items) {
      const item = document.createElement("div");
      item.className = "site-item";
      const details = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = site.name;
      const link = document.createElement("a");
      link.href = site.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = site.url;
      const scanTime = document.createElement("span");
      scanTime.className = "site-scan-time";
      scanTime.textContent = site.scan_requested
        ? "Scan queued"
        : site.last_scanned_at
        ? `Last scanned ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(site.last_scanned_at))}`
        : "Waiting for first scan";
      details.append(name, link, scanTime);
      const actions = document.createElement("div");
      actions.className = "site-actions";
      const scan = document.createElement("button");
      scan.type = "button";
      scan.className = "site-scan";
      scan.textContent = "Scan now";
      scan.addEventListener("click", async () => {
        scan.disabled = true;
        try {
          await api(`/api/sites/${site.id}/scan`, { method: "POST" });
          await loadSites();
        } catch (error) {
          document.querySelector("#site-message").textContent = error.message;
          scan.disabled = false;
        }
      });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "site-delete";
      remove.textContent = "Remove";
      remove.setAttribute("aria-label", `Remove ${site.name}`);
      remove.addEventListener("click", async () => {
        remove.disabled = true;
        try {
          await api(`/api/sites/${site.id}`, { method: "DELETE" });
          await loadSites();
        } catch (error) {
          document.querySelector("#site-message").textContent = error.message;
          remove.disabled = false;
        }
      });
      actions.append(scan, remove);
      item.append(details, actions);
      siteList.append(item);
    }
  } catch (error) {
    document.querySelector("#site-message").textContent = error.message;
  }
}

document.querySelector("#site-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = document.querySelector("#site-message");
  message.textContent = "";
  const values = new FormData(event.currentTarget);
  try {
    await api("/api/sites", {
      method: "POST",
      body: JSON.stringify({ name: values.get("name"), url: values.get("url") }),
    });
    event.currentTarget.reset();
    await loadSites();
  } catch (error) {
    message.textContent = error.message;
  }
});

const passwordForm = document.querySelector("#change-password-form");
passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = document.querySelector("#password-message");
  message.textContent = "";
  const values = new FormData(passwordForm);
  try {
    await api("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({
        current_password: values.get("current_password"),
        new_password: values.get("new_password"),
      }),
    });
    message.textContent = "Password updated.";
    passwordForm.reset();
  } catch (error) {
    message.textContent = error.message;
  }
});

statusFilter.addEventListener("change", loadOpportunities);
opportunityList.addEventListener("change", async (event) => {
  const id = event.target.dataset.statusId;
  if (!id) return;
  try {
    await api(`/api/opportunities/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: event.target.value }),
    });
    await Promise.all([loadOpportunities(), loadReminders()]);
  } catch (error) {
    loadError.textContent = error.message;
  }
});

api("/api/auth/me")
  .then(showDashboard)
  .catch(showLogin);
