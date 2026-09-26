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
    { href: '/',        key: 'ask',    label: 'Ask' },
    { href: '/upload',  key: 'upload', label: 'New brain' },
    { href: '/brains',  key: 'brains', label: 'Brains' },
    { href: '/graph',   key: 'graph',  label: 'Graph' },
  ];

  const links = PAGES.map(p => {
    const active = path === p.href;
    return '<a class="nav-item' + (active ? ' active' : '') + '" href="' +
           p.href + qs + '">' + icon(p.key) + '<span>' + p.label + '</span></a>';
  }).join('');


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

  function deleteChat(chatBrain, chatId) {
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

  function deleteBrainChats(chatBrain) {
    try { localStorage.removeItem('kestrel.chats.' + chatBrain); } catch (e) {}
    renderChats();
    if ((brain || 'demo') === chatBrain) {
      location.href = '/' + (chatBrain !== 'demo' ? '?brain=' + encodeURIComponent(chatBrain) + '&new=1' : '?new=1');
    }
  }

  function renderChats() {
    const box = document.getElementById('sb-chats');
    if (box) box.innerHTML = chatGroup();
  }

  function esc(s) { return (s || '').replace(/[<>&"]/g, ''); }

  function chatGroup() {
    const view = chatView();
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
      '<div class="chats-head"><span class="nav-label">Chats</span>' +
      '<button type="button" class="head-btn" data-action="view-toggle" title="View and sort" aria-label="View and sort">' + FILTER + '</button></div>' +
      '<a class="nav-item" href="' + newHref + '">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' +
      'stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>' +
      '<span>New chat</span></a>';

    if (!entries.length) {
      html += '<div class="chat-empty">No saved chats yet</div>';
      return html;
    }

    const chatRow = (b, c) => {
      const active = c.id === currentChat && b === (brain || 'demo');
      const title = esc(c.title || 'Untitled');
      const csep = b !== 'demo' ? '?brain=' + encodeURIComponent(b) + '&chat=' : '?chat=';
      return '<div class="nav-item chat-item' + (active ? ' active' : '') + '" data-chat-row>' +
        '<a class="chat-link" href="/' + csep + encodeURIComponent(c.id) + '" title="' + title + '">' +
        '<span class="chat-title">' + esc(title.slice(0, 30)) + '</span></a>' +
        '<button type="button" class="row-del" data-action="chat-del" data-brain="' + esc(b) +
        '" data-id="' + esc(c.id) + '" title="Delete chat" aria-label="Delete chat">' + TRASH + '</button></div>';
    };

    if (view.mode === 'timeline') {
      entries.slice(0, 14).forEach(e => { html += chatRow(e.brain, e.chat); });
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
      const label = b === 'demo' ? 'Demo brain' : b;
      html += '<div class="brain-row" data-action="group-toggle" data-brain="' + esc(b) + '" title="Expand or collapse">' +
        CARET + FOLDER + '<span class="brain-name">' + esc(label) + '</span>' +
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
        (view.mode === 'brain' ? 'Grouped by brain' : 'Timeline') +
        ' · sorted by ' + (view.sort === 'created' ? 'created' : 'updated') + '</div>';
    }
  }

  // One delegated listener: the list re-renders often, so per-element handlers
  // would be rebuilt (and lost) on every render.
  document.addEventListener('click', e => {
    const box = document.getElementById('sb-chats');
    if (!box || !box.contains(e.target)) { closeViewMenu(); return; }
    const btn = e.target.closest('[data-action]');
    if (!btn) { closeViewMenu(); return; }
    e.preventDefault();
    const action = btn.dataset.action;
    const view = chatView();

    if (action === 'view-toggle') { openViewMenu(btn); return; }
    if (action === 'view-mode') {
      view.mode = btn.dataset.value; saveView(view); closeViewMenu(); renderChats(); return;
    }
    if (action === 'view-sort') {
      view.sort = btn.dataset.value; saveView(view); closeViewMenu(); renderChats(); return;
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
      '<div class="pop-note">View</div>' +
      '<button type="button" data-action="view-mode" data-value="brain">By brain' + (view.mode === 'brain' ? '<span class="tick">✓</span>' : '') + '</button>' +
      '<button type="button" data-action="view-mode" data-value="timeline">Timeline' + (view.mode === 'timeline' ? '<span class="tick">✓</span>' : '') + '</button>' +
      '<div class="pop-sep"></div>' +
      '<div class="pop-note">Sort by</div>' +
      '<button type="button" data-action="view-sort" data-value="updated">Updated' + (view.sort === 'updated' ? '<span class="tick">✓</span>' : '') + '</button>' +
      '<button type="button" data-action="view-sort" data-value="created">Created' + (view.sort === 'created' ? '<span class="tick">✓</span>' : '') + '</button>';
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
      '<div class="nav-label">Workspace</div>' + links +
      '<div id="sb-chats"></div>' +
    '</nav>' +
    '<div class="sb-foot">' +
      '<div class="row"><span class="led" id="sb-led"></span>' +
      '<span id="sb-prov">connecting…</span></div>' +
    '</div>';

  const toggle = document.createElement('button');
  toggle.className = 'sb-toggle';
  toggle.type = 'button';
  toggle.setAttribute('aria-label', 'Toggle navigation');
  toggle.textContent = '☰';
  toggle.addEventListener('click', () => shell.classList.toggle('open'));

  document.body.insertBefore(toggle, document.body.firstChild);
  document.body.insertBefore(shell, document.body.firstChild);

  renderChats();
  // index.html dispatches this after saving; the sidebar is otherwise built once
  // at load and a new conversation would not appear until a reload.
  window.addEventListener('kestrel:chats', renderChats);
  window.addEventListener('storage', e => {
    if (!e.key || e.key.indexOf('kestrel.chats.') === 0) renderChats();
  });

  // Status LED. "healthy" alone is not enough — the tenant's /health is
  // unauthenticated, so only claim ok when the authenticated probe passed.
  fetch('/health').then(r => r.json()).then(d => {
    const ok = d.provider === 'mock' || (d.upstream === 'healthy' && d.auth !== 'failed');
    document.getElementById('sb-led').className = 'led ' + (ok ? 'ok' : 'bad');
    let label = d.provider;
    if (d.auth === 'failed') label += ' · key rejected';
    else if (d.upstream) label += ' · ' + d.upstream;
    document.getElementById('sb-prov').textContent = label;
  }).catch(() => {
    document.getElementById('sb-led').className = 'led bad';
    document.getElementById('sb-prov').textContent = 'unreachable';
  });

})();
