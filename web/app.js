const $ = (sel) => document.querySelector(sel);
const fmt = (epoch) => epoch ? new Date(epoch * 1000).toLocaleString("ko-KR") : "";
const minutesOfDay = (t) => {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
};
const minutesToHHMM = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const dayLabels = ["월", "화", "수", "목", "금", "토", "일"];

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status} ${text}`);
  }
  return r.json();
}

async function refresh() {
  const [status, schedules, blocklist, audit] = await Promise.all([
    api("/api/status"),
    api("/api/schedules"),
    api("/api/blocklist"),
    api("/api/audit?limit=15"),
  ]);
  renderStatus(status);
  renderSessions(status);
  renderSchedules(schedules.schedules);
  renderBlocklist(blocklist.domains);
  renderAudit(audit.entries);
}

function renderStatus(s) {
  const el = $("#status");
  el.className = "status " + (s.frozen ? "frozen" : s.active ? "active" : "idle");
  if (!s.active) {
    el.textContent = `idle · ${s.blocked_domains.length}개 도메인 등록`;
    return;
  }
  const expires = s.expires_at ? fmt(s.expires_at) : "—";
  el.textContent = `${s.frozen ? "🔒 FROZEN" : "🟢 ACTIVE"} · ${s.reason} · 만료 ${expires}${s.hosts_synced ? "" : " ⚠ hosts unsynced"}`;
}

function renderSessions(s) {
  const c = $("#sessions");
  c.innerHTML = "";
  const sessions = s.sources.filter((x) => x.type === "session");
  if (sessions.length === 0) {
    c.innerHTML = `<p class="muted">활성 세션 없음</p>`;
    return;
  }
  for (const sess of sessions) {
    const div = document.createElement("div");
    div.className = "session-card" + (sess.frozen ? " frozen" : "");
    const left = document.createElement("div");
    left.innerHTML = `<strong>${sess.label}</strong><br><span class="muted">만료 ${fmt(sess.ends_at)}${sess.frozen ? " · 🔒" : ""}</span>`;
    const btn = document.createElement("button");
    btn.textContent = "취소";
    btn.className = sess.frozen ? "ghost" : "danger";
    btn.onclick = async () => {
      try {
        await api(`/api/sessions/${sess.id}`, { method: "DELETE" });
        refresh();
      } catch (e) { alert(e.message); }
    };
    div.appendChild(left);
    div.appendChild(btn);
    c.appendChild(div);
  }
}

function renderSchedules(list) {
  const ul = $("#schedules");
  ul.innerHTML = "";
  if (list.length === 0) {
    ul.innerHTML = `<li class="muted">스케줄 없음</li>`;
    return;
  }
  for (const s of list) {
    const li = document.createElement("li");
    const days = s.days.map((d) => dayLabels[d]).join(",");
    const span = document.createElement("span");
    span.innerHTML = `<strong>${s.name}</strong><br><span class="muted">${days} · ${minutesToHHMM(s.start_minute)}–${minutesToHHMM(s.end_minute)}${s.enabled ? "" : " (off)"}</span>`;
    const btn = document.createElement("button");
    btn.textContent = "삭제";
    btn.className = "danger";
    btn.onclick = async () => {
      if (!confirm(`삭제: ${s.name}?`)) return;
      await api(`/api/schedules/${s.id}`, { method: "DELETE" });
      refresh();
    };
    li.appendChild(span);
    li.appendChild(btn);
    ul.appendChild(li);
  }
}

function renderBlocklist(list) {
  const ul = $("#blocklist");
  ul.innerHTML = "";
  if (list.length === 0) {
    ul.innerHTML = `<li class="muted">차단 도메인 없음</li>`;
    return;
  }
  for (const d of list) {
    const li = document.createElement("li");
    li.innerHTML = `<span>${d}</span>`;
    const btn = document.createElement("button");
    btn.textContent = "삭제";
    btn.className = "danger";
    btn.onclick = async () => {
      await api(`/api/blocklist/${encodeURIComponent(d)}`, { method: "DELETE" });
      refresh();
    };
    li.appendChild(btn);
    ul.appendChild(li);
  }
}

function renderAudit(entries) {
  const ul = $("#audit");
  ul.innerHTML = "";
  for (const e of entries) {
    const li = document.createElement("li");
    li.textContent = `${new Date(e.at * 1000).toLocaleTimeString("ko-KR")} ${e.event}${e.detail ? " " + JSON.stringify(e.detail) : ""}`;
    ul.appendChild(li);
  }
}

$("#frozen-form").onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const frozen = fd.get("frozen") === "on";
  if (frozen && !confirm("Frozen 모드는 만료 전 해제 불가입니다. 진행할까요?")) return;
  await api("/api/sessions", {
    method: "POST",
    body: JSON.stringify({
      label: fd.get("label") || "focus",
      duration_minutes: Number(fd.get("minutes")),
      frozen,
    }),
  });
  refresh();
};

$("#schedule-form").onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const days = fd.getAll("d").map(Number);
  if (days.length === 0) { alert("요일을 1개 이상 선택하세요"); return; }
  await api("/api/schedules", {
    method: "POST",
    body: JSON.stringify({
      name: fd.get("name"),
      days,
      start_minute: minutesOfDay(fd.get("start")),
      end_minute: minutesOfDay(fd.get("end")),
    }),
  });
  refresh();
};

$("#block-form").onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await api("/api/blocklist", {
    method: "POST",
    body: JSON.stringify({ domains: [fd.get("domain")] }),
  });
  e.target.reset();
  refresh();
};

refresh();
setInterval(refresh, 3000);
