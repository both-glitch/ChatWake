const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const currentUser = tg.initDataUnsafe?.user || {};
const userId = currentUser.id;
const myUsername = (currentUser.username || "").toLowerCase();
const BOT_USERNAME = "Group_Productivitybot"; // no @

let refreshTimer = null;
let currentChatId = null;
let currentTitle = null;
let memberRowCache = {};

// ---------- THEME ----------
function applyTheme(theme) {
  document.body.setAttribute("data-theme", theme);
  document.getElementById("theme-toggle").textContent = theme === "light" ? "☀️" : "🌙";
}
function toggleTheme() {
  const current = document.body.getAttribute("data-theme") === "light" ? "dark" : "light";
  applyTheme(current);
  try { localStorage.setItem("chatwake-theme", current); } catch (e) {}
}
(function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("chatwake-theme"); } catch (e) {}
  const platformDark = tg.colorScheme === "dark";
  applyTheme(saved || (platformDark ? "dark" : "light"));
})();

// ---------- HELPERS ----------
function showToast(msg, isError) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show" + (isError ? " error" : "");
  setTimeout(() => t.classList.remove("show"), 2400);
}

function formatLastSeen(isoLike) {
  const d = new Date(isoLike.replace(" ", "T") + "Z");
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function statusStyle(status) {
  if (status === "active") return { cls: "status-active", label: "Active" };
  if (status === "quiet") return { cls: "status-quiet", label: "Quiet" };
  return { cls: "status-ghosting", label: "Ghosting" };
}

function startButtonCooldown(btnEl, seconds, baseLabel) {
  if (!btnEl) return;
  let remaining = Math.max(1, Math.ceil(seconds));
  btnEl.disabled = true;
  btnEl.style.opacity = "0.5";
  btnEl.textContent = `${baseLabel} (${remaining}s)`;
  const interval = setInterval(() => {
    remaining -= 1;
    if (remaining <= 0) {
      clearInterval(interval);
      btnEl.disabled = false;
      btnEl.style.opacity = "1";
      btnEl.textContent = baseLabel;
    } else {
      btnEl.textContent = `${baseLabel} (${remaining}s)`;
    }
  }, 1000);
}

// ---------- INVITATIONS RECEIVED ----------
async function loadInvitations() {
  const container = document.getElementById("invitations-view");
  if (!myUsername) { container.innerHTML = ""; return; }

  const res = await fetch(`/api/invitations?username=${encodeURIComponent(myUsername)}`);
  const invites = await res.json();

  if (!invites.length) { container.innerHTML = ""; return; }

  container.innerHTML = `
    <div class="invite-section">
      <h4>Pending Invitations</h4>
      ${invites.map(i => `
        <div class="invite-card">
          <div class="invite-text">You've been invited to help manage <b>${i.group_title}</b></div>
          <div class="invite-actions">
            <button class="btn-accept" onclick="respondInvite(${i.id}, true)">Accept</button>
            <button class="btn-decline" onclick="respondInvite(${i.id}, false)">Decline</button>
          </div>
        </div>`).join("")}
    </div>`;
}

async function respondInvite(invitationId, accept) {
  const res = await fetch(`/api/invitations/${invitationId}/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, accept }),
  });
  const result = await res.json();
  if (result.ok) {
    showToast(accept ? "Invitation accepted" : "Invitation declined");
    tg.HapticFeedback.notificationOccurred("success");
    loadInvitations();
    loadGroups();
  } else {
    showToast("Something went wrong", true);
  }
}

// ---------- GROUPS ----------
async function loadGroups() {
  clearInterval(refreshTimer);
  memberRowCache = {};
  document.getElementById("invite-toggle").style.display = "none";
  const res = await fetch(`/api/groups?user_id=${userId}`);
  const groups = await res.json();
  document.getElementById("groups-view").style.display = "block";
  document.getElementById("members-view").style.display = "none";
  const view = document.getElementById("groups-view");
  view.innerHTML = groups.length
    ? groups.map(g => `
        <div class="card">
          <div class="member-info">
            <span class="member-name">${g.title}</span>
            <span class="role-tag">${g.role === "owner" ? "Owner" : "Collaborator"}</span>
          </div>
          <button class="btn-accent" onclick="openGroup(${g.chat_id}, '${g.title.replace(/'/g, "\\'")}')">Open</button>
        </div>`).join("")
    : `<div class="empty-msg">No groups yet.<br>Add the bot to a Telegram group to get started.</div>`;
}

function openGroup(chatId, title) {
  currentChatId = chatId;
  currentTitle = title;
  memberRowCache = {};
  renderShell();
  loadMembers();
  refreshTimer = setInterval(() => loadMembers(), 8000);
}

function renderShell() {
  document.getElementById("groups-view").style.display = "none";
  document.getElementById("invite-toggle").style.display = "flex";
  document.getElementById("invite-toggle").textContent = "+";
  const view = document.getElementById("members-view");
  view.style.display = "block";
  view.innerHTML = `
    <div class="top-row">
      <button class="btn-card" onclick="goBack()">Back</button>
      <h3>${currentTitle}</h3>
      <span style="width:52px"></span>
    </div>
    <div class="bulk-row">
      <button class="btn-ghost" onclick="act('wakeup-all',${currentChatId}, null, this)">Wake All Ghosts</button>
      <button class="btn-quiet-action" onclick="act('nudge-all',${currentChatId}, null, this)">Nudge All Quiet</button>
    </div>
    <div class="card" id="invite-panel" style="flex-direction:column; align-items:stretch; display:none;">
      <h4>Invite someone to help</h4>
      <div class="invite-row">
        <input type="text" id="invite-username-input" placeholder="@username" />
        <button class="btn-accent" onclick="sendInvite()">Invite</button>
      </div>
      <div class="invite-link-box" id="invite-link-box"></div>
      <div class="history-list" id="invite-history-list"></div>
    </div>
    <div id="member-list"></div>
  `;
}

function toggleInvitePanel() {
  const panel = document.getElementById("invite-panel");
  if (!panel) return;
  const isOpen = panel.style.display === "flex";
  panel.style.display = isOpen ? "none" : "flex";
  document.getElementById("invite-toggle").textContent = isOpen ? "+" : "×";
  if (!isOpen) loadInviteHistory();
}

async function sendInvite() {
  const input = document.getElementById("invite-username-input");
  const username = input.value.trim().replace(/^@/, "");
  if (!username) { showToast("Enter a username first", true); return; }

  const res = await fetch("/api/invite", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: currentChatId, username, user_id: userId }),
  });
  const result = await res.json();

  if (result.ok) {
    showToast(`Invitation sent successfully to @${username}`);
    input.value = "";
    const linkBox = document.getElementById("invite-link-box");
    linkBox.style.display = "block";
    linkBox.textContent = `Share this link with them to open ChatWake: https://t.me/${BOT_USERNAME}/app`;
    loadInviteHistory();
  } else {
    showToast(result.error || "Couldn't send invite", true);
  }
}

