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

  const brainRow = brain
    ? '<div class="nav-label">Current brain</div>' +
      '<div class="nav-item active" style="cursor:default">' +
      '<span class="badge" style="margin:0 0 0 2px">' + brain + '</span></div>'
    : '';

  const shell = document.createElement('aside');
  shell.className = 'shell';
  shell.innerHTML =
    '<div class="brand">' +
      '<div class="mark">◆</div>' +
      '<div><div class="name">Kestrel</div>' +
      '<div class="sub">Company Brain</div></div>' +
    '</div>' +
    '<nav class="nav">' +
      '<div class="nav-label">Workspace</div>' + links + brainRow +
    '</nav>' +
    '<div class="sb-foot">' +
      '<div class="row"><span class="led" id="sb-led"></span>' +
      '<span id="sb-prov">connecting…</span></div>' +
      '<div class="row"><span id="sb-graph">graph: —</span></div>' +
    '</div>';

  const toggle = document.createElement('button');
  toggle.className = 'sb-toggle';
  toggle.type = 'button';
  toggle.setAttribute('aria-label', 'Toggle navigation');
  toggle.textContent = '☰';
  toggle.addEventListener('click', () => shell.classList.toggle('open'));

  document.body.insertBefore(toggle, document.body.firstChild);
  document.body.insertBefore(shell, document.body.firstChild);

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

  const statsUrl = '/api/stats' + (brain ? '?dataset=' + encodeURIComponent(brain) : '');
  fetch(statsUrl).then(r => r.json()).then(d => {
    document.getElementById('sb-graph').textContent = d.ok
      ? 'graph: ' + d.nodes + ' nodes · ' + d.edges + ' edges'
      : 'graph: not ready';
  }).catch(() => {});
})();
