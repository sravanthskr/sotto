/* ============================================================
   SOTTO · app behaviour v2 — presence, state language, bridge
   States: idle · ready · listening · understanding · thinking · responding ·
           interrupted · denied · offline · (speaking flag)
   Bridge: window.pywebview.api — existing methods preserved;
   new methods are OPTIONAL and used only when present (capability-based UI).
   ============================================================ */
(() => {
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const body = document.body;
  const reducedMedia = window.matchMedia('(prefers-reduced-motion: reduce)');
  const bridge = () => (window.pywebview ? window.pywebview.api : null);
  const hasApi = (name) => { const a = bridge(); return !!(a && typeof a[name] === 'function'); };
  async function callIf(name, ...args) { if (!hasApi(name)) return null; try { return await bridge()[name](...args); } catch { return null; } }
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  let state = 'idle';           // idle | ready | listening | understanding | thinking | responding | interrupted | denied | offline
  let mode = 'home';            // home | exchange
  let level = 0, shown = 0;     // envelope
  const env = { atk: 60, rel: 250 };
  let speaking = false;
  let lastMsg = '';
  let speakAloud = true;
  let retries = 0;
  const history = [];
  let stateSince = performance.now();

  /* ---------------------------------------------------------- presence */
  const presence = $('#presence');
  const canvas = $('#thread');
  const ctx = canvas.getContext('2d');
  let phase = 0, lastT = performance.now();

  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  function sizeCanvas() {
    const r = presence.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.max(200, Math.round(r.width)) * dpr;
    canvas.height = 120 * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function line(x1, y1, x2, y2, w, alpha) {
    ctx.beginPath();
    ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
    ctx.strokeStyle = cssVar('--accent');
    ctx.globalAlpha = alpha; ctx.lineWidth = w; ctx.lineCap = 'round'; ctx.stroke();
    ctx.globalAlpha = 1;
  }
  function dot(x, y, r, color) { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill(); }

  /* wave helpers — one filament, many behaviours (Apple-informed: morph, don't swap) */
  function waveY(i, n, midY, amp, freq, speed, harm) {
    const u = i / n;
    const win = Math.pow(Math.sin(Math.PI * u), 1.5);
    const y1 = Math.sin(u * freq + phase * speed);
    const y2 = harm ? 0.35 * Math.sin(u * freq * 2.3 + phase * speed * 1.7) : 0;
    return midY + amp * win * (y1 + y2);
  }
  function strokeWave(xs, xe, amp, opts) {
    opts = opts || {};
    const n = 110, midY = 60;
    ctx.beginPath();
    for (let i = 0; i <= n; i++) {
      const x = xs + (i / n) * (xe - xs);
      const y = waveY(i, n, midY, amp, opts.freq || 9.4, opts.speed == null ? 2.6 : opts.speed, opts.harm);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    if (opts.halo) { ctx.strokeStyle = cssVar('--accent'); ctx.globalAlpha = 0.10; ctx.lineWidth = (opts.w || 2) * 5; ctx.lineCap = 'round'; ctx.stroke(); }
    ctx.strokeStyle = cssVar('--accent');
    ctx.globalAlpha = opts.alpha == null ? 0.95 : opts.alpha;
    ctx.lineWidth = opts.w || 2;
    ctx.lineCap = 'round'; ctx.stroke(); ctx.globalAlpha = 1;
  }

  function draw() {
    try { drawFrame(performance.now()); } catch (e) { /* keep the presence alive no matter what */ }
    requestAnimationFrame(draw);
  }

  /* state-specific STILL silhouettes — even with reduced motion, every state looks different */
  function drawStill(W, mid, pad) {
    const amp = Math.max(shown, 0.15);
    if (state === 'listening') { strokeWave(pad, W - pad, 10 + amp * 30, { freq: 9.8, speed: 0, harm: true, w: 2, alpha: 0.9 }); dot(W / 2, mid, 2.6, cssVar('--accent-strong')); }
    else if (state === 'understanding') { strokeWave(W * 0.3, W * 0.7, 3, { freq: 9.8, speed: 0, w: 2.4, alpha: 0.95 }); dot(W / 2, mid, 3.4, cssVar('--accent-strong')); }
    else if (state === 'thinking') {
      line(pad, mid, W / 2 - 46, mid, 1.8, 0.5); line(W / 2 + 46, mid, W - pad, mid, 1.8, 0.5);
      ctx.beginPath(); ctx.arc(W / 2, mid, 15, 0, Math.PI * 2); ctx.strokeStyle = cssVar('--accent'); ctx.globalAlpha = 0.3; ctx.lineWidth = 1.8; ctx.stroke();
      ctx.beginPath(); ctx.arc(W / 2, mid, 15, -0.6, Math.PI * 0.5); ctx.globalAlpha = 0.95; ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.stroke(); ctx.globalAlpha = 1;
    }
    else if (state === 'responding') { strokeWave(pad, W - pad, 8 + amp * 24, { freq: 7.2, speed: 0, w: 2.2, alpha: 0.95, halo: true }); dot(W / 2, mid, 2.4, cssVar('--accent-strong')); }
    else if (state === 'ready') { strokeWave(W / 2 - W * 0.34, W / 2 + W * 0.34, 1.5, { freq: 5, speed: 0, w: 2, alpha: 0.9 }); dot(W / 2, mid, 3.8, cssVar('--accent-strong')); }
    else if (state === 'interrupted') { strokeWave(W * 0.3, W * 0.7, 1, { freq: 7.2, speed: 0, w: 2, alpha: 0.5 }); }
    else if (state === 'denied' || state === 'offline') { strokeWave(W * 0.38, W * 0.62, 0, { alpha: 0.4, w: 1.8 }); }
    else { strokeWave(W / 2 - W * 0.09, W / 2 + W * 0.09, 1, { freq: 4, speed: 0, w: 2, alpha: 0.75 }); dot(W / 2, mid, 3.4, cssVar('--accent-strong')); }
  }

  function drawFrame(t) {
    const dt = Math.min(50, t - lastT); lastT = t; phase += dt / 1000;
    const k = level > shown ? dt / env.atk : dt / env.rel;
    shown += Math.max(-1, Math.min(1, k)) * (level - shown);
    presence.style.setProperty('--lvl', shown.toFixed(3));

    const W = canvas.width / (Math.min(window.devicePixelRatio || 1, 2));
    const H = 120, mid = H / 2, pad = W * 0.06;
    const since = (t - stateSince) / 1000;
    ctx.clearRect(0, 0, W, H);
    const calm = reducedMedia.matches || body.classList.contains('reduce-motion') || state === 'denied' || state === 'offline';

    if (calm) { drawStill(W, mid, pad); return; }

    if (state === 'listening') {
      /* user is talking — quick, dense, reactive; blooms in; a floor of motion so pauses still breathe */
      const bloom = Math.min(1, since / 0.24);
      const xs = W / 2 - (W / 2 - pad) * bloom, xe = W / 2 + (W / 2 - pad) * bloom;
      strokeWave(xs, xe, 4 + shown * 40, { freq: 9.8, speed: 3.0, harm: true, w: 2 });
      dot(W / 2, mid, 2.6, cssVar('--accent-strong'));
    } else if (state === 'understanding') {
      /* speech ended — the wave gathers toward the centre and holds as a bright filament */
      const p = Math.min(1, since / 0.45);
      const half = (W / 2 - pad) * (1 - p * 0.82);
      strokeWave(W / 2 - half, W / 2 + half, (4 + shown * 30) * (1 - p), { freq: 9.8, speed: 3.0, w: 2 + p * 0.6 });
      if (p > 0.55) dot(W / 2, mid, 3.4, cssVar('--accent-strong'));
    } else if (state === 'thinking') {
      /* working — slow knot with a travelling light; no reactivity, period ≥5s */
      line(pad, mid, W / 2 - 46, mid, 1.8, 0.5);
      line(W / 2 + 46, mid, W - pad, mid, 1.8, 0.5);
      const r = 15 + Math.sin(phase * 0.7) * 1.6;
      ctx.beginPath(); ctx.arc(W / 2, mid, r, 0, Math.PI * 2);
      ctx.strokeStyle = cssVar('--accent'); ctx.globalAlpha = 0.28; ctx.lineWidth = 1.8; ctx.stroke();
      ctx.beginPath(); ctx.arc(W / 2, mid, r, phase * 0.55, phase * 0.55 + Math.PI * 0.6);
      ctx.globalAlpha = 0.95; ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.stroke();
      ctx.globalAlpha = 1;
    } else if (state === 'responding') {
      /* the assistant talks — softer, slower, rounder than listening; a faint halo for presence */
      strokeWave(pad, W - pad, 3 + shown * 34, { freq: 7.2, speed: 2.2, w: 2.2, halo: true });
      dot(W / 2, mid, 2.4, cssVar('--accent-strong'));
    } else if (state === 'interrupted') {
      /* stopped — the wave falls and stills, then the dot returns */
      const d = Math.max(0, 1 - since / 0.9);
      const half = (W / 2 - pad) * (0.55 + 0.45 * (1 - d));
      strokeWave(W / 2 - half, W / 2 + half, (3 + shown * 20) * d, { freq: 7.2, speed: 2.2, w: 2, alpha: 0.35 + 0.5 * d });
      if (d < 0.45) dot(W / 2, mid, 3.2, cssVar('--accent-strong'));
    } else if (state === 'ready') {
      /* about to listen — the filament extends and the dot brightens */
      const grow = Math.min(1, since / 0.3);
      const half = W * (0.14 + 0.2 * grow);
      strokeWave(W / 2 - half, W / 2 + half, 1.2, { freq: 5, speed: 0.9, w: 2, alpha: 0.9 });
      dot(W / 2, mid, 3.8, cssVar('--accent-strong'));
    } else {
      /* idle — a held breath: short filament, calm dot */
      const half = W * 0.085 + Math.sin(phase * 0.98) * W * 0.006;
      strokeWave(W / 2 - half, W / 2 + half, 0.8 + 0.5 * Math.sin(phase * 0.98), { freq: 4, speed: 0.6, w: 2, alpha: 0.75 });
      dot(W / 2, mid, 3.4 + 0.25 * Math.sin(phase * 0.98), cssVar('--accent-strong'));
    }
  }

  /* ------------------------------------------------- state machine */
  const LABEL = {
    idle: 'Tap to talk', ready: 'Ready', listening: 'Listening…', understanding: 'Understood',
    thinking: 'Thinking…', responding: '', interrupted: 'Stopped', denied: 'Microphone unavailable', offline: 'Offline',
  };
  const HINT = {
    idle: 'Press the mic, or hold Space', ready: 'Listening…',
    listening: 'Speak — pause when you’re done', thinking: 'Thinking…',
  };

  function setState(next) {
    if (state === next) return;
    state = next; stateSince = performance.now();
    body.dataset.state = next;
    if (HINT[next] !== undefined) $('#hint').textContent = HINT[next];
    else if (next !== 'responding') $('#hint').textContent = LABEL[next] || '';
    else $('#hint').textContent = '';
    $('#sr').textContent = LABEL[next] || next;
  }
  function setMode(next) { mode = next; body.dataset.mode = next; }

  function setSpeaking(on) {
    speaking = on;
    body.classList.toggle('speaking', on);
    const mic = $('#mic');
    if (mic) mic.setAttribute('aria-label', on ? 'Stop speaking' : 'Talk');
  }

  /* --------------------------------------------------------- toast */
  let toastTimer = null;
  function toast(msg, tag = 'SOTTO', ms = 3200) {
    $('#toastMsg').textContent = msg;
    $('#toastTag').textContent = tag;
    $('#toast').classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $('#toast').classList.remove('show'), ms);
  }

  /* --------------------------------------------------------- theme */
  const SUN = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 3.4v2M12 18.6v2M3.4 12h2M18.6 12h2M6 6l1.4 1.4M16.6 16.6L18 18M18 6l-1.4 1.4M7.4 16.6L6 18"/></svg>';
  const MOON = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="M20 14.2A8.4 8.4 0 0 1 9.8 4a8.5 8.5 0 1 0 10.2 10.2z"/></svg>';
  let themePref = 'light';
  const systemLight = () => window.matchMedia('(prefers-color-scheme: light)').matches;
  function resolveTheme(pref) { return pref === 'system' ? (systemLight() ? 'light' : 'dark') : (pref === 'light' ? 'light' : 'dark'); }
  function applyThemePref(pref, notify = false) {
    themePref = pref;
    const resolved = resolveTheme(pref);
    body.dataset.theme = resolved;
    $('#btnTheme').innerHTML = resolved === 'light' ? MOON : SUN;
    $('#btnTheme').setAttribute('aria-label', resolved === 'light' ? 'Switch to dark theme' : 'Switch to light theme');
    $$('#segThemeQuick button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.themeSet === pref)));
    try { localStorage.setItem('sotto-theme-v2', pref); } catch {}
    sizeCanvas();
    if (notify) toast(resolved === 'light' ? 'Light theme — morning paper' : 'Dark theme', 'THEME', 1800);
  }
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { if (themePref === 'system') applyThemePref('system'); });

  /* ------------------------------------------------ clock & status */
  function tickClock() {
    const now = new Date();
    $('#stClock').textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  async function pollStatus() {
    const raw = await callIf('status');
    const box = $('.homestatus');
    const dot = $('#stDot');
    let s = null;
    try { s = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch {}
    if (!s) { box.classList.remove('off'); if (dot) dot.classList.remove('warn'); $('#stConn').textContent = 'Standalone'; return; }
    const ok = s.online !== false;
    box.classList.toggle('off', !ok);
    if (dot) dot.classList.toggle('warn', !!(ok && s.state && s.state !== 'ready'));
    const text = s.state === 'connecting' ? 'Connecting…' : s.state === 'failover' ? 'Fallback · ' + (s.provider || '') : (s.provider ? 'Online · ' + s.provider : 'Online');
    $('#stConn').textContent = ok ? text : 'Offline';
  }

  /* ------------------------------------------------------ exchange */
  const escapeHtml = (s) => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const scrollDown = () => { const ex = $('#exchange'); ex.scrollTop = ex.scrollHeight; };

  function addTurn(said) {
    const el = document.createElement('article');
    el.className = 'turn';
    el.innerHTML = `<div class="said"><span class="t">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>${escapeHtml(said)}</div>`;
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
    return el;
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
  function respActions(turn, text) {
    const row = document.createElement('div');
    row.className = 'resp-actions';
    const copy = document.createElement('button');
    copy.className = 'ract';
    copy.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8.5" y="8.5" width="11" height="11" rx="2.5"/><path d="M5.5 15.2V6.7A2.2 2.2 0 0 1 7.7 4.5h8.5"/></svg><span>Copy</span>';
    copy.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(text); copy.querySelector('span').textContent = 'Copied'; setTimeout(() => copy.querySelector('span').textContent = 'Copy', 1800); } catch { toast('Clipboard unavailable', 'NOTICE'); }
    });
    row.appendChild(copy);
    if ($('#speakSwitch').getAttribute('aria-pressed') === 'true' && hasApi('say')) {
      const again = document.createElement('button');
      again.className = 'ract';
      again.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9.4v5.2h3.4L12 18.5V5.5L7.4 9.4z"/><path d="M15.5 8.6a4.6 4.6 0 0 1 0 6.8"/></svg><span>Speak again</span>';
      again.addEventListener('click', () => { callIf('say', text); setSpeaking(true); speakFallbackTimer(text); });
      row.appendChild(again);
    }
    if (hasApi('say_slow')) {
      const slower = document.createElement('button');
      slower.className = 'ract';
      slower.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14M5 7v10"/></svg><span>Slower</span>';
      slower.addEventListener('click', () => { callIf('say_slow', text); setSpeaking(true); speakFallbackTimer(text, 1.45); toast('Playing it slowly', 'VOICE', 1600); });
      row.appendChild(slower);
    }
    (turn.querySelector('.resp') || turn).appendChild(row);
    return row;
  }
  function followups(turn, items) {
    if (!items || !items.length) return;
    const row = document.createElement('div');
    row.className = 'chips inline';
    row.innerHTML = items.map(t => `<button class="chip"><span class="dot"></span>${escapeHtml(t)}</button>`).join('');
    row.querySelectorAll('.chip').forEach(b => b.addEventListener('click', () => send(b.textContent.trim())));
    turn.appendChild(row);
  }

  /* ------------------------------------------------------ modules */
  function bar(title, rows) {
    const el = document.createElement('div');
    el.className = 'module';
    const body = rows.map(r => {
      const v = Math.max(0, Math.min(100, Number(r.value) || 0));
      const high = v >= 85 ? ' high' : '';
      return `<div class="bar-row${high}"><span class="bar-lab">${escapeHtml(r.label)}</span><span class="bar-track"><i class="bar-fill" style="width:${v}%"></i></span><span class="bar-val">${escapeHtml(r.text || v + '%')}</span></div>`;
    }).join('');
    el.innerHTML = `<div class="m-row"><span class="m-meta">${escapeHtml(title)}</span><span class="m-label">${escapeHtml(rows.length + ' readings')}</span></div>${body}`;
    return el;
  }
  function fmt(s) { s = Math.max(0, Math.round(s)); return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; }

  const MODULES = {
    set_reminder(turn, e) { const m = /(\d+)/.exec(e.result || e.text || ''); if (m) timerModule(turn, Math.max(1, parseInt(m[1], 10))); else generic(turn, e); },
    system_status(turn, e) {
      const rows = e.rows || (e.payload && e.payload.rows);
      if (Array.isArray(rows) && rows.length) turn.querySelector('.resp').appendChild(bar('System', rows));
      else generic(turn, e);
    },
    volume(turn, e) {
      const p = e.payload || e; const v = Number(p.level);
      if (Number.isNaN(v)) return generic(turn, e);
      const el = document.createElement('div');
      el.className = 'module';
      el.innerHTML = `<div class="m-row"><span class="m-meta">Volume</span><span class="m-label" id="volVal">${v}%</span></div>
        <input class="range" id="volRange" type="range" min="0" max="100" value="${v}" aria-label="Volume">
        <div class="m-row"><span class="m-label">${p.muted ? 'Muted' : 'Output — default device'}</span><button class="m-quiet" id="volMute">${p.muted ? 'Unmute' : 'Mute'}</button></div>`;
      turn.querySelector('.resp').appendChild(el);
      const range = el.querySelector('#volRange'); const val = el.querySelector('#volVal');
      let send_t;
      range.addEventListener('input', () => { val.textContent = range.value + '%'; clearTimeout(send_t); send_t = setTimeout(() => callIf('set_volume', Number(range.value)), 160); });
      el.querySelector('#volMute').addEventListener('click', (ev) => { callIf('media_control', 'mute_toggle'); ev.target.textContent = ev.target.textContent === 'Mute' ? 'Unmute' : 'Mute'; toast('Toggled mute', 'SYSTEM', 1600); });
    },
    media(turn, e) {
      const p = e.payload || e;
      if (p.none) {
        const el = document.createElement('div');
        el.className = 'module';
        el.innerHTML = '<div class="m-row"><span class="m-meta">Media</span><span class="m-label">Idle</span></div><div class="m-sub">Nothing is playing right now.</div>';
        turn.querySelector('.resp').appendChild(el);
        return;
      }
      const el = document.createElement('div');
      el.className = 'module';
      el.innerHTML = `<div class="mu">
          <span class="art"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18.5V6.8l10-2v11.7"/><circle cx="6.6" cy="18.5" r="2.6"/><circle cx="16.6" cy="16.5" r="2.6"/></svg></span>
          <div style="flex:1;min-width:0"><div class="m-title" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(p.title || 'Now playing')}</div><div class="m-sub">${escapeHtml(p.artist || '')}${p.album ? ' — ' + escapeHtml(p.album) : ''}</div></div>
          <button class="nav" data-mc="prev" aria-label="Previous track"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 6.5L8.5 12l6.5 5.5"/></svg></button>
          <button class="btn-silent" id="muToggle" style="min-width:44px;padding:10px 12px" aria-label="Play or pause"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M9 6.5v11M15 6.5v11"/></svg></button>
          <button class="nav" data-mc="next" aria-label="Next track"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6.5l6.5 5.5L9 17.5"/></svg></button>
        </div>
        <div class="prog"><i id="muProg"></i></div>
        <div class="times"><span id="muCur">${fmt(p.pos || 0)}</span><span>${fmt(p.dur || 0)}</span></div>`;
      turn.querySelector('.resp').appendChild(el);
      el.querySelectorAll('[data-mc]').forEach(b => b.addEventListener('click', () => { callIf('media_control', b.dataset.mc); toast(b.dataset.mc === 'next' ? 'Next track' : 'Previous track', 'MEDIA', 1400); }));
      let pos = Number(p.pos || 0), dur = Number(p.dur || 0), playing = p.playing !== false;
      const upd = () => { el.querySelector('#muProg').style.width = dur ? ((pos / dur) * 100).toFixed(2) + '%' : '0%'; el.querySelector('#muCur').textContent = fmt(pos); };
      upd();
      const iv = setInterval(() => { if (!el.isConnected) return clearInterval(iv); if (playing && dur) { pos = Math.min(dur, pos + 1); upd(); } }, 1000);
      el.querySelector('#muToggle').addEventListener('click', () => { playing = !playing; callIf('media_control', playing ? 'play' : 'pause'); toast(playing ? 'Playing' : 'Paused', 'MEDIA', 1500); });
    },
    downloads(turn, e) {
      const p = e.payload || e;
      const files = Array.isArray(p.files) ? p.files : [];
      const groups = Array.isArray(p.groups) ? p.groups : [];
      const el = document.createElement('div');
      el.className = 'module';
      const head = `<div class="m-row"><span class="m-meta">Downloads</span><span class="m-label">${p.moved != null ? escapeHtml(String(p.moved)) + ' files organised' : 'Recent'}</span></div>`;
      const groupsHtml = groups.length ? `<div class="pill-meta">${groups.map(g => `<span>${escapeHtml(g.name)} · ${escapeHtml(String(g.n))}</span>`).join('')}</div>` : '';
      const rows = files.slice(0, 5).map(f => `<div class="frow"><span class="fname">${escapeHtml(f.name || f)}</span>${f.note ? `<span class="fnote">${escapeHtml(f.note)}</span>` : ''}${f.tag ? `<span class="ftag">${escapeHtml(f.tag)}</span>` : ''}</div>`).join('');
      el.innerHTML = head + groupsHtml + (rows ? `<div>${rows}</div>` : '');
      turn.querySelector('.resp').appendChild(el);
    },
    clipboard(turn, e) {
      const p = e.payload || e; const text = String(p.text || '');
      if (!text) return generic(turn, e);
      const el = document.createElement('div');
      el.className = 'module';
      el.innerHTML = `<div class="m-row"><span class="m-meta">Clipboard</span><span class="m-label">${text.length} chars</span></div>
        <div class="clipbody">${escapeHtml(text)}</div>
        <button class="m-quiet" id="clipCopy">Copy again</button>`;
      turn.querySelector('.resp').appendChild(el);
      el.querySelector('#clipCopy').addEventListener('click', async () => { try { await navigator.clipboard.writeText(text); toast('Copied', 'CLIPBOARD', 1600); } catch { toast('Clipboard unavailable', 'NOTICE'); } });
    },
    file(turn, e) {
      const p = e.payload || e;
      const el = document.createElement('div');
      el.className = 'module';
      el.innerHTML = `<div class="ev"><span class="glyph"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3.5h8l4 4V20a.5.5 0 0 1-.5.5h-11A.5.5 0 0 1 6 20V3.5z"/><path d="M14 3.5V8h4"/></svg></span>
        <div style="min-width:0"><div class="m-title" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(p.name || 'File')}</div><div class="m-sub">${escapeHtml([p.kind, p.size, p.where].filter(Boolean).join(' · '))}</div></div></div>`;
      turn.querySelector('.resp').appendChild(el);
    },
    action(turn, e) {
      const p = e.payload || e;
      const el = document.createElement('div');
      el.className = 'module';
      const okIcon = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
      const warnIcon = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="8.4"/><path d="M12 8.2v4.6M12 15.7v.2"/></svg>';
      if (p.confirm) {
        el.innerHTML = `<div class="actline"><span class="glyph">${warnIcon}</span><span>${escapeHtml(p.what || 'Do this?')}</span></div>
          <div class="actbtns"><button class="btn-silent" data-act="ok">${escapeHtml(p.confirmLabel || 'Do it')}</button><button class="btn-quiet" data-act="no">Cancel</button></div>`;
        el.querySelector('[data-act="ok"]').addEventListener('click', async () => {
          await callIf('confirm_action', p.id);
          el.innerHTML = `<div class="actline"><span class="glyph">${okIcon}</span><span>${escapeHtml(p.done || p.what || 'Done')}</span></div>`;
          toast('Done', 'SYSTEM', 1800);
        });
        el.querySelector('[data-act="no"]').addEventListener('click', () => { el.innerHTML = '<div class="m-sub" style="color:var(--ink-3)">Cancelled — nothing happened.</div>'; });
      } else {
        el.innerHTML = `<div class="actline"><span class="glyph">${okIcon}</span><span>${escapeHtml(p.what || e.text || 'Done')}</span></div>`;
      }
      turn.querySelector('.resp').appendChild(el);
    },
  };

  function generic(turn, e) {
    // future-proof fallback: any tool payload renders as a quiet key/value card
    const p = e.payload || {};
    const rows = p.rows || (Array.isArray(p.lines) ? p.lines.map(l => ({ label: l[0], value: l[1] })) : []);
    const el = document.createElement('div');
    el.className = 'module';
    const head = `<div class="m-row"><span class="m-meta">${escapeHtml((e.name || 'result').replace(/_/g, ' '))}</span><span class="m-label"></span></div>`;
    const bodyHtml = rows.length
      ? rows.map(r => `<div class="kl"><span class="k">${escapeHtml(r.label)}</span><span class="v">${escapeHtml(String(r.value))}</span></div>`).join('')
      : `<div class="m-sub">${escapeHtml(e.result || e.text || 'No details provided.')}</div>`;
    el.innerHTML = head + bodyHtml;
    (turn.querySelector('.resp') || turn).appendChild(el);
  }

  function handleTool(turn, e) {
    const name = (e.name || '').toLowerCase();
    const fn = MODULES[name.replace(/[^a-z_]/g, '')] || generic;
    fn(turn, e);
  }

  function timerModule(turn, minutes) {
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
      if (!el.isConnected) return clearInterval(iv);
      if (!paused) { left = Math.max(0, left - 1); num.textContent = fmt(left); bar.style.transform = `scaleX(${1 - left / t})`; if (!left) clearInterval(iv); }
    }, 1000);
    el.querySelector('#tpause').addEventListener('click', (ev) => { paused = !paused; ev.target.textContent = paused ? 'Resume' : 'Pause'; });
    el.querySelector('#treset').addEventListener('click', () => { left = t; num.textContent = fmt(t); bar.style.transform = 'scaleX(0)'; });
  }

  /* ------------------------------------------------------ the turn */
  let speakingFallback = null;
  function speakFallbackTimer(text, factor = 1) { clearTimeout(speakingFallback); speakingFallback = setTimeout(() => setSpeaking(false), Math.min(45000, 1200 + String(text || '').length * 62 * factor)); }

  async function send(text, viaVoice = false, isRetry = false) {
    text = (text || '').trim();
    if (!text) return;
    if (!isRetry) retries = 0;
    if (speaking) stopSpeaking(true);
    lastMsg = text;
    setMode('exchange');
    closeSheets();
    const turn = addTurn(text);
    const intentChip = addIntent(turn, viaVoice ? 'heard' : 'typed');
    addThinking(turn);
    setState('thinking');
    const api = bridge();
    if (!api) { addNotice(turn, 'The Python bridge isn’t connected, so I can’t think yet. Start the app normally and try again.'); setState('idle'); return; }
    callIf('log', 'send ' + (viaVoice ? 'voice' : 'typed') + (isRetry ? ' retry' : '') + ': ' + text.slice(0, 90));
    try { await api.send(text); callIf('log', 'send resolved'); } catch (err) { callIf('log', 'send rejected: ' + err); addNotice(turn, 'The request didn’t reach the assistant.'); setState('idle'); return; }
    const voice = addVoice(turn);
    turn.querySelector('.thinking')?.remove();
    let said = false;
    const poll = setInterval(async () => {
      let events = [];
      try { events = JSON.parse((await api.poll()) || '[]'); } catch {}
      if (events.length) callIf('log', 'poll: ' + events.map((x) => x.type).join(','));
      for (const e of events) {
        if (e.type === 'intent' && e.text) { intentChip.querySelector('.chip').innerHTML = '<span class="dot"></span>' + escapeHtml(e.text); }
        else if (e.type === 'text') { if (!said) { said = true; setState('responding'); } streamWord(voice, e.text); }
        else if (e.type === 'tool') { handleTool(turn, e); }
        else if (e.type === 'notice') { addNotice(turn, e.text, e.tone || 'info'); }
        else if (e.type === 'prompt') { showPrompt(escapeHtml(e.text), e.action ? { action: e.action, onAction: () => send(e.say || 'Organise my downloads') } : null); }
        else if (e.type === 'speaking') { setSpeaking(true); }
        else if (e.type === 'speaking_end') { setSpeaking(false); }
        else if (e.type === 'learned') { /* quiet */ }
        else if (e.type === 'done') {
          callIf('log', 'done');
          retries = 0;
          if (!said && e.text) { setState('responding'); streamWord(voice, e.text); }
          const answer = e.full || (voice.textContent || '').trim();
          if (answer) respActions(turn, answer);
          if (speakAloud && e.text) { callIf('say', e.text); setSpeaking(true); speakFallbackTimer(e.text); }
          followups(turn, e.followups || ['Tell me more', 'Do that again', 'Never mind']);
        }
        else if (e.type === 'error') {
          callIf('log', 'error event: ' + (e.text || ''));
          addNotice(turn, e.text);
          setState('idle');
          if (retries < 2) {
            retries += 1;
            const delay = retries === 1 ? 4000 : 30000;
            toast(retries === 1 ? 'Trying again — one moment…' : 'One more try…', 'NOTICE', 3600);
            setTimeout(() => { if (lastMsg === text) send(lastMsg, viaVoice === true, true); }, delay);
          } else {
            toast('I couldn’t reach my thinking service — connection hiccup.', 'NOTICE', 4200);
          }
        }
      }
      let busy = true;
      try { busy = await api.busy(); } catch {}
      if (!busy && events.length === 0) {
        callIf('log', 'settle busy=false');
        clearInterval(poll);
        if (state === 'thinking' || state === 'understanding') setState('responding');
        setTimeout(() => { if (state !== 'listening' && state !== 'interrupted') setState('idle'); }, reducedMedia.matches ? 150 : 1200);
      }
    }, 90);
  }

  function addNotice(turn, text, tone = 'warn') {
    const el = document.createElement('div');
    el.className = tone === 'warn' ? 'notice warnline' : 'notice';
    el.innerHTML = `
      <div class="n-title">${tone === 'warn' ? 'That didn’t go through.' : 'A note from Sotto.'}</div>
      <div class="n-body">${escapeHtml(text || '')}</div>
      ${tone === 'warn' ? '<div class="n-actions"><button class="btn-silent">Try again</button></div>' : ''}`;
    el.querySelector('.btn-silent')?.addEventListener('click', () => send(lastMsg));
    (turn.querySelector('.resp') || turn).appendChild(el);
  }

  /* -------------------------------------------------------- listening */
  let listening = false, levelTimer = null, partialTimer = null;

  function hideLive() { const live = $('#liveLine'); if (!live) return; clearInterval(partialTimer); partialTimer = null; live.hidden = true; live.innerHTML = ''; }

  async function startListening() {
    if (listening) return;
    const api = bridge();
    if (!api) { toast('The assistant backend isn’t running — start the app normally.', 'NOTICE', 3600); return; }
    listening = true;
    setState('listening');
    const live = $('#liveLine');
    if (live) { live.hidden = false; live.classList.remove('dim'); live.innerHTML = '<span class="caret"></span>'; }
    if (hasApi('listen_partial')) {
      partialTimer = setInterval(async () => {
        const p = await callIf('listen_partial');
        const l = $('#liveLine');
        if (p != null && l) l.innerHTML = escapeHtml(String(p)) + '<span class="caret"></span>';
      }, 260);
    }
    try { await api.listen_start(); } catch { listening = false; setState('idle'); hideLive(); return; }
    levelTimer = setInterval(async () => {
      try { level = Math.max(0, Math.min(1, (await api.listen_level()) || 0)); } catch {}
    }, 50);
  }

  async function stopListening() {
    if (!listening) return;
    const api = bridge();
    listening = false;
    clearInterval(levelTimer);
    clearInterval(partialTimer); partialTimer = null;
    level = 0;
    setState('understanding');
    let text = '';
    try { text = (await api.listen_stop()) || ''; } catch {}
    const live = $('#liveLine');
    if (live && text) { live.classList.add('dim'); live.innerHTML = escapeHtml(text); await wait(380); }
    hideLive();
    if (!text) {
      setState('idle');
      toast('I didn’t quite catch that.', 'HEARD', 3000);
      return;
    }
    setState('idle');
    send(text, true);
  }

  function stopSpeaking(silent = false) {
    if (!speaking) return;
    setSpeaking(false);
    clearTimeout(speakingFallback);
    callIf('stop_speaking');
    setState('interrupted');
    if (!silent) toast('Stopped', 'SOTTO', 1400);
    setTimeout(() => { if (state === 'interrupted') setState('idle'); }, reducedMedia.matches ? 150 : 900);
  }

  function toggleTalk() {
    if (speaking) { stopSpeaking(); return; }
    listening ? stopListening() : startListening();
  }

  /* ---------------------------------------------------------- sheets */
  const sideMode = () => window.matchMedia('(min-width: 768px)').matches;
  let lastOpenAt = 0;
  function toggleSheet(id) {
    const s = document.getElementById(id);
    if (s && s.classList.contains('show') && s.classList.contains('side')) { closeSheets(); return; }
    if (id === 'sheetHistory') loadHistory();
    if (id === 'sheetMemory') loadMemory();
    if (id === 'sheetSettings') closeQuick();
    openSheet(id);
  }
  function openSheet(id) {
    closeSheets();
    const sheet = document.getElementById(id);
    if (!sheet) return;
    const side = sideMode();
    sheet.classList.toggle('side', side);
    sheet.classList.add('show');
    $$('.sheet.side').forEach((s) => { if (s !== sheet) s.classList.remove('show'); });
    if (!side) { $('#scrim').classList.add('show'); body.classList.add('sheet-open'); }
    else { body.classList.add('panel-open'); }
    lastOpenAt = performance.now();
    const focusable = sheet.querySelector('[data-autofocus]') || sheet.querySelector('input, button, select');
    setTimeout(() => focusable?.focus(), reducedMedia.matches ? 20 : 360);
  }
  function closeSheets() {
    $$('.sheet').forEach(s => s.classList.remove('show'));
    $('#scrim').classList.remove('show');
    body.classList.remove('sheet-open');
    body.classList.remove('panel-open');
  }

  /* quick settings popover (anchored, not a sheet) */
  function closeQuick() { const qm = $('#quickMenu'); if (qm && !qm.hidden) { qm.hidden = true; $('#btnSettings').setAttribute('aria-expanded', 'false'); } }
  document.addEventListener('click', (e) => { const qm = $('#quickMenu'); if (qm && !qm.hidden && !qm.contains(e.target) && !e.target.closest('#btnSettings')) closeQuick(); });
  /* side panels are non-modal: a click anywhere outside quietly closes them (context is never trapped) */
  document.addEventListener('click', (e) => {
    if (performance.now() - lastOpenAt < 260) return;
    $$('.sheet.side.show').forEach((s) => { if (!s.contains(e.target)) closeSheets(); });
  });

  /* typing lives in the dock — voice morphs into text, one control */
  function setTyping(on) {
    $('#dock').classList.toggle('typing', on);
    const i = $('#typeInput');
    if (on) { setTimeout(() => i && i.focus(), 60); }
    else if (i) { i.value = ''; try { $('#btnType').focus(); } catch {} }
  }

  /* prompt line: nudges & briefing wait quietly above the chips */
  function showPrompt(html, opts) {
    dismissPrompt();
    const el = document.createElement('div');
    el.className = 'prompt-line'; el.id = 'promptLine';
    el.innerHTML = '<span class="pl-text">' + html + '</span>';
    if (opts && opts.action) {
      const b = document.createElement('button'); b.className = 'btn-quiet';
      b.style.cssText = 'min-height:32px;padding:4px 10px;font-size:12.5px';
      b.textContent = opts.action;
      b.addEventListener('click', () => { opts.onAction && opts.onAction(); dismissPrompt(); });
      el.appendChild(b);
    }
    const x = document.createElement('button');
    x.className = 'pl-x'; x.setAttribute('aria-label', 'Dismiss');
    x.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    x.addEventListener('click', dismissPrompt);
    el.appendChild(x);
    $('#suggestions').after(el);
  }
  function dismissPrompt() { const p = $('#promptLine'); if (p) p.remove(); }

  /* drag-to-dismiss for sheets (grab handle) */
  $$('.sheet').forEach((sheet) => {
    const grab = sheet.querySelector('.grab'); if (!grab) return;
    let sy = 0, dy = 0, dragging = false;
    grab.addEventListener('pointerdown', (e) => { dragging = true; dy = 0; sy = e.clientY; sheet.classList.add('dragging'); try { grab.setPointerCapture(e.pointerId); } catch {} e.preventDefault(); });
    grab.addEventListener('pointermove', (e) => { if (!dragging) return; dy = Math.max(0, e.clientY - sy); sheet.style.transform = 'translate(-50%, ' + dy + 'px)'; });
    const finish = () => { if (!dragging) return; dragging = false; sheet.classList.remove('dragging'); sheet.style.transform = ''; if (dy > 110) closeSheets(); };
    grab.addEventListener('pointerup', finish);
    grab.addEventListener('pointercancel', finish);
  });

  /* ---- history ---- */
  function dayBucket(iso) {
    if (!iso) return 'Earlier';
    const d = new Date(iso); if (isNaN(d)) return 'Earlier';
    const now = new Date();
    const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startYesterday = new Date(startToday.getTime() - 864e5);
    if (d >= startToday) return 'Today';
    if (d >= startYesterday) return 'Yesterday';
    return 'Earlier';
  }
  function whenLabel(iso) {
    if (!iso) return '';
    const d = new Date(iso); if (isNaN(d)) return String(iso).slice(0, 16);
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' · ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  async function loadHistory() {
    const api = bridge();
    if (!api) { $('#hEmpty').classList.add('show'); return; }
    let rows = [];
    try { rows = JSON.parse((await api.list_sessions()) || '[]'); } catch {}
    const q = ($('#hSearch').value || '').toLowerCase();
    const items = (rows || []).filter(r => !q || (r.title || '').toLowerCase().includes(q) || (r.summary || '').toLowerCase().includes(q));
    $('#hEmpty').classList.toggle('show', !items.length);
    $('#hEmpty').querySelector('.he-t').textContent = q ? `No conversations for “${q}”` : 'Nothing here yet.';
    $('#hEmpty').querySelector('.he-s').textContent = q ? 'Try another word, or browse recent.' : 'Your conversations will appear here.';
    const groups = {};
    for (const r of items) { const b = dayBucket(r.updated); (groups[b] = groups[b] || []).push(r); }
    const order = ['Today', 'Yesterday', 'Earlier'].filter(k => groups[k]);
    const canDelete = hasApi('delete_session');
    $('#hList').innerHTML = order.map(k => `
      <div class="hgroup"><div class="glab">${k}</div>
      ${groups[k].map(r => `
        <button class="hitem" data-id="${escapeHtml(String(r.id))}">
          <span class="h-top"><span class="h-name">${escapeHtml(r.title || 'Untitled')}</span><span class="h-when">${escapeHtml(whenLabel(r.updated))}</span></span>
          <span class="h-sum">${escapeHtml(r.summary || ((r.count || 0) + ' message' + ((r.count === 1) ? '' : 's')))}</span>
          ${canDelete ? '<span class="hdel" role="button" tabindex="0" aria-label="Delete conversation"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></span>' : ''}
        </button>`).join('')}
      </div>`).join('');
    $$('#hList .hitem').forEach(b => b.addEventListener('click', async (ev) => {
      if (ev.target.closest('.hdel')) return;
      try { await api.open_session(b.dataset.id); } catch {}
      closeSheets();
      setMode('exchange');
      toast('Conversation restored', 'HISTORY', 2400);
    }));
    if (canDelete) $$('#hList .hdel').forEach(d => {
      const doDel = async (ev) => { ev.stopPropagation(); const item = d.closest('.hitem'); await callIf('delete_session', item.dataset.id); item.remove(); toast('Conversation deleted', 'HISTORY', 2200); };
      d.addEventListener('click', doDel);
      d.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') doDel(ev); });
    });
  }

  /* ---- memory hub ---- */
  const MEM_SEGMENTS = {
    memory: { api: 'list_memory', empty: 'Nothing remembered yet — say “remember…” and it will show up here.', title: 'What I know' },
    notes: { api: 'list_notes', empty: 'No notes yet — ask me to note something.', title: 'Notes you asked for' },
    tasks: { api: 'list_tasks', empty: 'No reminders yet — say “remind me…”', title: 'Things I’ll remind you about' },
    activity: { api: 'list_activity', empty: 'Nothing recent — what I do will be logged here.', title: 'What I recently did' },
  };
  let memSeg = 'memory';
  async function loadMemory() {
    const seg = MEM_SEGMENTS[memSeg];
    $$('#memSeg button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mem === memSeg)));
    $('#memTitle').textContent = seg.title;
    const list = $('#memList');
    let rows = null;
    if (hasApi(seg.api)) { try { rows = JSON.parse((await callIf(seg.api)) || '[]'); } catch { rows = null; } }
    if (!rows || !rows.length) {
      list.innerHTML = `<div class="hempty show"><span class="he-t">${escapeHtml(seg.empty)}</span></div>`;
      return;
    }
    list.innerHTML = rows.map(r => `
      <div class="hitem">
        <span class="h-top"><span class="h-name">${escapeHtml(r.title || r.name || String(r))}</span>${r.when ? `<span class="h-when">${escapeHtml(whenLabel(r.when))}</span>` : ''}</span>
        ${r.summary ? `<span class="h-sum">${escapeHtml(r.summary)}</span>` : ''}
      </div>`).join('');
  }

  /* ------------------------------------------------------------- boot */
  async function boot() {
    sizeCanvas();
    requestAnimationFrame(draw);
    body.classList.toggle('reduce-motion', (() => { try { return localStorage.getItem('sotto-motion') === 'reduced'; } catch { return false; } })());
    tickClock();
    setInterval(tickClock, 15000);
    pollStatus();
    setInterval(pollStatus, 30000);
    const api = bridge();
    if (api) {
      try {
        const info = JSON.parse((await api.info()) || '{}');
        if (info.voices?.length) {
          $('#voiceSelect').innerHTML = info.voices.map(v => `<option>${escapeHtml(v)}</option>`).join('');
          $('#voiceSelect').value = info.current_voice || info.voices[0];
        }
        if (info.providers?.length) {
          $('#providerList').innerHTML = info.providers.map(p =>
            `<div class="result"><span class="r-top"><span class="r-name">${escapeHtml(p.name)}</span><span class="r-meta">${p.key ? 'KEY SET' : 'NO KEY'}</span></span><span class="r-take">${escapeHtml(p.model || '')}</span></div>`).join('');
        }
        if (info.version) $('#aboutLine').textContent = 'Sotto · ' + info.version;
      } catch {}
    }
    const h = new Date().getHours();
    $('#lead').textContent = h < 12 ? 'Good morning.' : h < 18 ? 'Good afternoon.' : 'Good evening.';
    // capability-based chrome: only show what the bridge supports
    if (!hasApi('new_session')) $('#btnNewChat').style.display = 'none';
  }

  /* --------------------------------------------------------- events */
  window.addEventListener('pywebviewready', boot);
  let resizeT = null;
  window.addEventListener('resize', () => { clearTimeout(resizeT); resizeT = setTimeout(sizeCanvas, 120); });
  if (window.ResizeObserver) { new ResizeObserver(() => sizeCanvas()).observe(document.querySelector('.presence')); }
  document.addEventListener('DOMContentLoaded', () => {
    // theme: default dark; explicit choice persists; "system" follows the OS
    let savedTheme = null;
    try { savedTheme = localStorage.getItem('sotto-theme-v2'); } catch {}
    applyThemePref(savedTheme === 'light' || savedTheme === 'dark' || savedTheme === 'system' ? savedTheme : 'light');

    /* presence affordances: ready state on hover / before listening */
    const presenceEl = $('#presence');
    presenceEl.addEventListener('mouseenter', () => { if (state === 'idle') setState('ready'); });
    presenceEl.addEventListener('mouseleave', () => { if (state === 'ready') setState('idle'); });
    $('#presence .hit').addEventListener('click', toggleTalk);
    $('#presence .hit').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); toggleTalk(); } });

    $('#mic').addEventListener('click', toggleTalk);
    $('#btnHistory').addEventListener('click', () => toggleSheet('sheetHistory'));
    $('#btnMemory').addEventListener('click', () => toggleSheet('sheetMemory'));
    $('#btnSettings').addEventListener('click', (e) => { e.stopPropagation(); const qm = $('#quickMenu'); if (qm.hidden) { qm.hidden = false; $('#btnSettings').setAttribute('aria-expanded', 'true'); } else closeQuick(); });
    $('#btnMoreSettings').addEventListener('click', () => toggleSheet('sheetSettings'));
    $('#btnType').addEventListener('click', () => setTyping(true));
    $('#btnTypeClose').addEventListener('click', () => setTyping(false));
    $('#btnTheme').addEventListener('click', () => { applyThemePref(resolveTheme(themePref) === 'dark' ? 'light' : 'dark', true); });

    $('#scrim').addEventListener('click', closeSheets);
    $$('[data-close]').forEach(b => b.addEventListener('click', closeSheets));
    $('#hSearch').addEventListener('input', loadHistory);
    $$('#memSeg button').forEach(b => b.addEventListener('click', () => { memSeg = b.dataset.mem; loadMemory(); }));
    $('#btnNewChat').addEventListener('click', async () => {
      await callIf('new_session');
      $('#exchange').innerHTML = '';
      history.length = 0;
      setMode('home');
      closeSheets();
      toast('New conversation', 'SOTTO', 2000);
    });

    $('#voiceSelect').addEventListener('change', (e) => callIf('set_voice', e.target.value));
    $('#btnVoiceTest').addEventListener('click', () => { callIf('say', 'This is my voice — this is how I sound.'); toast('Testing the selected voice', 'VOICE', 2000); });
    $('#speakSwitch').addEventListener('click', (e) => {
      speakAloud = !speakAloud;
      e.currentTarget.setAttribute('aria-pressed', String(speakAloud));
      try { localStorage.setItem('sotto-speak', speakAloud ? '1' : '0'); } catch {}
    });
    $('#soundSwitch').addEventListener('click', (e) => {
      const on = e.currentTarget.getAttribute('aria-pressed') !== 'true';
      e.currentTarget.setAttribute('aria-pressed', String(on));
      callIf('set_sound', on);
    });
    $('#wakeSwitch').addEventListener('click', (e) => {
      const on = e.currentTarget.getAttribute('aria-pressed') !== 'true';
      e.currentTarget.setAttribute('aria-pressed', String(on));
      callIf('set_wake', on);
      toast(on ? 'Wake word on' : 'Wake word off', 'VOICE', 1800);
    });
    $$('#segThemeQuick button').forEach(b => b.addEventListener('click', () => applyThemePref(b.dataset.themeSet)));
    $('#motionSwitch').addEventListener('click', (e) => {
      const on = e.currentTarget.getAttribute('aria-pressed') !== 'true';
      e.currentTarget.setAttribute('aria-pressed', String(on));
      try { localStorage.setItem('sotto-motion', on ? 'reduced' : 'full'); } catch {}
      body.classList.toggle('reduce-motion', on);
      toast(on ? 'Motion reduced' : 'Full motion', 'SETTING', 1600);
    });

    $('#btnSend').addEventListener('click', () => { const v = $('#typeInput').value; $('#typeInput').value = ''; setTyping(false); send(v); });
    $('#typeInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') { const v = e.target.value; e.target.value = ''; setTyping(false); send(v); } });
    document.querySelectorAll('[data-say]').forEach(c => c.addEventListener('click', () => send(c.dataset.say)));

    /* keyboard: hold Space to talk (release sends) · Esc dismiss · ⌘K type
       Space is voice-first: it always means "the voice", even when a button has focus. */
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { closeQuick(); closeSheets(); setTyping(false); }
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === 'k') { e.preventDefault(); setTyping(true); return; }
      if (mod && e.shiftKey) {
        const k = e.key.toLowerCase();
        if (k === 'h') { e.preventDefault(); toggleSheet('sheetHistory'); return; }
        if (k === 'm') { e.preventDefault(); toggleSheet('sheetMemory'); return; }
        if (k === 's') { e.preventDefault(); toggleSheet('sheetSettings'); return; }
        if (k === 'd') { e.preventDefault(); $('#btnTheme').click(); return; }
      }
      const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '');
      if (e.code === 'Space' && !typing && !body.classList.contains('sheet-open')) {
        e.preventDefault();
        if (e.repeat) return;
        if (speaking) { stopSpeaking(); return; }
        if (state === 'idle' || state === 'ready') startListening();
      }
    });
    document.addEventListener('keyup', (e) => {
      const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '');
      if (e.code === 'Space' && !typing) {
        e.preventDefault();
        if (listening) stopListening();
      }
    });

    try { const s = localStorage.getItem('sotto-speak'); if (s === '0') { speakAloud = false; $('#speakSwitch').setAttribute('aria-pressed', 'false'); } } catch {}
    if (!window.pywebview) {
      setState('offline');
      $('#stConn').textContent = 'Standalone';
      document.querySelector('.homestatus').classList.add('off');
    }
    if (!window.pywebview) boot();
  });
})();
