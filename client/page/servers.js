/* The servers page (client/page/servers.html): public servers, your private servers and the one you host, checking a
   server's mods before joining, joining, hosting, and the admin console. Everything comes from the inZOI Multiplayer
   program (client/servers.py) over POST /servers/*, /host/*, /admin on this same address.
   Text from servers and players always goes in as text (never as HTML). */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const stage = $('stage');
  let S = null;                      // the latest /servers/state
  let tab = 'public';
  let selected = null;               // address of the selected server
  let modalOpen = false;
  let consoleCtx = null;             // the admin console: {local, tab, data}
  let polling = false;

  // ---------------------------------------------------------------- helpers
  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else if (k === 'value') e.value = v;
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat()) {
      if (kid === null || kid === undefined || kid === false) continue;
      e.appendChild(typeof kid === 'string' || typeof kid === 'number' ? document.createTextNode(String(kid)) : kid);
    }
    return e;
  }
  const clear = (e) => { while (e.firstChild) e.removeChild(e.firstChild); };
  async function api(path, body) {
    try {
      const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify(body || {}) });
      return await r.json();
    } catch (e) {
      return { error: "The inZOI Multiplayer program isn't running. Open inZOI Multiplayer.exe and keep it open." };
    }
  }
  let toastTimer = null;
  function toast(text, ms) {
    const t = $('toast');
    t.textContent = text;
    t.classList.add('on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('on'), ms || 4000);
  }
  const mb = (n) => (n || 0) < 1048576 ? ((n || 0) / 1024).toFixed(0) + ' KB'
    : (n / 1048576 < 100 ? (n / 1048576).toFixed(1) : Math.round(n / 1048576)) + ' MB';
  function ago(seconds) {
    if (!seconds && seconds !== 0) return '';
    if (seconds < 90) return 'just now';
    if (seconds < 5400) return Math.round(seconds / 60) + ' min';
    if (seconds < 172800) return Math.round(seconds / 3600) + ' h';
    return Math.round(seconds / 86400) + ' days';
  }
  const when = (t) => t ? ago(Date.now() / 1000 - t) + ' ago' : '';

  function fit() {
    const s = Math.min(innerWidth / 1920, innerHeight / 1080);
    stage.style.transform = `translate(${(innerWidth - 1920 * s) / 2}px, ${(innerHeight - 1080 * s) / 2}px) scale(${s})`;
  }
  addEventListener('resize', fit);
  fit();

  // ---------------------------------------------------------------- icons (the game's line icons, drawn here)
  const W = 'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"';
  const ICONS = {
    plus: `<svg viewBox="0 0 16 16"><path d="M8 3v10M3 8h10" ${W}/></svg>`,
    host: `<svg viewBox="0 0 16 16"><rect x="2" y="2.5" width="12" height="4.5" rx="1" ${W}/><rect x="2" y="9" width="12" height="4.5" rx="1" ${W}/><path d="M4.5 4.8h.01M4.5 11.3h.01" ${W}/></svg>`,
    search: `<svg viewBox="0 0 18 18"><circle cx="7.5" cy="7.5" r="5.5" fill="none" stroke="#fff" stroke-width="2"/><path d="m11.8 11.8 4.4 4.4" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>`,
    reset: `<svg viewBox="0 0 12 12"><path d="M10 6a4 4 0 1 1-1.2-2.85M10 1.5v2.2H7.8" fill="none" stroke="#fff" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    sort: `<svg viewBox="0 0 24 24"><path d="M6 4v15m0 0-3-3m3 3 3-3M12 6h9M12 11h7M12 16h5" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    checked: `<svg viewBox="0 0 15 15"><circle cx="7.5" cy="7.5" r="6.4" fill="none" stroke="#fff" stroke-width="1.4"/><path d="m4.6 7.6 2 2 3.8-4" fill="none" stroke="#fff" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
    people: `<svg viewBox="0 0 14 14"><circle cx="7" cy="4.6" r="2.6" ${W}/><path d="M2 12.5c.6-2.6 2.6-4 5-4s4.4 1.4 5 4" ${W}/></svg>`,
    ping: `<svg viewBox="0 0 14 14"><path d="M2 12V9.5M5.3 12V7M8.7 12V4.5M12 12V2" ${W}/></svg>`,
    mods: `<svg viewBox="0 0 14 14"><ellipse cx="7" cy="3.4" rx="4.6" ry="1.9" ${W}/><path d="M2.4 3.4v7.2c0 1 2 1.9 4.6 1.9s4.6-.9 4.6-1.9V3.4M2.4 7c0 1 2 1.9 4.6 1.9S11.6 8 11.6 7" ${W}/></svg>`,
    version: `<svg viewBox="0 0 14 14"><rect x="2" y="5" width="10" height="7.5" rx=".8" ${W}/><path d="M1.5 5h11V3.2h-11zM7 3.2v9.3M7 3.2C6 1 3.8 1.3 4.6 2.6 5.2 3.4 7 3.2 7 3.2zM7 3.2c1-2.2 3.2-1.9 2.4-.6C8.8 3.4 7 3.2 7 3.2z" ${W}/></svg>`,
    lock: `<svg viewBox="0 0 16 16"><rect x="3" y="7" width="10" height="7" rx="1.2" fill="#fff"/><path d="M5.2 7V5.2a2.8 2.8 0 0 1 5.6 0V7" fill="none" stroke="#fff" stroke-width="1.8"/></svg>`,
    globe: `<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.2" fill="none" stroke="#fff" stroke-width="1.7"/><path d="M1.8 8h12.4M8 1.8c2 2 2 10.4 0 12.4M8 1.8c-2 2-2 10.4 0 12.4" fill="none" stroke="#fff" stroke-width="1.4"/></svg>`,
    home: `<svg viewBox="0 0 16 16"><path d="M2 7.5 8 2.5l6 5V14H2z" fill="#fff"/><rect x="6.5" y="9.5" width="3" height="4.5" fill="#8f9598"/></svg>`,
    key: `<svg viewBox="0 0 16 16"><path d="M2.5 13.5 8.2 7.8" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/><circle cx="10.5" cy="5.5" r="3" fill="none" stroke="#fff" stroke-width="1.8"/><path d="m4.5 11.5 1.6 1.6" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg>`,
    join: `<svg viewBox="0 0 18 18"><path d="M7 3.5H3.5v11H7M11 5.5 14.5 9 11 12.5M14.5 9H6.5" ${W}/></svg>`,
    refresh: `<svg viewBox="0 0 18 18"><path d="M15 9a6 6 0 1 1-1.8-4.3M15 2.5v3.4h-3.4" ${W}/></svg>`,
    edit: `<svg viewBox="0 0 18 18"><path d="M3.5 14.5h3l8-8-3-3-8 8z" ${W}/></svg>`,
    trash: `<svg viewBox="0 0 18 18"><path d="M3.5 5h11M7 5V3.2h4V5M5 5l.8 10h6.4L13 5M7.7 8v4.5M10.3 8v4.5" ${W}/></svg>`,
    admin: `<svg viewBox="0 0 18 18"><path d="M9 2 3.5 4.2v4.2c0 3.4 2.4 6 5.5 7.6 3.1-1.6 5.5-4.2 5.5-7.6V4.2z" ${W}/><path d="m6.6 9 1.7 1.7L11.6 7.4" ${W}/></svg>`,
    stop: `<svg viewBox="0 0 18 18"><rect x="4" y="4" width="10" height="10" rx="1.5" ${W}/></svg>`,
    gear: `<svg viewBox="0 0 18 18"><circle cx="9" cy="9" r="2.4" ${W}/><path d="M9 1.8v2.1M9 14.1v2.1M1.8 9h2.1M14.1 9h2.1M3.9 3.9l1.5 1.5M12.6 12.6l1.5 1.5M3.9 14.1l1.5-1.5M12.6 5.4l1.5-1.5" ${W}/></svg>`,
    save: `<svg viewBox="0 0 18 18"><path d="M9 3v8.5M5.5 8 9 11.5 12.5 8M3.5 14.5h11" ${W}/></svg>`,
    handle: `<svg viewBox="0 0 16 14"><path d="M1 2h14M1 7h14M1 12h14" stroke="#d9dcdd" stroke-width="1.6" stroke-linecap="round"/></svg>`,
  };
  function icon(name, color) {
    const span = document.createElement('span');
    span.innerHTML = ICONS[name] || '';                 // static, trusted markup (never data from servers)
    const svg = span.firstChild;
    if (color && svg) svg.style.color = color;
    return svg || span;
  }
  function shield(kind) {
    const fill = { ok: '#aef69d', warn: '#ffd27a', bad: '#ff9d90', here: '#c3ead9' }[kind] || '#aef69d';
    const mark = kind === 'ok' || kind === 'here' ? '<path d="m6 10.3 2.6 2.6 4.6-5.2" fill="none" stroke="#2f4a2b" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>'
      : '<path d="M9.5 5.5v5.2M9.5 13.6v.2" fill="none" stroke="#5a3a1a" stroke-width="2" stroke-linecap="round"/>';
    const span = document.createElement('span');
    span.innerHTML = `<svg class="shield" viewBox="0 0 19 21"><path d="M9.5 1 1.5 4.2v5.4c0 4.8 3.4 8.6 8 10.4 4.6-1.8 8-5.6 8-10.4V4.2z" fill="${fill}"/>${mark}</svg>`;
    return span.firstChild;
  }
  document.querySelectorAll('[data-icon]').forEach((e) => e.prepend(icon(e.dataset.icon)));
  // the background's dots, where the game's own page has them (not behind the details: they'd cross its text)
  [[22, 62], [22, 86], [42, 101], [22, 110], [42, 126], [22, 134], [42, 150], [42, 174], [1545, 28], [1569, 28],
   [1593, 28], [1617, 28], [1641, 28], [1641, 52], [1641, 76], [1641, 100], [651, 149], [473, 309], [497, 309],
   [1815, 221], [1839, 221], [1863, 221], [1887, 221], [1609, 661], [1609, 685], [101, 701], [125, 701], [65, 753],
   [65, 777], [65, 801], [65, 825], [669, 929], [669, 953], [577, 989], [1863, 945], [1863, 969], [1887, 971], [1887, 995],
   [1887, 1019], [1887, 1043], [21, 1049], [45, 1049]].forEach(([x, y]) => {
    const d = document.createElement('span');
    d.className = 'dot';
    d.style.left = x + 'px';
    d.style.top = y + 'px';
    $('dots').appendChild(d);
  });

  // ---------------------------------------------------------------- the rows
  const SORTS = ['players', 'ping', 'name'];
  let sortBy = 'players';
  function hereRow() {
    const ho = S && S.hosting;
    if (!ho) return null;
    return { address: '127.0.0.1:' + ho.port, here: true, saved: false, online: true, name: ho.name,
             description: ho.settings.description, motd: ho.settings.motd, players: ho.players,
             max_players: ho.settings.max_players, password: !!ho.settings.password, public: ho.settings.public,
             current: ho.playing_here, connected: ho.playing_here && S.connected, version: S.version, ping: 0,
             hosted: true, check: { verdict: 'ready', line: 'Your server, running in this program', mods: [], problems: [] },
             mods_count: null, names: [] };
  }
  function rows() {
    if (!S) return [];
    if (tab === 'public') return S.public.slice();
    const out = S.saved.slice();
    const here = hereRow();
    return here ? [here, ...out.filter((r) => !r.here)] : out;
  }
  function verdictClass(r) {
    if (r.here) return 'here';
    if (!r.online) return 'problem';
    const v = r.check && r.check.verdict;
    return v === 'ready' ? 'ready' : v === 'download' ? 'download' : (v === 'full' || v === 'incompatible') ? 'problem' : '';
  }
  function stateText(r) {
    if (r.here) return r.connected ? 'Hosting · Here' : 'Hosting';
    if (r.connected) return 'Connected';
    if (!r.online) return 'Offline';
    const c = r.check || {};
    if (c.verdict === 'download') return c.missing + (c.missing === 1 ? ' Mod' : ' Mods') + ' to Get';
    if (c.verdict === 'full') return 'Full';
    if (c.verdict === 'incompatible') return "Can't Join";
    if (c.verdict === 'old') return 'Older Server';
    return 'Ready';
  }
  function subLine(r) {
    const box = h('div', { class: 'sub' });
    const bit = (name, text) => {
      if (box.childNodes.length) box.appendChild(h('span', { class: 'sep' }, '·'));
      box.append(icon(name), text);
    };
    if (!r.online) {
      bit('ping', r.error || 'Offline');
      return box;
    }
    bit('people', (r.players || 0) + ' / ' + (r.max_players || '?'));
    if (r.ping !== null && r.ping !== undefined && !r.here) bit('ping', r.ping + ' ms');
    if (r.mods_count !== null && r.mods_count !== undefined) bit('mods', r.mods_count ? r.mods_count + ' mods' : 'No mods');
    if (r.version) bit('version', r.version);
    if (r.description) { box.appendChild(h('span', { class: 'sep' }, '·')); box.append(r.description); }
    return box;
  }
  function filtered() {
    const q = $('search').value.trim().toLowerCase();
    const fs = $('f-status').value, fc = $('f-compat').value, fm = $('f-mods').value, fa = $('f-access').value,
      ft = $('f-type').value;
    const list = rows().filter((r) => {
      if (fs === 'online' && !r.online) return false;
      if (fs === 'room' && !(r.online && (r.players || 0) < (r.max_players || 0))) return false;
      if (fs === 'offline' && r.online) return false;
      const vc = verdictClass(r);
      if (fc === 'ready' && !(vc === 'ready' || vc === 'here' || vc === 'download' || (r.check && r.check.verdict === 'old'))) return false;
      if (fc === 'problem' && vc !== 'problem') return false;
      if (fm === 'have' && !(r.check && r.check.missing === 0)) return false;
      if (fm === 'download' && vc !== 'download') return false;
      if (fm === 'none' && r.mods_count) return false;
      if (fa === 'open' && r.password) return false;
      if (fa === 'password' && !r.password) return false;
      if (ft === 'hosted' && !r.hosted) return false;
      if (ft === 'standalone' && r.hosted) return false;
      if (q) {
        const hay = [r.name, r.server_name, r.description, r.address, r.host, (r.names || []).join(' ')].join(' ').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    list.sort((a, b) => {
      if (a.here !== b.here) return a.here ? -1 : 1;
      if (sortBy === 'name') return String(a.name).localeCompare(String(b.name));
      if (sortBy === 'ping') return (a.online ? a.ping : 1e9) - (b.online ? b.ping : 1e9);
      return (b.online - a.online) || ((b.players || 0) - (a.players || 0));
    });
    return list;
  }

  async function toggleSaved(r) {
    if (r.here) return;
    if (r.saved) {
      if (!(await confirmBox('Remove ' + (r.name || r.address) + ' from Private Servers?', 'You can add it again with ' +
        'its address. (Your multiplayer save for it stays on your PC.)', 'Remove'))) return;
      await api('/servers/remove', { address: r.address });
      toast('Removed from Private Servers.');
    } else {
      const res = await api('/servers/save', { address: r.address });
      toast(res.error || 'Saved in Private Servers.');
    }
    poll(true);
  }

  function renderList() {
    const box = $('rows');
    const list = filtered();
    const all = rows();
    clear(box);
    $('count').textContent = all.length;
    $('all-count').textContent = list.length;
    $('all-check').className = 'check' + (list.length && list.every((r) => r.saved || r.here) ? ' on' : '');
    $('list-title').textContent = tab === 'public' ? 'Public Servers' : 'Private Servers';
    $('add-server').style.display = tab === 'private' ? '' : 'none';
    $('host-server').style.display = tab === 'private' && !(S && S.hosting) ? '' : 'none';
    $('sort').title = 'Sort: ' + sortBy;
    const note = $('list-note');
    if (tab === 'public' && S) {
      const errs = Object.keys(S.public_errors || {});
      note.textContent = !S.directories.length ? '' : errs.length === S.directories.length && errs.length
        ? "Couldn't get the list of public servers right now." : (S.public_at ? 'Updated ' + when(S.public_at) : 'Looking for servers...');
    } else {
      note.textContent = '';
    }
    if (!list.length) {
      let text;
      if (!S) text = 'Connecting to the inZOI Multiplayer program...';
      else if (all.length) text = 'No server matches these filters.';
      else if (tab === 'public') text = S.directories.length
        ? 'No public servers right now. Host one yourself in Private Servers and make it public.'
        : 'The list of public servers comes from a server that keeps one (like a friend\'s Raspberry Pi). Join one ' +
          'in Private Servers first, or host your own.';
      else text = 'No saved servers yet. Add one with its address (the friend who hosts gives it to you), or host your own.';
      box.appendChild(h('div', { class: 'empty-list' }, text));
    }
    list.forEach((r, i) => {
      const vc = verdictClass(r);
      const kind = r.here ? 'here' : !r.online || vc === 'problem' ? 'bad' : vc === 'download' ? 'warn' : 'ok';
      const thumb = h('div', { class: 'thumb' + (r.here ? ' here' : '') }, String(r.name || '?').trim().charAt(0).toUpperCase(),
                      shield(kind));
      const check = h('span', { class: 'check' + (r.saved || r.here ? ' on' : ''),
                                title: r.here ? 'Your server' : r.saved ? 'In Private Servers' : 'Save in Private Servers',
                                onclick: (e) => { e.stopPropagation(); toggleSaved(r); } });
      const type = icon(r.here ? 'home' : r.password ? 'lock' : r.public ? 'globe' : 'key');
      type.classList.add('type');
      const row = h('div', { class: 'row' + (selected === r.address ? ' sel' : ''), onclick: () => select(r.address) },
        icon('handle'), h('span', { class: 'num' }, i + 1), check, thumb, type,
        h('div', { class: 'name' }, r.name || r.address), subLine(r), h('span', { class: 'vdiv' }),
        h('span', { class: 'state ' + (r.connected && !r.here ? 'connected' : vc) }, stateText(r)));
      row.firstChild.classList.add('handle');
      row.addEventListener('dblclick', () => join(r));
      box.appendChild(row);
    });
  }

  function selectedRow() {
    return rows().find((r) => r.address === selected) || null;
  }
  function select(address) {
    selected = address;
    renderList();
    renderDetails();
    renderActions();
    const r = selectedRow();
    if (r && !r.here) {
      api('/servers/check', { address: r.address }).then((fresh) => {
        if (fresh && !fresh.error && S) {
          const list = tab === 'public' ? S.public : S.saved;
          const i = list.findIndex((x) => x.address === fresh.address);
          if (i >= 0) list[i] = { ...list[i], ...fresh };
          renderList(); renderDetails(); renderActions();
        }
      });
    }
  }

  // ---------------------------------------------------------------- details
  function renderDetails() {
    const d = $('details');
    const r = selectedRow();
    clear(d);
    if (!r) {
      d.appendChild(h('div', { class: 'empty-details' }, 'You can view details by selecting a server', h('br'),
                      'from the list on the left.'));
      return;
    }
    d.appendChild(h('h2', {}, r.name || r.address));
    const addrBits = [r.here ? 'Hosted by you, on this PC' : r.address];
    if (r.server_name && r.server_name !== r.name) addrBits.unshift('"' + r.server_name + '"');
    if (r.version) addrBits.push('inZOI Multiplayer ' + r.version);
    if (r.online && !r.here && r.ping !== undefined && r.ping !== null) addrBits.push(r.ping + ' ms');
    d.appendChild(h('div', { class: 'addr' }, addrBits.join(' · ')));
    if (r.description) d.appendChild(h('div', { class: 'desc' }, r.description));

    const c = r.check;
    let verdict = r.online ? (c ? c.line : '') : "Can't reach this server: " + (r.error || 'offline');
    if (r.connected) verdict = r.here ? "You're playing on your own server." : "You're on this server.";
    if (verdict) d.appendChild(h('div', { class: 'verdict ' + (r.connected ? 'ready' : verdictClass(r)) }, verdict,
      c && c.problems && c.problems.length > 1 ? h('div', { class: 'note' }, c.problems.slice(1).join(' ')) : null));

    if (r.current && S) d.appendChild(connectionBox(r));

    if (r.online) {
      d.appendChild(h('h3', {}, 'About'));
      const facts = h('dl', { class: 'facts' });
      const add = (k, v) => { if (v !== undefined && v !== null && v !== '') facts.append(h('dt', {}, k), h('dd', {}, v)); };
      add('Players', (r.players || 0) + ' of ' + (r.max_players || '?'));
      add('Run by', r.here ? 'You' : r.hosted ? (r.host ? r.host + ' (plays on it too)' : 'a player') : 'a stand-alone server');
      add('Who can join', r.public ? 'Everyone (public)' : 'People with the address (private)');
      add('Password', r.password ? 'Yes' : 'No');
      if (r.world) add('Shared world', `version ${r.world.version}` + (r.world.by ? `, saved by ${r.world.by}` : '') +
        (r.world.time ? ` ${when(r.world.time)}` : ''));
      if (r.uptime) add('Up for', ago(r.uptime));
      if (c && c.source) add('Mods', c.source === 'host' ? "the host's mods" : "everyone's mods, shared");
      d.appendChild(facts);
      if (r.motd) { d.appendChild(h('h3', {}, 'Welcome message')); d.appendChild(h('div', { class: 'desc' }, r.motd)); }
      if (r.names && r.names.length) {
        d.appendChild(h('h3', {}, 'Playing now'));
        d.appendChild(h('div', { class: 'people' }, r.names.map((n) => h('span', { class: 'person' }, n))));
      }
      if (c && c.mods) {
        d.appendChild(h('h3', {}, c.mods.length ? `Mods (${c.mods.length})` : 'Mods'));
        if (!c.mods.length) d.appendChild(h('div', { class: 'note' }, 'This server uses no mods.'));
        c.mods.forEach((m) => {
          const mark = m.state === 'ok' ? '✓' : m.state === 'missing' ? '↓' : '≠';
          const what = m.state === 'ok' ? 'you have it' : m.state === 'missing' ? mb(m.size) + ' to get'
            : 'yours is ' + (m.mine || 'different') + ': ' + mb(m.size);
          d.appendChild(h('div', { class: 'modrow' }, h('span', { class: 'st ' + m.state }, mark),
            h('span', { class: 'mn' }, m.name + (m.version ? ' ' + m.version : '')), h('span', { class: 'ms' }, what)));
        });
        if (c.missing) d.appendChild(h('div', { class: 'note' }, 'When you join, the program offers to download the ' +
          'mods you don\'t have. Without them, some clothes and things won\'t show up for you.'));
        if (c.extra && c.extra.length && c.source === 'everyone') d.appendChild(h('div', { class: 'note' },
          'Your other mods (' + c.extra.slice(0, 6).join(', ') + (c.extra.length > 6 ? '...' : '') +
          ') will be shared with the players there.'));
      }
    }
    if (r.here && S.hosting) d.appendChild(hostingBox(S.hosting));
  }

  function connectionBox(r) {
    const box = h('div', {});
    box.appendChild(h('h3', {}, 'Your connection'));
    const status = S.connected ? 'Connected as ' + S.name : (S.error || 'Connecting...');
    box.appendChild(h('div', { class: 'desc' }, status));
    if (S.save) box.appendChild(h('div', { class: 'note' }, 'Your multiplayer save here: ' + S.save +
      (S.in_game ? '' : '. It loads by itself when you go back to the main menu.')));
    else if (S.connected) box.appendChild(h('div', { class: 'note' }, 'Load the save you want to play here: the program ' +
      'asks whether to make a multiplayer copy of it.'));
    const o = S.mods && S.mods.offer;
    if (o && o.state !== 'done') {
      const n = (o.names || []).length;
      let text = '';
      if (o.state === 'ask' || o.state === 'declined') text = `This server uses ${n} mod${n === 1 ? '' : 's'} you don't have (${mb(o.size)}).`;
      else if (o.state === 'downloading' || o.state === 'waiting') text = (o.state === 'waiting' ? 'Waiting for them to be shared... ' : 'Downloading mods: ') + mb(o.done) + ' of ' + mb(o.total);
      else if (o.state === 'installing') text = 'Installing the mods...';
      else text = o.message || o.state;
      box.appendChild(h('div', { class: 'note' }, text));
      if (o.state === 'downloading' || o.state === 'waiting') {
        const fill = h('div', { class: 'fill' });
        fill.style.width = Math.floor(100 * (o.done || 0) / Math.max(1, o.total || 1)) + '%';
        box.appendChild(h('div', { class: 'bar' }, fill));
      }
    } else if (o && o.state === 'done') {
      box.appendChild(h('div', { class: 'note' }, 'Mods installed. ' + (o.message || '')));
    }
    return box;
  }

  function hostingBox(ho) {
    const box = h('div', {});
    box.appendChild(h('h3', {}, 'Friends join with'));
    if (!ho.addresses.length) box.appendChild(h('div', { class: 'note' }, 'This PC has no address friends can reach ' +
      'yet: install Tailscale and share this PC with them, or forward port ' + ho.port + ' in your router.'));
    ho.addresses.forEach((a) => box.appendChild(h('div', { class: 'addrrow' }, h('div', { class: 'a' }, a.address),
      h('div', { class: 'how' }, a.how))));
    if (ho.settings.password) box.appendChild(h('div', { class: 'note' }, 'and the password you picked.'));
    if (ho.settings.public) {
      box.appendChild(h('h3', {}, 'Public listing'));
      const st = Object.entries(ho.public_status || {});
      if (!st.length) box.appendChild(h('div', { class: 'note' }, 'Public: telling the server lists about it...'));
      st.forEach(([dir, s]) => box.appendChild(h('div', { class: 'note' }, (s.ok && s.reachable ? '✓ Listed' :
        s.ok ? '⚠ Listed, but the list can\'t reach it: ' + (s.error || '') : '⚠ ' + (s.error || 'not listed')) +
        ' (' + dir + ')')));
    }
    return box;
  }

  // ---------------------------------------------------------------- the action column
  function button(label, cls, onclick, disabled, iconName) {
    return h('button', { class: 'btn ' + (cls || ''), onclick, disabled: !!disabled }, iconName ? icon(iconName) : null, label);
  }
  function renderActions() {
    const box = $('action-buttons');
    clear(box);
    const r = selectedRow();
    $('sel-name').textContent = r ? (r.name || r.address) : 'Selected';
    $('sel-sub').textContent = r ? (r.here ? 'Your server' : r.online ? (r.players || 0) + ' playing now' : 'Offline') : 'No server selected';
    if (!r) {
      box.appendChild(button('Join', 'fill', null, true, 'join'));
      box.appendChild(button('Check Again', 'fill', null, true, 'refresh'));
      if (tab === 'private') {
        box.appendChild(button('Add Server', '', addServer, false, 'plus'));
        if (!(S && S.hosting)) box.appendChild(button('Host a Server', '', hostServer, false, 'host'));
      }
    } else if (r.here) {
      if (!r.current) box.appendChild(button('Play Here', 'primary', () => join(r), false, 'join'));
      box.appendChild(button('Server Settings', 'fill', () => openConsole(true), false, 'gear'));
      box.appendChild(button('Stop Hosting', 'danger', stopHosting, false, 'stop'));
    } else {
      const c = r.check || {};
      const can = r.online && c.verdict !== 'incompatible' && c.verdict !== 'full';
      if (r.connected) box.appendChild(button('Connected', 'primary', null, true, 'join'));
      else box.appendChild(button(c.verdict === 'download' ? 'Join and Get Mods' : 'Join', 'primary', () => join(r), !can, 'join'));
      box.appendChild(button('Check Again', 'fill', () => recheck(r), false, 'refresh'));
      if (r.connected) box.appendChild(button(S.admin ? 'Admin Console' : 'Admin Code', '', () => openConsole(false), false, 'admin'));
      if (r.saved) {
        box.appendChild(button('Edit', '', () => editServer(r), false, 'edit'));
        box.appendChild(button('Remove', 'danger', () => removeServer(r), false, 'trash'));
      } else {
        box.appendChild(button('Save to Private', '', () => editServer(r, true), false, 'save'));
      }
    }
    const me = $('me');
    clear(me);
    if (S) {
      const dot = h('span', { class: 'status-dot ' + (S.connected ? 'on' : 'wait') });
      const where = S.connected ? (S.server && S.server.name) || S.current : null;
      me.append(dot, where ? 'Online on ' : (S.error || 'Not connected'), where ? h('b', {}, where) : '',
        where ? ' as ' : '', where ? h('b', {}, S.name) : '', h('br'), 'inZOI Multiplayer ' + S.version);
    }
  }

  async function recheck(r) {
    toast('Checking ' + (r.name || r.address) + '...', 1500);
    const fresh = await api('/servers/check', { address: r.address });
    if (fresh.error && !fresh.address) return toast(fresh.error);
    await poll(true);
  }

  // ---------------------------------------------------------------- joining
  async function join(r) {
    if (r.connected) return;
    if (r.here) {
      const res = await api('/servers/join', { address: r.address });
      if (res.error) return toast(res.error);
      toast('Playing on your own server.');
      return poll(true);
    }
    const c = r.check || {};
    if (!r.online) return toast("Can't reach this server right now.");
    if (c.verdict === 'incompatible') return toast(c.line);
    if (c.verdict === 'full') return toast('This server is full.');
    let password = '';
    if (r.password && !r.password_saved) {
      password = await askText('Password for ' + (r.name || r.address), 'This server needs a password: the person ' +
        'running it can give it to you.', 'Password', '', true);
      if (password === null) return;
    }
    const res = await api('/servers/join', { address: r.address, password, name: r.name });
    if (res.error) return toast(res.error);
    selected = r.address;
    toast('Joining ' + (r.name || r.address) + '...');
    await poll(true);
    let tries = 0;
    const wait = setInterval(async () => {
      tries++;
      await poll(true);
      if (S && S.connected && S.current && sameAddress(S.current, r.address)) {
        clearInterval(wait);
        const o = S.mods && S.mods.offer;
        if (o && o.state === 'ask') askMods(o);
        else toast("You're on " + (r.name || r.address) + (S.in_game ? '.' : '. Go back to the game to play.'), 5000);
      } else if (S && S.error && tries > 2) {
        clearInterval(wait);
        toast(S.error, 7000);
      } else if (tries > 30) {
        clearInterval(wait);
      }
    }, 1000);
  }
  function sameAddress(a, b) {
    const n = (x) => { x = String(x).trim().toLowerCase(); return x.includes(':') ? x : x + ':24242'; };
    return n(a) === n(b);
  }
  function askMods(o) {
    const n = (o.names || []).length;
    openModal(h('div', {},
      h('h2', {}, 'Get the mods this server uses?'),
      h('div', { class: 'lead' }, `${n} mod${n === 1 ? '' : 's'} you don't have (${mb(o.size)}): ` +
        (o.names || []).slice(0, 8).join(', ') + (n > 8 ? '...' : '') +
        '. Without them, some of the other players\' clothes and things won\'t show up for you.'),
      h('div', { class: 'buttons' },
        button('Not Now', '', () => { api('/mods', { key: o.key, answer: 'no' }); closeModal(); }),
        button('Download', 'primary', async () => { await api('/servers/get_mods', {}); closeModal(); toast('Downloading mods...'); poll(true); }))));
  }

  // ---------------------------------------------------------------- saving servers
  function editServer(r, adding) {
    const addr = h('input', { value: r ? r.address : '', placeholder: 'e.g. 100.107.110.78' });
    const name = h('input', { value: r ? (r.name !== r.address ? r.name : '') : '', placeholder: 'Optional' });
    const pw = h('input', { type: 'password', placeholder: r && r.password_saved ? '(saved: type to change)' : 'If the server has one' });
    const err = h('div', { class: 'error-line' });
    const save = async (thenJoin) => {
      const body = { address: addr.value.trim(), name: name.value.trim() };
      if (pw.value) body.password = pw.value;
      if (r && r.saved && !adding) body.old = r.address;
      const res = await api('/servers/save', body);
      if (res.error) { err.textContent = res.error; return; }
      closeModal();
      tab = 'private';
      setTabs();
      selected = res.row ? res.row.address : body.address;
      await poll(true);
      if (thenJoin && res.row) join(res.row);
    };
    openModal(h('div', {},
      h('h2', {}, r && !adding ? 'Edit Server' : 'Add a Server'),
      h('div', { class: 'lead' }, 'The friend who runs the server gives you its address (for a server over Tailscale, ' +
        'the 100.x.x.x address of their PC or Raspberry Pi). Add :port at the end if it isn\'t 24242.'),
      h('label', { class: 'field' }, h('span', {}, 'Address'), addr),
      h('label', { class: 'field' }, h('span', {}, 'Password'), pw),
      h('label', { class: 'field' }, h('span', {}, 'Name in your list'), name),
      err,
      h('div', { class: 'buttons' }, button('Cancel', '', closeModal), button('Save', 'fill', () => save(false)),
        button('Save and Join', 'primary', () => save(true)))));
    addr.focus();
  }
  function addServer() { editServer(null, true); }
  async function removeServer(r) {
    if (!(await confirmBox('Remove ' + (r.name || r.address) + '?', 'It leaves your Private Servers list. You can add it ' +
      'again with its address. (Your multiplayer save for it stays on your PC.)', 'Remove'))) return;
    await api('/servers/remove', { address: r.address });
    selected = null;
    poll(true);
  }

  // ---------------------------------------------------------------- hosting
  function hostServer() {
    const name = h('input', { value: (S && S.name ? S.name + "'s server" : ''), maxlength: 60 });
    const desc = h('textarea', { maxlength: 300, placeholder: 'What it is, who it\'s for (shown on the servers page)' });
    const pw = h('input', { type: 'password', placeholder: 'None', maxlength: 100 });
    const max = h('input', { type: 'number', value: 16, min: 1, max: 64 });
    const port = h('input', { type: 'number', value: 24242, min: 1024, max: 65535 });
    let pub = false;
    const sw = h('button', { type: 'button', class: 'switch', role: 'switch', 'aria-checked': 'false',
      onclick: () => { pub = !pub; sw.classList.toggle('on', pub); sw.setAttribute('aria-checked', String(pub)); } },
      h('span', { class: 'knob' }), h('span', {}, 'Public server',
        h('span', { class: 'what' }, 'Listed in Public Servers for everyone with inZOI Multiplayer. Off: only people ' +
          'you give the address to can join.')));
    const err = h('div', { class: 'error-line' });
    openModal(h('div', {},
      h('h2', {}, 'Host a Server'),
      h('div', { class: 'lead' }, 'Your server runs in this program while it\'s open, and you play on it too. ' +
        'Everyone who joins gets your mods.'),
      h('label', { class: 'field' }, h('span', {}, 'Server name'), name),
      h('label', { class: 'field' }, h('span', {}, 'Description'), desc),
      sw,
      h('label', { class: 'field' }, h('span', {}, 'Password (optional)'), pw),
      h('div', { class: 'inline' }, h('label', { class: 'field' }, h('span', {}, 'Max players'), max),
        h('label', { class: 'field' }, h('span', {}, 'Port'), port)),
      err,
      h('div', { class: 'buttons' }, button('Cancel', '', closeModal), button('Start Hosting', 'primary', async () => {
        const res = await api('/host/start', { name: name.value.trim(), password: pw.value, public: pub,
                                               max_players: Number(max.value) || 16, port: Number(port.value) || 24242 });
        if (res.error) { err.textContent = res.error; return; }
        if (desc.value.trim()) await api('/admin', { op: 'set', local: true, description: desc.value.trim() });
        closeModal();
        tab = 'private';
        setTabs();
        selected = '127.0.0.1:' + (Number(port.value) || 24242);
        toast('Your server is running. Friends join with the addresses shown on the right.', 6000);
        poll(true);
      }))));
    name.focus();
  }
  async function stopHosting() {
    if (!(await confirmBox('Stop hosting?', 'Everyone on your server is disconnected. Your server\'s settings, players ' +
      'and world stay saved for the next time you host.', 'Stop Hosting'))) return;
    await api('/host/stop', {});
    selected = null;
    toast('Your server is stopped.');
    poll(true);
  }

  // ---------------------------------------------------------------- the admin console
  async function openConsole(local) {
    consoleCtx = { local, tab: 'overview', data: null };
    await loadConsole();
  }
  async function loadConsole() {
    if (!consoleCtx) return;
    const res = await api('/admin', { op: 'status', local: consoleCtx.local });
    if (!consoleCtx) return;
    if (!res.ok) return claimBox(res.error);
    consoleCtx.data = res;
    renderConsole();
  }
  function claimBox(why) {
    const code = h('input', { placeholder: 'Admin code', maxlength: 32 });
    const err = h('div', { class: 'error-line' }, why && !/not an admin/.test(why) ? why : '');
    openModal(h('div', {},
      h('h2', {}, 'Admin Console'),
      h('div', { class: 'lead' }, "You're not an admin of this server. If the server's owner gave you its admin " +
        'code, type it here. (The owner finds it in their admin console, or with --admin-code on the server\'s PC.)'),
      h('label', { class: 'field' }, h('span', {}, 'Admin code'), code), err,
      h('div', { class: 'buttons' }, button('Close', '', () => { consoleCtx = null; closeModal(); }),
        button('Become Admin', 'primary', async () => {
          const res = await api('/admin', { op: 'claim', code: code.value.trim() });
          if (!res.ok) { err.textContent = res.error || 'That code didn\'t work.'; return; }
          toast("You're an admin of this server now.");
          loadConsole();
        }))));
    code.focus();
  }
  async function act(op, fields, done) {
    const res = await api('/admin', { op, local: consoleCtx.local, ...(fields || {}) });
    if (!res.ok) { toast(res.error || 'That didn\'t work.'); return null; }
    if (done) toast(done);
    await loadConsole();
    poll(true);
    return res;
  }
  function renderConsole() {
    const st = consoleCtx.data;
    const tabs = [['overview', 'Overview'], ['players', 'Players'], ['settings', 'Settings'], ['world', 'World'], ['log', 'Log']];
    const body = h('div', { class: 'console-body' });
    const head = h('div', { class: 'console-tabs' }, tabs.map(([k, label]) => h('button', {
      class: consoleCtx.tab === k ? 'on' : '', onclick: () => { consoleCtx.tab = k; renderConsole(); } }, label)));
    const view = { overview: consoleOverview, players: consolePlayers, settings: consoleSettings, world: consoleWorld,
                   log: consoleLog }[consoleCtx.tab];
    body.appendChild(view(st));
    openModal(h('div', { style: 'display:flex;flex-direction:column;height:100%' },
      h('h2', {}, 'Admin Console · ' + st.shown_name),
      h('div', { class: 'lead', style: 'margin-bottom:0' }, (consoleCtx.local ? 'Your server, on this PC' : 'You are an admin of this server') +
        ' · inZOI Multiplayer ' + st.version + ' · up for ' + ago(st.uptime)),
      head, body,
      h('div', { class: 'buttons' }, button('Close', 'fill', () => { consoleCtx = null; closeModal(); }))), true);
  }
  function card(k, v) { return h('div', { class: 'card' }, h('div', { class: 'k' }, k), h('div', { class: 'v' }, v)); }
  function consoleOverview(st) {
    const box = h('div', {});
    box.appendChild(h('div', { class: 'cards' }, card('Players online', st.players.length + ' / ' + st.settings.max_players),
      card('Listed as', st.settings.public ? 'Public' : 'Private'), card('Password', st.settings.password ? 'Yes' : 'No'),
      card('Mods', st.mods.count + (st.mods.count ? ' (' + mb(st.mods.size) + ')' : ''))));
    if (st.settings.public) {
      box.appendChild(h('h3', {}, 'Public listing'));
      const s = Object.entries(st.public_status || {});
      if (!s.length) box.appendChild(h('div', { class: 'note' }, st.settings.directories.length || st.directory
        ? 'Telling the server lists about this server...' : 'No server list to be listed on: add one under Settings ' +
          '(a server that keeps the public list, e.g. the address of a Raspberry Pi running with --directory).'));
      s.forEach(([dir, x]) => box.appendChild(h('div', { class: 'note' }, (x.ok && x.reachable ? '✓ Listed by ' :
        '⚠ ') + dir + (x.ok && x.reachable ? ' as ' + x.address : ': ' + (x.error || 'not listed')))));
    }
    box.appendChild(h('h3', {}, 'Message everyone'));
    const say = h('input', { placeholder: 'Shown in everyone\'s chat as "Server"', maxlength: 500 });
    box.appendChild(h('div', { class: 'inline' }, h('label', { class: 'field' }, say),
      button('Send', 'fill', async () => { if (say.value.trim() && await act('say', { text: say.value.trim() }, 'Sent.')) say.value = ''; })));
    box.appendChild(h('h3', {}, 'Admin code'));
    box.appendChild(h('div', { class: 'inline' }, h('div', { class: 'code' }, st.admin_code)));
    box.appendChild(h('div', { class: 'note' }, 'Give this code to someone you trust: typed in their Admin Console, it ' +
      'makes them an admin of this server.'));
    box.appendChild(h('h3', {}, 'Restart'));
    if (st.restartable) {
      const secs = h('select', {}, [30, 60, 120, 300].map((s) => h('option', { value: s }, s + ' seconds')));
      box.appendChild(h('div', { class: 'inline' }, h('label', { class: 'field' }, h('span', {}, 'Warn players'), secs),
        button('Restart Server', 'danger', async () => {
          if (await confirmBox('Restart the server?', 'Everyone gets a warning, their games are saved, and they ' +
            'reconnect by themselves once it\'s back.', 'Restart')) act('restart', { in: Number(secs.value) }, 'Restarting...');
        })));
    } else {
      box.appendChild(h('div', { class: 'note' }, st.hosted ? 'This server runs inside your inZOI Multiplayer program: ' +
        'to restart it, close and open the program.' : 'This server can\'t be restarted from here.'));
    }
    return box;
  }
  function consolePlayers(st) {
    const box = h('div', {});
    box.appendChild(h('h3', {}, 'Online now'));
    const t = h('table', { class: 'table' }, h('tr', {}, h('th', {}, 'Name'), h('th', {}, 'Here since'), h('th', {}, 'Address'), h('th', {}, '')));
    if (!st.players.length) t.appendChild(h('tr', {}, h('td', { colspan: 4 }, 'Nobody is online.')));
    st.players.forEach((p) => t.appendChild(h('tr', {},
      h('td', {}, p.name, p.host ? h('span', { class: 'tag' }, 'host') : null, p.admin ? h('span', { class: 'tag' }, 'admin') : null),
      h('td', {}, when(p.since)), h('td', {}, p.ip),
      h('td', {}, p.host ? '' : [
        h('button', { class: 'mini', onclick: async () => { const why = await askText('Kick ' + p.name, 'They can join again.', 'Reason (optional)', ''); if (why !== null) act('kick', { id: p.id, reason: why }, p.name + ' was kicked.'); } }, 'Kick'),
        h('button', { class: 'mini danger', onclick: async () => { const why = await askText('Ban ' + p.name, 'They can\'t join again until you unban them.', 'Reason (optional)', ''); if (why !== null) act('ban', { id: p.id, reason: why }, p.name + ' is banned.'); } }, 'Ban'),
        p.admin ? h('button', { class: 'mini', onclick: () => act('admin_remove', { id: p.id }, p.name + ' is no longer an admin.') }, 'Remove admin')
          : h('button', { class: 'mini', onclick: () => act('admin_add', { id: p.id }, p.name + ' is an admin now.') }, 'Make admin')]))));
    box.appendChild(t);
    if (st.bans.length) {
      box.appendChild(h('h3', {}, 'Banned'));
      const b = h('table', { class: 'table' }, h('tr', {}, h('th', {}, 'Name'), h('th', {}, 'Reason'), h('th', {}, 'By'), h('th', {}, '')));
      st.bans.forEach((x) => b.appendChild(h('tr', {}, h('td', {}, x.name), h('td', {}, x.reason || ''), h('td', {}, (x.by || '') + ' ' + when(x.time)),
        h('td', {}, h('button', { class: 'mini', onclick: () => act('unban', { id: x.id }, x.name + ' can join again.') }, 'Unban')))));
      box.appendChild(b);
    }
    box.appendChild(h('h3', {}, 'Everyone who has joined'));
    const k = h('table', { class: 'table' }, h('tr', {}, h('th', {}, 'Name'), h('th', {}, 'Last seen'), h('th', {}, '')));
    st.known.filter((p) => !p.online).forEach((p) => k.appendChild(h('tr', {},
      h('td', {}, p.name || p.id, p.admin ? h('span', { class: 'tag' }, 'admin') : null, p.banned ? h('span', { class: 'tag' }, 'banned') : null),
      h('td', {}, when(p.last_seen)),
      h('td', {}, p.banned ? h('button', { class: 'mini', onclick: () => act('unban', { id: p.id }, 'Unbanned.') }, 'Unban')
        : [h('button', { class: 'mini danger', onclick: async () => { const why = await askText('Ban ' + (p.name || p.id), '', 'Reason (optional)', ''); if (why !== null) act('ban', { id: p.id, reason: why }, 'Banned.'); } }, 'Ban'),
           p.admin ? h('button', { class: 'mini', onclick: () => act('admin_remove', { id: p.id }, 'No longer an admin.') }, 'Remove admin')
             : h('button', { class: 'mini', onclick: () => act('admin_add', { id: p.id }, 'Admin now.') }, 'Make admin')]))));
    box.appendChild(k);
    return box;
  }
  function consoleSettings(st) {
    const s = st.settings;
    const name = h('input', { value: s.name, placeholder: st.shown_name, maxlength: 60 });
    const desc = h('textarea', { maxlength: 300 }); desc.value = s.description || '';
    const motd = h('textarea', { maxlength: 300 }); motd.value = s.motd || '';
    const pw = h('input', { value: s.password, maxlength: 100, placeholder: 'None' });
    const max = h('input', { type: 'number', value: s.max_players, min: 1, max: 64 });
    const addr = h('input', { value: s.public_address, placeholder: 'Automatic', maxlength: 200 });
    const dirs = h('input', { value: (s.directories || []).join(', '), placeholder: 'e.g. 100.107.110.78', maxlength: 400 });
    let pub = !!s.public;
    const sw = h('button', { type: 'button', class: 'switch' + (pub ? ' on' : ''), role: 'switch', 'aria-checked': String(pub),
      onclick: () => { pub = !pub; sw.classList.toggle('on', pub); sw.setAttribute('aria-checked', String(pub)); } },
      h('span', { class: 'knob' }), h('span', {}, 'Public server', h('span', { class: 'what' },
        'Listed in Public Servers for everyone. Off: private, only people with the address can join.')));
    const box = h('div', {},
      h('label', { class: 'field' }, h('span', {}, 'Server name'), name),
      h('label', { class: 'field' }, h('span', {}, 'Description (on the servers page)'), desc),
      h('label', { class: 'field' }, h('span', {}, 'Welcome message (when someone joins)'), motd),
      sw,
      h('div', { class: 'inline' }, h('label', { class: 'field' }, h('span', {}, 'Password'), pw),
        h('label', { class: 'field' }, h('span', {}, 'Max players'), max)),
      h('h3', {}, 'Public listing (advanced)'),
      h('label', { class: 'field' }, h('span', {}, 'Address players use to reach this server'), addr,
        h('span', { class: 'hint' }, 'Leave empty: the server list uses the address it sees this server at.')),
      h('label', { class: 'field' }, h('span', {}, 'Server lists to be listed on (comma-separated addresses)'), dirs,
        h('span', { class: 'hint' }, 'Servers that keep the public list, e.g. a Raspberry Pi started with --directory.')),
      h('div', { class: 'buttons' }, button('Save Settings', 'primary', () => act('set', {
        name: name.value.trim(), description: desc.value.trim(), motd: motd.value.trim(), password: pw.value,
        max_players: Number(max.value) || 16, public: pub, public_address: addr.value.trim(),
        directories: dirs.value.split(',').map((x) => x.trim()).filter(Boolean) }, 'Settings saved.'))));
    return box;
  }
  function consoleWorld(st) {
    const box = h('div', {});
    const w = st.world;
    if (!w) {
      box.appendChild(h('div', { class: 'note' }, 'No shared world on this server yet.'));
      return box;
    }
    box.appendChild(h('div', { class: 'cards' }, card('Shared world', w.name || 'unnamed'), card('Version', w.version),
      card('Saved by', w.by || '?'), card('Size', mb(w.size))));
    box.appendChild(h('h3', {}, 'Earlier versions'));
    const t = h('table', { class: 'table' }, h('tr', {}, h('th', {}, 'Version'), h('th', {}, 'Saved by'), h('th', {}, 'When'), h('th', {}, 'Size'), h('th', {}, '')));
    (w.history || []).forEach((v) => t.appendChild(h('tr', {}, h('td', {}, v.version), h('td', {}, v.by || ''), h('td', {}, when(v.time)), h('td', {}, mb(v.size)),
      h('td', {}, v.version === w.version ? 'current' : h('button', { class: 'mini', onclick: async () => {
        if (await confirmBox('Go back to version ' + v.version + '?', 'It becomes the shared world again (as a new ' +
          'version), and everyone is offered to load it. Nothing is deleted: you can go forward again the same way.', 'Go Back')) act('world_restore', { version: v.version }, 'Done.');
      } }, 'Go back to this')))));
    box.appendChild(t);
    return box;
  }
  function consoleLog(st) {
    return h('div', { class: 'log' }, (st.log || []).slice().reverse().join('\n') || 'Nothing yet.');
  }

  // ---------------------------------------------------------------- dialogs
  let modalResolve = null;
  let modalKind = null;              // 'console' (the admin console) or 'dialog' (a question, possibly over it)
  function openModal(content, wide) {
    const m = $('modal');
    clear(m);
    m.className = 'modal' + (wide ? ' wide' : '');
    m.appendChild(content);
    $('modal-back').classList.add('on');
    modalOpen = true;
    modalKind = wide ? 'console' : 'dialog';
  }
  function closeModal() {
    if (modalResolve) { const r = modalResolve; modalResolve = null; r(null); }
    if (modalKind === 'dialog' && consoleCtx && consoleCtx.data) { renderConsole(); return; }   // back to the console
    $('modal-back').classList.remove('on');
    modalOpen = false;
    modalKind = null;
  }
  function typing() {
    const a = document.activeElement;
    return !!a && $('modal').contains(a) && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName);
  }
  function askText(title, lead, label, value, secret) {
    return new Promise((resolve) => {
      const input = h('input', { value: value || '', type: secret ? 'password' : 'text' });
      const ok = () => { modalResolve = null; closeModal(); resolve(input.value); };
      input.addEventListener('keydown', (e) => { if (e.key === 'Enter') ok(); });
      openModal(h('div', {}, h('h2', {}, title), lead ? h('div', { class: 'lead' }, lead) : null,
        h('label', { class: 'field' }, h('span', {}, label), input),
        h('div', { class: 'buttons' }, button('Cancel', '', closeModal), button('OK', 'primary', ok))));
      modalResolve = resolve;
      input.focus();
    });
  }
  function confirmBox(title, lead, yes) {
    return new Promise((resolve) => {
      openModal(h('div', {}, h('h2', {}, title), h('div', { class: 'lead' }, lead),
        h('div', { class: 'buttons' }, button('Cancel', '', closeModal),
          button(yes, 'primary', () => { modalResolve = null; closeModal(); resolve(true); }))));
      modalResolve = (v) => resolve(!!v);
    });
  }

  // ---------------------------------------------------------------- page plumbing
  function setTabs() {
    document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('on', t.dataset.tab === tab));
  }
  document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => {
    tab = t.dataset.tab;
    selected = null;
    setTabs();
    renderAll();
  }));
  const FILTERS = ['f-status', 'f-compat', 'f-mods', 'f-access', 'f-type'];
  ['search', ...FILTERS].forEach((id) => $(id).addEventListener('input', renderList));
  $('reset').addEventListener('click', () => {
    $('search').value = '';
    FILTERS.forEach((id) => { $(id).value = 'all'; });
    sortBy = 'players';
    renderList();
  });
  $('sort').addEventListener('click', () => {
    sortBy = SORTS[(SORTS.indexOf(sortBy) + 1) % SORTS.length];
    toast('Sorted by ' + sortBy, 1500);
    renderList();
  });
  $('add-server').addEventListener('click', addServer);
  $('host-server').addEventListener('click', hostServer);
  async function back() {
    if (modalOpen) { consoleCtx = null; return closeModal(); }
    const r = await api('/page/close', {});
    if (r.error) window.close();
  }
  $('back').addEventListener('click', back);
  $('back-label').addEventListener('click', back);
  addEventListener('keydown', (e) => { if (e.key === 'Escape') back(); });
  $('modal-back').addEventListener('mousedown', (e) => { if (e.target === $('modal-back') && !consoleCtx) closeModal(); });

  function renderAll() {
    renderList();
    renderDetails();
    renderActions();
  }
  // After a refresh, redraw only what changed: a click landing while its button is being replaced would be lost.
  const drawn = {};
  function changed(key, value) {
    const s = JSON.stringify(value);
    if (drawn[key] === s) return false;
    drawn[key] = s;
    return true;
  }
  function renderChanged() {
    const r = selectedRow();
    const filters = ['search', ...FILTERS].map((id) => $(id).value).concat(sortBy);
    if (changed('list', [tab, selected, filters, rows(), S.public_at, S.directories])) renderList();
    if (changed('details', [r, S.connected, S.error, S.mods, S.save, S.hosting, S.in_game])) renderDetails();
    if (changed('actions', [r, tab, S.admin, S.connected, !!S.hosting, S.error, S.name, S.server && S.server.name])) renderActions();
  }
  async function poll(force) {
    if (polling && !force) return;
    polling = true;
    const res = await api('/servers/state', {});
    polling = false;
    if (res.error && !res.saved) {
      $('list-note').textContent = res.error;
      return;
    }
    const first = !S;
    S = res;
    if (first && !S.saved.length && !S.hosting && S.public.length === 0) tab = 'private';
    if (first && S.current) {                                      // start on the server we're on
      const onPublic = S.public.some((r) => r.current);
      tab = onPublic ? 'public' : 'private';
      const here = rows().find((r) => r.current);
      if (here) selected = here.address;
      setTabs();
    }
    if (first || force) renderAll(); else renderChanged();
    if (consoleCtx && consoleCtx.data && modalKind === 'console' && consoleCtx.tab !== 'settings' && !typing()) loadConsole();
  }
  poll(true);
  setInterval(() => { if (!document.hidden) poll(); }, 2500);
})();
