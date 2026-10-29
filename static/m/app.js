/* IT support — staff mobile app (/admin/m/). Plain JavaScript, no build step.
   Screens: ticket views (with counts) · ticket (conversation, reply / internal note, status, priority, assignee)
   · overview · activity · account. Same session and permissions as the admin panel. */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const app = $('#app');
  const Cap = window.Capacitor;
  const native = !!(Cap && Cap.isNativePlatform && Cap.isNativePlatform());
  const plugin = (n) => (Cap && Cap.Plugins && Cap.Plugins[n]) || null;
  const store = {
    get(k, d) { try { const v = localStorage.getItem('tktm.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('tktm.' + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };

  // ── language ─────────────────────────────────────────────────────────
  let LANG = store.get('lang', window.TKT_LANG || 'ar');
  const T = {
    ar: {
      app: 'الدعم الفني', appSub: 'تطبيق فريق الدعم', signin: 'تسجيل الدخول', user: 'اسم المستخدم', pass: 'كلمة المرور',
      invalid: 'اسم المستخدم أو كلمة المرور غير صحيحة', tooMany: 'محاولات كثيرة — انتظر 15 دقيقة', other: 'English',
      tickets: 'التذاكر', overview: 'نظرة عامة', activity: 'النشاط', account: 'حسابي', search: 'ابحث بالرقم أو الموضوع أو الاسم',
      v_mine: 'تذاكري', v_unassigned: 'غير معيّنة', v_open: 'مفتوحة', v_in_progress: 'قيد المعالجة', v_waiting: 'معلّقة',
      v_closed: 'مغلقة', v_all: 'الكل',
      s_open: 'مفتوحة', s_in_progress: 'قيد المعالجة', s_waiting: 'معلّقة', s_closed: 'مغلقة',
      p_high: 'عالية', p_medium: 'متوسطة', p_low: 'منخفضة',
      empty: 'لا توجد تذاكر هنا', emptyAct: 'لا يوجد نشاط بعد', pull: 'اسحب للتحديث', release: 'أفلت للتحديث', loading: 'جارٍ التحديث…',
      status: 'الحالة', priority: 'الأولوية', assignee: 'المسؤول', requester: 'مقدّم الطلب', category: 'التصنيف', location: 'الموقع',
      unassigned: 'غير معيّن', nobody: 'إلغاء التعيين', desc: 'وصف المشكلة', files: 'المرفقات',
      reply: 'رد على المعلم', note: 'ملاحظة داخلية', replyPh: 'اكتب ردك… يصل إلى المعلم بالبريد', notePh: 'ملاحظة للفريق فقط — لا يراها المعلم',
      close: 'إغلاق', closeT: 'إغلاق التذكرة', closePh: 'رسالة ختامية للمعلم (اختياري)', reopen: 'إعادة فتح', wait: 'تعليق', resume: 'استئناف',
      cancel: 'إلغاء', confirm: 'تأكيد', sent: 'أُرسل', saved: 'تم الحفظ', failed: 'تعذّر الحفظ — حاول مرة أخرى', forbidden: 'لا تملك صلاحية لهذا الإجراء',
      offline: 'لا يوجد اتصال — تُعرض آخر نسخة محفوظة', ago: 'منذ', now: 'الآن', min: 'د', hour: 'س', day: 'ي',
      k_unassigned: 'غير معيّنة', k_mine: 'تذاكري المفتوحة', k_open: 'مفتوحة', k_waiting: 'معلّقة', k_progress: 'قيد المعالجة', k_closed: 'مغلقة',
      highOpen: 'عالية الأولوية مفتوحة', lang: 'اللغة', notif: 'الإشعارات', notifOn: 'مفعّلة', notifOff: 'تفعيل الإشعارات', web: 'فتح لوحة التحكم الكاملة',
      logout: 'تسجيل الخروج', role: 'الدور', newT: 'تذكرة جديدة', assignedT: 'عُيّنت لك تذكرة', replyT: 'رد جديد', noteT: 'ملاحظة داخلية جديدة',
      teacher: 'المعلم', you: 'أنت', back: 'رجوع', refresh: 'تحديث', internal: 'داخلية', replies: 'ردود',
    },
    en: {
      app: 'IT Support', appSub: 'Support team app', signin: 'Sign in', user: 'Username', pass: 'Password',
      invalid: 'Incorrect username or password', tooMany: 'Too many attempts — wait 15 minutes', other: 'العربية',
      tickets: 'Tickets', overview: 'Overview', activity: 'Activity', account: 'Account', search: 'Search number, subject or name',
      v_mine: 'My tickets', v_unassigned: 'Unassigned', v_open: 'Open', v_in_progress: 'In progress', v_waiting: 'Waiting',
      v_closed: 'Closed', v_all: 'All',
      s_open: 'Open', s_in_progress: 'In progress', s_waiting: 'Waiting', s_closed: 'Closed',
      p_high: 'High', p_medium: 'Medium', p_low: 'Low',
      empty: 'No tickets here', emptyAct: 'No activity yet', pull: 'Pull to refresh', release: 'Release to refresh', loading: 'Refreshing…',
      status: 'Status', priority: 'Priority', assignee: 'Assignee', requester: 'Requester', category: 'Category', location: 'Location',
      unassigned: 'Unassigned', nobody: 'Unassign', desc: 'Problem description', files: 'Attachments',
      reply: 'Reply to teacher', note: 'Internal note', replyPh: 'Write your reply… emailed to the teacher', notePh: 'Team-only note — the teacher does not see it',
      close: 'Close', closeT: 'Close the ticket', closePh: 'Closing message to the teacher (optional)', reopen: 'Reopen', wait: 'Hold', resume: 'Resume',
      cancel: 'Cancel', confirm: 'Confirm', sent: 'Sent', saved: 'Saved', failed: 'Could not save — try again', forbidden: 'You do not have permission for this',
      offline: 'Offline — showing the last saved copy', ago: '', now: 'now', min: 'm', hour: 'h', day: 'd',
      k_unassigned: 'Unassigned', k_mine: 'My open tickets', k_open: 'Open', k_waiting: 'Waiting', k_progress: 'In progress', k_closed: 'Closed',
      highOpen: 'High priority, not closed', lang: 'Language', notif: 'Notifications', notifOn: 'On', notifOff: 'Turn on notifications', web: 'Open the full admin panel',
      logout: 'Sign out', role: 'Role', newT: 'New ticket', assignedT: 'Ticket assigned to you', replyT: 'New reply', noteT: 'New internal note',
      teacher: 'Teacher', you: 'You', back: 'Back', refresh: 'Refresh', internal: 'internal', replies: 'replies',
    },
  };
  const t = (k) => (T[LANG] && T[LANG][k]) || T.ar[k] || k;
  function applyLang() {
    document.documentElement.lang = LANG;
    document.documentElement.dir = LANG === 'ar' ? 'rtl' : 'ltr';
  }

  // ── icons (inline SVG, no download) ──────────────────────────────────
  const P = {
    back: '<path d="M15 18l-6-6 6-6"/>', search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    x: '<path d="M18 6L6 18M6 6l12 12"/>', inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z"/>',
    chart: '<path d="M3 3v18h18"/><path d="M8 17V11M13 17V7M18 17v-4"/>', bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>', send: '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/>',
    chev: '<path d="M9 18l6-6-6-6"/>', check: '<path d="M20 6L9 17l-5-5"/>', flag: '<path d="M4 22V4"/><path d="M4 4h12l-2 4 2 4H4"/>',
    clip: '<path d="M21 12l-9 9a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8"/>', lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    pin: '<path d="M12 22s7-6.5 7-12a7 7 0 0 0-14 0c0 5.5 7 12 7 12z"/><circle cx="12" cy="10" r="2.5"/>', reply: '<path d="M9 17l-5-5 5-5"/><path d="M4 12h11a5 5 0 0 1 5 5v2"/>',
    pause: '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>', play: '<path d="M7 4l13 8-13 8z"/>',
    done: '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>', undo: '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-15-6.7L3 13"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>', out: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>',
    web: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/>', refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
    tag: '<path d="M20 12l-8 8-9-9V3h8z"/><circle cx="7.5" cy="7.5" r="1.5"/>', chat: '<path d="M21 12a8 8 0 0 1-11.5 7.2L3 21l1.8-6.5A8 8 0 1 1 21 12z"/>',
  };
  const ic = (n, cls) => `<svg class="${cls || ''}" viewBox="0 0 24 24" aria-hidden="true">${P[n] || ''}</svg>`;

  // ── helpers ──────────────────────────────────────────────────────────
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const COLORS = ['#0C67EC', '#7c3aed', '#0f9d58', '#e8710a', '#c2185b', '#00897b', '#5c6bc0', '#8d6e63'];
  const avColor = (s) => { let h = 0; for (const c of String(s || '?')) h = (h * 31 + c.charCodeAt(0)) >>> 0; return COLORS[h % COLORS.length]; };
  const initials = (s) => { const p = String(s || '?').trim().split(/\s+/); return ((p[0] || '?')[0] + (p[1] ? p[1][0] : '')).toUpperCase(); };
  const av = (name, cls = 'av') => `<span class="${cls}" style="background:${avColor(name)}" aria-hidden="true">${esc(initials(name))}</span>`;
  const utc = (iso) => (iso ? new Date(/Z|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z') : null);
  function ago(iso) {
    const d = utc(iso); if (!d) return '';
    const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (s < 60) return t('now');
    const [n, u] = s < 3600 ? [Math.floor(s / 60), 'minute'] : s < 86400 ? [Math.floor(s / 3600), 'hour'] : s < 7 * 86400 ? [Math.floor(s / 86400), 'day'] : [null];
    if (n == null) return fullTime(iso).slice(0, 10);
    try { return new Intl.RelativeTimeFormat(LANG, { numeric: 'auto', style: 'short' }).format(-n, u); }
    catch (e) { return LANG === 'ar' ? `${t('ago')} ${n} ${t({ minute: 'min', hour: 'hour', day: 'day' }[u])}` : `${n}${t({ minute: 'min', hour: 'hour', day: 'day' }[u])}`; }
  }
  const fullTime = (iso) => { const d = utc(iso); if (!d) return ''; const p = (x) => String(x).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`; };
  const statusPill = (s) => `<span class="pill" style="--sc:var(--${s})">${esc(t('s_' + s))}</span>`;
  function toast(msg, err) {
    const el = $('#toast'); el.textContent = msg; el.className = 'toast' + (err ? ' err' : ''); el.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(() => { el.hidden = true; }, 2600);
  }
  function haptic() { try { const h = plugin('Haptics'); if (h) h.impact({ style: 'LIGHT' }); else if (navigator.vibrate) navigator.vibrate(8); } catch (e) { /* ignore */ } }

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      method: opts.method || 'GET', credentials: 'same-origin',
      headers: opts.body ? { 'Content-Type': 'application/json', Accept: 'application/json' } : { Accept: 'application/json' },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    const type = res.headers.get('content-type') || '';
    if (res.status === 401 || (res.redirected && /login/.test(res.url)) || (!type.includes('json') && res.ok)) {
      const e = new Error('auth'); e.auth = true; throw e;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { const e = new Error(data.error || 'http ' + res.status); e.status = res.status; e.data = data; throw e; }
    return data;
  }

  // ── state ────────────────────────────────────────────────────────────
  const S = {
    me: store.get('me', null), view: store.get('view', null), q: '', list: null, counts: {}, ticket: null,
    mode: 'reply', unread: store.get('unread', 0), since: store.get('since', null), offline: !navigator.onLine,
  };

  // ── routing (#/tickets, #/t/12, #/overview, #/activity, #/account) ──
  function go(hash) { if (location.hash !== hash) location.hash = hash; else route(); }
  window.addEventListener('hashchange', route);
  function route() {
    closeSheet();
    if (!S.me) return renderLogin();
    const h = location.hash || '#/tickets';
    const m = h.match(/^#\/t\/(\d+)/);
    if (m) return openTicket(+m[1]);
    if (h.startsWith('#/overview')) return renderOverview();
    if (h.startsWith('#/activity')) return renderActivity();
    if (h.startsWith('#/account')) return renderAccount();
    return renderList();
  }

  function shell(title, body, opts = {}) {
    const tab = opts.tab || '';
    app.innerHTML = `
      <header class="appbar"><div class="row">
        ${opts.back ? `<button class="ibtn" data-act="back" aria-label="${t('back')}">${ic('back', 'flip')}</button>` : ''}
        <h1>${title}${opts.sub ? `<span class="sub">${opts.sub}</span>` : ''}</h1>
        ${opts.right || ''}
      </div>${opts.below || ''}</header>
      ${S.offline ? `<div class="offline">${t('offline')}</div>` : ''}
      ${opts.views || ''}
      <main id="main">${body}</main>
      ${opts.composer || ''}
      ${opts.noNav ? '' : `<nav class="nav" aria-label="${t('app')}">
        ${navBtn('tickets', 'inbox', '#/tickets', tab)}${navBtn('overview', 'chart', '#/overview', tab)}
        ${navBtn('activity', 'bell', '#/activity', tab, S.unread)}${navBtn('account', 'user', '#/account', tab)}</nav>`}`;
    const b = app.querySelector('[data-act=back]');
    if (b) b.onclick = () => (history.length > 1 ? history.back() : go('#/tickets'));
    app.querySelectorAll('.nav button').forEach((x) => { x.onclick = () => { haptic(); go(x.dataset.go); }; });
  }
  const navBtn = (k, i, h, tab, badge) => `<button class="${tab === k ? 'on' : ''}" data-go="${h}" aria-current="${tab === k ? 'page' : 'false'}">
      ${ic(i)}<span>${t(k)}</span>${badge ? `<span class="badge">${badge > 99 ? '99+' : badge}</span>` : ''}</button>`;

  // ── sign in ──────────────────────────────────────────────────────────
  function renderLogin(err) {
    app.innerHTML = `<div class="login"><div class="card">
      <img class="logo" src="/static/icon-192.png" alt="">
      <h1>${t('app')}</h1><p class="s">${t('appSub')}</p>
      ${err ? `<div class="err">${esc(err)}</div>` : ''}
      <form id="lf" autocomplete="on">
        <div class="field"><label for="lu">${t('user')}</label><div class="inp">${ic('user')}<input id="lu" name="username" autocomplete="username" autocapitalize="none" dir="ltr" required></div></div>
        <div class="field"><label for="lp">${t('pass')}</label><div class="inp">${ic('lock')}<input id="lp" name="password" type="password" autocomplete="current-password" dir="ltr" required></div></div>
        <button class="btn pri" type="submit">${t('signin')}</button>
      </form></div>
      <button class="lang" id="ll">${ic('globe')} ${t('other')}</button></div>`;
    $('#ll').onclick = () => { LANG = LANG === 'ar' ? 'en' : 'ar'; store.set('lang', LANG); applyLang(); renderLogin(); };
    $('#lf').onsubmit = async (e) => {
      e.preventDefault();
      const btn = e.target.querySelector('button'); btn.disabled = true;
      try {
        S.me = await api('/admin/m/api/login', { method: 'POST', body: { username: $('#lu').value.trim(), password: $('#lp').value, lang: LANG } });
        store.set('me', S.me); S.view = S.view || (S.me.isTech ? 'mine' : 'unassigned');
        S.since = new Date().toISOString(); store.set('since', S.since);
        askNotify(); go('#/tickets');
      } catch (er) { renderLogin(er.status === 429 ? t('tooMany') : t('invalid')); }
    };
  }

  // ── ticket list ──────────────────────────────────────────────────────
  const VIEWS = ['mine', 'unassigned', 'open', 'in_progress', 'waiting', 'closed', 'all'];
  function viewsBar() {
    const vs = S.me && S.me.isTech ? VIEWS.filter((v) => v !== 'unassigned') : VIEWS;
    return `<div class="views" role="tablist">${vs.map((v) => `<button class="chip ${S.view === v ? 'on' : ''}" role="tab" aria-selected="${S.view === v}" data-v="${v}">
      ${esc(t('v_' + v))}<b>${S.counts[v] == null ? '·' : S.counts[v]}</b></button>`).join('')}</div>`;
  }
  function card(x) {
    const pc = `var(--${x.priority})`;
    const last = x.last ? `${x.last.internal ? ic('lock') + ' ' : ''}${esc(x.last.author ? x.last.author + ': ' : '')}${esc(x.last.body)}` : esc([x.category, x.categoryItem].filter(Boolean).join(' / '));
    return `<button class="tk" data-id="${x.id}" style="--pc:${pc}">
      ${av(x.teacherName)}
      <div class="body">
        <div class="l1"><span class="who">${esc(x.teacherName)}</span><span class="mono">#${x.serial}</span><time>${esc(ago(x.activityAt))}</time></div>
        <h3>${esc(x.subject)}</h3>
        <div class="snip">${last}</div>
        <div class="l3">${statusPill(x.status)}
          ${x.priority === 'high' ? `<span class="tag hi">${ic('flag')}${t('p_high')}</span>` : ''}
          ${x.assigneeName ? `<span class="tag">${ic('user')}${esc(x.assigneeName)}</span>` : `<span class="tag">${t('unassigned')}</span>`}
          ${x.replies ? `<span class="tag">${ic('chat')}${x.replies}</span>` : ''}
          ${x.attachments ? `<span class="tag">${ic('clip')}${x.attachments}</span>` : ''}
          ${x.location ? `<span class="tag">${ic('pin')}${esc(x.location)}</span>` : ''}
        </div>
      </div></button>`;
  }
  function renderList() {
    if (!S.view) S.view = S.me.isTech ? 'mine' : 'unassigned';
    const cached = store.get('list.' + S.view, null);
    if (!S.list && cached) { S.list = cached.tickets; S.counts = cached.counts || {}; }
    const searchOpen = !!S.searchOpen;
    shell(t('tickets'), `<div class="ptr" id="ptr"></div><div class="list" id="list">${listHtml()}</div>`, {
      tab: 'tickets', views: viewsBar(),
      right: `<button class="ibtn" data-act="search" aria-label="${t('search')}">${ic(searchOpen ? 'x' : 'search')}</button>
              <button class="ibtn" data-act="refresh" aria-label="${t('refresh')}">${ic('refresh')}</button>`,
      below: searchOpen ? `<label class="search">${ic('search')}<input id="q" type="search" value="${esc(S.q)}" placeholder="${t('search')}" enterkeyhint="search"></label>` : '',
    });
    app.querySelectorAll('.chip').forEach((c) => { c.onclick = () => { haptic(); S.view = c.dataset.v; store.set('view', S.view); S.list = null; renderList(); }; });
    app.querySelector('[data-act=search]').onclick = () => { S.searchOpen = !searchOpen; if (!S.searchOpen && S.q) { S.q = ''; S.list = null; } renderList(); if (S.searchOpen) $('#q').focus(); };
    app.querySelector('[data-act=refresh]').onclick = () => loadList(true);
    const q = $('#q');
    if (q) q.oninput = () => { clearTimeout(q._t); q._t = setTimeout(() => { S.q = q.value.trim(); loadList(); }, 280); };
    bindList(); pullToRefresh();
    loadList();
  }
  function listHtml() {
    if (!S.list) return '<div class="skel"></div><div class="skel"></div><div class="skel"></div><div class="skel"></div>';
    if (!S.list.length) return `<div class="empty">${ic('inbox')}<div>${t('empty')}</div></div>`;
    return S.list.map(card).join('');
  }
  function bindList() {
    app.querySelectorAll('.tk').forEach((b) => { b.onclick = () => { haptic(); go('#/t/' + b.dataset.id); }; });
  }
  async function loadList(spin) {
    const view = S.view;
    try {
      if (spin) toast(t('loading'));
      const d = await api(`/admin/m/api/tickets?view=${encodeURIComponent(view)}&q=${encodeURIComponent(S.q || '')}`);
      if (view !== S.view || !/^#\/tickets|^$/.test(location.hash || '')) return;
      S.list = d.tickets; S.counts = d.counts; S.offline = false;
      if (!S.q) store.set('list.' + view, { tickets: d.tickets, counts: d.counts });
      const list = $('#list'); if (list) { list.innerHTML = listHtml(); bindList(); }
      const vb = app.querySelector('.views'); if (vb) { vb.outerHTML = viewsBar(); app.querySelectorAll('.chip').forEach((c) => { c.onclick = () => { haptic(); S.view = c.dataset.v; store.set('view', S.view); S.list = null; renderList(); }; }); }
      if (spin) $('#toast').hidden = true;
    } catch (e) { onError(e); }
  }
  function pullToRefresh() {
    const ptr = $('#ptr'); let y0 = null, dy = 0;
    window.ontouchstart = (e) => { y0 = window.scrollY <= 0 ? e.touches[0].clientY : null; dy = 0; };
    window.ontouchmove = (e) => {
      if (y0 == null || !ptr) return; dy = Math.max(0, e.touches[0].clientY - y0);
      const h = Math.min(70, dy / 2.2); ptr.style.height = h + 'px';
      ptr.innerHTML = `${ic('refresh')} ${h > 50 ? t('release') : t('pull')}`;
    };
    window.ontouchend = async () => {
      if (y0 == null || !ptr) return; const go_ = dy / 2.2 > 50; y0 = null;
      if (go_) { ptr.innerHTML = `${ic('refresh', 'spin')} ${t('loading')}`; haptic(); await (location.hash.startsWith('#/activity') ? loadActivity() : loadList()); }
      ptr.style.height = '0px';
    };
  }

  // ── ticket ───────────────────────────────────────────────────────────
  async function openTicket(id) {
    const lite = (S.list || []).find((x) => x.id === id);
    if (!S.ticket || S.ticket.id !== id) S.ticket = lite ? Object.assign({ comments: null }, lite, { serial: lite.serial }) : null;
    renderTicket();
    try {
      S.ticket = await api('/admin/m/api/tickets/' + id);
      if (location.hash === '#/t/' + id) renderTicket();
    } catch (e) { onError(e); }
  }
  function renderTicket() {
    const x = S.ticket;
    if (!x) { shell('…', '<div class="list"><div class="skel"></div><div class="skel"></div></div>', { back: true, noNav: true }); return; }
    const can = x.can || {};
    const prio = x.priority || 'medium';
    const props = `<div class="props">
      ${propRow('status', t('status'), statusPill(x.status), can.manage)}
      ${propRow('priority', t('priority'), `<span class="tag ${prio === 'high' ? 'hi' : ''}" style="color:var(--${prio})">${ic('flag')}${t('p_' + prio)}</span>`, can.priority)}
      ${propRow('assignee', t('assignee'), x.assigneeName ? `${av(x.assigneeName, 'mini')}${esc(x.assigneeName)}` : `<span style="color:var(--muted)">${t('unassigned')}</span>`, can.assign)}
      ${propRow('', t('requester'), `${esc(x.teacherName)}${x.teacherPhone ? ` · <a class="mono" href="tel:${esc(x.teacherPhone)}">${esc(x.teacherPhone)}</a>` : ''}`, false)}
      ${x.category ? propRow('', t('category'), esc([x.category, x.categoryItem].filter(Boolean).join(' / ')), false) : ''}
      ${x.location ? propRow('', t('location'), esc(x.location), false) : ''}
    </div>`;
    const files = (x.attachments || []).length ? `<div class="files">${x.attachments.map((u, i) => `<a href="${esc(u)}" target="_blank" rel="noopener">${ic('clip')}${t('files')} ${i + 1}</a>`).join('')}</div>` : '';
    const desc = x.description || files ? `<div class="desc"><div class="h">${t('desc')}</div><p>${esc(x.description)}</p>${files}</div>` : '';
    const acts = can.manage ? `<div class="actions" style="margin:10px 0 0">
      ${x.status !== 'closed' ? `<button class="act ok" data-a="close">${ic('done')}${t('close')}</button>` : `<button class="act pri" data-a="reopen">${ic('undo')}${t('reopen')}</button>`}
      ${x.status === 'waiting' ? `<button class="act" data-a="resume">${ic('play')}${t('resume')}</button>` : x.status !== 'closed' ? `<button class="act warn" data-a="wait">${ic('pause')}${t('wait')}</button>` : ''}
    </div>` : '';
    const thread = x.comments == null ? '<div class="skel"></div>' : x.comments.map(msg).join('');
    const composer = can.manage ? `<div class="composer ${S.mode === 'note' ? 'note' : ''}" id="composer">
      <div class="seg" role="tablist">
        <button class="${S.mode === 'reply' ? 'on' : ''}" data-m="reply" role="tab">${ic('reply')} ${t('reply')}</button>
        <button class="n ${S.mode === 'note' ? 'on' : ''}" data-m="note" role="tab">${ic('lock')} ${t('note')}</button></div>
      <div class="comp"><textarea id="txt" rows="1" placeholder="${S.mode === 'note' ? t('notePh') : t('replyPh')}" aria-label="${S.mode === 'note' ? t('note') : t('reply')}">${esc(S.draft && S.draft.id === x.id ? S.draft.text : '')}</textarea>
      <button class="send" id="send" aria-label="${t('sent')}" disabled>${ic('send')}</button></div></div>` : '';
    shell(`<span class="mono">#${x.serial}</span>`, `
      <div class="hd"><h2>${esc(x.subject)}</h2><div class="meta">${esc(x.teacherName)} · ${esc(fullTime(x.createdAt))}</div></div>
      ${props}${desc}${acts}<div class="thread" id="thread">${thread}</div>
      <div style="height:${can.manage ? 130 : 20}px"></div>`, {
      back: true, noNav: true, composer,
      sub: esc(t('s_' + x.status)),
      right: `<button class="ibtn" data-act="refresh" aria-label="${t('refresh')}">${ic('refresh')}</button>`,
    });
    app.querySelector('[data-act=refresh]').onclick = () => openTicket(x.id);
    app.querySelectorAll('.prop[data-p]').forEach((p) => { p.onclick = () => { if (!p.disabled) pickProp(p.dataset.p); }; });
    app.querySelectorAll('[data-a]').forEach((b) => { b.onclick = () => action(b.dataset.a); });
    const ta = $('#txt'), send = $('#send');
    if (ta) {
      const fit = () => { ta.style.height = 'auto'; ta.style.height = Math.min(140, ta.scrollHeight) + 'px'; send.disabled = !ta.value.trim(); S.draft = { id: x.id, text: ta.value }; };
      ta.oninput = fit; fit();
      send.onclick = () => postComment(ta.value.trim());
      app.querySelectorAll('.seg button').forEach((b) => { b.onclick = () => { S.mode = b.dataset.m; haptic(); renderTicket(); $('#txt').focus(); }; });
    }
  }
  const propRow = (k, label, value, enabled) => `<button class="prop" ${k ? `data-p="${k}"` : ''} ${enabled && k ? '' : 'disabled'}>
      <span class="k">${label}</span><span class="v">${value}</span>${enabled && k ? `<span class="chev">${ic('chev', 'flip')}</span>` : ''}</button>`;
  function msg(c) {
    if (c.authorRole === 'system') return `<div class="sys">${esc(c.body)} · ${esc(ago(c.createdAt))}</div>`;
    const mine = c.authorRole === 'staff';
    const name = c.authorName || (mine ? '' : S.ticket.teacherName);
    return `<div class="msg ${mine ? 'me' : ''} ${c.internal ? 'note' : ''}">
      ${mine ? '' : av(name)}
      <div class="bub"><div class="h"><b>${c.internal ? ic('lock') + ' ' : ''}${esc(name || t('you'))}</b><time title="${esc(fullTime(c.createdAt))}">${esc(ago(c.createdAt))}</time></div>${esc(c.body)}</div></div>`;
  }
  async function postComment(body) {
    if (!body) return;
    const x = S.ticket, internal = S.mode === 'note';
    const temp = { authorRole: 'staff', authorName: S.me.fullName, body, internal, createdAt: new Date().toISOString() };
    x.comments = (x.comments || []).concat([temp]); S.draft = null; renderTicket(); scrollEnd(); haptic();
    try {
      const d = await api(`/admin/api/tickets/${x.id}/comment`, { method: 'POST', body: { body, internal } });
      S.ticket = Object.assign(d, { can: x.can, staff: x.staff }); renderTicket(); scrollEnd(); toast(t('sent'));
      S.list = null;
    } catch (e) { x.comments.pop(); S.draft = { id: x.id, text: body }; renderTicket(); onError(e); }
  }
  const scrollEnd = () => window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });

  async function call(path, body) {
    const x = S.ticket;
    try {
      const d = await api(path, { method: 'POST', body: body || {} });
      S.ticket = Object.assign(d, { can: x.can, staff: x.staff }); S.list = null; renderTicket(); toast(t('saved')); haptic();
    } catch (e) { onError(e); }
  }
  function action(a) {
    const id = S.ticket.id;
    if (a === 'close') {
      return sheet(`<h4>${t('closeT')}</h4><textarea id="cn" placeholder="${t('closePh')}"></textarea>
        <div class="btns"><button class="btn" data-x>${t('cancel')}</button><button class="btn pri" id="cok">${t('close')}</button></div>`, (el) => {
        el.querySelector('#cok').onclick = () => { const note = el.querySelector('#cn').value.trim(); closeSheet(); call(`/admin/api/tickets/${id}/close`, { comment: note }); };
      });
    }
    const map = { reopen: 'reopen', wait: 'wait', resume: 'resume' };
    if (map[a]) call(`/admin/api/tickets/${id}/${map[a]}`);
  }
  function pickProp(p) {
    const x = S.ticket, id = x.id;
    if (p === 'status') {
      const opts = [];
      if (x.status === 'closed') opts.push(['reopen', 'open', t('reopen')]);
      else {
        if (x.status === 'waiting') opts.push(['resume', x.assigneeId ? 'in_progress' : 'open', t('resume')]);
        else opts.push(['wait', 'waiting', t('s_waiting')]);
        opts.push(['close', 'closed', t('s_closed')]);
      }
      return sheet(`<h4>${t('status')}</h4>${opts.map(([a, s, l]) => `<button class="opt" data-o="${a}"><span class="sw" style="--sc:var(--${s})"></span>${esc(l)}</button>`).join('')}`, (el) => {
        el.querySelectorAll('[data-o]').forEach((b) => { b.onclick = () => { closeSheet(); action(b.dataset.o); }; });
      });
    }
    if (p === 'priority') {
      return sheet(`<h4>${t('priority')}</h4>${['high', 'medium', 'low'].map((k) => `<button class="opt" data-o="${k}"><span class="sw" style="--sc:var(--${k})"></span>${t('p_' + k)}${x.priority === k ? `<span class="ck">${ic('check')}</span>` : ''}</button>`).join('')}`, (el) => {
        el.querySelectorAll('[data-o]').forEach((b) => { b.onclick = () => { closeSheet(); call(`/admin/api/tickets/${id}/priority`, { priority: b.dataset.o }); }; });
      });
    }
    if (p === 'assignee') {
      const staff = x.staff || [];
      return sheet(`<h4>${t('assignee')}</h4>${staff.map((s) => `<button class="opt" data-o="${s.id}">${av(s.name)}<span>${esc(s.name)}</span>${x.assigneeId === s.id ? `<span class="ck">${ic('check')}</span>` : ''}</button>`).join('')}
        ${x.assigneeId ? `<button class="opt" data-o="">${ic('x')}<span>${t('nobody')}</span></button>` : ''}`, (el) => {
        el.querySelectorAll('[data-o]').forEach((b) => { b.onclick = () => { closeSheet(); call(`/admin/api/tickets/${id}/assign`, { assigneeId: b.dataset.o ? +b.dataset.o : null }); }; });
      });
    }
  }
  function sheet(inner, bind) {
    const el = $('#sheet');
    el.innerHTML = `<div class="panel"><div class="grab"></div>${inner}</div>`; el.hidden = false;
    el.onclick = (e) => { if (e.target === el || e.target.hasAttribute('data-x')) closeSheet(); };
    if (bind) bind(el);
  }
  function closeSheet() { const el = $('#sheet'); if (el) { el.hidden = true; el.innerHTML = ''; } }

  // ── overview ─────────────────────────────────────────────────────────
  async function renderOverview() {
    const c = S.counts || {};
    const kpi = (v, label, col, n) => `<button class="kpi" data-v="${v}" style="--sc:${col}"><div class="n">${n == null ? '·' : n}</div><div class="l">${label}</div></button>`;
    const draw = (high) => {
      shell(t('overview'), `<div class="kpis">
        ${S.me.isTech ? '' : kpi('unassigned', t('k_unassigned'), 'var(--open)', c.unassigned)}
        ${kpi('mine', t('k_mine'), 'var(--brand)', c.mine)}
        ${kpi('open', t('k_open'), 'var(--open)', c.open)}
        ${kpi('in_progress', t('k_progress'), 'var(--in_progress)', c.in_progress)}
        ${kpi('waiting', t('k_waiting'), 'var(--waiting)', c.waiting)}
        ${kpi('closed', t('k_closed'), 'var(--closed)', c.closed)}
      </div>
      <div class="sect">${t('highOpen')} (${high ? high.length : '·'})</div>
      <div class="list" id="hl">${high ? (high.length ? high.map(card).join('') : `<div class="empty">${t('empty')}</div>`) : '<div class="skel"></div>'}</div>`, { tab: 'overview' });
      app.querySelectorAll('.kpi').forEach((k) => { k.onclick = () => { S.view = k.dataset.v; store.set('view', S.view); S.list = null; go('#/tickets'); }; });
      bindList();
    };
    draw(null);
    try {
      const d = await api('/admin/m/api/tickets?view=all');
      S.counts = d.counts; if (!location.hash.startsWith('#/overview')) return;
      draw(d.tickets.filter((x) => x.priority === 'high' && x.status !== 'closed'));
      Object.assign(c, d.counts);
    } catch (e) { onError(e); }
  }

  // ── activity ─────────────────────────────────────────────────────────
  function renderActivity() {
    S.unread = 0; store.set('unread', 0); setBadge(0);
    shell(t('activity'), `<div class="ptr" id="ptr"></div><div class="feed" id="feed"><div class="skel"></div><div class="skel"></div></div>`, { tab: 'activity' });
    pullToRefresh(); loadActivity();
  }
  async function loadActivity() {
    try {
      const rows = await api('/admin/m/api/activity');
      const f = $('#feed'); if (!f) return;
      f.innerHTML = rows.length ? rows.map((r) => `<button class="fi ${r.internal ? 'note' : ''}" data-id="${r.ticketId}">${av(r.who)}
        <div style="flex:1;min-width:0"><div class="t"><b>${esc(r.who)}</b> · <span class="mono">#${r.serial}</span> · ${esc(ago(r.at))}</div>
        <div class="t" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(r.subject)}</div>
        <div class="b">${r.internal ? ic('lock') + ' ' : ''}${esc(r.body)}</div></div></button>`).join('')
        : `<div class="empty">${ic('bell')}<div>${t('emptyAct')}</div></div>`;
      f.querySelectorAll('.fi').forEach((b) => { b.onclick = () => go('#/t/' + b.dataset.id); });
    } catch (e) { onError(e); }
  }

  // ── account ──────────────────────────────────────────────────────────
  function renderAccount() {
    const me = S.me;
    const notifOn = native ? !!store.get('notif', false) : (window.Notification && Notification.permission === 'granted');
    shell(t('account'), `<div class="me-card"><span class="av">${esc(initials(me.fullName))}</span>
        <div><div style="font-weight:800;font-size:1.05rem">${esc(me.fullName)}</div>
        <div style="color:var(--muted)">${esc(LANG === 'ar' ? me.roleLabelAr : me.roleLabelEn)} · <span class="mono">${esc(me.username)}</span></div></div></div>
      <div class="menu">
        <button class="opt" id="mlang">${ic('globe')}<span>${t('lang')}</span><span class="ck" style="color:var(--muted)">${LANG === 'ar' ? 'العربية' : 'English'}</span></button>
        <button class="opt" id="mnot">${ic('bell')}<span>${t('notif')}</span><span class="ck" style="color:var(--muted)">${notifOn ? t('notifOn') : t('notifOff')}</span></button>
        <a class="opt" href="/admin/" style="color:inherit;text-decoration:none">${ic('web')}<span>${t('web')}</span></a>
      </div>
      <div class="menu"><button class="opt danger" id="mout">${ic('out')}<span>${t('logout')}</span></button></div>`, { tab: 'account' });
    $('#mlang').onclick = async () => {
      LANG = LANG === 'ar' ? 'en' : 'ar'; store.set('lang', LANG); applyLang();
      try { await api('/admin/m/api/lang', { method: 'POST', body: { lang: LANG } }); } catch (e) { /* offline is fine */ }
      renderAccount();
    };
    $('#mnot').onclick = async () => { await askNotify(true); renderAccount(); };
    $('#mout').onclick = async () => {
      try { await api('/admin/m/api/logout', { method: 'POST' }); } catch (e) { /* ignore */ }
      S.me = null; store.set('me', null); S.list = null; renderLogin();
    };
  }

  // ── notifications (polling while the app is open; native ones in the Android app) ──
  async function askNotify(force) {
    const LN = plugin('LocalNotifications');
    if (LN) {
      try { const r = await LN.requestPermissions(); store.set('notif', r.display === 'granted'); } catch (e) { /* ignore */ }
      return;
    }
    if (window.Notification && (force || Notification.permission === 'default')) { try { await Notification.requestPermission(); } catch (e) { /* ignore */ } }
  }
  function setBadge(n) { const b = app.querySelector('.nav button[data-go="#/activity"]'); if (b) { const old = b.querySelector('.badge'); if (old) old.remove(); if (n) b.insertAdjacentHTML('beforeend', `<span class="badge">${n > 99 ? '99+' : n}</span>`); } }
  async function notify(ev) {
    const title = { new: t('newT'), assigned: t('assignedT'), reply: t('replyT'), note: t('noteT') }[ev.kind] + ` · #${ev.serial}`;
    const body = (ev.who ? ev.who + ': ' : '') + (ev.body || ev.subject);
    const LN = plugin('LocalNotifications');
    if (LN && store.get('notif', false)) {
      try { await LN.schedule({ notifications: [{ id: Math.floor(Math.random() * 2e9), title, body, extra: { ticketId: ev.ticketId } }] }); } catch (e) { /* ignore */ }
    } else if (!native && window.Notification && Notification.permission === 'granted' && document.hidden) {
      try { const n = new Notification(title, { body, icon: '/static/icon-192.png', tag: 'tkt-' + ev.ticketId }); n.onclick = () => { window.focus(); go('#/t/' + ev.ticketId); }; } catch (e) { /* ignore */ }
    }
  }
  async function poll() {
    if (!S.me || S.offline) return;
    try {
      const since = S.since || new Date().toISOString();
      const d = await api('/admin/m/api/updates?since=' + encodeURIComponent(since.replace('Z', '')));
      S.since = d.now; store.set('since', S.since);
      if (d.events && d.events.length) {
        S.unread += d.events.length; store.set('unread', S.unread);
        if (!location.hash.startsWith('#/activity')) setBadge(S.unread);
        for (const ev of d.events.slice(-3)) notify(ev);
        if ((location.hash || '#/tickets').startsWith('#/tickets')) loadList();
        if (S.ticket && location.hash === '#/t/' + S.ticket.id && d.events.some((e) => e.ticketId === S.ticket.id)) openTicket(S.ticket.id);
      }
    } catch (e) { if (e.auth) onError(e); }
  }

  // ── errors, connectivity, start-up ──────────────────────────────────
  function onError(e) {
    if (e.auth) { S.me = null; store.set('me', null); renderLogin(); return; }
    if (e.status === 403) return toast(t('forbidden'), true);
    if (!navigator.onLine || e instanceof TypeError) { S.offline = true; return toast(t('offline'), true); }
    toast(t('failed'), true);
  }
  window.addEventListener('online', () => { S.offline = false; route(); });
  window.addEventListener('offline', () => { S.offline = true; toast(t('offline'), true); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
  setInterval(() => { if (!document.hidden) poll(); }, 30000);

  if (native) {
    const A = plugin('App');
    if (A) A.addListener('backButton', () => {
      if (!$('#sheet').hidden) return closeSheet();
      if (location.hash && !/^#\/tickets/.test(location.hash)) history.back(); else A.exitApp();
    });
    const LN = plugin('LocalNotifications');
    if (LN) LN.addListener('localNotificationActionPerformed', (a) => { const id = a && a.notification && a.notification.extra && a.notification.extra.ticketId; if (id) go('#/t/' + id); });
    const SB = plugin('StatusBar');
    if (SB) { try { SB.setBackgroundColor({ color: '#0a3a8a' }); SB.setStyle({ style: 'DARK' }); } catch (e) { /* ignore */ } }
  }

  applyLang();
  (async () => {
    if (S.me) route(); // instant start from the saved account and lists, then confirm the session
    try {
      S.me = await api('/admin/m/api/me'); store.set('me', S.me);
      if (S.me.lang && !store.get('lang', null)) { LANG = S.me.lang; applyLang(); }
      if (!S.since) { S.since = new Date().toISOString(); store.set('since', S.since); }
      route(); poll();
    } catch (e) {
      if (e.auth) { S.me = null; store.set('me', null); renderLogin(); } else if (!S.me) renderLogin(); else onError(e);
    }
  })();
})();
