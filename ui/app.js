/* RealAssistant desktop UI */
(() => {
  const $ = (id) => document.getElementById(id);
  const app = $("app");
  let bridge = null;
  let ready = false;
  let session = null;
  let busy = false;
  let speakReplies = false;
  let pollTimer = null;
  let streamEl = null;
  let lastUserText = "";
  let info = null;

  const SUGGESTIONS = [
    "Open notepad",
    "What's my system status?",
    "Remind me in 10 minutes to stretch",
    "Organise my downloads",
  ];

  const esc = (s) => String(s ?? "").replace(/[&<>]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

  async function call(name, ...args) {
    if (!bridge) throw new Error("The app bridge isn't ready yet.");
    const raw = await bridge[name](...args);
    if (typeof raw !== "string") return raw;
    try { return JSON.parse(raw); } catch { return raw; }
  }

  /* ---------------- render ---------------- */
  function renderMessages() {
    const box = $("messages");
    box.innerHTML = "";
    const msgs = (session && session.messages) || [];
    if (!msgs.length) { renderEmpty(); return; }
    msgs.forEach((m) => appendMessage(m.role, m.text, m.tools, m.ts));
    scrollDown();
  }

  function renderEmpty() {
    const box = $("messages");
    box.innerHTML = `
      <div class="card" data-od-id="empty-state">
        <h2>Start a conversation</h2>
        <p>Ask a question, or tell me to do something on this PC.</p>
        <div class="suggest">
          ${SUGGESTIONS.map((s) => `<button type="button" data-say="${esc(s)}">${esc(s)}</button>`).join("")}
        </div>
      </div>`;
    box.querySelectorAll("[data-say]").forEach((b) =>
      b.addEventListener("click", () => { $("input").value = b.dataset.say; submit(); }));
  }

  function appendMessage(role, text, tools, ts) {
    const box = $("messages");
    if (box.querySelector("[data-od-id=empty-state]")) box.innerHTML = "";
    const el = document.createElement("article");
    el.className = `msg ${role}`;
    el.innerHTML = `
      <div class="who" aria-hidden="true">${role === "user" ? "YOU" : "RA"}</div>
      <div class="body">
        <div class="text"></div>
        ${tools && tools.length ? `<div class="tools">${tools.map(toolChip).join("")}</div>` : ""}
        <div class="time"></div>
      </div>`;
    el.querySelector(".text").textContent = text || "";
    el.querySelector(".time").textContent = ts ? new Date(ts * 1000).toLocaleTimeString() : "";
    box.appendChild(el);
    return el;
  }

  function toolChip(t) {
    const label = `${t.name}${t.result ? " → " + String(t.result).slice(0, 60) : ""}`;
    return `<span class="chip" title="${esc(t.result || "")}">${esc(label)}</span>`;
  }

  function addToolChip(el, t) {
    let wrap = el.querySelector(".tools");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "tools";
      el.querySelector(".body").appendChild(wrap);
    }
    wrap.insertAdjacentHTML("beforeend", toolChip(t));
  }

  function renderError(message) {
    const box = $("messages");
    const el = document.createElement("article");
    el.className = "msg assistant";
    el.innerHTML = `
      <div class="who" aria-hidden="true">RA</div>
      <div class="body">
        <div class="card err" data-od-id="error-state">
          <h2>That didn't go through</h2>
          <p class="msg-text">${esc(message)}</p>
          <button class="btn-retry" type="button">Try again</button>
        </div>
      </div>`;
    el.querySelector(".btn-retry").addEventListener("click", () => {
      el.remove();
      if (lastUserText) sendText(lastUserText);
    });
    box.appendChild(el);
    scrollDown();
  }

  const scrollDown = () => { const b = $("messages"); b.scrollTop = b.scrollHeight; };

  /* ---------------- sessions ---------------- */
  async function refreshSessions() {
    const list = await call("list_sessions");
    const box = $("session-list");
    const q = ($("session-search").value || "").toLowerCase();
    const rows = (list || []).filter((s) => !q || (s.title || "").toLowerCase().includes(q));
    if (!rows.length) {
      box.innerHTML = `<p class="empty-side">${q ? "No chats match that." : "No chats yet."}</p>`;
      return;
    }
    box.innerHTML = rows.map((s) => `
      <button class="session" type="button" role="listitem" data-id="${esc(s.id)}"
              aria-current="${session && session.id === s.id}">
        <span class="t">${esc(s.title || "Untitled")}</span>
        <span class="del" title="Delete">✕</span>
      </button>`).join("");
    box.querySelectorAll(".session").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        if (e.target.classList.contains("del")) {
          await call("delete_session", btn.dataset.id);
          if (session && session.id === btn.dataset.id) { session = null; $("chat-title").textContent = "New chat"; renderMessages(); }
          refreshSessions();
          return;
        }
        await openSession(btn.dataset.id);
      });
    });
  }

  async function openSession(id) {
    const s = await call("open_session", id);
    if (!s) return;
    session = s;
    $("chat-title").textContent = s.title || "New chat";
    renderMessages();
    refreshSessions();
  }

  async function newSession() {
    session = await call("new_session", "New chat");
    $("chat-title").textContent = "New chat";
    renderMessages();
    refreshSessions();
    $("input").focus();
  }

  /* ---------------- chat ---------------- */
  async function submit() {
    const text = $("input").value.trim();
    if (!text || busy) return;
    $("input").value = "";
    autoGrow();
    sendText(text);
  }

  async function sendText(text) {
    lastUserText = text;
    if (!session) await newSession();
    appendMessage("user", text, null, Date.now() / 1000);
    if (session) session.messages.push({ role: "user", text, ts: Date.now() / 1000 });
    const el = appendMessage("assistant", "", null, null);
    el.classList.add("thinking");
    streamEl = el;
    busy = true;
    setBusy(true);
    scrollDown();
    await call("send", text);
    startPolling();
  }

  function setBusy(b) {
    $("send").disabled = b;
    $("input").disabled = b;
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(tick, 80);
  }
  function stopPolling() {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  async function tick() {
    let events = [];
    try { events = await call("poll"); } catch { return; }
    for (const e of events) handleEvent(e);
    let still = false;
    try { still = await call("busy"); } catch {}
    if (!still) {
      stopPolling();
      busy = false;
      setBusy(false);
      if (streamEl) streamEl.classList.remove("thinking");
      streamEl = null;
      refreshSessions();
      $("input").focus();
    }
  }

  function handleEvent(e) {
    if (!streamEl) return;
    if (e.type === "text") {
      const t = streamEl.querySelector(".text");
      t.textContent += e.text;
      scrollDown();
    } else if (e.type === "tool") {
      addToolChip(streamEl, e);
      scrollDown();
    } else if (e.type === "learned") {
      addToolChip(streamEl, { name: "remembered", result: (e.facts || []).join("; ") });
    } else if (e.type === "done") {
      streamEl.querySelector(".time").textContent = new Date().toLocaleTimeString();
      if (speakReplies && e.text) call("say", e.text);
    } else if (e.type === "error") {
      streamEl.remove();
      streamEl = null;
      stopPolling();
      busy = false;
      setBusy(false);
      renderError(e.text || "Something went wrong.");
    }
  }

  /* ---------------- panels ---------------- */
  async function openPanel(name) {
    info = await call("info");
    $("rail").hidden = false;
    app.classList.add("rail-open");
    $("rail-title").textContent = name[0].toUpperCase() + name.slice(1);
    document.querySelectorAll(".tab").forEach((t) =>
      t.setAttribute("aria-pressed", String(t.dataset.panel === name)));
    const body = $("rail-body");
    if (name === "memory") {
      const facts = info.memory || [];
      body.innerHTML = facts.length
        ? `<ul>${facts.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>`
        : `<p class="rail-empty">Nothing remembered yet — tell me something about you.</p>`;
    } else if (name === "notes") {
      const notes = info.notes || [];
      body.innerHTML = notes.length
        ? `<ul>${notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>`
        : `<p class="rail-empty">No notes yet.</p>`;
    } else {
      const rem = info.reminders || [];
      body.innerHTML = rem.length
        ? `<ul>${rem.map((r) => `<li>${esc(r.message)} — ${esc(String(r.due).replace("T", " "))}</li>`).join("")}</ul>`
        : `<p class="rail-empty">No reminders set.</p>`;
    }
  }

  function closePanel() {
    $("rail").hidden = true;
    app.classList.remove("rail-open");
    document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-pressed", "false"));
  }

  /* ---------------- voice ---------------- */
  async function dictate() {
    const btn = $("mic");
    btn.setAttribute("aria-pressed", "true");
    $("chat-meta").textContent = "Listening…";
    try {
      const res = await call("listen");
      const text = (res && res.text) || "";
      if (text) { $("input").value = text; submit(); }
      else { $("chat-meta").textContent = "Didn't catch that — try again."; }
    } catch (err) {
      $("chat-meta").textContent = "Mic error: " + err.message;
    }
    btn.setAttribute("aria-pressed", "false");
  }

  /* ---------------- boot ---------------- */
  function autoGrow() {
    const t = $("input");
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 180) + "px";
  }

  async function boot() {
    bridge = window.pywebview.api;
    const meta = await call("info");
    info = meta;
    const modelShort = (meta.model || "").split("/").pop();
    $("chat-meta").textContent = `${modelShort} · ${meta.apps} apps indexed`;

    const sessions = await call("list_sessions");
    if (sessions && sessions.length) await openSession(sessions[0].id);
    else await newSession();

    refreshSessions();
    $("input").focus();
    ready = true;
  }

  window.addEventListener("pywebviewready", boot);

  document.addEventListener("DOMContentLoaded", () => {
    $("new-chat").addEventListener("click", newSession);
    $("composer").addEventListener("submit", (e) => { e.preventDefault(); submit(); });
    $("input").addEventListener("input", autoGrow);
    $("input").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
    });
    $("mic").addEventListener("click", dictate);
    $("toggle-speak").addEventListener("click", () => {
      speakReplies = !speakReplies;
      $("toggle-speak").setAttribute("aria-pressed", String(speakReplies));
    });
    $("session-search").addEventListener("input", refreshSessions);
    $("rail-close").addEventListener("click", closePanel);
    document.querySelectorAll(".tab").forEach((t) => {
      t.addEventListener("click", () => {
        const isOpen = t.getAttribute("aria-pressed") === "true";
        isOpen ? closePanel() : openPanel(t.dataset.panel);
      });
    });

    // design preview when opened directly in a browser (no pywebview bridge)
    if (!window.pywebview) {
      $("chat-meta").textContent = "Design preview";
      renderEmpty();
    }
  });
})();