function historyStatusLabel(status) {
  if (status === "accepted") return { cls: "history-accepted", label: "Accepted" };
  if (status === "declined") return { cls: "history-declined", label: "Declined" };
  return { cls: "history-pending", label: "Requesting…" };
}

async function loadInviteHistory() {
  const res = await fetch(`/api/groups/${currentChatId}/invite-history?user_id=${userId}`);
  const history = await res.json();
  const box = document.getElementById("invite-history-list");
  if (!box) return;

  if (!history.length) {
    box.innerHTML = `<div class="empty-msg" style="margin-top:10px; font-size:12px;">No invites sent in the last 24 hours.</div>`;
    return;
  }

  box.innerHTML = history.map(h => {
    const s = historyStatusLabel(h.status);
    return `
      <div class="history-row">
        <span class="history-username">@${h.username}</span>
        <span class="history-status ${s.cls}">${s.label}</span>
      </div>`;
  }).join("");
}

function actionButtonHtml(chatId, username, status) {
  if (status === "ghosting") {
    return `<button class="btn-ghost" onclick="act('wakeup-single',${chatId},'${username}', this)">Wake Up</button>`;
  }
  if (status === "quiet") {
    return `<button class="btn-quiet-action" onclick="act('nudge-single',${chatId},'${username}', this)">Nudge</button>`;
  }
  return "";
}

