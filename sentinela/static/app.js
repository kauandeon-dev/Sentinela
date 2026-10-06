/* Sentinela — painel web (JavaScript puro, sem build). */
(function () {
  'use strict';

  // ================================================================ ícones
  const svg = (d, s = 17, w = 1.9) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
  const I = {
    shield: (s = 19, w = 2.2) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.4-3 8-7 10-4-2-7-5.6-7-10V6z"/><path d="M9 12l2 2 4-4"/></svg>`,
    check: (c = '#6fa8ff', s = 14) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5 9-11"/></svg>`,
    grid: svg('<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>'),
    cal: svg('<rect x="3" y="4" width="18" height="17" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="16" y1="2" x2="16" y2="6"/>'),
    clock: svg('<circle cx="12" cy="12" r="9"/><line x1="12" y1="7" x2="12" y2="12"/><line x1="12" y1="12" x2="16" y2="14"/>'),
    doc: svg('<rect x="4" y="3" width="16" height="18" rx="2"/><line x1="8" y1="8" x2="16" y2="8"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="8" y1="16" x2="13" y2="16"/>'),
    db: svg('<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.66 3.58 3 8 3s8-1.34 8-3V6"/><path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/>'),
    logout: svg('<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="M10 17l-5-5 5-5"/><line x1="5" y1="12" x2="16" y2="12"/>'),
    refresh: (c = '#fff') => `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v4h-4"/></svg>`,
    restore: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v4h4"/></svg>',
    download: svg('<path d="M12 3v13"/><path d="M7 12l5 5 5-5"/><line x1="5" y1="21" x2="19" y2="21"/>', 15, 2),
    trash: svg('<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>', 15, 2),
    verify: svg('<path d="M12 3l7 3v5c0 4.4-3 8-7 10-4-2-7-5.6-7-10V6z"/><path d="M9 12l2 2 4-4"/>', 15, 2),
    warn: (c = '#b7791f', s = 18) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l10 17H2z"/><line x1="12" y1="10" x2="12" y2="14"/><line x1="12" y1="17" x2="12" y2="17"/></svg>`,
    back: svg('<path d="M15 6l-6 6 6 6"/>', 15, 2.2),
    spinner: (s = 15) => `<svg class="spin" width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 3a9 9 0 1 0 9 9"/></svg>`,
    x: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#d64545" stroke-width="2.6" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    moon: svg('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'),
    sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
    eye: svg('<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>', 16),
    eyeOff: svg('<path d="M17.9 17.9A10.9 10.9 0 0 1 12 19c-7 0-11-7-11-7a19.8 19.8 0 0 1 5.1-5.9M9.9 4.2A10.4 10.4 0 0 1 12 4c7 0 11 7 11 7a19.9 19.9 0 0 1-2.2 3.3"/><line x1="1" y1="1" x2="23" y2="23"/>', 16),
    search: svg('<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.6" y2="16.6"/>', 15),
    copy: svg('<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>', 14),
    caret: svg('<path d="M6 9l6 6 6-6"/>', 13, 2.2),
    disk: svg('<rect x="3" y="4" width="18" height="16" rx="2"/><line x1="3" y1="14" x2="21" y2="14"/><circle cx="17" cy="17" r="1"/>', 16),
    shieldSm: svg('<path d="M12 3l7 3v5c0 4.4-3 8-7 10-4-2-7-5.6-7-10V6z"/>', 16),
    ok: svg('<path d="M5 12l5 5 9-11"/>', 12, 3),
    info: svg('<circle cx="12" cy="12" r="9"/><line x1="12" y1="11" x2="12" y2="16"/><line x1="12" y1="8" x2="12" y2="8"/>', 12, 2.6),
    bang: svg('<line x1="12" y1="7" x2="12" y2="13"/><line x1="12" y1="17" x2="12" y2="17"/>', 12, 3),
    key: svg('<circle cx="7.5" cy="15.5" r="4.5"/><path d="M10.7 12.3L20 3M16 7l3 3M14 9l2 2"/>', 13),
    keyLg: svg('<circle cx="7.5" cy="15.5" r="4.5"/><path d="M10.7 12.3L20 3M16 7l3 3M14 9l2 2"/>', 17),
    cloud: svg('<path d="M7 18a5 5 0 0 1-.6-9.96A6 6 0 0 1 18 8a4.5 4.5 0 0 1-.5 10z"/>'),
    cloudLg: svg('<path d="M7 18a5 5 0 0 1-.6-9.96A6 6 0 0 1 18 8a4.5 4.5 0 0 1-.5 10z"/>', 20),
    bell: svg('<path d="M18 16v-5a6 6 0 1 0-12 0v5l-2 2h16z"/><path d="M10 21h4"/>'),
    server: svg('<rect x="3" y="4" width="18" height="7" rx="1.5"/><rect x="3" y="13" width="18" height="7" rx="1.5"/><line x1="7" y1="7.5" x2="7" y2="7.5"/><line x1="7" y1="16.5" x2="7" y2="16.5"/>', 20),
    hdd: svg('<rect x="3" y="5" width="18" height="14" rx="2"/><line x1="3" y1="13" x2="21" y2="13"/><circle cx="17" cy="16" r="1"/>', 20),
    bucket: svg('<path d="M4 6h16l-2 14H6z"/><ellipse cx="12" cy="6" rx="8" ry="2.5"/>', 20),
    plus: svg('<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>', 15, 2.2),
    sync: svg('<path d="M21 12a9 9 0 0 1-15.4 6.4L3 16"/><path d="M3 12a9 9 0 0 1 15.4-6.4L21 8"/><path d="M21 3v5h-5M3 21v-5h5"/>', 15, 2),
    edit: svg('<path d="M4 20h4L19 9l-4-4L4 16z"/>', 15, 2),
    send: svg('<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/>', 15, 2),
    pause: svg('<line x1="9" y1="5" x2="9" y2="19"/><line x1="15" y1="5" x2="15" y2="19"/>', 15, 2.2),
    play: svg('<path d="M7 4l13 8-13 8z"/>', 15, 2),
    find: svg('<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.6" y2="16.6"/>', 15, 2),
  };

  // ============================================================ utilidades
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
  const parse = (s) => (s ? new Date(s.replace(' ', 'T')) : null);
  const pad = (n) => String(n).padStart(2, '0');
  const num = (v, d = 1) => v.toFixed(d).replace('.', ',');

  function fmtWhen(s) {
    const d = parse(s); if (!d) return '—';
    return `${pad(d.getDate())} ${MESES[d.getMonth()]} ${d.getFullYear()} · ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  function fmtDay(s) {
    const d = parse(s); if (!d) return '—';
    return `${pad(d.getDate())} ${MESES[d.getMonth()]} ${d.getFullYear()}`;
  }
  function fmtSize(n) {
    if (n == null) return '—';
    const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0; n = +n;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return i === 0 ? `${n} B` : `${num(n)} ${u[i]}`;
  }
  function fmtDur(s) {
    if (s == null) return '—';
    if (s < 60) return s < 1 ? '<1s' : `${Math.round(s)}s`;
    const m = Math.floor(s / 60); return `${m}min ${pad(Math.round(s % 60))}s`;
  }
  function relPast(s) {
    const d = parse(s); if (!d) return '';
    const m = Math.round((Date.now() - d) / 60000);
    if (m < 1) return 'agora mesmo';
    if (m < 60) return `há ${m} min`;
    const h = Math.round(m / 60);
    if (h < 48) return `há ${h}h`;
    return `há ${Math.round(h / 24)} dias`;
  }
  function relFuture(s) {
    const d = parse(s); if (!d) return '';
    const m = Math.round((d - Date.now()) / 60000);
    if (m <= 0) return 'em instantes';
    if (m < 60) return `em ~${m} min`;
    const h = Math.round(m / 60);
    if (h < 48) return `em ~${h} ${h === 1 ? 'hora' : 'horas'}`;
    return `em ~${Math.round(h / 24)} dias`;
  }
  function dayLabel(s) {
    const d = parse(s); if (!d) return '—';
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const that = new Date(d); that.setHours(0, 0, 0, 0);
    const diff = Math.round((that - today) / 86400000);
    const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    if (diff === 0) return `Hoje, ${hm}`;
    if (diff === 1) return `Amanhã, ${hm}`;
    return `${pad(d.getDate())} ${MESES[d.getMonth()]}, ${hm}`;
  }
  const TYPE = { auto: 'Automático', manual: 'Manual', 'pre-restore': 'Pré-restauração' };
  const KIND = { backup: 'Backup', restore: 'Restauração', verify: 'Verificação', replicate: 'Cópias externas' };
  const PILL = { success: 'Concluído', error: 'Falhou', running: 'Em execução' };
  const pill = (st) => `<span class="pill ${esc(st)}"><i></i>${PILL[st] || esc(st)}</span>`;
  const time = (s) => (s || '').slice(11, 19);
  const TITLES = { dashboard: 'Painel', policy: 'Política de backup', history: 'Histórico', detail: 'Backup', logs: 'Logs', conn: 'Conexão', dest: 'Cópias externas', notif: 'Avisos', login: 'Entrar' };

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } finally { ta.remove(); }
    return Promise.resolve();
  }

  // ================================================================= tema
  const Theme = {
    saved() { try { return localStorage.getItem('sentinela-tema'); } catch (e) { return null; } },
    isDark() { return document.documentElement.dataset.theme === 'dark'; },
    apply() {
      const s = this.saved();
      const dark = s ? s === 'dark' : window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    },
    toggle() {
      const next = this.isDark() ? 'light' : 'dark';
      try { localStorage.setItem('sentinela-tema', next); } catch (e) { /* sem armazenamento */ }
      document.documentElement.dataset.theme = next;
    },
  };
  Theme.apply();
  const themeBtn = (cls = '') => `<button class="iconbtn ${cls}" data-action="theme" title="${Theme.isDark() ? 'Tema claro' : 'Tema escuro'}">${Theme.isDark() ? I.sun : I.moon}</button>`;

  // ================================================================== API
  async function api(method, url, data) {
    const opt = { method, headers: {}, credentials: 'same-origin' };
    if (data !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(data); }
    const r = await fetch(url, opt);
    let body = {};
    try { body = await r.json(); } catch (e) { /* sem corpo */ }
    if (r.status === 401 && url !== '/api/login') { S.user = null; go('login'); throw new Error(body.error || 'Sessão expirada'); }
    if (!r.ok) throw new Error(body.error || `Erro ${r.status}`);
    return body;
  }

  // =============================================================== estado
  const S = {
    user: null, route: 'login', param: null, data: null,
    backups: null, filter: 'all', detail: null, liveExec: null,
    policyDraft: null, connDraft: null, test: { status: 'idle' },
    busy: {}, loginErr: '', showPw: false,
    dests: null, destDraft: null, destTest: { status: 'idle' },
    notif: null, notifDraft: null, notifTest: null,
  };
  // Terminal de logs (estado próprio: é atualizado sem redesenhar a página)
  const L = {
    execs: new Map(), lastId: 0, loaded: false, level: 'all', kind: 'all', q: '',
    follow: true, collapsed: new Set(), fresh: new Set(), running: false,
  };
  const app = document.getElementById('app');
  const modalRoot = document.getElementById('modal-root');
  const toastRoot = document.getElementById('toast-root');
  let toastTimer = null, pollTimer = null;

  function toast(msg, err) {
    toastRoot.innerHTML = `<div class="toast${err ? ' err' : ''}">${err ? I.warn('#ffb4b4', 16) : I.check('#5cd08a', 16)}<span>${esc(msg)}</span></div>`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastRoot.innerHTML = ''; }, err ? 6000 : 2800);
  }

  // ============================================================= roteador
  const ROUTES = { painel: 'dashboard', politica: 'policy', historico: 'history', backup: 'detail', logs: 'logs', conexao: 'conn', copias: 'dest', avisos: 'notif', login: 'login' };
  const PATH = { dashboard: 'painel', policy: 'politica', history: 'historico', detail: 'backup', logs: 'logs', conn: 'conexao', dest: 'copias', notif: 'avisos', login: 'login' };

  function go(route, param) {
    const h = '#/' + PATH[route] + (param ? '/' + encodeURIComponent(param) : '');
    if (location.hash !== h) location.hash = h; else onRoute();
  }

  async function onRoute() {
    const parts = location.hash.replace(/^#\/?/, '').split('/');
    let route = ROUTES[parts[0]] || 'dashboard';
    const param = parts[1] ? decodeURIComponent(parts[1]) : null;
    if (!S.user && route !== 'login') route = 'login';
    if (S.user && route === 'login') route = 'dashboard';
    if (route !== S.route || param !== S.param) {
      if (route === 'detail') S.detail = null;
      if (route === 'policy') S.policyDraft = null;
      if (route === 'conn') { S.connDraft = null; S.test = { status: 'idle' }; }
      if (route === 'dest') { S.destDraft = null; S.destTest = { status: 'idle' }; }
      if (route === 'notif') { S.notifDraft = null; S.notifTest = null; }
    }
    const changed = route !== S.route || param !== S.param;
    S.route = route; S.param = param;
    document.title = `${TITLES[route]} · Sentinela`;
    S.enter = changed;
    if (changed) window.scrollTo(0, 0);
    render();
    await load();
    render();
    if (route === 'logs') scrollTerm(true);
    schedulePoll();
  }

  async function load() {
    if (S.route === 'login') return;
    try {
      const tasks = [api('GET', '/api/state').then((d) => { S.data = d; })];
      if (S.route === 'history') tasks.push(api('GET', '/api/backups').then((d) => { S.backups = d.backups; }));
      if (S.route === 'detail') tasks.push(api('GET', '/api/backups/' + encodeURIComponent(S.param)).then((d) => { S.detail = d; }).catch((e) => { S.detail = { error: e.message }; }));
      if (S.route === 'logs') tasks.push(loadLogs());
      if (S.route === 'dest') tasks.push(api('GET', '/api/destinations').then((d) => { S.dests = d; }));
      if (S.route === 'notif') tasks.push(api('GET', '/api/notifications').then((d) => { S.notif = d; }));
      await Promise.all(tasks);
      if (S.route === 'dashboard') {
        const cur = S.data.current;
        S.liveExec = cur ? (await api('GET', '/api/executions/' + cur.execution_id)).execution : null;
      }
      if (S.route === 'policy' && !S.policyDraft) S.policyDraft = Object.assign({}, S.data.policy);
      if (S.route === 'conn' && !S.connDraft) S.connDraft = newConnDraft(S.data.connection, S.data.policy.directory);
      if (S.route === 'notif' && !S.notifDraft && S.notif) S.notifDraft = newNotifDraft(S.notif.config);
    } catch (e) {
      if (S.user) toast(e.message, true);
    }
  }

  // Atualização periódica: rápida enquanto algo executa, lenta no resto.
  function schedulePoll() {
    clearTimeout(pollTimer);
    if (!S.user || ['policy', 'conn', 'login', 'notif'].includes(S.route) || (S.route === 'dest' && S.destDraft)) return;
    const running = S.data && S.data.running;
    if (S.route === 'logs') {
      pollTimer = setTimeout(async () => {
        try { await tailLogs(); } catch (e) { /* ignora falha momentânea */ }
        schedulePoll();
      }, L.running ? 900 : 3000);
      return;
    }
    pollTimer = setTimeout(async () => {
      if (modalRoot.innerHTML) { schedulePoll(); return; }
      const wasRunning = running;
      await load();
      render();
      if (S.route === 'detail') scrollTerm(false);
      if (wasRunning && S.data && !S.data.running) notifyFinished();
      schedulePoll();
    }, running ? 1200 : 15000);
  }

  function notifyFinished() {
    const last = S.data.recent && S.data.recent[0];
    if (!last) return;
    if (last.status === 'success') toast('Backup concluído · ' + fmtSize(last.size));
    else if (last.status === 'error') toast('A execução falhou — veja os logs', true);
  }

  // =============================================================== render
  function render() {
    if (S.route === 'login') { app.innerHTML = viewLogin(); bindLogin(); return; }
    const body = !S.data ? skeleton() : ({
      dashboard: viewDashboard, policy: viewPolicy, history: viewHistory,
      detail: viewDetail, logs: viewLogs, conn: viewConn, dest: viewDest, notif: viewNotif,
    }[S.route])();
    const main = document.querySelector('.main');
    const scroll = main ? main.scrollTop : 0;
    const term = document.getElementById('term-body');
    const termScroll = term ? term.scrollTop : null;
    app.innerHTML = viewShell(body);
    const m2 = document.querySelector('.main');
    if (S.enter && S.data) {
      // página nova: começa do topo, com animação de entrada
      document.querySelector('.content').classList.add('fade'); S.enter = false;
    } else if (m2) {
      m2.scrollTop = scroll;  // mesma página atualizada: mantém a posição
    }
    const t2 = document.getElementById('term-body'); if (t2 && termScroll != null) t2.scrollTop = termScroll;
    document.querySelectorAll('[data-w]').forEach((el) => { el.style.width = el.dataset.w + '%'; });
    if (S.route === 'logs') bindTerm();
  }

  function skeleton() {
    const box = (h) => `<div class="skel" style="height:${h}px"></div>`;
    return `<div class="page-head"><div style="width:220px">${box(26)}<div style="height:8px"></div>${box(14)}</div></div>
      <div class="stats">${[1, 2, 3, 4].map(() => `<div class="card pad">${box(12)}<div style="height:12px"></div>${box(24)}</div>`).join('')}</div>
      <div class="card pad">${box(180)}</div>`;
  }

  // ================================================================ login
  function viewLogin() {
    const feat = (t) => `<div class="feat"><span>${I.check()}</span>${t}</div>`;
    return `<div class="login">
      <div class="login-side">
        <div class="brand"><span class="brand-logo">${I.shield(24)}</span>
          <div><div class="brand-name">Sentinela</div><div class="brand-sub">backup · segurança · rastreabilidade</div></div></div>
        <div class="login-pitch">
          <h2>Proteção automatizada de bancos de dados para pequenas empresas.</h2>
          ${feat('Agendamento automático diário ou por intervalo')}
          ${feat('Criptografia AES-256 e compressão gzip')}
          ${feat('Armazenamento isolado seguindo a regra 3-2-1')}
          ${feat('Bancos locais ou remotos via túnel SSH')}
        </div>
        <div class="login-foot">Projeto Integrador · IFSC São Lourenço do Oeste · Open source</div>
      </div>
      <div class="login-main">
        <div class="login-theme">${themeBtn('light')}</div>
        <form class="login-form" id="login-form" autocomplete="on">
          <h1>Entrar</h1>
          <p>Acesse o painel de backup do servidor.</p>
          ${S.loginErr ? `<div class="login-err">${esc(S.loginErr)}</div>` : ''}
          <label class="lbl" for="lu">Usuário</label>
          <input class="input mb18" id="lu" name="username" autocomplete="username" required autofocus>
          <label class="lbl" for="lp">Senha</label>
          <div class="pw mb24"><input class="input" id="lp" name="password" type="${S.showPw ? 'text' : 'password'}" autocomplete="current-password" required>
            <button type="button" data-action="toggle-pw" title="${S.showPw ? 'Ocultar' : 'Mostrar'} senha">${S.showPw ? I.eyeOff : I.eye}</button></div>
          <button class="btn btn-primary btn-block" type="submit" ${S.busy.login ? 'disabled' : ''}>${S.busy.login ? 'Entrando…' : 'Entrar no painel'}</button>
        </form>
      </div>
    </div>`;
  }

  function bindLogin() {
    const f = document.getElementById('login-form');
    f.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const username = f.username.value, password = f.password.value;
      S.busy.login = true; S.loginErr = ''; render();
      try {
        const r = await api('POST', '/api/login', { username, password });
        S.user = r.user; S.busy.login = false; S.data = null;
        go('dashboard');
      } catch (e) {
        S.busy.login = false; S.loginErr = e.message; render();
        document.getElementById('lu').value = username;
        document.getElementById('lp').focus();
      }
    });
  }

  // ================================================================ shell
  function viewShell(body) {
    const d = S.data;
    const running = d && d.running;
    const nav = (r, icon, label, extra = '') => {
      const active = S.route === r || (r === 'history' && S.route === 'detail');
      const badge = (r === 'logs' && running ? '<span class="badge" title="Execução em andamento"></span>' : '') + extra;
      return `<a href="#/${PATH[r]}" class="${active ? 'active' : ''}">${icon}${label}${badge}</a>`;
    };
    const u = S.user || '';
    return `<div class="shell">
      <aside class="sidebar">
        <div class="side-brand"><span class="logo">${I.shield()}</span>
          <div><div class="name">Sentinela</div><div class="ver">v${esc(d ? d.version : '')} · beta</div></div></div>
        <div class="side-sec">PRINCIPAL</div>
        <nav class="nav">
          ${nav('dashboard', I.grid, 'Painel')}
          ${nav('policy', I.cal, 'Política de backup')}
          ${nav('history', I.clock, 'Histórico')}
          ${nav('logs', I.doc, 'Logs')}
          ${nav('conn', I.db, 'Conexão')}
        </nav>
        <div class="side-sec">REGRA 3-2-1</div>
        <nav class="nav">
          ${nav('dest', I.cloud, 'Cópias externas', destBadge(d))}
          ${nav('notif', I.bell, 'Avisos')}
        </nav>
        <div class="side-bottom">
          <div class="dbbox">${dbBox(d)}</div>
          <div class="me"><span class="avatar">${esc(u.slice(0, 1))}</span>
            <div class="who" style="flex:1;min-width:0"><div class="n">${esc(u)}</div><div class="r">administrador</div></div>
            ${themeBtn()}
            <button class="iconbtn" data-action="logout" title="Sair">${I.logout}</button></div>
        </div>
      </aside>
      <main class="main"><div class="content">${body}</div></main>
    </div>`;
  }

  function destBadge(d) {
    if (!d || !d.destinations) return '';
    const bad = d.destinations.some((x) => x.enabled && x.last && x.last.status === 'error');
    if (bad) return '<span class="badge err" title="Cópia externa falhando"></span>';
    if (d.rule321 && d.rule321.backup_id && !d.rule321.ok) return '<span class="badge warn" title="Regra 3-2-1 incompleta"></span>';
    return '';
  }

  function dbBox(d) {
    let state = '<span class="dot y"></span>Não configurado', sub = '';
    if (d) {
      const cs = d.conn_status, label = d.connection.sgbd_label.replace(' (MySQL)', '');
      if (d.running) state = `<span class="dot b"></span>${esc(label)} · em execução`;
      else if (!d.active) state = '<span class="dot y"></span>Conexão pendente';
      else if (cs && cs.ok) state = `<span class="dot g"></span>${esc(label)} · conectado`;
      else if (cs && !cs.ok) state = `<span class="dot r"></span>${esc(label)} · falha`;
      else state = `<span class="dot y"></span>${esc(label)} · não testado`;
      if (d.active) sub = d.connection.ssh && d.connection.ssh.enabled ? `via SSH ${d.connection.ssh.host}` : `${d.connection.host}:${d.connection.port}`;
    }
    return `<div class="t">BANCO DE DADOS</div><div class="v">${state}</div>${sub ? `<div class="s">${esc(sub)}</div>` : ''}`;
  }

  const runBtn = () => `<button class="btn btn-primary" data-action="run" ${S.busy.run || (S.data && S.data.running) ? 'disabled' : ''}>${S.data && S.data.running ? I.spinner() + 'Em execução…' : I.refresh() + 'Fazer backup agora'}</button>`;

  // ============================================================ dashboard
  function viewDashboard() {
    const d = S.data, p = d.policy;
    const last = d.last_backup;
    const st = d.storage;
    const pct = Math.min(100, Math.round((st.copies / st.expected) * 100));
    const sched = p.schedule_mode === 'daily' ? 'Diário · 00:00' : `A cada ${p.interval_days} dias`;
    const copies = `${st.copies} ${st.copies === 1 ? 'cópia guardada' : 'cópias guardadas'}`;

    let alert = '';
    if (!d.active) {
      alert = `<div class="alert info">${I.db}<span>Configure a conexão com o banco de dados para ativar os backups automáticos.</span><a href="#/conexao">Configurar →</a></div>`;
    } else if (destFailing(d)) {
      const x = destFailing(d);
      alert = `<div class="alert">${I.warn()}<span>A cópia externa em <strong>${esc(x.name)}</strong> está falhando: ${esc(shortErr(x.last.error))}</span><a href="#/copias">Ver destinos →</a></div>`;
    } else if (d.failures.count) {
      const f = d.failures.last;
      alert = `<div class="alert">${I.warn()}<span>${d.failures.count} ${d.failures.count === 1 ? 'backup falhou' : 'backups falharam'} — o mais recente em <strong>${fmtDay(f.created_at)}</strong>: ${esc(shortErr(f.error))}</span><a href="#/backup/${esc(f.id)}">Ver logs →</a></div>`;
    }

    const rows = d.recent.length ? d.recent.map((b) => `
      <div class="row" data-open="${esc(b.id)}">
        <span class="r-date">${fmtWhen(b.created_at)}</span>
        <span class="r-type">${TYPE[b.trigger] || esc(b.trigger)}</span>
        <span class="r-size">${fmtSize(b.size)}</span>
        ${pill(b.status)}
      </div>`).join('') : '<div class="empty"><span class="big">Nenhum backup ainda</span>Clique em "Fazer backup agora" para criar a primeira cópia.</div>';

    const disk = st.disk ? ` · ${fmtSize(st.disk.free)} livres` : '';
    const lastOk = last && last.status === 'success';
    return `
      <div class="page-head"><div><h1>Painel</h1><p>Visão geral do sistema de backup.</p></div>${runBtn()}</div>
      ${d.current ? viewLive(d.current, S.liveExec) : ''}
      <div class="stats">
        <div class="card pad stat"><span class="ic ${d.running ? '' : d.active ? 'g' : 'y'}">${I.shieldSm}</span><div class="k">Status</div>
          <div class="v"><span class="dot ${d.running ? 'b' : d.active ? 'g' : 'y'}"></span>${d.running ? 'Executando' : d.active ? 'Ativo' : 'Inativo'}</div>
          <div class="s">${d.active ? 'Agendamento habilitado' : 'Aguardando configuração'}</div></div>
        <div class="card pad stat"><span class="ic">${I.cal}</span><div class="k">Próximo backup</div>
          <div class="v">${d.active && d.next_run_at ? dayLabel(d.next_run_at) : '—'}</div>
          <div class="s">${d.active && d.next_run_at ? relFuture(d.next_run_at) : 'sem agendamento ativo'}</div></div>
        <div class="card pad stat"><span class="ic ${last ? (lastOk ? 'g' : 'r') : ''}">${I.clock}</span><div class="k">Último backup</div>
          <div class="v">${last ? (lastOk ? 'Concluído' : 'Falhou') : '—'}</div>
          <div class="s">${last ? relPast(last.created_at) + (lastOk ? ' · ' + fmtSize(last.size) : '') : 'nenhuma execução'}</div></div>
        <div class="card pad stat"><span class="ic">${I.disk}</span><div class="k">Retenção</div>
          <div class="v">${p.retention_days} ${p.retention_days === 1 ? 'dia' : 'dias'}</div>
          <div class="s">${copies}</div></div>
      </div>
      ${alert}
      <div class="grid-dash">
        <div class="col">
          <div class="card">
            <div class="card-head"><span class="card-title">Últimas execuções</span><span class="muted" style="font-size:12px">tamanho de cada cópia</span></div>
            ${viewChart(d.chart)}
          </div>
          <div class="card">
            <div class="card-head"><span class="card-title">Backups recentes</span><a class="link" href="#/historico">Ver tudo →</a></div>
            ${rows}
          </div>
        </div>
        <div class="col">
          ${viewRule(d)}
          ${viewHealth(d.health)}
          <div class="card pad">
            <div class="card-title" style="margin-bottom:14px">Armazenamento</div>
            <div class="bar"><div data-w="${pct}"></div></div>
            <div class="kv" style="margin-top:10px"><span>${copies}</span><span class="mono">${fmtSize(st.bytes)}</span></div>
            <div class="hint mono" style="word-break:break-all">${esc(st.directory)}${esc(disk)}</div>
          </div>
          <div class="card pad">
            <div class="card-title" style="margin-bottom:14px">Configuração atual</div>
            <div class="col" style="gap:11px">
              <div class="kv"><span>SGBD</span><span>${esc(d.connection.sgbd_label)}</span></div>
              <div class="kv"><span>Banco</span><span class="mono">${esc(d.connection.dbname || '—')}</span></div>
              <div class="kv"><span>Acesso</span><span>${d.connection.ssh && d.connection.ssh.enabled ? 'Túnel SSH · ' + esc(d.connection.ssh.host) : 'Direto'}</span></div>
              <div class="kv"><span>Agendamento</span><span>${sched}</span></div>
              <div class="kv"><span>Criptografia</span><span>${p.encryption ? 'AES-256 · ativa' : 'Desativada'}</span></div>
              <div class="kv"><span>Compressão</span><span>${p.compression ? 'gzip · ativa' : 'Desativada'}</span></div>
            </div>
          </div>
        </div>
      </div>`;
  }

  function destFailing(d) {
    return (d.destinations || []).find((x) => x.enabled && x.last && x.last.status === 'error');
  }

  // Cartão da regra 3-2-1: quantas cópias, mídias e cópias fora do local existem
  // para o backup válido mais recente.
  function ruleTiles(r) {
    const tile = (n, need, label, sub) => `<div class="rule-tile ${n >= need ? 'ok' : 'miss'}"><div class="n">${need}</div><div class="l">${label}</div><div class="s">${sub}</div></div>`;
    const has = !!r.backup_id;
    return `<div class="rule">
      ${tile(has ? r.copies : 0, 3, 'cópias', has ? `${r.copies} ${r.copies === 1 ? 'existe' : 'existem'}` : 'sem backup')}
      ${tile(has ? r.media : 0, 2, 'mídias', has ? `${r.media} em uso` : '—')}
      ${tile(has ? r.offsite : 0, 1, 'fora do local', has ? `${r.offsite} ${r.offsite === 1 ? 'cópia' : 'cópias'}` : '—')}
    </div>`;
  }
  function viewRule(d) {
    const r = d.rule321 || {};
    const ds = d.destinations || [];
    const rows = ds.map((x) => {
      const st = !x.enabled ? '<span class="tag">pausado</span>' : x.last ? repPill(x.last.status) : '<span class="tag">aguardando</span>';
      return `<div class="kv dest-kv"><span>${destIcon(x.type, 15)}${esc(x.name)}</span><span>${st}</span></div>`;
    }).join('');
    const head = !r.backup_id ? '' : r.ok ? `<span class="pill success"><i></i>Atendida</span>` : `<span class="pill warn"><i></i>Incompleta</span>`;
    return `<div class="card pad">
      <div class="card-title" style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center">Regra 3-2-1 ${head}</div>
      ${ruleTiles(r)}
      ${ds.length ? `<div class="col" style="gap:9px;margin-top:14px">${rows}</div>` : '<div class="hint">Nenhum destino externo: se o disco deste servidor falhar, todas as cópias se perdem.</div>'}
      <a class="btn btn-soft btn-sm" style="margin-top:14px" href="#/copias">${ds.length ? 'Gerenciar destinos' : I.plus + 'Adicionar destino externo'}</a>
    </div>`;
  }
  const REP = { success: ['success', 'Conferida'], error: ['error', 'Falhou'], deleted: ['muted', 'Excluída'], delete_pending: ['warn', 'Exclusão pendente'] };
  const repPill = (st) => { const p = REP[st] || ['muted', st]; return `<span class="pill ${p[0]}"><i></i>${esc(p[1])}</span>`; };
  const destIcon = (t, sz) => { const ic = { directory: I.hdd, sftp: I.server, s3: I.bucket }[t] || I.cloud; return sz ? `<span class="di sm">${ic}</span>` : `<span class="di">${ic}</span>`; };

  function shortErr(e) {
    e = (e || 'erro desconhecido').replace(/^Falha na conexão com o banco: /, 'conexão recusada — ');
    return e.length > 120 ? e.slice(0, 120) + '…' : e;
  }

  // Execução em andamento: etapas, progresso e últimas linhas do log.
  const STEPS = {
    backup: [['conexao', 'Conexão'], ['dump', 'Dump · gzip · AES'], ['verificacao', 'Verificação'], ['fim', 'Concluído']],
    restore: [['verificacao', 'Verificar cópia'], ['pre-backup', 'Cópia do estado atual'], ['conexao', 'Conexão'], ['aplicando', 'Aplicando dump']],
    verify: [['verificacao', 'Leitura completa'], ['fim', 'Concluído']],
  };
  function liveSteps(cur) {
    if (cur.kind === 'backup') {
      const ext = S.data && S.data.destinations && S.data.destinations.some((x) => x.enabled);
      return ext ? [...STEPS.backup.slice(0, 3), ['replicacao', 'Cópias externas'], ['fim', 'Concluído']] : STEPS.backup;
    }
    if (cur.kind === 'replicate') return cur.stage === 'busca' ? [['busca', 'Buscar cópia externa'], ['fim', 'Concluído']] : [['replicacao', 'Enviar e conferir'], ['fim', 'Concluído']];
    if (cur.kind === 'restore' && cur.stage === 'busca') return [['busca', 'Buscar cópia externa'], ...STEPS.restore];
    if (cur.kind === 'verify' && cur.stage === 'replicacao') return [['verificacao', 'Cópia local'], ['replicacao', 'Cópias externas'], ['fim', 'Concluído']];
    return STEPS[cur.kind] || STEPS.backup;
  }
  function viewLive(cur, ex) {
    const steps = liveSteps(cur);
    const stage = cur.stage === 'inicio' ? 'conexao' : cur.stage;
    const idx = Math.max(0, steps.findIndex((s) => s[0] === stage));
    const title = { backup: 'Backup em andamento', restore: 'Restauração em andamento', verify: 'Verificação em andamento', replicate: 'Cópias externas em andamento' }[cur.kind];
    const det = cur.total && ['verificacao', 'aplicando', 'replicacao', 'busca'].includes(stage);
    const pct = det ? Math.min(99, Math.round((cur.bytes / cur.total) * 100)) : 0;
    const lines = ex && ex.lines ? ex.lines.slice(-6) : [];
    return `<div class="card live">
      <div class="live-head"><span class="live-dot"></span><div style="flex:1;min-width:0">
        <div class="ttl">${title}${cur.kind === 'backup' ? ` · ${esc(TYPE[cur.trigger] || cur.trigger)}` : ''}</div>
        <div class="sub">${esc(cur.backup_id || '')}${cur.ssh ? ' · via túnel SSH' : ''}${stage === 'replicacao' && cur.dest ? ' · destino ' + esc(cur.dest) : ''}</div></div>
        <a class="btn btn-ghost btn-sm" href="#/logs">${I.doc}Abrir terminal</a></div>
      <div class="live-body">
        <div class="steps">${steps.map((s, i) => `<div class="step ${i < idx ? 'done' : i === idx ? 'active' : ''}"><span class="bullet">${i < idx ? I.ok : ''}</span><span class="lb">${s[1]}</span></div>`).join('')}</div>
        <div class="bar ${det ? '' : 'indet'}"><div ${det ? `data-w="${pct}"` : ''}></div></div>
        <div class="live-meta"><span>decorrido <b>${fmtDur(cur.elapsed)}</b></span>
          ${cur.bytes ? `<span>processado <b>${fmtSize(cur.bytes)}</b>${cur.total ? ` de ${fmtSize(cur.total)} (${pct}%)` : ''}</span>` : ''}</div>
        ${lines.length ? `<div class="term mini"><div class="term-body">${lines.map((l) => lineHtml(l)).join('')}<span class="cursor"></span></div></div>` : ''}
      </div></div>`;
  }

  // Gráfico de barras (SVG puro) com o tamanho das últimas cópias.
  function viewChart(items) {
    if (!items || !items.length) return '<div class="empty">O gráfico aparece depois dos primeiros backups.</div>';
    const W = 640, H = 150, PL = 52, PB = 20, PT = 8;
    const max = Math.max(...items.map((b) => b.size || 0), 1);
    const slots = Math.max(items.length, 8);
    const days = new Set(items.map((b) => b.created_at.slice(0, 10)));
    const sameDay = days.size === 1;
    const slot = (W - PL) / slots;
    const bw = Math.min(30, slot * 0.62);
    const ih = H - PB - PT;
    let g = '';
    [0, 0.5, 1].forEach((f) => {
      const y = PT + ih - ih * f;
      g += `<line class="grid" x1="${PL}" x2="${W}" y1="${y}" y2="${y}"/><text x="${PL - 8}" y="${y + 3}" text-anchor="end">${f ? fmtSize(max * f) : '0'}</text>`;
    });
    items.forEach((b, i) => {
      const x = PL + i * slot + (slot - bw) / 2;
      const err = b.status === 'error';
      const h = err ? Math.max(8, ih * 0.08) : Math.max(3, ((b.size || 0) / max) * ih);
      const cls = err ? 'bar-err' : b.trigger === 'auto' ? 'bar-ok' : 'bar-man';
      const tip = `${fmtWhen(b.created_at)} · ${TYPE[b.trigger] || b.trigger} · ${err ? 'Falhou' : fmtSize(b.size) + ' · ' + fmtDur(b.duration)}`;
      const d = parse(b.created_at);
      const txt = sameDay ? `${pad(d.getHours())}:${pad(d.getMinutes())}` : `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
      const lab = items.length <= 10 || i % 2 === 0 ? `<text x="${x + bw / 2}" y="${H - 5}" text-anchor="middle">${txt}</text>` : '';
      g += `<g class="b" data-open="${esc(b.id)}"><title>${esc(tip)}</title><rect class="${cls}" x="${x}" y="${PT + ih - h}" width="${bw}" height="${h}" rx="3"/>${lab}</g>`;
    });
    return `<div class="chart-wrap"><svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Tamanho das últimas cópias">${g}</svg></div>
      <div class="legend"><span><i style="background:var(--chart-bar)"></i>Automático</span><span><i style="background:var(--chart-bar-2)"></i>Manual</span><span><i style="background:var(--red)"></i>Falha</span></div>`;
  }

  function viewHealth(items) {
    if (!items || !items.length) return '';
    const scored = items.filter((i) => i.state !== 'info');
    const good = scored.filter((i) => i.state === 'ok').length;
    const icon = { ok: I.ok, warn: I.bang, err: I.bang, info: I.key };
    return `<div class="card pad">
      <div class="card-title" style="margin-bottom:12px">Saúde da proteção</div>
      <div class="score"><b>${good}/${scored.length}</b><span>itens em ordem</span></div>
      <ul class="health">${items.map((i) => `<li class="${i.state}"><span class="hi">${icon[i.state]}</span><div><div class="ht">${esc(i.title)}</div><div class="hd">${esc(i.detail)}</div></div></li>`).join('')}</ul>
    </div>`;
  }

  // ============================================================== política
  function viewPolicy() {
    const p = S.policyDraft || S.data.policy;
    const Lm = S.data.limits;
    const seg = (on, act, label) => `<div class="${on ? 'on' : ''}" data-action="${act}">${label}</div>`;
    return `<div class="narrow">
      <div class="page-head"><div><h1>Política de backup</h1><p>Defina como, quando e por quanto tempo as cópias são feitas.</p></div></div>

      <div class="card pad-lg mb16">
        <div class="card-title">Banco de dados</div>
        <div class="card-sub" style="margin-bottom:0">SGBD em uso: <strong>${esc(S.data.connection.sgbd_label)}</strong>${S.data.connection.dbname ? ` · banco <span class="mono">${esc(S.data.connection.dbname)}</span>` : ''}${S.data.connection.ssh && S.data.connection.ssh.enabled ? ` · via SSH <span class="mono">${esc(S.data.connection.ssh.host)}</span>` : ''}. Altere na tela <a href="#/conexao">Conexão</a>.</div>
      </div>

      <div class="card pad-lg mb16">
        <div class="card-title">Agendamento</div>
        <div class="card-sub">Automação elimina a dependência de intervenção manual.</div>
        <div class="seg">${seg(p.schedule_mode === 'daily', 'pol-daily', 'Diário à meia-noite')}${seg(p.schedule_mode === 'custom', 'pol-custom', 'Intervalo personalizado')}</div>
        ${p.schedule_mode === 'custom' ? `<div class="inline">Executar a cada <input class="num" type="number" id="pol-interval" min="${Lm.interval[0]}" max="${Lm.interval[1]}" value="${esc(p.interval_days)}"> dias, à meia-noite</div>` : ''}
      </div>

      <div class="card pad-lg mb16">
        <div class="card-title">Retenção</div>
        <div class="card-sub" style="margin-bottom:18px">Por quantos dias cada cópia é mantida antes de ser excluída automaticamente.</div>
        <div class="range-row">
          <input type="range" id="pol-retention" min="${Lm.retention[0]}" max="${Lm.retention[1]}" value="${esc(p.retention_days)}">
          <div class="range-val"><b id="ret-val">${esc(p.retention_days)}</b><span>dias</span></div>
        </div>
        <div class="hint">Mínimo: ${Lm.retention[0]} dia · máximo: ${Lm.retention[1]} dias. A cópia válida mais recente nunca é excluída.</div>
      </div>

      <div class="card pad-lg mb16">
        <div class="card-title">Diretório de armazenamento</div>
        <div class="card-sub">Pasta isolada da aplicação, onde fica a cópia local. As cópias em outro disco e fora do local ficam em <a href="#/copias">Cópias externas</a>.</div>
        <input class="input mono" id="pol-dir" value="${esc(p.directory)}" spellcheck="false">
      </div>

      <div class="card pad-lg mb22">
        <div class="card-title" style="margin-bottom:16px">Segurança das cópias</div>
        <div class="toggle-row"><div><div class="t">Criptografia (AES-256)</div><div class="d">Protege o conteúdo mesmo se a cópia for interceptada.</div></div>
          <button class="toggle ${p.encryption ? 'on' : ''}" data-action="pol-enc" aria-label="Criptografia"><span></span></button></div>
        <div class="toggle-row"><div><div class="t">Compressão (gzip)</div><div class="d">Reduz o espaço ocupado em disco pelas cópias diárias.</div></div>
          <button class="toggle ${p.compression ? 'on' : ''}" data-action="pol-comp" aria-label="Compressão"><span></span></button></div>
        ${p.encryption ? `<div class="warn-note">A chave de criptografia fica em <code>${esc(S.data.key_path)}</code>. Guarde uma cópia dela fora do servidor: sem a chave, as cópias não podem ser recuperadas.</div>` : ''}
      </div>

      <div class="actions">
        <button class="btn btn-primary btn-lg" data-action="pol-save" ${S.busy.pol ? 'disabled' : ''}>${S.busy.pol ? 'Salvando…' : 'Salvar política'}</button>
        <a class="btn btn-ghost btn-lg" href="#/painel">Cancelar</a>
      </div>
    </div>`;
  }

  // ============================================================= histórico
  function viewHistory() {
    const all = S.backups;
    const match = (b, f) => f === 'all' || (f === 'auto' ? b.trigger === 'auto' : f === 'manual' ? b.trigger !== 'auto' : b.status === 'error');
    const list = all ? all.filter((b) => match(b, S.filter)) : null;
    const count = (f) => (all ? all.filter((b) => match(b, f)).length : '');
    const tab = (f, label) => `<div class="${S.filter === f ? 'on' : ''}" data-filter="${f}">${label}<span class="count">${count(f)}</span></div>`;
    const rows = !list ? `<div class="empty">${I.spinner()}</div>` : list.length ? list.map((b) => `
      <div class="row" data-open="${esc(b.id)}">
        <span class="c-date">${fmtWhen(b.created_at)}</span>
        <span class="c-type">${TYPE[b.trigger] || esc(b.trigger)}</span>
        <span class="c-db">${esc(b.dbname)} <small>· ${esc(b.sgbd_label.replace(' (MySQL)', ''))}</small></span>
        <span class="c-size">${fmtSize(b.size)}</span>
        <span class="c-dur">${fmtDur(b.duration)}</span>
        <span class="c-st">${b.ext ? `<span class="tag" title="Cópias externas conferidas">+${b.ext} ext</span>` : ''}${b.origin === 'imported' ? '<span class="tag" title="Encontrada num destino externo">importada</span>' : ''}${pill(b.status)}</span>
      </div>`).join('') : '<div class="empty">Nenhuma cópia neste filtro.</div>';
    return `
      <div class="page-head"><div><h1>Histórico de backups</h1><p>${list ? list.length : '…'} ${list && list.length === 1 ? 'cópia listada' : 'cópias listadas'} · cópias expiradas são removidas pela retenção.</p></div>${runBtn()}</div>
      <div class="tabs">${tab('all', 'Todos')}${tab('auto', 'Automáticos')}${tab('manual', 'Manuais')}${tab('error', 'Falhas')}</div>
      <div class="card table" style="overflow:hidden">
        <div class="thead"><span class="c-date">Data</span><span class="c-type">Tipo</span><span class="c-db">Banco · SGBD</span><span class="c-size">Tamanho</span><span class="c-dur">Duração</span><span class="c-st">Status</span></div>
        ${rows}
      </div>`;
  }

  // =============================================================== detalhe
  function lineHtml(l, q, isNew) {
    let msg = esc(l.message);
    if (q) {
      const rx = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      msg = l.message.split(rx).map(esc).join('\u0000');
      const found = l.message.match(rx) || [];
      let k = 0;
      msg = msg.replace(/\u0000/g, () => `<mark>${esc(found[k++])}</mark>`);
    }
    return `<div class="ln ${esc(l.level)}${isNew ? ' new' : ''}"><span class="t">${esc(time(l.ts))}</span><span class="l ${esc(l.level)}">${esc(l.level)}</span><span class="m">${msg}</span></div>`;
  }

  function viewDetail() {
    const D = S.detail;
    const backLink = `<a class="back" href="#/historico">${I.back}Histórico</a>`;
    if (!D) return backLink + `<div class="loading">${I.spinner(18)} Carregando…</div>`;
    if (D.error) return backLink + `<div class="card pad empty">${esc(D.error)}</div>`;
    const b = D.backup;
    const ok = b.status === 'success';
    const prot = [b.encrypted ? 'AES-256-GCM' : null, b.compressed ? 'gzip' : null].filter(Boolean).join(' · ') || 'Nenhuma';
    let integ = 'Não verificada';
    if (b.verify_ok === true) integ = `<span style="color:var(--green-ink);font-weight:600">Íntegra</span> · ${fmtWhen(b.verified_at)}`;
    if (b.verify_ok === false) integ = `<span style="color:var(--red-h);font-weight:600">Corrompida</span> · ${fmtWhen(b.verified_at)}`;
    const running = S.data.running;
    const reps = D.replicas || [];
    const extOk = reps.some((r) => r.status === 'success');
    const canRestore = ok && (b.local || extOk);
    const others = (D.executions || []);
    const extra = others.length ? `<div class="grp" style="cursor:default">outras execuções desta cópia: ${others.map((e) => `${KIND[e.kind]} ${fmtWhen(e.started_at)} (${PILL[e.status]})`).map(esc).join(' · ')} — <a href="#/logs">ver no terminal</a></div>` : '';
    return `${backLink}
      <div class="detail-head"><div><h1>${esc(b.id)}</h1><p>${fmtWhen(b.created_at)}</p></div>${pill(b.status)}</div>
      <div class="grid-detail">
        <div class="card pad-lg">
          <div class="card-title" style="margin-bottom:16px">Metadados</div>
          <div class="meta">
            <div><div class="k">TIPO</div><div class="v">${TYPE[b.trigger] || esc(b.trigger)}</div></div>
            <div><div class="k">SGBD</div><div class="v">${esc(b.sgbd_label)}</div></div>
            <div><div class="k">BANCO DE DADOS</div><div class="v mono">${esc(b.dbname)}</div></div>
            <div><div class="k">TAMANHO</div><div class="v">${fmtSize(b.size)}${b.raw_size ? ` <span style="color:var(--muted-3)">(dump ${fmtSize(b.raw_size)})</span>` : ''}</div></div>
            <div><div class="k">DURAÇÃO</div><div class="v">${fmtDur(b.duration)}</div></div>
            <div><div class="k">PROTEÇÃO</div><div class="v">${prot}</div></div>
            <div><div class="k">INTEGRIDADE</div><div class="v">${integ}</div></div>
            <div><div class="k">SHA-256 ${b.sha256 ? `<button class="copy" data-action="copy-sha" title="Copiar">${I.copy}</button>` : ''}</div><div class="v mono" style="font-size:11.5px;word-break:break-all">${esc(b.sha256 || '—')}</div></div>
          </div>
          ${ok ? `<div class="path"><div class="k">LOCAL DE ARMAZENAMENTO</div><div class="v">${b.local ? esc(b.path) : '<span style="color:var(--amber-ink)">Não está neste servidor' + (extOk ? ' — disponível nas cópias externas' : '') + '</span>'}</div></div>` : ''}
          ${b.error ? `<div class="err-box">${esc(b.error)}</div>` : ''}
        </div>
        <div class="card pad-lg act">
          <div class="card-title" style="margin-bottom:6px">Ações</div>
          <button class="btn btn-primary" data-action="restore" ${!canRestore || running ? 'disabled' : ''}>${I.restore}Restaurar este backup</button>
          ${ok && !b.local && extOk ? `<button class="btn btn-soft" data-action="fetch" ${running ? 'disabled' : ''}>${I.download}Trazer para o servidor</button>` : ''}
          <button class="btn btn-ghost" data-action="verify" ${!ok || running || S.busy.verify ? 'disabled' : ''}>${S.busy.verify ? I.spinner() + 'Verificando…' : I.verify + 'Verificar integridade'}</button>
          <a class="btn btn-ghost ${ok && b.local ? '' : 'disabled'}" ${ok && b.local ? `href="/api/backups/${encodeURIComponent(b.id)}/download"` : ''}>${I.download}Baixar cópia</a>
          <button class="btn btn-danger-ghost" data-action="delete" ${b.status === 'running' ? 'disabled' : ''}>${I.trash}Excluir cópia</button>
          ${ok && b.encrypted ? '<div class="hint">A cópia baixada continua criptografada. Para ler fora do painel: <span class="mono">python -m sentinela decrypt</span>.</div>' : ''}
        </div>
      </div>
      ${ok ? viewReplicas(reps) : ''}
      <div class="term">
        <div class="term-head"><span class="lights"><i></i><i></i><i></i></span><span class="title">log desta execução</span>
          <span class="info">${b.status === 'running' ? '<span class="live-badge"><i></i>ao vivo</span>' : ''}${D.logs.length} linhas</span></div>
        <div class="term-body mid" id="detail-term">${D.logs.length ? D.logs.map((l) => lineHtml(l)).join('') : '<div class="term-empty">Sem registros.</div>'}${b.status === 'running' ? '<span class="cursor"></span>' : ''}${extra}</div>
      </div>`;
  }

  function viewReplicas(reps) {
    const rows = reps.map((r) => `<div class="rep-row">
        <div class="rep-main">${destIcon(r.dest_type)}<div style="min-width:0"><div class="rep-name">${esc(r.dest_name)} <span class="muted" style="font-weight:400">· ${esc(r.dest_type_label)}</span></div>
          <div class="rep-sub mono">${esc(r.remote_path || r.dest_target || '')}</div>
          ${r.error && r.status !== 'deleted' ? `<div class="rep-err">${esc(r.error)}</div>` : ''}</div></div>
        <div class="rep-side">${repPill(r.status)}<div class="rep-sub">${r.verify_ok === 0 ? '<span style="color:var(--red-h)">corrompida</span> · ' : ''}${r.verified_at ? 'conferida ' + fmtWhen(r.verified_at) : r.uploaded_at ? fmtWhen(r.uploaded_at) : ''}${r.attempts > 1 ? ` · ${r.attempts} tentativas` : ''}</div></div>
      </div>`).join('');
    return `<div class="card mb16">
      <div class="card-head"><span class="card-title">Cópias externas</span><a class="link" href="#/copias">Destinos →</a></div>
      ${reps.length ? rows : `<div class="empty">Esta cópia existe só neste servidor. ${S.data.destinations && S.data.destinations.length ? 'Ela será enviada na próxima sincronização.' : '<a href="#/copias">Adicione um destino externo</a> para cumprir a regra 3-2-1.'}</div>`}
    </div>`;
  }

  // ============================================================ terminal
  async function loadLogs() {
    const r = await api('GET', '/api/logs?limit=40');
    L.execs = new Map();
    r.executions.slice().reverse().forEach((e) => L.execs.set(e.id, e));
    L.lastId = r.last_id; L.running = r.running; L.loaded = true; L.fresh = new Set();
  }

  async function tailLogs() {
    const r = await api('GET', '/api/logs/tail?since=' + L.lastId);
    let changed = false;
    r.executions.forEach((e) => {
      const old = L.execs.get(e.id);
      if (!old) { e.lines = []; L.execs.set(e.id, e); changed = true; } else if (old.status !== e.status || old.finished_at !== e.finished_at) {
        Object.assign(old, e, { lines: old.lines }); changed = true;
      }
    });
    L.fresh = new Set();
    r.lines.forEach((ln) => {
      const ex = L.execs.get(ln.execution_id);
      if (ex && !ex.lines.some((x) => x.id === ln.id)) { ex.lines.push(ln); L.fresh.add(ln.id); changed = true; }
    });
    // execuções que terminaram entre duas consultas
    if (L.running && !r.running) {
      L.execs.forEach((e) => { if (e.status === 'running') changed = true; });
      const fresh = await api('GET', '/api/logs?limit=40');
      fresh.executions.forEach((e) => { const o = L.execs.get(e.id); if (o) Object.assign(o, e); });
    }
    const was = L.running;
    L.lastId = r.last_id; L.running = r.running;
    if (S.data) { S.data.running = r.running; S.data.current = r.current; }
    if (changed || was !== L.running) updateTerm();
    if (was !== L.running) {
      updateNavBadge();
      if (!L.running) { try { S.data = await api('GET', '/api/state'); } catch (e) { /* ignora */ } }
      const box = document.querySelector('.dbbox'); if (box) box.innerHTML = dbBox(S.data);
    }
  }

  function visibleExecs() {
    return [...L.execs.values()].sort((a, b) => a.id - b.id)
      .filter((e) => L.kind === 'all' || e.kind === L.kind);
  }

  function filteredLines(e) {
    const q = L.q.toLowerCase();
    return e.lines.filter((l) => (L.level === 'all' || l.level === L.level) && (!q || l.message.toLowerCase().includes(q)));
  }

  function termLinesHtml() {
    const filtering = L.level !== 'all' || L.q;
    const parts = [];
    let shown = 0, total = 0;
    visibleExecs().forEach((e) => {
      const lines = filteredLines(e);
      total += e.lines.length;
      if (filtering && !lines.length) return;
      shown += lines.length;
      const closed = L.collapsed.has(e.id);
      const trig = e.kind === 'backup' ? ` · ${TYPE[e.trigger] || e.trigger}` : '';
      const ref = e.backup_id ? ` · <a href="#/backup/${esc(e.backup_id)}">${esc(e.backup_id)}</a>` : '';
      const dur = e.finished_at ? ` · ${fmtDur((parse(e.finished_at) - parse(e.started_at)) / 1000)}` : '';
      parts.push(`<div class="grp ${closed ? 'closed' : ''}" data-grp="${e.id}"><span class="caret">${I.caret}</span>━━ ${fmtWhen(e.started_at)} · ${KIND[e.kind] || esc(e.kind)}${esc(trig)}${ref}${esc(dur)}<span class="st ${esc(e.status)}"><i></i>${PILL[e.status] || esc(e.status)}</span></div>`);
      parts.push(`<div class="grp-lines ${closed ? 'hidden' : ''}">${lines.map((l) => lineHtml(l, L.q, L.fresh.has(l.id))).join('')}</div>`);
    });
    if (!parts.length) {
      return { html: `<div class="term-empty">${L.execs.size ? 'Nenhuma linha corresponde aos filtros.' : 'Nenhuma execução registrada ainda. Os logs aparecem aqui assim que um backup começar.'}</div>`, shown, total };
    }
    if (L.running) parts.push('<span class="cursor"></span>');
    return { html: parts.join(''), shown, total };
  }

  function termInfo(shown, total) {
    return `${L.running ? '<span class="live-badge"><i></i>ao vivo</span>' : ''}<span>${shown === total ? `${total} linhas` : `${shown} de ${total} linhas`} · ${L.execs.size} execuções</span>`;
  }

  function viewLogs() {
    if (!L.loaded) return `<div class="page-head"><div><h1>Logs de execução</h1><p>Registro detalhado de cada etapa, com horário exato.</p></div></div><div class="loading">${I.spinner(18)} Carregando…</div>`;
    const t = termLinesHtml();
    const chip = (group, v, label) => `<div class="${(group === 'level' ? L.level : L.kind) === v ? 'on' : ''} ${v}" data-chip="${group}:${v}">${label}</div>`;
    return `
      <div class="page-head"><div><h1>Logs de execução</h1><p>Registro detalhado de cada etapa, com horário exato — atualizado ao vivo.</p></div>
        <div class="actions"><button class="btn btn-ghost" data-action="copy-logs">${I.copy}Copiar</button>
        <a class="btn btn-ghost" href="/api/logs/download">${I.download}Baixar logs</a></div></div>
      <div class="toolbar">
        <div class="search">${I.search}<input class="input sm" id="log-q" placeholder="Buscar nos logs…  ( / )" value="${esc(L.q)}" autocomplete="off" spellcheck="false"></div>
        <div class="chips">${chip('level', 'all', 'Todos')}${chip('level', 'INFO', 'INFO')}${chip('level', 'OK', 'OK')}${chip('level', 'WARN', 'WARN')}${chip('level', 'ERRO', 'ERRO')}</div>
        <div class="chips">${chip('kind', 'all', 'Tudo')}${chip('kind', 'backup', 'Backups')}${chip('kind', 'restore', 'Restaurações')}${chip('kind', 'verify', 'Verificações')}${chip('kind', 'replicate', 'Cópias externas')}</div>
        <label class="follow tb-right"><button class="toggle sm ${L.follow ? 'on' : ''}" data-action="follow" aria-label="Seguir"><span></span></button>Seguir novas linhas</label>
      </div>
      <div class="term">
        <div class="term-head"><span class="lights"><i></i><i></i><i></i></span><span class="title">sentinela.log — tail -f</span><span class="info" id="term-info">${termInfo(t.shown, t.total)}</span></div>
        <div class="term-body tall" id="term-body">${t.html}</div>
      </div>`;
  }

  function updateTerm() {
    const body = document.getElementById('term-body');
    if (!body) return;
    const nearBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 60;
    const t = termLinesHtml();
    body.innerHTML = t.html;
    const info = document.getElementById('term-info');
    if (info) info.innerHTML = termInfo(t.shown, t.total);
    if (L.follow && (nearBottom || L.fresh.size)) body.scrollTop = body.scrollHeight;
  }

  function scrollTerm(force) {
    const body = document.getElementById(S.route === 'logs' ? 'term-body' : 'detail-term');
    if (!body) return;
    if (force || (S.route === 'logs' ? L.follow : S.data && S.data.running)) body.scrollTop = body.scrollHeight;
  }

  function updateNavBadge() {
    const a = document.querySelector('.nav a[href="#/logs"]');
    if (!a) return;
    const b = a.querySelector('.badge');
    if (L.running && !b) a.insertAdjacentHTML('beforeend', '<span class="badge"></span>');
    if (!L.running && b) b.remove();
  }

  function bindTerm() {
    const body = document.getElementById('term-body');
    if (!body) return;
    body.addEventListener('scroll', () => {
      const atBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 60;
      if (L.follow !== atBottom && !(atBottom && L.follow)) {
        L.follow = atBottom;
        const tg = document.querySelector('[data-action="follow"]');
        if (tg) tg.classList.toggle('on', L.follow);
      }
    }, { passive: true });
    const q = document.getElementById('log-q');
    let deb = null;
    q.addEventListener('input', () => {
      clearTimeout(deb);
      deb = setTimeout(() => { L.q = q.value.trim(); L.fresh = new Set(); updateTerm(); }, 120);
    });
  }

  function termText() {
    const out = [];
    visibleExecs().forEach((e) => {
      const lines = filteredLines(e);
      if ((L.level !== 'all' || L.q) && !lines.length) return;
      out.push(`━━ ${fmtWhen(e.started_at)} · ${KIND[e.kind] || e.kind}${e.backup_id ? ' · ' + e.backup_id : ''} · ${PILL[e.status] || e.status}`);
      lines.forEach((l) => out.push(`${time(l.ts)}  ${l.level.padEnd(4)}  ${l.message}`));
      out.push('');
    });
    return out.join('\n');
  }

  // =============================================================== conexão
  function viewConn() {
    const c = S.connDraft || S.data.connection;
    const sh = c.ssh || {};
    const seg = (on, act, label) => `<div class="${on ? 'on' : ''}" data-action="${act}">${label}</div>`;
    const t = S.test;
    let testMsg = '';
    if (t.status === 'testing') testMsg = `<span class="test-run">${I.spinner()}Testando${sh.enabled ? ' (abrindo túnel SSH)' : ''}…</span>`;
    if (t.status === 'ok') testMsg = `<span class="test-ok">${I.check('#22a565', 15)}Conexão bem-sucedida · ${esc(t.version)}${sh.enabled ? ' · via SSH' : ''}</span>`;
    if (t.status === 'error') testMsg = `<span class="test-err">${I.x}<span>${esc(t.error)}</span></span>`;
    const f = (id, label, val, type = 'text', ph = '') => `<div><label class="lbl" for="${id}">${label}</label><input class="input sm mono" id="${id}" type="${type}" value="${esc(val)}" placeholder="${esc(ph)}" spellcheck="false" autocomplete="off"></div>`;
    return `<div class="narrow-sm">
      <div class="page-head"><div><h1>Conexão com o banco</h1><p>Configure o acesso ao banco de dados que será copiado.</p></div></div>
      <div class="card pad-lg mb16">
        <div class="lbl" style="margin-bottom:10px">Gerenciador (SGBD)</div>
        <div class="seg full mb20">${seg(c.sgbd === 'postgres', 'sgbd-postgres', 'PostgreSQL')}${seg(c.sgbd === 'mariadb', 'sgbd-mariadb', 'MariaDB (MySQL)')}</div>
        <div class="lbl" style="margin-bottom:10px">Forma de acesso</div>
        <div class="seg full">${seg(!sh.enabled, 'ssh-off', 'Conexão direta')}${seg(sh.enabled, 'ssh-on', 'Túnel SSH')}</div>
        ${sh.enabled ? viewSsh(sh, f, seg) : '<div class="hint">O Sentinela conecta direto na porta do banco. Use o túnel SSH quando o banco estiver em outro servidor e a porta dele não estiver exposta.</div>'}
      </div>
      <div class="card pad-lg mb16">
        <div class="card-title">Banco de dados</div>
        <div class="card-sub">${sh.enabled ? 'Host e porta do banco <strong>vistos a partir do servidor SSH</strong> — normalmente <span class="mono">localhost</span>.' : 'Endereço do servidor de banco de dados.'}</div>
        <div class="g21 mb16">${f('c-host', 'Host', c.host)}${f('c-port', 'Porta', c.port)}</div>
        <div class="mb16">${f('c-dbname', 'Nome do banco', c.dbname, 'text', 'ex.: loja_producao')}</div>
        <div class="g2 mb20">${f('c-user', 'Usuário', c.user)}${f('c-password', 'Senha', c.password || '', 'password', S.data.connection.has_password ? '•••••••• (mantida)' : '')}</div>
        <div class="actions" style="gap:14px">
          <button class="btn btn-soft" data-action="conn-test" ${t.status === 'testing' ? 'disabled' : ''}>Testar conexão</button>
          ${testMsg}
        </div>
      </div>
      <div class="card pad-lg mb22">
        <div class="card-title">Diretório de backup</div>
        <div class="card-sub">Pasta isolada onde fica a cópia local. Outro disco e nuvem: <a href="#/copias">Cópias externas</a>.</div>
        <input class="input mono" id="c-directory" value="${esc(c.directory)}" spellcheck="false">
      </div>
      <button class="btn btn-primary btn-lg" data-action="conn-save" ${S.busy.conn ? 'disabled' : ''}>${S.busy.conn ? 'Salvando…' : 'Salvar configurações'}</button>
    </div>`;
  }

  function viewSsh(sh, f, seg) {
    const saved = S.data.connection.ssh || {};
    const keep = (has) => (has ? '•••••••• (mantida)' : '');
    const hostKey = sh.host_key
      ? `<div class="hint">${I.key} Chave do servidor registrada: <span class="mono">${esc(sh.host_key)}</span> · <a data-action="ssh-reset">redefinir</a></div>`
      : '<div class="hint">A impressão digital do servidor SSH será registrada na primeira conexão; se ela mudar depois, a conexão é bloqueada.</div>';
    const auth = sh.auth === 'key'
      ? `<div class="mb16"><label class="lbl" for="s-private_key">Chave privada</label>
           <textarea class="input mono" id="s-private_key" rows="5" spellcheck="false" placeholder="${saved.has_private_key ? 'Chave mantida — cole outra para substituir' : '-----BEGIN OPENSSH PRIVATE KEY-----'}">${esc(sh.private_key || '')}</textarea>
           <div class="hint">Formatos aceitos: OpenSSH ou PEM (ed25519, RSA, ECDSA). Chaves PuTTY (.ppk) precisam ser exportadas como OpenSSH.</div></div>
         ${f('s-key_passphrase', 'Senha da chave (se houver)', sh.key_passphrase || '', 'password', keep(saved.has_passphrase))}`
      : f('s-password', 'Senha SSH', sh.password || '', 'password', keep(saved.has_password));
    return `<div class="divider">
        <div class="g21 mb16">${f('s-host', 'Servidor SSH', sh.host, 'text', 'ex.: 200.100.50.10')}${f('s-port', 'Porta SSH', sh.port || '22')}</div>
        <div class="mb16">${f('s-user', 'Usuário SSH', sh.user, 'text', 'ex.: backup')}</div>
        <div class="lbl" style="margin-bottom:10px">Autenticação</div>
        <div class="seg mb16">${seg(sh.auth !== 'key', 'ssh-auth-password', 'Senha')}${seg(sh.auth === 'key', 'ssh-auth-key', 'Chave privada')}</div>
        ${auth}
        ${hostKey}
      </div>`;
  }

  // ======================================================= cópias externas
  const DTYPE = { directory: 'Outro disco', sftp: 'Servidor SFTP', s3: 'Armazenamento S3' };
  const fieldInput = (id, label, val, type = 'text', ph = '', hint = '') => `<div><label class="lbl" for="${id}">${label}</label><input class="input sm mono" id="${id}" type="${type}" value="${esc(val)}" placeholder="${esc(ph)}" spellcheck="false" autocomplete="off">${hint ? `<div class="hint">${hint}</div>` : ''}</div>`;

  function viewDest() {
    const D = S.dests;
    const head = `<div class="page-head"><div><h1>Cópias externas</h1><p>Regra 3-2-1: 3 cópias dos dados, em 2 mídias diferentes, com 1 fora do local.</p></div>
      <div class="actions">${D && D.destinations.length ? `<button class="btn btn-ghost" data-action="dest-sync" ${S.data.running || S.busy.sync ? 'disabled' : ''}>${S.busy.sync ? I.spinner() : I.sync}Sincronizar agora</button>` : ''}
      ${S.destDraft ? '' : `<button class="btn btn-primary" data-action="dest-new">${I.plus}Adicionar destino</button>`}</div></div>`;
    if (!D) return head + `<div class="loading">${I.spinner(18)} Carregando…</div>`;
    const r = D.rule321;
    const check = (ok, t, d) => `<li class="${ok ? 'ok' : 'warn'}"><span class="hi">${ok ? I.ok : I.bang}</span><div><div class="ht">${t}</div><div class="hd">${d}</div></div></li>`;
    const sameDisk = D.destinations.some((x) => x.same_device);
    const ruleCard = `<div class="card pad-lg mb16">
      <div class="card-title" style="margin-bottom:14px">Situação da cópia mais recente${r.backup_id ? ` <span class="mono muted" style="font-weight:400;font-size:12px">· ${esc(r.backup_id)}</span>` : ''}</div>
      ${ruleTiles(r)}
      <ul class="health" style="margin-top:16px">
        ${check(r.copies >= 3, '3 cópias', 'O banco em produção, a cópia local e pelo menos uma cópia externa conferida.')}
        ${check(r.media >= 2, '2 mídias diferentes', 'A cópia externa precisa estar em outro disco/serviço — um HD externo no mesmo disco da pasta local não conta.' + (sameDisk ? ' <b>Há destino no mesmo disco das cópias locais.</b>' : ''))}
        ${check(r.offsite >= 1, '1 fora do local', 'Um destino em outro prédio ou na nuvem (SFTP em outro lugar ou S3), para sobreviver a incêndio, furto ou ransomware no servidor.')}
      </ul>
      ${D.pending ? `<div class="warn-note">${D.pending} envio(s) pendente(s). O Sentinela tenta de novo a cada hora; use "Sincronizar agora" para enviar já.</div>` : ''}
    </div>`;
    const cards = D.destinations.map(destCard).join('');
    return `${head}
      ${S.destDraft ? viewDestForm() : ''}
      ${ruleCard}
      ${D.destinations.length ? `<div class="dest-list mb16">${cards}</div>` : (S.destDraft ? '' : `<div class="card pad-lg mb16 empty"><span class="big">Nenhum destino externo</span>Hoje todas as cópias ficam só em <span class="mono">${esc(S.data.policy.directory)}</span>. Adicione um HD externo e um destino fora do local (SFTP ou S3).</div>`)}
      ${viewKeyCard()}`;
  }

  function destCard(x) {
    const last = x.last;
    let status = '<span class="muted">Ainda não recebeu cópias</span>';
    if (last) status = last.status === 'success' ? `Última cópia conferida ${relPast(last.at)}` : `<span style="color:var(--red-h)">Falhou ${relPast(last.at)}: ${esc(last.error || '')}</span>`;
    return `<div class="card pad dest ${x.enabled ? '' : 'off'}">
      <div class="dest-head">${destIcon(x.type)}<div style="flex:1;min-width:0">
        <div class="dest-name">${esc(x.name)} ${x.offsite ? '<span class="tag">fora do local</span>' : '<span class="tag">no local</span>'}${x.enabled ? '' : ' <span class="tag">pausado</span>'}${x.same_device ? ' <span class="tag warn">mesmo disco das cópias locais</span>' : ''}</div>
        <div class="dest-target mono">${esc(x.type_label)} · ${esc(x.target)}</div></div>
        ${last ? repPill(last.status) : ''}</div>
      <div class="dest-stats"><span><b>${x.copies}</b> ${x.copies === 1 ? 'cópia' : 'cópias'}</span><span><b>${fmtSize(x.bytes)}</b></span>${x.missing ? `<span style="color:var(--amber-ink)"><b>${x.missing}</b> pendente(s)</span>` : ''}${x.pending_deletes ? `<span style="color:var(--amber-ink)"><b>${x.pending_deletes}</b> exclusão(ões) pendente(s)</span>` : ''}</div>
      <div class="dest-status">${status}</div>
      ${x.host_key ? `<div class="hint">${I.key} Servidor: <span class="mono">${esc(x.host_key)}</span></div>` : ''}
      <div class="dest-actions">
        <button class="btn btn-ghost btn-sm" data-action="dest-edit" data-id="${esc(x.id)}">${I.edit}Editar</button>
        <button class="btn btn-ghost btn-sm" data-action="dest-toggle" data-id="${esc(x.id)}">${x.enabled ? I.pause + 'Pausar' : I.play + 'Ativar'}</button>
        <button class="btn btn-ghost btn-sm" data-action="dest-import" data-id="${esc(x.id)}" title="Procura cópias neste destino que não estão no histórico (servidor novo)">${I.find}Procurar cópias</button>
        <button class="btn btn-danger-ghost btn-sm" data-action="dest-remove" data-id="${esc(x.id)}">${I.trash}Remover</button>
      </div>
    </div>`;
  }

  function viewDestForm() {
    const d = S.destDraft;
    const seg = (on, act, label) => `<div class="${on ? 'on' : ''}" data-action="${act}">${label}</div>`;
    const keep = (has) => (has ? '•••••••• (mantida)' : '');
    const t = S.destTest;
    let msg = '';
    if (t.status === 'testing') msg = `<span class="test-run">${I.spinner()}Gravando, lendo e apagando um arquivo de teste…</span>`;
    if (t.status === 'ok') msg = `<span class="test-ok">${I.check('#22a565', 15)}Destino funcionando · ${esc(t.summary)}</span>`;
    if (t.status === 'error') msg = `<span class="test-err">${I.x}<span>${esc(t.error)}</span></span>`;
    let fields = '';
    if (d.type === 'directory') {
      fields = `<div class="mb16">${fieldInput('d-path', 'Pasta no outro disco', d.path, 'text', '/mnt/hd-externo/sentinela', 'Monte o HD externo, NAS (NFS/SMB) ou segundo disco e informe uma pasta nele. Precisa ser diferente da pasta das cópias locais.')}</div>`;
    } else if (d.type === 'sftp') {
      const auth = d.auth === 'key'
        ? `<div class="mb16"><label class="lbl" for="d-private_key">Chave privada</label><textarea class="input mono" id="d-private_key" rows="4" spellcheck="false" placeholder="${d.has_private_key ? 'Chave mantida — cole outra para substituir' : '-----BEGIN OPENSSH PRIVATE KEY-----'}">${esc(d.private_key || '')}</textarea></div>
           <div class="mb16">${fieldInput('d-key_passphrase', 'Senha da chave (se houver)', d.key_passphrase || '', 'password', keep(d.has_key_passphrase))}</div>`
        : `<div class="mb16">${fieldInput('d-password', 'Senha', d.password || '', 'password', keep(d.has_password))}</div>`;
      fields = `<div class="g21 mb16">${fieldInput('d-host', 'Servidor', d.host, 'text', 'backup.empresa.com.br')}${fieldInput('d-port', 'Porta', d.port || '22')}</div>
        <div class="g2 mb16">${fieldInput('d-user', 'Usuário', d.user, 'text', 'backup')}${fieldInput('d-path', 'Pasta remota', d.path, 'text', 'sentinela/copias')}</div>
        <div class="lbl" style="margin-bottom:10px">Autenticação</div>
        <div class="seg mb16">${seg(d.auth !== 'key', 'dest-auth-password', 'Senha')}${seg(d.auth === 'key', 'dest-auth-key', 'Chave privada')}</div>
        ${auth}
        ${d.host_key ? `<div class="hint">${I.key} Chave do servidor registrada: <span class="mono">${esc(d.host_key)}</span> · <a data-action="dest-reset-key">redefinir</a></div>` : '<div class="hint">A impressão digital do servidor é registrada na primeira conexão; se mudar, os envios são bloqueados.</div>'}`;
    } else {
      fields = `<div class="g2 mb16">${fieldInput('d-bucket', 'Bucket', d.bucket, 'text', 'empresa-backups')}${fieldInput('d-prefix', 'Pasta (prefixo)', d.prefix, 'text', 'sentinela')}</div>
        <div class="g21 mb16">${fieldInput('d-endpoint', 'Endpoint (vazio = AWS)', d.endpoint, 'text', 's3.us-west-004.backblazeb2.com')}${fieldInput('d-region', 'Região', d.region || '', 'text', 'us-east-1')}</div>
        <div class="g2 mb16">${fieldInput('d-access_key', 'Chave de acesso (Access Key)', d.access_key)}${fieldInput('d-secret_key', 'Chave secreta (Secret Key)', d.secret_key || '', 'password', keep(d.has_secret_key))}</div>
        <div class="hint" style="margin-top:-6px;margin-bottom:6px">Funciona com AWS S3, Backblaze B2, Wasabi, Cloudflare R2, MinIO e outros compatíveis. Use uma chave com permissão só neste bucket.</div>`;
    }
    return `<div class="card pad-lg mb16 dest-form">
      <div class="card-title" style="margin-bottom:14px">${d.id ? 'Editar destino' : 'Novo destino externo'}</div>
      ${d.id ? '' : `<div class="seg full mb20">${seg(d.type === 'directory', 'dest-type-directory', 'Outro disco')}${seg(d.type === 'sftp', 'dest-type-sftp', 'Servidor SFTP')}${seg(d.type === 's3', 'dest-type-s3', 'Armazenamento S3')}</div>`}
      <div class="mb16">${fieldInput('d-name', 'Nome', d.name, 'text', { directory: 'HD externo', sftp: 'Servidor da filial', s3: 'Nuvem' }[d.type])}</div>
      ${fields}
      <div class="toggle-row" style="margin-top:6px"><div><div class="t">Fica fora do local</div><div class="d">Marque se o destino está em outro prédio/cidade ou na nuvem (conta como o "1" da regra 3-2-1).</div></div>
        <button class="toggle ${d.offsite ? 'on' : ''}" data-action="dest-offsite" aria-label="Fora do local"><span></span></button></div>
      <div class="actions" style="gap:12px;margin-top:20px;flex-wrap:wrap">
        <button class="btn btn-primary" data-action="dest-save" ${S.busy.dest ? 'disabled' : ''}>${S.busy.dest ? 'Salvando…' : 'Salvar destino'}</button>
        <button class="btn btn-soft" data-action="dest-test" ${t.status === 'testing' ? 'disabled' : ''}>Testar destino</button>
        <button class="btn btn-ghost" data-action="dest-cancel">Cancelar</button>
        ${msg}
      </div>
    </div>`;
  }

  function viewKeyCard() {
    const d = S.data;
    return `<div class="card pad-lg mb16">
      <div class="card-title" style="display:flex;align-items:center;gap:8px">${I.keyLg}Chave mestra</div>
      <div class="card-sub">As cópias (inclusive as externas) só podem ser lidas com a chave mestra deste servidor. Guarde uma cópia dela <b>fora do servidor e longe das cópias</b> — num pendrive guardado ou num cofre de senhas. Se o servidor for perdido, ela é necessária para restaurar.</div>
      <div class="kv mb16"><span>Identificador</span><span class="mono">${esc(d.key_id)}</span></div>
      <div class="kv mb16"><span>Exportada</span><span>${d.key_exported_at ? fmtWhen(d.key_exported_at) : '<span style="color:var(--amber-ink)">nunca</span>'}</span></div>
      <div class="key-row"><input class="input sm" id="key-pw" type="password" placeholder="Sua senha do painel" autocomplete="current-password">
        <button class="btn btn-soft" data-action="key-export" ${S.busy.key ? 'disabled' : ''}>${I.download}Baixar chave mestra</button></div>
      <div class="hint">Num servidor novo, importe a chave com <span class="mono">python -m sentinela key import ARQUIVO.key</span> e use "Procurar cópias" no destino.</div>
    </div>`;
  }

  function readDest() {
    const d = S.destDraft; if (!d) return;
    ['name', 'path', 'host', 'port', 'user', 'password', 'private_key', 'key_passphrase', 'bucket', 'prefix', 'endpoint', 'region', 'access_key', 'secret_key'].forEach((k) => {
      const el = document.getElementById('d-' + k); if (el) d[k] = el.value;
    });
  }
  function newDestDraft(type, from) {
    const base = { type, name: '', enabled: true, offsite: type !== 'directory', auth: 'password', port: '22', password: '', private_key: '', key_passphrase: '', secret_key: '' };
    return Object.assign(base, from || {});
  }

  // ================================================================ avisos
  function viewNotif() {
    const N = S.notif, d = S.notifDraft;
    const head = `<div class="page-head"><div><h1>Avisos de falha</h1><p>Receba um alerta assim que um backup, uma cópia externa ou uma restauração falhar.</p></div></div>`;
    if (!N || !d) return head + `<div class="loading">${I.spinner(18)} Carregando…</div>`;
    const seg = (on, act, label) => `<div class="${on ? 'on' : ''}" data-action="${act}">${label}</div>`;
    const keep = (has) => (has ? '•••••••• (mantida)' : '');
    const chan = (ch, title, desc, body) => `<div class="card pad-lg mb16">
      <div class="toggle-row"><div><div class="t" style="font-weight:600">${title}</div><div class="d">${desc}</div></div>
        <button class="toggle ${d[ch].enabled ? 'on' : ''}" data-action="nt-toggle" data-ch="${ch}" aria-label="${title}"><span></span></button></div>
      ${d[ch].enabled ? `<div class="divider">${body}</div>` : ''}</div>`;
    const e = d.email, t = d.telegram, w = d.webhook;
    const email = `<div class="g21 mb16">${fieldInput('n-email-host', 'Servidor SMTP', e.host, 'text', 'smtp.gmail.com')}${fieldInput('n-email-port', 'Porta', e.port)}</div>
      <div class="lbl" style="margin-bottom:10px">Segurança</div>
      <div class="seg mb16">${seg(e.security === 'starttls', 'nt-sec-starttls', 'STARTTLS (587)')}${seg(e.security === 'ssl', 'nt-sec-ssl', 'SSL/TLS (465)')}${seg(e.security === 'none', 'nt-sec-none', 'Nenhuma')}</div>
      <div class="g2 mb16">${fieldInput('n-email-user', 'Usuário', e.user, 'text', 'alertas@empresa.com.br')}${fieldInput('n-email-password', 'Senha', e.password || '', 'password', keep(e.has_password), 'No Gmail/Outlook, use uma senha de app.')}</div>
      <div class="mb16">${fieldInput('n-email-sender', 'Remetente (opcional)', e.sender, 'text', 'Sentinela <alertas@empresa.com.br>')}</div>
      ${fieldInput('n-email-recipients', 'Destinatários', e.recipients, 'text', 'ti@empresa.com.br, dono@empresa.com.br', 'Separe vários endereços por vírgula.')}`;
    const tg = `<div class="g2">${fieldInput('n-telegram-token', 'Token do bot', t.token || '', 'password', keep(t.has_token) || '123456:ABC-DEF…')}${fieldInput('n-telegram-chat_id', 'Chat ID', t.chat_id, 'text', '123456789')}</div>
      <div class="hint">Crie o bot com o @BotFather, envie /start para ele e descubra o chat_id em api.telegram.org/bot&lt;token&gt;/getUpdates. Para grupos, adicione o bot ao grupo.</div>`;
    const wh = `<div class="mb16">${fieldInput('n-webhook-url', 'URL', w.url, 'text', 'https://hooks.slack.com/services/…')}</div>
      <div class="lbl" style="margin-bottom:10px">Formato</div>
      <div class="seg full">${seg(w.format === 'generic', 'nt-fmt-generic', 'JSON genérico')}${seg(w.format === 'slack', 'nt-fmt-slack', 'Slack')}${seg(w.format === 'discord', 'nt-fmt-discord', 'Discord')}${seg(w.format === 'teams', 'nt-fmt-teams', 'Teams')}</div>`;
    const evs = Object.entries(N.events).map(([k, label]) => `<div class="toggle-row"><div><div class="t">${esc(label)}</div><div class="d">${EV_DESC[k] || ''}</div></div>
      <button class="toggle ${d.events[k] ? 'on' : ''}" data-action="nt-event" data-ev="${k}" aria-label="${esc(label)}"><span></span></button></div>`).join('');
    const results = S.notifTest ? `<div class="test-results">${S.notifTest.map((r) => r.ok ? `<span class="test-ok">${I.check('#22a565', 15)}${esc(r.label)}: enviado</span>` : `<span class="test-err">${I.x}<span>${esc(r.label)}: ${esc(r.error)}</span></span>`).join('')}</div>` : '';
    const hist = N.history.length ? N.history.map((h) => `<div class="row" style="cursor:default">
        <span class="r-date">${fmtWhen(h.ts)}</span><span style="flex:1;min-width:0;font-size:13px">${esc(h.title)}<div class="muted" style="font-size:11.5px">${esc(N.channels[h.channel] || h.channel)}${h.attempts > 1 ? ` · ${h.attempts} tentativas` : ''}${h.error ? ' · ' + esc(h.error) : ''}</div></span>
        ${h.ok ? '<span class="pill success"><i></i>Enviado</span>' : '<span class="pill error"><i></i>Falhou</span>'}</div>`).join('') : '<div class="empty">Nenhum aviso enviado ainda.</div>';
    return `<div class="narrow">${head}
      ${chan('email', 'E-mail', 'Envia por qualquer servidor SMTP (Gmail, Outlook, provedor da empresa).', email)}
      ${chan('telegram', 'Telegram', 'Mensagem instantânea no celular por um bot do Telegram.', tg)}
      ${chan('webhook', 'Webhook', 'Slack, Discord, Microsoft Teams ou qualquer sistema que receba JSON.', wh)}
      <div class="card pad-lg mb16"><div class="card-title" style="margin-bottom:16px">Quando avisar</div>${evs}
        <div class="hint">Avisos repetidos do mesmo problema são agrupados por algumas horas. Envios que falharem são repetidos automaticamente.</div></div>
      <div class="actions mb22" style="gap:12px;flex-wrap:wrap">
        <button class="btn btn-primary btn-lg" data-action="nt-save" ${S.busy.nt ? 'disabled' : ''}>${S.busy.nt ? 'Salvando…' : 'Salvar avisos'}</button>
        <button class="btn btn-soft btn-lg" data-action="nt-test" ${S.busy.ntTest ? 'disabled' : ''}>${S.busy.ntTest ? I.spinner() + 'Enviando…' : I.send + 'Enviar teste'}</button>
      </div>
      ${results}
      <div class="card"><div class="card-head"><span class="card-title">Avisos enviados</span></div>${hist}</div>
    </div>`;
  }
  const EV_DESC = {
    backup_failed: 'Backup automático ou manual não gerou cópia (banco fora do ar, senha, disco…).',
    replica_failed: 'A cópia local ficou pronta, mas o envio a um destino externo falhou.',
    restore_failed: 'Uma restauração foi abortada.',
    verify_failed: 'A verificação encontrou uma cópia corrompida ou alterada.',
    late: 'Nenhuma cópia válida dentro do prazo do agendamento (serviço parado, falhas seguidas).',
    recovered: 'O backup voltou a funcionar depois de uma falha.',
    success: 'Todo backup concluído (pode gerar muitas mensagens).',
  };

  function readNotif() {
    const d = S.notifDraft; if (!d) return;
    document.querySelectorAll('[id^="n-"]').forEach((el) => {
      const [, ch, ...f] = el.id.split('-');
      d[ch][f.join('-')] = el.value;
    });
  }
  function newNotifDraft(cfg) {
    const c = JSON.parse(JSON.stringify(cfg));
    c.email.password = ''; c.telegram.token = '';
    return c;
  }

  // Lê os campos das telas de formulário para o rascunho (sem redesenhar).
  function readConn() {
    const d = S.connDraft; if (!d) return;
    ['host', 'port', 'dbname', 'user', 'password', 'directory'].forEach((k) => {
      const el = document.getElementById('c-' + k); if (el) d[k] = el.value;
    });
    ['host', 'port', 'user', 'password', 'private_key', 'key_passphrase'].forEach((k) => {
      const el = document.getElementById('s-' + k); if (el) d.ssh[k] = el.value;
    });
  }
  function readPolicy() {
    const d = S.policyDraft; if (!d) return;
    const iv = document.getElementById('pol-interval'); if (iv) d.interval_days = +iv.value || 1;
    const r = document.getElementById('pol-retention'); if (r) d.retention_days = +r.value;
    const dir = document.getElementById('pol-dir'); if (dir) d.directory = dir.value;
  }

  // ================================================================= modal
  function confirmModal({ title, html, okLabel, onOk }) {
    modalRoot.innerHTML = `<div class="overlay" data-close="1"><div class="modal" role="dialog" aria-modal="true">
      <div class="ic">${I.warn('#d97706', 24)}</div>
      <h3>${title}</h3><p>${html}</p>
      <div class="foot"><button class="btn btn-ghost" data-close="1">Cancelar</button><button class="btn btn-danger" id="modal-ok">${okLabel}</button></div>
    </div></div>`;
    document.getElementById('modal-ok').addEventListener('click', async () => { modalRoot.innerHTML = ''; await onOk(); });
  }
  modalRoot.addEventListener('click', (e) => { if (e.target.dataset.close) modalRoot.innerHTML = ''; });

  // ================================================================= ações
  const actions = {
    theme() { Theme.toggle(); render(); },
    'toggle-pw'() {
      const u = document.getElementById('lu').value, p = document.getElementById('lp').value;
      S.showPw = !S.showPw; render();
      document.getElementById('lu').value = u; const lp = document.getElementById('lp'); lp.value = p; lp.focus();
    },
    async logout() {
      try { await api('POST', '/api/logout'); } catch (e) { /* ignora */ }
      S.user = null; S.data = null; L.loaded = false; go('login');
    },
    async run() {
      S.busy.run = true; render();
      try {
        await api('POST', '/api/backups');
        toast('Backup manual iniciado…');
        S.busy.run = false;
        await load(); render(); schedulePoll();
      } catch (e) { S.busy.run = false; render(); toast(e.message, true); }
    },
    follow() {
      L.follow = !L.follow;
      document.querySelector('[data-action="follow"]').classList.toggle('on', L.follow);
      if (L.follow) scrollTerm(true);
    },
    async 'copy-logs'() {
      await copyText(termText());
      toast('Logs visíveis copiados');
    },
    async 'copy-sha'() {
      await copyText(S.detail.backup.sha256);
      toast('SHA-256 copiado');
    },
    'pol-daily'() { readPolicy(); S.policyDraft.schedule_mode = 'daily'; render(); },
    'pol-custom'() { readPolicy(); S.policyDraft.schedule_mode = 'custom'; render(); },
    'pol-enc'() { readPolicy(); S.policyDraft.encryption = !S.policyDraft.encryption; render(); },
    'pol-comp'() { readPolicy(); S.policyDraft.compression = !S.policyDraft.compression; render(); },
    async 'pol-save'() {
      readPolicy(); S.busy.pol = true; render();
      try {
        const r = await api('PUT', '/api/policy', S.policyDraft);
        S.policyDraft = Object.assign({}, r.policy); S.data.policy = r.policy;
        toast('Política de backup salva');
      } catch (e) { toast(e.message, true); }
      S.busy.pol = false; render();
    },
    'sgbd-postgres'() { setSgbd('postgres'); },
    'sgbd-mariadb'() { setSgbd('mariadb'); },
    'ssh-on'() { readConn(); S.connDraft.ssh.enabled = true; S.test = { status: 'idle' }; render(); },
    'ssh-off'() { readConn(); S.connDraft.ssh.enabled = false; S.test = { status: 'idle' }; render(); },
    'ssh-auth-password'() { readConn(); S.connDraft.ssh.auth = 'password'; render(); },
    'ssh-auth-key'() { readConn(); S.connDraft.ssh.auth = 'key'; render(); },
    'ssh-reset'() {
      readConn(); S.connDraft.ssh.reset_host_key = true; S.connDraft.ssh.host_key = null; render();
      toast('A chave do servidor será registrada de novo na próxima conexão');
    },
    async 'conn-test'() {
      readConn(); S.test = { status: 'testing' }; render();
      try {
        const r = await api('POST', '/api/connection/test', S.connDraft);
        S.test = r.ok ? { status: 'ok', version: r.version } : { status: 'error', error: r.error };
        if (r.ok && r.ssh_host_key) S.connDraft.ssh.host_key = r.ssh_host_key;
      } catch (e) { S.test = { status: 'error', error: e.message }; }
      render();
    },
    async 'conn-save'() {
      readConn(); S.busy.conn = true; render();
      try {
        const r = await api('PUT', '/api/connection', S.connDraft);
        S.data.connection = r.connection;
        S.connDraft = newConnDraft(r.connection, S.connDraft.directory);
        toast('Configurações de conexão salvas');
        await load();
      } catch (e) { toast(e.message, true); }
      S.busy.conn = false; render();
    },
    restore() {
      const b = S.detail.backup;
      confirmModal({
        title: 'Restaurar backup?',
        html: `Isto substituirá os dados atuais do banco <strong class="mono">${esc(S.data.connection.dbname)}</strong> pela cópia de <strong>${fmtWhen(b.created_at)}</strong>. Antes, o Sentinela gera automaticamente uma cópia do estado atual.`,
        okLabel: 'Restaurar agora',
        async onOk() {
          try {
            await api('POST', `/api/backups/${encodeURIComponent(b.id)}/restore`);
            toast('Restauração iniciada — acompanhe no terminal');
            L.follow = true;
            go('logs');
          } catch (e) { toast(e.message, true); }
        },
      });
    },
    async verify() {
      const b = S.detail.backup;
      S.busy.verify = true; render();
      try {
        const r = await api('POST', `/api/backups/${encodeURIComponent(b.id)}/verify`);
        if (r.ok) toast('Cópia íntegra: hash, criptografia e dump conferem');
        else toast('Cópia inválida: ' + r.error, true);
      } catch (e) { toast(e.message, true); }
      S.busy.verify = false; await load(); render();
    },
    async fetch() {
      try {
        await api('POST', `/api/backups/${encodeURIComponent(S.detail.backup.id)}/fetch`);
        toast('Buscando a cópia num destino externo…'); L.follow = true; go('logs');
      } catch (e) { toast(e.message, true); }
    },

    // ----------------------------------------------------- cópias externas
    'dest-new'() { S.destDraft = newDestDraft('directory'); S.destTest = { status: 'idle' }; render(); window.scrollTo(0, 0); const m = document.querySelector('.main'); if (m) m.scrollTop = 0; },
    'dest-type-directory'() { setDestType('directory'); },
    'dest-type-sftp'() { setDestType('sftp'); },
    'dest-type-s3'() { setDestType('s3'); },
    'dest-auth-password'() { readDest(); S.destDraft.auth = 'password'; render(); },
    'dest-auth-key'() { readDest(); S.destDraft.auth = 'key'; render(); },
    'dest-reset-key'() { readDest(); S.destDraft.reset_host_key = true; S.destDraft.host_key = null; render(); toast('A chave do servidor será registrada de novo na próxima conexão'); },
    'dest-offsite'() { readDest(); S.destDraft.offsite = !S.destDraft.offsite; render(); },
    'dest-cancel'() { S.destDraft = null; S.destTest = { status: 'idle' }; render(); schedulePoll(); },
    'dest-edit'(el) {
      const x = S.dests.destinations.find((d) => d.id === el.dataset.id);
      S.destDraft = newDestDraft(x.type, x); S.destTest = { status: 'idle' }; render();
      const m = document.querySelector('.main'); if (m) m.scrollTop = 0; window.scrollTo(0, 0);
    },
    async 'dest-test'() {
      readDest(); S.destTest = { status: 'testing' }; render();
      try {
        const r = await api('POST', '/api/destinations/test', destPayload());
        S.destTest = r.ok ? { status: 'ok', summary: r.summary } : { status: 'error', error: r.error };
        if (r.ok && r.host_key) S.destDraft.host_key = r.host_key;
      } catch (e) { S.destTest = { status: 'error', error: e.message }; }
      render();
    },
    async 'dest-save'() {
      readDest(); S.busy.dest = true; render();
      try {
        const d = S.destDraft;
        if (d.id) await api('PUT', '/api/destinations/' + encodeURIComponent(d.id), destPayload());
        else await api('POST', '/api/destinations', destPayload());
        toast(d.id ? 'Destino atualizado' : 'Destino adicionado — as cópias serão enviadas a partir do próximo backup');
        S.destDraft = null; S.destTest = { status: 'idle' };
        await load();
      } catch (e) { toast(e.message, true); }
      S.busy.dest = false; render(); schedulePoll();
    },
    async 'dest-toggle'(el) {
      const x = S.dests.destinations.find((d) => d.id === el.dataset.id);
      try {
        await api('PUT', '/api/destinations/' + encodeURIComponent(x.id), { enabled: !x.enabled });
        toast(x.enabled ? 'Destino pausado' : 'Destino ativado'); await load(); render();
      } catch (e) { toast(e.message, true); }
    },
    'dest-remove'(el) {
      const x = S.dests.destinations.find((d) => d.id === el.dataset.id);
      confirmModal({
        title: 'Remover destino?',
        html: `O destino <strong>${esc(x.name)}</strong> deixa de receber cópias. As ${x.copies} cópia(s) já enviadas <strong>continuam lá</strong> — apague-as manualmente se quiser.`,
        okLabel: 'Remover',
        async onOk() {
          try { await api('DELETE', '/api/destinations/' + encodeURIComponent(x.id)); toast('Destino removido'); await load(); render(); } catch (e) { toast(e.message, true); }
        },
      });
    },
    async 'dest-import'(el) {
      const x = S.dests.destinations.find((d) => d.id === el.dataset.id);
      el.disabled = true; el.innerHTML = I.spinner() + 'Procurando…';
      try {
        const r = await api('POST', `/api/destinations/${encodeURIComponent(x.id)}/import`);
        let msg = `${r.found} cópia(s) em ${x.name}; ${r.imported} nova(s) adicionada(s) ao histórico`;
        if (r.missing_keys.length) msg += `. Atenção: ${r.missing_keys.length} chave(s) mestra(s) de outra instalação são necessárias (${r.missing_keys.join(', ')})`;
        toast(msg, r.missing_keys.length > 0);
        await load(); render();
      } catch (e) { toast(e.message, true); render(); }
    },
    async 'dest-sync'() {
      S.busy.sync = true; render();
      try {
        const r = await api('POST', '/api/destinations/sync', {});
        if (r.execution) { toast('Sincronização iniciada — acompanhe no terminal'); L.follow = true; S.busy.sync = false; go('logs'); return; }
        toast('Nada pendente: todas as cópias já estão nos destinos');
      } catch (e) { toast(e.message, true); }
      S.busy.sync = false; await load(); render(); schedulePoll();
    },
    async 'key-export'() {
      const pw = document.getElementById('key-pw').value;
      if (!pw) { toast('Informe sua senha do painel', true); return; }
      S.busy.key = true; render();
      try {
        const r = await fetch('/api/key/export', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: pw }) });
        if (!r.ok) { let b = {}; try { b = await r.json(); } catch (e) { /* */ } throw new Error(b.error || `Erro ${r.status}`); }
        const blob = await r.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = `sentinela-${S.data.key_id}.key`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
        toast('Chave mestra baixada — guarde-a fora do servidor');
        S.data = await api('GET', '/api/state');
      } catch (e) { toast(e.message, true); }
      S.busy.key = false; render();
    },

    // ---------------------------------------------------------------- avisos
    'nt-toggle'(el) { readNotif(); const c = S.notifDraft[el.dataset.ch]; c.enabled = !c.enabled; render(); },
    'nt-event'(el) { readNotif(); const ev = S.notifDraft.events; ev[el.dataset.ev] = !ev[el.dataset.ev]; render(); },
    'nt-sec-starttls'() { setSec('starttls', '587'); },
    'nt-sec-ssl'() { setSec('ssl', '465'); },
    'nt-sec-none'() { setSec('none', '25'); },
    'nt-fmt-generic'() { readNotif(); S.notifDraft.webhook.format = 'generic'; render(); },
    'nt-fmt-slack'() { readNotif(); S.notifDraft.webhook.format = 'slack'; render(); },
    'nt-fmt-discord'() { readNotif(); S.notifDraft.webhook.format = 'discord'; render(); },
    'nt-fmt-teams'() { readNotif(); S.notifDraft.webhook.format = 'teams'; render(); },
    async 'nt-save'() {
      readNotif(); S.busy.nt = true; render();
      try {
        const r = await api('PUT', '/api/notifications', S.notifDraft);
        S.notif.config = r.config; S.notifDraft = newNotifDraft(r.config);
        toast(r.config.active.length ? 'Avisos salvos' : 'Avisos salvos — nenhum canal ativo');
        S.data = await api('GET', '/api/state');
      } catch (e) { toast(e.message, true); }
      S.busy.nt = false; render();
    },
    async 'nt-test'() {
      readNotif(); S.busy.ntTest = true; S.notifTest = null; render();
      try {
        const r = await api('POST', '/api/notifications/test', S.notifDraft);
        S.notifTest = r.results;
      } catch (e) { toast(e.message, true); }
      S.busy.ntTest = false; render();
    },

    delete() {
      const b = S.detail.backup;
      confirmModal({
        title: 'Excluir cópia?',
        html: `O arquivo da cópia <strong class="mono">${esc(b.id)}</strong> será apagado do diretório de backup. Esta ação não pode ser desfeita.`,
        okLabel: 'Excluir',
        async onOk() {
          try {
            await api('DELETE', `/api/backups/${encodeURIComponent(b.id)}`);
            toast('Cópia excluída'); go('history');
          } catch (e) { toast(e.message, true); }
        },
      });
    },
  };

  function newConnDraft(conn, directory) {
    const ssh = Object.assign({ password: '', private_key: '', key_passphrase: '' }, conn.ssh || {});
    return Object.assign({}, conn, { password: '', directory, ssh });
  }

  function setDestType(t) {
    readDest();
    const name = S.destDraft.name;
    S.destDraft = newDestDraft(t, { name }); S.destTest = { status: 'idle' }; render();
  }
  function destPayload() {
    const d = S.destDraft;
    const out = {};
    Object.keys(d).forEach((k) => { if (!k.startsWith('has_') && !['host_key', 'last', 'target', 'type_label', 'copies', 'bytes', 'missing', 'pending_deletes', 'same_device', 'created_at'].includes(k)) out[k] = d[k]; });
    return out;
  }
  function setSec(sec, port) {
    readNotif();
    const e = S.notifDraft.email;
    if (!e.port || ['587', '465', '25'].includes(String(e.port))) e.port = port;
    e.security = sec; render();
  }

  function setSgbd(s) {
    readConn();
    const d = S.connDraft;
    const defaults = { postgres: '5432', mariadb: '3306' };
    if (!d.port || d.port === defaults[d.sgbd]) d.port = defaults[s];
    d.sgbd = s; S.test = { status: 'idle' }; render();
  }

  // =============================================================== eventos
  app.addEventListener('click', (e) => {
    const a = e.target.closest('[data-action]');
    if (a && !a.disabled) { e.preventDefault(); actions[a.dataset.action](a); return; }
    const chip = e.target.closest('[data-chip]');
    if (chip) {
      const [group, v] = chip.dataset.chip.split(':');
      L[group] = v; L.fresh = new Set();
      chip.parentElement.querySelectorAll('[data-chip]').forEach((c) => c.classList.toggle('on', c === chip));
      updateTerm(); return;
    }
    const grp = e.target.closest('[data-grp]');
    if (grp) {
      if (e.target.closest('a')) return;
      const id = +grp.dataset.grp;
      if (L.collapsed.has(id)) L.collapsed.delete(id); else L.collapsed.add(id);
      grp.classList.toggle('closed');
      grp.nextElementSibling.classList.toggle('hidden');
      return;
    }
    const o = e.target.closest('[data-open]');
    if (o) { if (e.target.closest('a')) return; go('detail', o.dataset.open); return; }
    const f = e.target.closest('[data-filter]');
    if (f) { S.filter = f.dataset.filter; render(); }
  });
  app.addEventListener('input', (e) => {
    if (e.target.id === 'pol-retention') document.getElementById('ret-val').textContent = e.target.value;
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') modalRoot.innerHTML = '';
    if (e.key === '/' && S.route === 'logs' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
      e.preventDefault(); document.getElementById('log-q').focus();
    }
  });
  window.addEventListener('hashchange', onRoute);
  if (window.matchMedia) {
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (!Theme.saved()) { Theme.apply(); render(); } });
  }

  // ================================================================ início
  (async function boot() {
    try { const r = await api('GET', '/api/me'); S.user = r.user; } catch (e) { S.user = null; }
    onRoute();
  })();
})();
