/* Shared app shell: injects the left sidebar into every page.
 *
 * Written once and injected, rather than pasted into four HTML files, so the
 * navigation cannot drift between pages. The active item is derived from the
 * URL, and the current brain (?brain=) is carried across every link — losing it
 * on navigation would silently drop the user back to the demo brain.
 */
(function () {
  const ICONS = {
    ask: '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.9-.9L3 21l1.9-4.6A8.4 8.4 0 0 1 12 3.1a8.4 8.4 0 0 1 9 8.4z"/>',
    upload: '<path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5"/><path d="M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15"/>',
    brains: '<rect x="3" y="3" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="2"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2"/>',
    graph: '<circle cx="12" cy="5" r="2.4"/><circle cx="5" cy="18" r="2.4"/><circle cx="19" cy="18" r="2.4"/><path d="M10.4 6.8 6.6 15.7M13.6 6.8l3.8 8.9M7.4 18h9.2"/>',
  };

  function icon(name) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
           'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
           (ICONS[name] || '') + '</svg>';
  }

  // Keep ?brain= alive across navigation.
  const params = new URLSearchParams(location.search);
  const brain = params.get('brain') || params.get('dataset') || '';
  const qs = brain ? '?brain=' + encodeURIComponent(brain) : '';
  const currentChat = params.get('chat') || '';

  const path = location.pathname.replace(/\/+$/, '') || '/';
  const PAGES = [
    // "New chat" REPLACES the old Ask entry: same route, but it always starts
    // a fresh conversation (the chat itself lives under Chats).
    { href: '/',        key: 'ask',    lk: 'nav.new_chat',  fresh: true },
    { href: '/upload',  key: 'upload', lk: 'nav.new_brain' },
    { href: '/brains',  key: 'brains', lk: 'nav.brains' },
    { href: '/graph',   key: 'graph',  lk: 'nav.graph' },
  ];

  const T = (k, f) => (window.KI18N ? window.KI18N.t(k, f) : (f || k));

  function buildLinks() {
    return PAGES.map(p => {
      const active = path === p.href && !p.fresh;
      const href = p.fresh ? '/' + (qs ? qs + '&new=1' : '?new=1') : p.href + qs;
      return '<a class="nav-item' + (active ? ' active' : '') + '" href="' + href + '">' +
             icon(p.key) + '<span>' + T(p.lk, p.label) + '</span></a>';
    }).join('');
  }
  let links = buildLinks();


  // Conversation list across ALL brains. Each chat remembers the brain it was
  // built in; opening one navigates with ?brain=<its brain>, so the composer
  // always switches to the brain that chat belongs to — the way a chat app
  // switches project context when you open an old conversation.
  function chatList(view) {
    const out = [];
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (!key || key.indexOf('kestrel.chats.') !== 0) continue;
        const chatBrain = key.slice('kestrel.chats.'.length);
        const all = JSON.parse(localStorage.getItem(key) || '[]');
        all.forEach(c => out.push({ brain: chatBrain, chat: c }));
      }
    } catch (e) { /* storage unavailable - history is a convenience */ }
    const keyOf = e => (view.sort === 'created' ? (e.chat.created || e.chat.at || 0) : (e.chat.at || 0));
    return out.sort((a, b) => keyOf(b) - keyOf(a));
  }

  // View + sort + collapse state survive reloads.
  // NOT under kestrel.chats.* — that namespace is read as brains by chatList,
  // and a settings object here once showed up as a brain named "COLLAPSED".
  const VIEW_KEY = 'kestrel.sidebar.view';
  const COLLAPSE_KEY = 'kestrel.sidebar.collapsed';
  try { localStorage.removeItem('kestrel.chats.collapsed');
        localStorage.removeItem('kestrel.chats.view'); } catch (e) {}
  function chatView() {
    try { return JSON.parse(localStorage.getItem(VIEW_KEY)) || { mode: 'brain', sort: 'updated' }; }
    catch (e) { return { mode: 'brain', sort: 'updated' }; }
  }
  function saveView(v) { try { localStorage.setItem(VIEW_KEY, JSON.stringify(v)); } catch (e) {} }
  function collapsedBrains() {
    try { return JSON.parse(localStorage.getItem(COLLAPSE_KEY)) || []; }
    catch (e) { return []; }
  }

  async function deleteChat(chatBrain, chatId) {
    // server-side deletion first (Postgres), then the local copy
    let h = {};
    try { h = window.KestrelAuth ? await window.KestrelAuth.authHeaders() : {}; } catch (e) {}
    fetch('/api/chats/' + encodeURIComponent(chatId), { method: 'DELETE', headers: h }).catch(() => {});
    try {
      const key = 'kestrel.chats.' + chatBrain;
      const rest = JSON.parse(localStorage.getItem(key) || '[]').filter(c => c.id !== chatId);
      if (rest.length) localStorage.setItem(key, JSON.stringify(rest));
      else localStorage.removeItem(key);
    } catch (e) {}
    renderChats();
    // deleting the OPEN conversation starts a fresh one in the same brain
    if (currentChat === chatId && (brain || 'demo') === chatBrain) {
      location.href = '/' + (chatBrain !== 'demo' ? '?brain=' + encodeURIComponent(chatBrain) + '&new=1' : '?new=1');
    }
  }

  async function deleteBrainChats(chatBrain) {
    // every chat of this brain is removed server-side AND locally
    let h = {};
    try { h = window.KestrelAuth ? await window.KestrelAuth.authHeaders() : {}; } catch (e) {}
    try {
      const raw = localStorage.getItem('kestrel.chats.' + chatBrain) || '[]';
      JSON.parse(raw).forEach(c =>
        fetch('/api/chats/' + encodeURIComponent(c.id), { method: 'DELETE', headers: h }).catch(() => {}));
      localStorage.removeItem('kestrel.chats.' + chatBrain);
    } catch (e) {}
    renderChats();
    if ((brain || 'demo') === chatBrain) {
      location.href = '/' + (chatBrain !== 'demo' ? '?brain=' + encodeURIComponent(chatBrain) + '&new=1' : '?new=1');
    }
  }

  function renderChats() {
    const box = document.getElementById('sb-chats');
    if (box) box.innerHTML = chatGroup();
  }

  function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  function chatGroup() {
    const view = chatView();
    const sep0 = qs ? '&' : '?';
    const entries = chatList(view);
    const sep = qs ? '&' : '?';
    // ?new=1 tells the ask page to start a fresh conversation. Without it the
    // link would resume whatever chat this tab already had open.
    const newHref = '/' + (qs ? qs + '&new=1' : '?new=1');
    const FOLDER = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';
    const TRASH  = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M4 7h16M9 7V5h6v2m-8 0 1 13h8l1-13"/></svg>';
    const FILTER = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6h16M7 12h10M10 18h4"/></svg>';
    const CARET  = '<svg class="caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m9 6 6 6-6 6"/></svg>';

    let html =
      '<div class="chats-head"><span class="nav-label">' + T('nav.chats', 'Chats') + '</span>' +
      '<button type="button" class="head-btn" data-action="view-toggle" title="' + T('view.toggle', 'View and sort') + '" aria-label="' + T('view.toggle', 'View and sort') + '">' + FILTER + '</button></div>';

    if (!entries.length) {
      html += '<div class="chat-empty">' + T('nav.no_chats', 'No saved chats yet') + '</div>';
      return html;
    }

    const live = new URLSearchParams(location.search);
    const liveChat = live.get('chat') || '';
    const liveBrain = live.get('brain') || 'demo';
    const chatRow = (b, c, timeLabel) => {
      const active = c.id === liveChat && b === (liveBrain || (brain || 'demo'));
      const title = esc(c.title || 'Untitled');
      const csep = b !== 'demo' ? '?brain=' + encodeURIComponent(b) + '&chat=' : '?chat=';
      return '<div class="nav-item chat-item' + (active ? ' active' : '') + '" data-chat-row>' +
        '<a class="chat-link" href="/' + csep + encodeURIComponent(c.id) + '" title="' + title + '">' +
        '<span class="chat-title">' + esc(title.slice(0, 30)) + '</span></a>' +
        (timeLabel ? '<span class="chat-time">' + timeLabel + '</span>' : '') +
        '<button type="button" class="row-del" data-action="chat-del" data-brain="' + esc(b) +
        '" data-id="' + esc(c.id) + '" title="Delete chat" aria-label="Delete chat">' + TRASH + '</button></div>';
    };

    function sortKey(e) { return view.sort === 'created' ? (e.chat.created || e.chat.at || 0) : (e.chat.at || 0); }
    function relTime(ts) {
      if (!ts) return '';
      const s = Math.max(0, (Date.now() - ts) / 1000);
      if (s < 60) return 'now';
      if (s < 3600) return Math.round(s / 60) + 'm';
      if (s < 86400) return Math.round(s / 3600) + 'h';
      return Math.round(s / 86400) + 'd';
    }

    if (view.mode === 'timeline') {
      entries.slice(0, 14).forEach(e => {
        html += chatRow(e.brain, e.chat, relTime(sortKey(e)));
      });
      html += viewFooter();
      return html;
    }

    // grouped by brain — folders retract on click
    const collapsed = collapsedBrains();
    const groups = new Map();
    entries.forEach(e => {
      if (!groups.has(e.brain)) groups.set(e.brain, []);
      groups.get(e.brain).push(e.chat);
    });
    let shown = 0;
    for (const [b, chats] of groups) {
      if (shown >= 16) break;
      const isCollapsed = collapsed.indexOf(b) >= 0;
      const label = b === 'demo' ? T('brain.demo', 'Demo brain') : b;
      html += '<div class="brain-row" data-action="group-toggle" data-brain="' + esc(b) + '" title="Expand or collapse">' +
        CARET + FOLDER + '<span class="brain-name" data-newchat-brain="' + esc(b) + '">' + esc(label) + '</span>' +
        '<button type="button" class="row-del group-del" data-action="group-del" data-brain="' + esc(b) +
        '" title="Delete all chats in this brain" aria-label="Delete all chats in this brain">' + TRASH + '</button></div>';
      if (isCollapsed) continue;
      chats.slice(0, 5).forEach(c => {
        if (shown >= 16) return;
        shown += 1;
        html += chatRow(b, c);
      });
    }
    html += viewFooter();
    return html;

    function viewFooter() {
      return '<div class="view-note" data-view-note>' +
        (view.mode === 'brain' ? T('view.grouped', 'Grouped by brain') : T('view.timeline', 'Timeline')) +
        ' · ' + T('view.sorted', 'sorted by') + ' ' + (view.sort === 'created' ? T('view.created', 'created') : T('view.updated', 'updated')) + '</div>';
    }
  }

  // Chat links switch IN PLACE: the ask page owns the session state and
  // listens for this event (no navigation, no boot wait, no empty flash).
  // Modifier-clicks keep the native open-in-new-tab behavior.
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a.chat-link');
    if (!a) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    const u = new URL(a.href, location.origin);
    window.dispatchEvent(new CustomEvent('kestrel:open-chat', { detail: {
      chat: u.searchParams.get('chat'),
      brain: u.searchParams.get('brain') || 'demo',
    }}));
  });

  // One delegated listener: the list re-renders often, so per-element handlers
  // would be rebuilt (and lost) on every render.
  document.addEventListener('click', e => {
    const box = document.getElementById('sb-chats');
    const menu = document.getElementById('sb-viewmenu');
    const inList = box && box.contains(e.target);
    const inMenu = menu && menu.contains(e.target);
    if (!inList && !inMenu) { closeViewMenu(); return; }
    const btn = e.target.closest('[data-action]');
    if (!btn) { if (inList) closeViewMenu(); return; }
    e.preventDefault();
    const action = btn.dataset.action;
    const view = chatView();

    if (action === 'view-toggle') { openViewMenu(btn); return; }
    if (action === 'view-mode') {
      view.mode = btn.dataset.value; saveView(view); renderChats();
      // renderChats replaced the list — the old button node is detached, and a
      // detached node's rect is (0,0), which threw the menu to the top-left.
      const live = document.querySelector('[data-action=view-toggle]');
      if (live) openViewMenu(live);
      return;
    }
    if (action === 'view-sort') {
      view.sort = btn.dataset.value; saveView(view); renderChats();
      const live = document.querySelector('[data-action=view-toggle]');
      if (live) openViewMenu(live);
      return;
    }
    if (action === 'group-toggle') {
      if (e.target.closest('.row-del')) return;   // the ⋯/trash has its own action
      const l = collapsedBrains();
      const b = btn.dataset.brain;
      const at = l.indexOf(b);
      if (at >= 0) l.splice(at, 1); else l.push(b);
      try { localStorage.setItem(COLLAPSE_KEY, JSON.stringify(l)); } catch (err) {}
      renderChats(); return;
    }
    if (action === 'group-del') {
      e.stopPropagation();
      if (btn.dataset.armed === '1') { deleteBrainChats(btn.dataset.brain); return; }
      btn.dataset.armed = '1';
      btn.innerHTML = '× Remove';
      btn.classList.add('armed');
      return;
    }
    if (action === 'chat-del') {
      e.stopPropagation();
      if (btn.dataset.armed === '1') { deleteChat(btn.dataset.brain, btn.dataset.id); return; }
      btn.dataset.armed = '1';
      btn.innerHTML = '×';
      btn.classList.add('armed');
      btn.title = 'Click again to delete';
      return;
    }
  });

  function openViewMenu(btn) {
    const view = chatView();
    closeViewMenu();
    const menu = document.createElement('div');
    menu.className = 'pop sb-pop';
    menu.id = 'sb-viewmenu';
    menu.innerHTML =
      '<div class="pop-note">' + T('view.title', 'View') + '</div>' +
      '<button type="button" data-action="view-mode" data-value="brain">' + T('view.by_brain', 'By brain') + (view.mode === 'brain' ? '<span class="tick">✓</span>' : '') + '</button>' +
      '<button type="button" data-action="view-mode" data-value="timeline">' + T('view.timeline', 'Timeline') + (view.mode === 'timeline' ? '<span class="tick">✓</span>' : '') + '</button>' +
      '<div class="pop-sep"></div>' +
      '<div class="pop-note">' + T('view.sort_by', 'Sort by') + '</div>' +
      '<button type="button" data-action="view-sort" data-value="updated">' + T('view.updated', 'Updated') + (view.sort === 'updated' ? '<span class="tick">✓</span>' : '') + '</button>' +
      '<button type="button" data-action="view-sort" data-value="created">' + T('view.created', 'Created') + (view.sort === 'created' ? '<span class="tick">✓</span>' : '') + '</button>';
    document.body.appendChild(menu);
    const r = btn.getBoundingClientRect();
    menu.style.left = Math.max(10, r.left) + 'px';
    menu.style.top = (r.bottom + 8) + 'px';
    // .pop's absolute-anchoring (bottom/right) must not fight the fixed menu
    menu.style.bottom = 'auto';
    menu.style.right = 'auto';
  }
  function closeViewMenu() {
    const m = document.getElementById('sb-viewmenu');
    if (m) m.remove();
  }

  const shell = document.createElement('aside');
  shell.className = 'shell';
  shell.innerHTML =
    '<div class="brand">' +
      '<div class="mark">◆</div>' +
      '<div><div class="name">Kestrel</div>' +
      '<div class="sub">Company Brain</div></div>' +
    '</div>' +
    '<nav class="nav">' +
      '<div class="nav-label" data-nav-label>' + T('nav.workspace', 'Workspace') + '</div>' + links +
      '<div id="sb-chats"></div>' +
    '</nav>' +
    '<div class="sb-user" id="sb-user" hidden></div>';

  const toggle = document.createElement('button');
  toggle.className = 'sb-toggle';
  toggle.type = 'button';
  toggle.setAttribute('aria-label', 'Toggle navigation');
  toggle.textContent = '☰';
  toggle.addEventListener('click', () => shell.classList.toggle('open'));

  document.body.insertBefore(toggle, document.body.firstChild);
  document.body.insertBefore(shell, document.body.firstChild);

  // gliding hover highlight — one element slides between rows; in the gutter
  // it shrinks to a small tick that tracks the cursor (ZCode-style rail)
  const navEl = document.querySelector('.shell .nav');
  const slide = document.createElement('div');
  slide.className = 'sb-slide';
  slide.setAttribute('aria-hidden', 'true');
  let slideRAF = 0;
  function ensureSlide() {
    if (navEl && !slide.isConnected) navEl.appendChild(slide);
  }
  ensureSlide();
  if (navEl) {
    navEl.addEventListener('mousemove', (e) => {
      if (slideRAF) return;
      slideRAF = requestAnimationFrame(() => {
        slideRAF = 0;
        const rect = navEl.getBoundingClientRect();
        const y = e.clientY - rect.top + navEl.scrollTop;
        // elementFromPoint, not e.target: synthetic moves and moves over a
        // row's own padding/spans must both resolve to the row beneath
        const under = document.elementFromPoint(e.clientX, e.clientY);
        const row = under && under.closest('.nav-item, .brain-row');
        if (row && navEl.contains(row)) {
          slide.classList.remove('tick');
          slide.style.left = ''; slide.style.width = '';
          slide.style.top = row.offsetTop + 'px';
          slide.style.height = row.offsetHeight + 'px';
          slide.style.opacity = '1';
        } else {
          slide.classList.add('tick');
          slide.style.left = '10px'; slide.style.width = '46px';
          slide.style.top = (y - 1) + 'px'; slide.style.height = '2px';
          slide.style.opacity = '.8';
        }
      });
    });
    navEl.addEventListener('mouseleave', () => {
      if (slideRAF) { cancelAnimationFrame(slideRAF); slideRAF = 0; }
      slide.style.opacity = '0';
    });
    document.body.classList.add('sb-slide-on');
  }

  renderChats();
  // Server hydration: the sidebar previously read ONLY localStorage, so any
  // chat living in Postgres (cleared cache, new device, pre-auth history) was
  // invisible and restore fell through to "empty". Merge server rows in by id
  // (local entries win on conflict — they may hold unsynced turns), then
  // re-render. Runs once at boot; failures keep the local-only view.
  (async function hydrateChats() {
    try {
      const h = window.KestrelAuth ? await window.KestrelAuth.authHeaders() : {};
      // No hardcoded 'demo': the server resolves it to company_brain, so a
      // 'demo' entry re-fetched every company_brain chat and stored a
      // duplicate copy under kestrel.chats.demo — deletes then cleaned the
      // wrong key and the row came back. Brains come from the server list
      // plus whatever keys already exist locally.
      const brains = new Set();
      try {
        const rb = await fetch('/api/brains', { headers: h });
        if (rb.ok) ((await rb.json()).brains || []).forEach(b => {
          const n = b && (b.name || b);
          if (typeof n === 'string' && n) brains.add(n);
        });
      } catch (e) { /* fall back to local keys below */ }
      try {
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (k && k.indexOf('kestrel.chats.') === 0)
            brains.add(k.slice('kestrel.chats.'.length));
        }
      } catch (e) {}
      const knownIds = new Set();
      let changedHeal = false;
      try {
        // One-time self-heal: drop cross-key duplicates already stored
        // (same id under two brain keys). Keep the first key that holds it.
        const keys = [];
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (k && k.indexOf('kestrel.chats.') === 0) keys.push(k);
        }
        keys.forEach(k => {
          let arr = [];
          try { arr = JSON.parse(localStorage.getItem(k) || '[]'); } catch (e) {}
          const kept = arr.filter(c => {
            if (!c || !c.id || knownIds.has(c.id)) return false;
            knownIds.add(c.id);
            return true;
          });
          if (kept.length !== arr.length) {
            try {
              if (kept.length) localStorage.setItem(k, JSON.stringify(kept));
              else localStorage.removeItem(k);
              changedHeal = true;
            } catch (e) {}
          }
        });
      } catch (e) {}
      let changed = false;
      for (const b of brains) {
        let rows = [];
        try {
          const r = await fetch('/api/chats?brain=' + encodeURIComponent(b),
                                { headers: h });
          if (r.ok) rows = (await r.json()).chats || [];
        } catch (e) { continue; }
        if (!rows.length) continue;
        const key = 'kestrel.chats.' + b;
        let local = [];
        try { local = JSON.parse(localStorage.getItem(key) || '[]'); }
        catch (e) { local = []; }
        const seen = new Set(local.map(c => c.id));
        rows.forEach(s => {
          // Cross-key dedupe: one chat id lives under exactly one key, or
          // deletes clean the wrong copy and the row resurrects.
          if (s && s.id && !seen.has(s.id) && !knownIds.has(s.id)) {
            local.unshift({ id: s.id, title: s.title || 'Untitled',
                            at: s.at || Date.now(), turns: s.turns || [] });
            seen.add(s.id); knownIds.add(s.id); changed = true;
          }
        });
        if (changed) try {
          localStorage.setItem(key, JSON.stringify(local.slice(0, 100)));
        } catch (e) {}
      }
      if (changed || changedHeal) renderChats();
    } catch (e) { /* local-only view stands */ }
  })();
  // index.html dispatches this after saving; the sidebar is otherwise built once
  // at load and a new conversation would not appear until a reload.
  window.addEventListener('kestrel:chats', renderChats);
  window.addEventListener('storage', e => {
    if (!e.key || e.key.indexOf('kestrel.chats.') === 0) renderChats();
  });

  document.getElementById('jump-latest')?.addEventListener('click', () => {
    window.dispatchEvent(new Event('kestrel:jump-latest'));
  });

  // ==========================================================================
  // User area + settings — the account row (avatar, name) and the gear menu:
  // language, app theme, usage stats, upgrade, account management, sign out.
  // Lives in the shell so every page gets identical settings behaviour.
  // ==========================================================================
  const GEAR = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.09a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.09a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z"/></svg>';
  const MI = {
    globe:  '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z"/>',
    theme:  '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" stroke="none"/>',
    chart:  '<path d="M4 20V10M10 20V4M16 20v-7M20 20H4"/>',
    rocket: '<path d="M5 15c-1.5 1.5-2 5-2 5s3.5-.5 5-2M14 4c3-2 7-1 7-1s1 4-1 7l-6 6-4-4 4-6z"/><circle cx="14.5" cy="9.5" r="1.4"/>',
    person: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-3.5 4.5-5 8-5s6.5 1.5 8 5"/>',
    exit:   '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H3"/>',
    chev:   '<path d="m9 6 6 6-6 6"/>',
  };
  const mic = n => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + MI[n] + '</svg>';
  const chevSvg = '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + MI.chev + '</svg>';

  function closeSettings() {
    document.querySelectorAll('.settings-pop, .sub-pop').forEach(m => m.remove());
  }

  function userLabel(u) {
    const nm = [u.firstName, u.lastName].filter(Boolean).join(' ');
    const em = u.primaryEmailAddress || (u.emailAddresses && u.emailAddresses[0] && u.emailAddresses[0].emailAddress) || '';
    const initials = ((u.firstName || '') + (u.lastName || '')).trim()
      ? (u.firstName || ' ')[0] + (u.lastName || u.firstName || ' ')[0]
      : (em || 'K').slice(0, 2).toUpperCase();
    return { nm: nm || em || 'Kestrel user', em, initials: initials.toUpperCase() };
  }

  function renderUser(st) {
    const box = document.getElementById('sb-user');
    if (!box) return;
    if (st.mode !== 'clerk') { box.hidden = true; return; }
    box.hidden = false;
    if (st.signedIn) {
      const u = window.KestrelAuth.user || {};
      const w = userLabel(u);
      const img = u.imageUrl ? '<img src="' + u.imageUrl + '" alt="">' : '';
      box.innerHTML =
        '<button type="button" class="avatar" data-set="account" title="' + w.nm + '">' + img + (img ? '' : w.initials) + '</button>' +
        '<button type="button" class="who" data-set="account"><div class="nm">' + w.nm + '</div>' +
        '<div class="em">' + (w.em || '') + '</div></button>' +
        '<button type="button" class="gear" data-set="menu" aria-label="Settings">' + GEAR + '</button>';
    } else {
      box.innerHTML =
        '<button type="button" class="who" data-set="signin"><div class="nm">' + T('set.sign_in', 'Sign in') + '</div></button>';
    }
  }

  function settingsMenu() {
    closeSettings();
    const menu = document.createElement('div');
    menu.className = 'settings-pop';
    menu.id = 'sb-settings';

    const theme = window.KTheme ? window.KTheme.theme : 'system';
    const item = (set, ic, label, extra) =>
      '<button type="button" class="set-item" data-set="' + set + '">' + mic(ic) + '<span>' + label + '</span>' + (extra || '') + '</button>';
    const chevItem = (set, ic, label) => item(set, ic, label, chevSvg);

    let html =
      chevItem('lang', 'globe', T('set.language', 'Language')) +
      chevItem('theme', 'theme', T('set.theme', 'App theme')) +
      '<div class="set-sep"></div>' +
      item('usage', 'chart', T('set.usage', 'Usage stats')) +
      item('upgrade', 'rocket', T('set.upgrade', 'Upgrade'));
    if (window.KestrelAuth && window.KestrelAuth.state().signedIn) {
      html += '<div class="set-sep"></div>' +
        item('account', 'person', T('set.account', 'Manage account')) +
        item('signout', 'exit', T('set.signout', 'Disconnect'));
    }
    menu.innerHTML = html;
    document.body.appendChild(menu);
    const gear = document.querySelector('.sb-user .gear');
    const r = (gear || menu).getBoundingClientRect();
    menu.style.left = '12px';
    menu.style.top = '';
    menu.style.bottom = Math.max(10, window.innerHeight - r.top + 8) + 'px';
    return menu;
  }

  function subMenu(anchor, html) {
    const old = document.querySelector('.sub-pop');
    if (old) old.remove();
    const sub = document.createElement('div');
    sub.className = 'sub-pop';
    sub.innerHTML = html;
    document.body.appendChild(sub);
    const r = anchor.getBoundingClientRect();
    let left = r.right + 8;
    if (left + sub.offsetWidth > window.innerWidth - 8) left = window.innerWidth - sub.offsetWidth - 8;
    sub.style.left = left + 'px';
    sub.style.top = Math.max(10, r.top - 6) + 'px';
    return sub;
  }

  function openLangMenu(anchor) {
    const tick = c => (window.KI18N.lang === c ? '<span class="tick">✓</span>' : '');
    subMenu(anchor, window.KI18N.LANGS.map(l =>
      '<button type="button" class="set-item" data-lang="' + l.code + '">' +
      '<span>' + l.label + '</span>' + tick(l.code) + '</button>').join(''));
  }

  function openThemeMenu(anchor) {
    const theme = window.KTheme ? window.KTheme.theme : 'system';
    const tick = m => (theme === m ? '<span class="tick">✓</span>' : '');
    subMenu(anchor,
      '<button type="button" class="set-item" data-ktheme="system">' + mic('theme') + '<span>' + T('set.system', 'System default') + '</span>' + tick('system') + '</button>' +
      '<button type="button" class="set-item" data-ktheme="dark">' + mic('theme') + '<span>' + T('set.dark', 'Dark theme') + '</span>' + tick('dark') + '</button>' +
      '<button type="button" class="set-item" data-ktheme="light">' + mic('theme') + '<span>' + T('set.light', 'Light theme') + '</span>' + tick('light') + '</button>');
  }

  // ------------------------------------------------------------- modals
  function closeModal() {
    document.querySelectorAll('.km-scrim').forEach(m => m.remove());
  }

  function km(title, sub, bodyHtml) {
    closeModal();
    const scrim = document.createElement('div');
    scrim.className = 'km-scrim';
    scrim.innerHTML =
      '<div class="km-sheet"><div class="km-head"><h2>' + title + '</h2>' +
      '<button type="button" class="km-x" data-km-close aria-label="Close">✕</button></div>' +
      '<p class="km-sub">' + sub + '</p>' + bodyHtml + '</div>';
    document.body.appendChild(scrim);
    scrim.addEventListener('click', e => {
      if (e.target === scrim || e.target.closest('[data-km-close]')) closeModal();
    });
    return scrim;
  }

  async function openUsage() {
    const scrim = km(T('usage.title', 'Usage stats'), T('usage.sub', 'Last 30 days · estimated tokens'), '<div class="u-empty">…</div>');
    let rows = null;
    try {
      const h = await window.KestrelAuth.authHeaders();
      const r = await fetch('/api/usage?days=30', { headers: h });
      if (r.status === 401) {
        scrim.querySelector('.km-sheet').innerHTML =
          '<div class="km-head"><h2>' + T('usage.title', 'Usage stats') + '</h2>' +
          '<button type="button" class="km-x" data-km-close>✕</button></div>' +
          '<div class="u-empty">' + T('usage.signin', 'Sign in to see usage.') + '</div>';
        return;
      }
      rows = (await r.json()).usage || [];
    } catch (e) { rows = null; }
    if (!rows || !rows.length) {
      scrim.querySelector('.km-sheet').innerHTML =
        '<div class="km-head"><h2>' + T('usage.title', 'Usage stats') + '</h2>' +
        '<button type="button" class="km-x" data-km-close>✕</button></div>' +
        '<div class="u-empty">' + T('usage.empty', 'No model calls recorded yet.') + '</div>';
      return;
    }
    const n = v => (v || 0).toLocaleString();
    const secs = rows.reduce((a, r0) => a + (r0.total_ms || 0), 0) / 1000;
    const body = '<table class="u-table"><thead><tr>' +
      '<th>' + T('usage.feature', 'Feature') + '</th><th>' + T('usage.brain', 'Brain') + '</th>' +
      '<th>' + T('usage.model', 'Model') + '</th>' +
      '<th class="num">' + T('usage.calls', 'Calls') + '</th>' +
      '<th class="num">' + T('usage.tokens', 'Tokens') + '</th></tr></thead><tbody>' +
      rows.map(r0 => '<tr><td>' + (r0.feature || '—') + '</td><td>' + (r0.brain || '—') + '</td>' +
        '<td>' + (r0.model || '—') + '</td><td class="num">' + n(r0.calls) + '</td>' +
        '<td class="num">' + n((r0.prompt_tokens || 0) + (r0.completion_tokens || 0)) + '</td></tr>').join('') +
      '</tbody></table>' +
      '<div class="u-total"><span>' + rows.reduce((a, r0) => a + (r0.calls || 0), 0).toLocaleString() + ' ' + T('usage.calls', 'Calls') + '</span>' +
      '<span>' + n(rows.reduce((a, r0) => a + (r0.prompt_tokens || 0) + (r0.completion_tokens || 0), 0)) + ' ' + T('usage.tokens', 'Tokens') + '</span>' +
      '<span>' + secs.toFixed(1) + 's ' + T('usage.time', 'Time') + '</span></div>';
    scrim.querySelector('.km-sheet').innerHTML =
      '<div class="km-head"><h2>' + T('usage.title', 'Usage stats') + '</h2>' +
      '<button type="button" class="km-x" data-km-close>✕</button></div>' +
      '<p class="km-sub">' + T('usage.sub', 'Last 30 days · estimated tokens') + '</p>' + body;
  }

  function openUpgrade() {
    const tier = (cls, name, price, per, feats, btn, hot) =>
      '<div class="tier' + (hot ? ' hot' : '') + '"><div class="tn">' + name + '</div>' +
      '<div class="tp">' + price + ' <small>' + per + '</small></div>' +
      '<ul>' + feats.map(f => '<li>' + f + '</li>').join('') + '</ul>' +
      '<button type="button" class="tbtn' + (hot ? ' hot' : '') + '" ' + (btn.disabled ? 'disabled' : '') + '>' + btn.label + '</button></div>';
    const body = '<div class="tiers">' +
      tier('', T('up.free', 'Free'), '₹0', T('up.per_mo', '/mo'),
        [T('up.free_f1'), T('up.free_f2'), T('up.free_f3')],
        { label: T('up.current', 'Current plan'), disabled: true }) +
      tier('hot', T('up.pro', 'Pro'), '₹999', T('up.per_mo', '/mo'),
        [T('up.pro_f1'), T('up.pro_f2'), T('up.pro_f3')],
        { label: T('up.soon', 'Coming soon'), disabled: true }) +
      tier('', T('up.biz', 'Business'), '₹1,999', T('up.per_mo', '/mo'),
        [T('up.biz_f1'), T('up.biz_f2'), T('up.biz_f3')],
        { label: T('up.soon', 'Coming soon'), disabled: true }) +
      '</div><p class="km-note">' + T('up.note', '') + '</p>';
    km(T('up.title', 'Upgrade Kestrel'), T('upg.sub', ''), body);
  }

  // ------------------------------------------------------------- wiring
  document.addEventListener('click', async e => {
    const gear = e.target.closest('[data-set="menu"]');
    if (gear) {
      const wasOpen = !!document.getElementById('sb-settings');
      closeSettings();
      if (!wasOpen) settingsMenu();
      return;
    }
    const set = e.target.closest('[data-set]');
    if (set && !gear) {
      const which = set.dataset.set;
      if (which === 'lang') { openLangMenu(set); return; }
      if (which === 'theme') { openThemeMenu(set); return; }
      if (which === 'usage') { closeSettings(); openUsage(); return; }
      if (which === 'upgrade') { closeSettings(); openUpgrade(); return; }
      if (which === 'account') { closeSettings(); window.KestrelAuth.openAccount(); return; }
      if (which === 'signout') { closeSettings(); await window.KestrelAuth.signOut(); return; }
      if (which === 'signin') { location.href = '/'; return; }
    }
    const langBtn = e.target.closest('[data-lang]');
    if (langBtn) { window.KI18N.setLang(langBtn.dataset.lang); closeSettings(); return; }
    const themeBtn = e.target.closest('[data-ktheme]');
    if (themeBtn) { window.KTheme.set(themeBtn.dataset.ktheme); closeSettings(); return; }
    // click anywhere else closes the menus, but not clicks inside them
    if (!e.target.closest('.settings-pop') && !e.target.closest('.sub-pop')) closeSettings();
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeSettings(); closeModal(); }
  });

  if (window.KestrelAuth) window.KestrelAuth.addListener(renderUser);

  // language switch rebuilds every translated surface in the shell
  window.addEventListener('kestrel:lang', () => {
    const lbl = document.querySelector('[data-nav-label]');
    if (lbl) lbl.textContent = T('nav.workspace', 'Workspace');
    const nav = document.querySelector('.shell .nav');
    if (nav) {
      const chats = document.getElementById('sb-chats');
      nav.innerHTML = '<div class="nav-label" data-nav-label>' + T('nav.workspace', 'Workspace') + '</div>' +
        buildLinks() + (chats ? '<div id="sb-chats"></div>' : '');
    }
    ensureSlide();
    renderChats();
    renderUser(window.KestrelAuth ? window.KestrelAuth.state()
                                  : { mode: 'off', signedIn: false });
  });

})();