async function loadMembers() {
  const res = await fetch(`/api/groups/${currentChatId}/members?user_id=${userId}`);
  const members = await res.json();
  const list = document.getElementById("member-list");
  if (!list) return;

  if (!members.length) {
    list.innerHTML = `<div class="empty-msg">No members captured yet.<br>Have everyone send 1 message in the group.</div>`;
    memberRowCache = {};
    return;
  }

  const currentIds = new Set(members.map(m => m.telegram_id));
  Object.keys(memberRowCache).forEach(id => {
    if (!currentIds.has(Number(id))) {
      memberRowCache[id].el.remove();
      delete memberRowCache[id];
    }
  });

  members.forEach(m => {
    const cached = memberRowCache[m.telegram_id];
    const s = statusStyle(m.status);

    if (!cached) {
      const el = document.createElement("div");
      el.className = "card";
      el.innerHTML = `
        <div style="display: flex; align-items: center; gap: 12px;">
          <span style="font-size: 22px; color: var(--subtext);">○</span>
          <div class="member-info">
            <span class="member-name">${m.name}</span>
            <span class="status-row ${s.cls}"><span class="dot"></span>${s.label}</span>
            <span class="last-seen">Last reply: ${formatLastSeen(m.last_seen)}</span>
          </div>
        </div>
        <span class="action-slot">${actionButtonHtml(currentChatId, m.username, m.status)}</span>
      `;
      list.appendChild(el);
      memberRowCache[m.telegram_id] = {
        el,
        statusRow: el.querySelector(".status-row"),
        actionSlot: el.querySelector(".action-slot"),
        lastSeenEl: el.querySelector(".last-seen"),
        lastStatus: m.status,
        lastSeenValue: m.last_seen,
      };
    } else {
      if (cached.lastStatus !== m.status) {
        cached.statusRow.className = `status-row ${s.cls}`;
        cached.statusRow.innerHTML = `<span class="dot"></span>${s.label}`;
        const existingBtn = cached.actionSlot.querySelector("button");
        if (!existingBtn || !existingBtn.disabled) {
          cached.actionSlot.innerHTML = actionButtonHtml(currentChatId, m.username, m.status);
        }
        cached.lastStatus = m.status;
      }
      if (cached.lastSeenValue !== m.last_seen) {
        cached.lastSeenEl.textContent = `Last reply: ${formatLastSeen(m.last_seen)}`;
        cached.lastSeenValue = m.last_seen;
      }
    }
  });
}

function goBack() {
  clearInterval(refreshTimer);
  document.getElementById("invite-toggle").style.display = "none";
  document.getElementById("invite-toggle").textContent = "+";
  loadGroups();
}

async function act(type, chatId, username, btnEl) {
  let endpoint, body;
  if (type === "wakeup-single") { endpoint = "/api/wakeup"; body = { chat_id: chatId, username, user_id: userId }; }
  if (type === "nudge-single")  { endpoint = "/api/nudge";  body = { chat_id: chatId, username, user_id: userId }; }
  if (type === "wakeup-all")    { endpoint = "/api/wakeup-all"; body = { chat_id: chatId, user_id: userId }; }
  if (type === "nudge-all")     { endpoint = "/api/nudge-all";  body = { chat_id: chatId, user_id: userId }; }

  const originalLabel = btnEl ? btnEl.textContent : "";

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const result = await res.json();

    if (!res.ok || result.ok === false) {
      if (result.cooldown && btnEl) startButtonCooldown(btnEl, result.cooldown, originalLabel);
      showToast(result.error || "Action failed.", true);
      return;
    }

    tg.HapticFeedback.notificationOccurred("success");
    if (type === "wakeup-single") { showToast(`Woke up ${username}`); startButtonCooldown(btnEl, 120, "Wake Up"); }
    if (type === "nudge-single")  { showToast(`Nudged ${username}`); startButtonCooldown(btnEl, 120, "Nudge"); }
    if (type === "wakeup-all")    { showToast(result.count ? `Woke up ${result.count} member(s)` : "No one eligible right now"); startButtonCooldown(btnEl, 120, "Wake All Ghosts"); }
    if (type === "nudge-all")     { showToast(result.count ? `Nudged ${result.count} member(s)` : "No one eligible right now"); startButtonCooldown(btnEl, 120, "Nudge All Quiet"); }

    loadMembers();
  } catch (e) {
    showToast("Network error -- action may not have sent.", true);
  }
}

loadInvitations();
loadGroups();