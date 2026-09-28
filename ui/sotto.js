/* ============================================================
   SOTTO · app behaviour — presence, state machine, bridge
   ============================================================ */
(() => {
  const $ = (s) => document.querySelector(s);
  const body = document.body;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const bridge = () => (window.pywebview ? window.pywebview.api : null);

  let state = 'idle';           // idle | listening | understanding | thinking | responding | denied | offline
  let mode = 'home';            // home | exchange
  let level = 0;                // raw target
  let shown = 0;                // envelope-smoothed
  let env = { atk: 60, rel: 250 };
  let lastMsg = '';
  let speakAloud = true;
  let history = [];             // display turns
  let pendingTurn = null;

  /* ---------------------------------------------------------- presence */
  const presence = $('#presence');
  const canvas = $('#thread');
  const ctx = canvas.getContext('2d');
  let phase = 0, lastT = performance.now();

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function sizeCanvas() {
    const r = presence.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.max(200, r.width) * dpr;
    canvas.height = 120 * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function line(x1, y1, x2, y2, w, alpha) {
    const h = 120;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = cssVar('--accent');
    ctx.globalAlpha = alpha;
    ctx.lineWidth = w;
    ctx.lineCap = 'round';
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  function dot(x, y, r, color) {
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  }

  function draw() {
    const t = performance.now();
    const dt = Math.min(50, t - lastT);
    lastT = t;
    phase += dt / 1000;

    // envelope: attack 60ms / release 250ms (never raw jitter)
    const k = level > shown ? dt / env.atk : dt / env.rel;
    shown += Math.max(-1, Math.min(1, k)) * (level - shown);
    presence.style.setProperty('--lvl', shown.toFixed(3));

    const W = canvas.width / (Math.min(window.devicePixelRatio || 1, 2));
    const H = 120, mid = H / 2, pad = W * 0.07;

    ctx.clearRect(0, 0, W, H);
    const calm = reduced || state === 'denied' || state === 'offline';

    if (calm) {
      line(pad, mid, W - pad, mid, 1.7, 0.5);
      dot(W / 2, mid, 3.2, cssVar('--accent-strong'));
      requestAnimationFrame(draw);
      return;
    }

    if (state === 'listening') {
      // live waveform — two octaves, smoothed
      ctx.beginPath();
      const n = 96;
      for (let i = 0; i <= n; i++) {
        const x = pad + (i / n) * (W - pad * 2);
        const norm = Math.sin((i / n) * Math.PI);
        const a = 2 + shown * 26 * norm;
        const y = mid + (
          Math.sin(i * 0.22 + phase * 3.1) * 0.62 +
          Math.sin(i * 0.47 + phase * 5.3) * 0.38
        ) * a;
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      }
      ctx.strokeStyle = cssVar('--accent');
      ctx.lineWidth = 1.7;
      ctx.lineCap = 'round';
      ctx.globalAlpha = 0.9;
      ctx.stroke();
      ctx.globalAlpha = 1;
    } else if (state === 'thinking') {
      // slow knot + open centreline (never a spinner)
      const r = 15 + Math.sin(phase * 0.9) * 1.4;
      const sx = 0.78 + 0.22 * Math.sin(phase * 0.5);
      line(pad, mid, W * 0.42, mid, 1.7, 0.55);
      line(W * 0.58, mid, W - pad, mid, 1.7, 0.55);
      ctx.save();
      ctx.translate(W / 2, mid);
      ctx.scale(sx, 1);
      ctx.beginPath();
      ctx.arc(0, 0, r, phase * 0.5, phase * 0.5 + Math.PI * 1.55);
      ctx.strokeStyle = cssVar('--accent');
      ctx.lineWidth = 1.7;
      ctx.lineCap = 'round';
      ctx.globalAlpha = 0.85;
      ctx.stroke();
      ctx.restore();
      ctx.globalAlpha = 1;
    } else if (state === 'responding') {
      // speech-wave — syllable-rate motion
      ctx.beginPath();
      const n = 96;
      for (let i = 0; i <= n; i++) {
        const x = pad + (i / n) * (W - pad * 2);
        const norm = Math.sin((i / n) * Math.PI) ** 0.8;
        const a = 3 + shown * 14 * norm;
        const y = mid + Math.sin(i * 0.34 + phase * 6.4) * a;
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      }
      ctx.strokeStyle = cssVar('--accent');
      ctx.lineWidth = 1.7;
      ctx.lineCap = 'round';
      ctx.globalAlpha = 0.9;
      ctx.stroke();
      ctx.globalAlpha = 1;
    } else {
      // idle — short hairline + centre dot
      line(W * 0.42, mid, W * 0.58, mid, 1.7, 0.7);
      dot(W / 2, mid, 3.2, cssVar('--accent-strong'));
    }
    requestAnimationFrame(draw);
  }

  /* ------------------------------------------------- state machine */
  const LABEL = {
    idle: 'Tap to talk', listening: 'Listening…', understanding: 'Understood',
    thinking: 'Thinking…', responding: '', denied: 'Microphone unavailable', offline: 'Offline',
  };

  function setState(next) {
    if (state === next) return;
    state = next;
    body.dataset.state = next;
    if (next === 'listening') { $('#hint').textContent = 'Speak — pause when you’re done'; }
    else if (next === 'thinking') { $('#hint').textContent = 'Thinking…'; }
    else if (next === 'responding') { $('#hint').textContent = ''; }
    else if (next === 'idle') { $('#hint').textContent = 'Press the mic, or hold Space'; }
    else { $('#hint').textContent = LABEL[next] || ''; }
    $('#sr').textContent = LABEL[next] || next;
  }

  function setMode(next) { mode = next; body.dataset.mode = next; }

  /* --------------------------------------------------------- toast */
  let toastTimer = null;
  function toast(msg, tag = 'SOTTO', ms = 3200) {
    $('#toastMsg').textContent = msg;
    $('#toastTag').textContent = tag;
    $('#toast').classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $('#toast').classList.remove('show'), ms);
  }

  /* ------------------------------------------------------ exchange */
  function addTurn(said) {
    const el = document.createElement('article');
    el.className = 'turn';
    el.innerHTML = `<div class="said"><span class="t">${new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</span>${escapeHtml(said)}</div>`;
    $('#exchange').appendChild(el);
    history.forEach(t => t.classList.add('old'));
    history.push(el);
    scrollDown();
    return el;
  }

  function addIntent(turn, text) {
    const el = document.createElement('div');
    el.className = 'intent';
    el.innerHTML = `<span class="chip"><span class="dot"></span>${escapeHtml(text)}</span>`;
    turn.appendChild(el);
  }

  function addThinking(turn) {
    const el = document.createElement('div');
    el.className = 'thinking';
    el.innerHTML = `<span class="tpulse"></span><span>THINKING</span>`;
    turn.appendChild(el);
    return el;
  }

  function addVoice(turn) {
    const wrap = document.createElement('div');
    wrap.className = 'resp';
    const voice = document.createElement('div');
    voice.className = 'voice';
    wrap.appendChild(voice);
    turn.appendChild(wrap);
    return voice;
  }

  function streamWord(voice, chunk) {
    const parts = String(chunk).split(/(\s+)/);
    for (const p of parts) {
      if (!p) continue;
      const span = document.createElement('span');
      span.className = 'w';
      span.textContent = p;
      voice.appendChild(span);
    }
    scrollDown();
  }

  function followups(turn, items) {
    if (!items.length) return;
    const row = document.createElement('div');
    row.className = 'chips inline';
    row.innerHTML = items.map(t => `<button class="chip"><span class="dot"></span>${escapeHtml(t)}</button>`).join('');
    row.querySelectorAll('.chip').forEach(b => b.addEventListener('click', () => send(b.textContent.trim())));
    turn.appendChild(row);
  }

  function moduleTimer(turn, minutes) {
    const t = minutes * 60;
    const el = document.createElement('div');
    el.className = 'module';
    el.innerHTML = `
      <div class="m-row"><span class="m-meta">Timer</span><span class="m-label">${minutes} minutes</span></div>
      <div class="timer-num" id="tnum">${fmt(t)}</div>
      <div class="timer-bar"><i id="tbar"></i></div>
      <div class="timer-actions"><button class="btn-silent" id="tpause">Pause</button><button class="btn-quiet" id="treset">Reset</button></div>`;
    turn.querySelector('.resp').appendChild(el);
    let left = t, paused = false;
    const num = el.querySelector('#tnum'), bar = el.querySelector('#tbar');
    const iv = setInterval(() => {
      if (!paused) { left = Math.max(0, left - 1); num.textContent = fmt(left); bar.style.transform = `scaleX(${1 - left / t})`; if (!left) clearInterval(iv); }
    }, 1000);
    el.querySelector('#tpause').addEventListener('click', (e) => { paused = !paused; e.target.textContent = paused ? 'Resume' : 'Pause'; });
    el.querySelector('#treset').addEventListener('click', () => { left = t; num.textContent = fmt(t); bar.style.transform = 'scaleX(0)'; });
  }

  const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  const escapeHtml = (s) => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  const scrollDown = () => { const ex = $('#exchange'); ex.scrollTop = ex.scrollHeight; };

  /* ------------------------------------------------------ the turn */
  async function send(text, viaVoice = false) {
    text = (text || '').trim();
    if (!text) return;
    lastMsg = text;
    setMode('exchange');
    closeSheets();
    const turn = addTurn(text);
    addIntent(turn, viaVoice ? 'heard · voice' : 'typed');
    addThinking(turn);
    setState('thinking');
    const api = bridge();
    if (!api) { toast('Bridge not ready'); return; }
    await api.send(text);
    const voice = addVoice(turn);
    turn.querySelector('.thinking')?.remove();
    let said = false;
    const poll = setInterval(async () => {
      let events = [];
      try { events = JSON.parse(await api.poll() || '[]'); } catch {}
      for (const e of events) {
        if (e.type === 'text') {
          if (!said) { said = true; setState('responding'); }
          streamWord(voice, e.text);
        } else if (e.type === 'tool') {
          handleTool(turn, e);
        } else if (e.type === 'learned') {
          /* quiet */
        } else if (e.type === 'done') {
          if (!said && e.text) { setState('responding'); streamWord(voice, e.text); }
          if (speakAloud && e.text) api.say(e.text);
          followups(turn, ['Thanks', 'Do that again', 'Never mind']);
        } else if (e.type === 'error') {
          addNotice(turn, e.text);
          setState('idle');
          toast('Something went wrong — I’ll try again', 'NOTICE', 3600);
        }
      }
      let busy = true;
      try { busy = await api.busy(); } catch {}
      if (!busy && events.length === 0) {
        clearInterval(poll);
        setTimeout(() => setState('idle'), reduced ? 150 : 1200);   // settle
      }
    }, 90);
  }

  function handleTool(turn, e) {
    const name = (e.name || '').toLowerCase();
    if (name === 'set_reminder') {
      const m = /(\d+)/.exec(e.result || '');
      if (m) moduleTimer(turn, Math.max(1, parseInt(m[1], 10)));
    }
  }

  function addNotice(turn, text) {
    const el = document.createElement('div');
    el.className = 'notice warnline';
    el.innerHTML = `
      <div class="n-title">That didn’t go through.</div>
      <div class="n-body">${escapeHtml(text || '')}</div>
      <div class="n-actions"><button class="btn-silent">Try again</button></div>`;
    el.querySelector('.btn-silent').addEventListener('click', () => send(lastMsg));
    (turn.querySelector('.resp') || turn).appendChild(el);
  }

  /* -------------------------------------------------------- listening */
  let listening = false, levelTimer = null;

  async function startListening() {
    const api = bridge();
    if (!api) return;
    listening = true;
    setState('listening');
    await api.listen_start();
    levelTimer = setInterval(async () => {
      try { level = Math.max(0, Math.min(1, (await api.listen_level()) || 0)); } catch {}
    }, 50);
  }

  async function stopListening() {
    const api = bridge();
    listening = false;
    clearInterval(levelTimer);
    level = 0;
    setState('understanding');
    let text = '';
    try { text = (await api.listen_stop()) || ''; } catch {}
    if (!text) {
      setState('idle');
      toast('I didn’t quite catch that.', 'HEARD', 3000);
      return;
    }
    setState('idle');
    send(text, true);
  }

  function toggleTalk() { listening ? stopListening() : startListening(); }

  /* ---------------------------------------------------------- sheets */
  function openSheet(id) {
    closeSheets();
    document.getElementById(id).classList.add('show');
    $('#scrim').classList.add('show');
    body.classList.add('sheet-open');
    const focusable = document.querySelector(`#${id} input, #${id} button`);
    focusable?.focus();
  }
  function closeSheets() {
    document.querySelectorAll('.sheet').forEach(s => s.classList.remove('show'));
    $('#scrim').classList.remove('show');
    body.classList.remove('sheet-open');
  }

  async function loadHistory() {
    const api = bridge();
    if (!api) return;
    let rows = [];
    try { rows = JSON.parse(await api.list_sessions() || '[]'); } catch {}
    const q = ($('#hSearch').value || '').toLowerCase();
    const list = $('#hList');
    const items = (rows || []).filter(r => !q || (r.title || '').toLowerCase().includes(q));
    $('#hEmpty').classList.toggle('show', !items.length);
    list.innerHTML = items.map(r => `
      <button class="hitem" data-id="${r.id}">
        <span class="h-top"><span class="h-name">${escapeHtml(r.title || 'Untitled')}</span>
        <span class="h-when">${escapeHtml(String(r.updated || '').slice(0, 16).replace('T', ' · '))}</span></span>
        <span class="h-sum">${r.count} message${r.count === 1 ? '' : 's'}</span>
      </button>`).join('');
    list.querySelectorAll('.hitem').forEach(b => b.addEventListener('click', async () => {
      try { await api.open_session(b.dataset.id); } catch {}
      closeSheets();
      toast('Conversation restored', 'HISTORY', 2400);
    }));
  }

  /* ---------------------------------------------------------- boot */
  async function boot() {
    sizeCanvas();
    requestAnimationFrame(draw);
    const api = bridge();
    if (api) {
      try {
        const info = JSON.parse(await api.info() || '{}');
        if (info.voices?.length) {
          $('#voiceSelect').innerHTML = info.voices.map(v => `<option>${escapeHtml(v)}</option>`).join('');
          $('#voiceSelect').value = info.current_voice || info.voices[0];
        }
        if (info.providers?.length) {
          $('#providerList').innerHTML = info.providers.map(p =>
            `<div class="result"><span class="r-top"><span class="r-name">${escapeHtml(p.name)}</span>
             <span class="r-meta">${p.key ? 'KEY SET' : 'NO KEY'}</span></span>
             <span class="r-take">${escapeHtml(p.model || '')}</span></div>`).join('');
        }
      } catch {}
    }
    const h = new Date().getHours();
    $('#lead').textContent = h < 12 ? 'Good morning.' : h < 18 ? 'Good afternoon.' : 'Good evening.';
  }

  /* --------------------------------------------------------- events */
  window.addEventListener('pywebviewready', boot);
  window.addEventListener('resize', sizeCanvas);
  document.addEventListener('DOMContentLoaded', () => {
    $('#mic').addEventListener('click', toggleTalk);
    $('#btnHistory').addEventListener('click', () => { loadHistory(); openSheet('sheetHistory'); });
    $('#btnType').addEventListener('click', () => openSheet('sheetType'));
    $('#btnTheme').addEventListener('click', () => {
      body.dataset.theme = body.dataset.theme === 'light' ? 'dark' : 'light';
      localStorage.setItem('sotto-theme', body.dataset.theme);
      sizeCanvas();
    });
    const saved = localStorage.getItem('sotto-theme');
    if (saved) body.dataset.theme = saved;

    $('#scrim').addEventListener('click', closeSheets);
    document.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', closeSheets));
    $('#hSearch').addEventListener('input', loadHistory);
    $('#voiceSelect').addEventListener('change', (e) => bridge()?.set_voice(e.target.value));
    $('#speakSwitch').addEventListener('click', (e) => {
      speakAloud = !speakAloud;
      e.currentTarget.setAttribute('aria-pressed', String(speakAloud));
    });
    $('#btnSend').addEventListener('click', () => { const v = $('#typeInput').value; $('#typeInput').value = ''; send(v); });
    $('#typeInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') { const v = e.target.value; e.target.value = ''; send(v); } });

    document.querySelectorAll('[data-say]').forEach(c => c.addEventListener('click', () => send(c.dataset.say)));

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeSheets();
      if (e.code === 'Space' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '') && !body.classList.contains('sheet-open')) {
        e.preventDefault(); toggleTalk();
      }
    });
    if (!window.pywebview) boot();
  });
})();
