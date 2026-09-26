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
  function chatList() {
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
    return out.sort((a, b) => (b.chat.at || 0) - (a.chat.at || 0));
  }

  function renderChats() {
    const box = document.getElementById('sb-chats');
    if (box) box.innerHTML = chatGroup();
  }

  function chatGroup() {
    const entries = chatList();
    const sep = qs ? '&' : '?';
    // ?new=1 tells the ask page to start a fresh conversation. Without it the
    // link would resume whatever chat this tab already had open.
    const newHref = '/' + (qs ? qs + '&new=1' : '?new=1');
    let html = '<div class="nav-label">Chats</div>' +
      '<a class="nav-item" href="' + newHref + '">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' +
      'stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>' +
      '<span>New chat</span></a>';

    if (!entries.length) {
      html += '<div class="chat-empty">No saved chats yet</div>';
      return html;
    }
    entries.slice(0, 12).forEach(e => {
      const c = e.chat;
      const active = c.id === currentChat && e.brain === (brain || 'demo');
      const title = (c.title || 'Untitled').replace(/[<>&"]/g, '');
      const csep = e.brain && e.brain !== 'demo' ? '?brain=' + encodeURIComponent(e.brain) + '&chat=' : '?chat=';
      html += '<a class="nav-item chat-item' + (active ? ' active' : '') + '" href="/' + csep +
              encodeURIComponent(c.id) + '" title="' + title + '">' +
              '<span class="chat-title">' + title.slice(0, 26) + '</span>' +
              (e.brain && e.brain !== 'demo'
                ? '<span class="badge">' + e.brain + '</span>' : '') +
              '</a>';
    });
    return html;
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
