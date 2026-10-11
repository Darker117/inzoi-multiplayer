/**
 * app.js  --  inZOI Multiplayer panel.
 * Window management is handled by window.js (loaded before this file); see the `wf` global.
 *
 * Everything comes from the companion app on this PC (client/companion.py) over XMLHttpRequest to 127.0.0.1:24243.
 * Gameface quirks: no fetch, POST + JSON body only (query strings get mangled), non-2xx answers arrive with an
 * empty body, so the companion always answers 200 and puts errors in {"error": "..."}.
 */
(function () {
    'use strict';

    var API = 'http://127.0.0.1:24243';
    var root = (window.wf && wf.root) || document.getElementById('app-root');   // wf is missing in a plain browser preview
    var $ = function (id) { return document.getElementById(id); };
    var dot = document.querySelector('#title-text .dot');
    var label = $('title-label');
    var lastChatKey = '', unread = 0, seenUpTo = 0, lastStatus = null, busy = false;

    function post(path, body, cb) {
        var x = new XMLHttpRequest();
        x.open('POST', API + path, true);
        x.setRequestHeader('Content-Type', 'application/json');
        x.timeout = 4000;
        x.onreadystatechange = function () {
            if (x.readyState !== 4) { return; }
            var res = null;
            try { res = JSON.parse(x.responseText); } catch (e) { res = null; }
            if (cb) { cb(res); }
        };
        x.send(JSON.stringify(body || {}));
    }

    function el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.appendChild(document.createTextNode(String(text))); }
        return e;
    }

    function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

    // "Use_BarBell_Row" -> "barbell row", "Co_Friendship_G04_Start" -> "friendship"
    function prettyAction(bag) {
        if (!bag) { return ''; }
        var s = bag.replace(/^(Co_|Object_|Use_|Next_|Self_|Do_)/, '').replace(/_(G|B)\d+.*$/, '')
            .replace(/_(Start|Loop|End)\d*$/, '').replace(/_/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2');
        return s.toLowerCase();
    }

    // ------------------------------------------------------------------ rendering
    function renderPlayers(s) {
        var box = $('players');
        clear(box);
        if (!s.players.length) {
            box.appendChild(el('div', 'empty', s.connected ? 'Nobody else is online right now.' : 'Not connected yet.'));
            return;
        }
        s.players.forEach(function (p) {
            var row = el('div', 'player');
            var who = el('div', 'who');
            who.appendChild(el('div', 'name', p.name));
            var where = p.here ? 'Here with you' : (p.away ? 'In another city' : 'On the way...');
            var doing = prettyAction(p.doing);
            var sub = el('div', 'sub' + (p.here ? ' here' : ''), (p.zoi ? p.zoi + ' - ' : '') + where +
                (doing ? ' - ' + doing : ''));
            who.appendChild(sub);
            row.appendChild(who);
            var join = el('span', 'btn' + (p.here ? '' : ' off'), 'Join');
            join.addEventListener('click', function () {
                if (!p.here) { return; }
                post('/join', { id: p.id }, function (r) { showNotice(r && r.error); });
            });
            row.appendChild(join);
            box.appendChild(row);
        });
    }

    function renderChat(s) {
        var lines = s.chat.slice(-12);
        var newest = lines.length ? lines[lines.length - 1].time : 0;
        unread = 0;
        if (root._minimized) {
            s.chat.forEach(function (m) { if (!m.mine && !m.system && m.time > seenUpTo) { unread++; } });
        } else {
            seenUpTo = Math.max(seenUpTo, newest);
        }
        var key = newest + '|' + lines.length;
        if (key === lastChatKey) { return; }
        lastChatKey = key;
        var box = $('chat');
        clear(box);
        lines.forEach(function (m) {
            var row = el('div', 'msg' + (m.mine ? ' mine' : '') + (m.system ? ' system' : ''));
            if (!m.system) { row.appendChild(el('span', 'from', m.name)); }
            row.appendChild(document.createTextNode(m.text));
            box.appendChild(row);
        });
    }

    function renderTitle(s) {
        var n = s ? s.players.length : 0;
        dot.className = 'dot' + (s && s.connected ? ' on' : (s ? ' wait' : ''));
        var text = 'inZOI Multiplayer';
        if (s && s.connected) { text += n ? ' - ' + n + (n === 1 ? ' friend' : ' friends') + ' online' : ' - online'; }
        clear(label);
        label.appendChild(document.createTextNode(text));
        if (unread && root._minimized) { label.appendChild(el('span', 'badge', unread + ' new')); }
    }

    function showNotice(text) {
        var n = $('notice');
        n.style.display = text ? 'block' : 'none';
        clear(n);
        if (text) { n.appendChild(document.createTextNode(text)); }
    }

    var NOT_RUNNING = "The inZOI Multiplayer program isn't running. Open \"inZOI Multiplayer.exe\" and keep its window open while you play.";

    function render(s) {
        if (!s) {
            $('status').textContent = NOT_RUNNING;
            renderTitle(null);
            return;
        }
        var st = s.connected ? 'Online as ' + s.name + ' on ' + s.server
            : 'Connecting to ' + s.server + ' as ' + s.name + '...';
        if (s.mod !== 'running') { st += ' (getting the game ready)'; }
        $('status').textContent = st;
        if (s.notice) { showNotice(s.notice); }
        renderPlayers(s);
        renderChat(s);
        renderTitle(s);
        renderMods(s.mods);
        renderSave(s.save);
        renderBox('update', s.update && s.update.box);
        renderBox('world', s.world && s.world.box);
        $('s-version').textContent = 'inZOI Multiplayer ' + s.version +
            (s.save && s.save.name ? ' - multiplayer save: ' + s.save.name : '');
        $('s-sync').className = 'toggle' + (s.sync_time ? ' on' : '');
        $('s-sync').style.display = s.host ? 'none' : '';
        if (!lastStatus) {
            $('s-name').value = s.name;
            $('s-server').value = s.server;
            $('s-port').value = s.port;
            seenUpTo = s.chat.length ? s.chat[s.chat.length - 1].time : 0;
        }
        lastStatus = s;
    }

    function poll() {
        if (busy) { return; }
        busy = true;
        post('/status', {}, function (s) { busy = false; render(s); });
    }

    // ------------------------------------------------------------------ input
    function send() {
        var input = $('say');
        var text = input.value.replace(/^\s+|\s+$/g, '');
        if (!text) { return; }
        input.value = '';
        post('/chat', { text: text }, function (r) { showNotice(r && r.error); poll(); });
    }
    $('send').addEventListener('click', send);
    $('say').addEventListener('keydown', function (e) {
        if (e.keyCode === 13) { send(); e.preventDefault(); }
        e.stopPropagation();                         // typing must not drive the game camera / hotkeys
    });
    $('s-save').addEventListener('click', function () {
        var body = { name: $('s-name').value, server: $('s-server').value };
        if ($('s-port').value) { body.port = $('s-port').value; }
        if ($('s-password').value) { body.password = $('s-password').value; }
        post('/settings', body, function (r) {
            showNotice(r ? (r.error || 'Saved - reconnecting...') : NOT_RUNNING);
        });
    });
    $('s-sync').addEventListener('click', function () {
        var on = $('s-sync').className.indexOf(' on') < 0;
        $('s-sync').className = 'toggle' + (on ? ' on' : '');
        post('/settings', { sync_time: on }, function (r) { showNotice(r ? r.error : NOT_RUNNING); });
    });
    ['s-name', 's-server', 's-port', 's-password'].forEach(function (id) {
        $(id).addEventListener('keydown', function (e) { e.stopPropagation(); });
    });

    // ------------------------------------------------------------------ questions: the multiplayer save, updates
    var shownBoxes = {};
    function renderBox(name, box) {                             // name: 'save' or 'update' (also its endpoint)
        var wrap = $(name + '-box'), buttons = $(name + '-buttons');
        wrap.style.display = box ? 'block' : 'none';
        if (!box) { shownBoxes[name] = null; return; }
        $(name + '-text').textContent = box.text;
        if (shownBoxes[name] === box.key + box.text) { return; }   // keep the buttons while they're being clicked
        shownBoxes[name] = box.key + box.text;
        clear(buttons);
        box.buttons.forEach(function (b) {
            var btn = el('span', 'btn', b.label);
            btn.addEventListener('click', function () {
                post('/' + name, { key: box.key, action: b.id }, function (r) {
                    if (!r) { showNotice(NOT_RUNNING); } else { shownBoxes[name] = null; poll(); }
                });
            });
            buttons.appendChild(btn);
        });
    }
    function renderSave(sv) { renderBox('save', sv && sv.box); }

    // ------------------------------------------------------------------ mods
    var modsKey = null;
    function sizeText(n) {
        n = n || 0;
        return n < 104857600 ? (n / 1048576).toFixed(1) + ' MB' : Math.round(n / 1048576) + ' MB';
    }
    function renderMods(m) {
        m = m || {};
        var o = m.offer, text = '', ask = false, bar = false;
        var who = o ? (o.from.length ? o.from.join(', ') : 'someone') : '';
        modsKey = o ? o.key : null;
        if (!m.source) {
            text = 'Waiting for the server...';
        } else if (!o || o.state === 'done') {
            text = m.count ? "You have all the mods " + (m.source === 'host' ? 'the host uses.' : 'your friends use.')
                : (m.source === 'host' ? 'The host uses no mods.' : 'Nobody has shared any mods yet.');
            if (o) { text = 'Mods installed. ' + o.message; }
        } else if (o.state === 'ask' || o.state === 'declined' || o.state === 'error') {
            text = (m.source === 'host' ? 'The host (' + who + ') uses ' : 'Your friends (' + who + ') use ') +
                o.names.length + (o.names.length === 1 ? ' mod' : ' mods') + " you don't have (" + sizeText(o.size) +
                "). Without them, some of their clothes or things won't show up for you. Download them?";
            if (o.state === 'declined') { text = 'You chose not to download ' + o.names.length + ' mod(s) (' + sizeText(o.size) + ').'; }
            if (o.state === 'error') { text = 'The download stopped: ' + o.message; }
            ask = true;
        } else if (o.state === 'downloading' || o.state === 'waiting') {
            text = o.state === 'waiting' ? 'Waiting for ' + who + ' to finish sharing them...'
                : 'Downloading ' + o.names.length + ' mod(s): ' + sizeText(o.done) + ' of ' + sizeText(o.total);
            bar = true;
        } else if (o.state === 'installing') {
            text = 'Installing...';
        } else {
            text = o.message;
        }
        var frac = o && o.total ? o.done / o.total : 0;
        if (m.sharing && !bar) {
            frac = m.sharing.done / Math.max(1, m.sharing.total);
            text += ' Sharing your mods with friends: ' + sizeText(m.sharing.done) + ' of ' + sizeText(m.sharing.total);
            bar = true;
        }
        if (bar) { text += ' (' + Math.floor(100 * frac) + '%)'; }
        $('m-state').textContent = text;
        $('m-buttons').style.display = ask ? 'block' : 'none';
        $('m-yes').textContent = o && o.state === 'error' ? 'Try again' : 'Download';
        $('m-no').style.display = o && o.state === 'ask' ? '' : 'none';
        $('m-bar').style.display = bar ? 'block' : 'none';
        $('m-fill').style.width = Math.floor(100 * Math.min(1, frac)) + '%';
        var tab = $('tab-mods'), alert = o && o.state === 'ask';
        tab.textContent = alert ? 'Mods (' + o.names.length + ')' : 'Mods';
        tab.className = 'tab' + (tab.className.indexOf(' on') >= 0 ? ' on' : '') + (alert ? ' alert' : '');
        var list = $('m-list');
        clear(list);
        if (!(m.list || []).length) { list.appendChild(el('div', 'empty', 'None yet.')); }
        (m.list || []).forEach(function (x) {
            var row = el('div', 'mod');
            row.appendChild(el('span', x.have ? 'ok' : 'no', x.have ? 'OK' : '--'));
            row.appendChild(document.createTextNode(x.name));
            list.appendChild(row);
        });
    }
    function answerMods(yes) {
        if (!modsKey) { return; }
        post('/mods', { key: modsKey, answer: yes ? 'yes' : 'no' }, function (r) {
            if (!r) { showNotice(NOT_RUNNING); } else { renderMods(r); }
        });
    }
    $('m-yes').addEventListener('click', function () { answerMods(true); });
    $('m-no').addEventListener('click', function () { answerMods(false); });

    // ------------------------------------------------------------------ houses
    function houseRow(title, sub, label, on, cb) {
        var row = el('div', 'house');
        var t = el('div', 't', title);
        if (sub) { t.appendChild(el('div', 's', sub)); }
        row.appendChild(t);
        var b = el('span', 'btn' + (on ? '' : ' off'), label);
        if (on) { b.addEventListener('click', cb); }
        row.appendChild(b);
        return row;
    }

    function loadHouses() {
        post('/houses', {}, function (h) {
            if (!h || h.error) { showNotice(h ? h.error : NOT_RUNNING); return; }
            var mine = $('h-mine'), shared = $('h-shared');
            clear(mine);
            clear(shared);
            if (!h.library.length) { mine.appendChild(el('div', 'empty', 'No saved houses in your library yet.')); }
            h.library.slice(0, 6).forEach(function (x) {
                var sharing = h.sharing === x.title;
                mine.appendChild(houseRow(x.title, x.size + (x.beds ? ', ' + x.beds + ' bed' : ''),
                    sharing ? 'Shared' : 'Share', !sharing, function () {
                        post('/share', { id: x.id }, function (r) {
                            showNotice(r ? (r.error || 'Shared "' + r.name + '" with everyone.') : null);
                            loadHouses();
                        });
                    }));
            });
            if (!h.shared.length) { shared.appendChild(el('div', 'empty', 'Nobody has shared a house yet.')); }
            h.shared.forEach(function (x) {
                shared.appendChild(houseRow(x.name, 'by ' + x.by + (x.lot ? ' - goes on ' + x.lot : ''),
                    x.added ? 'Added' : 'Add to library', !x.added,
                    function () {
                        showNotice('Downloading ' + x.name + '...');
                        post('/add_house', { owner: x.owner }, function (r) {
                            showNotice(r ? (r.error || 'Added "' + r.title + '" to your library. Place it in Build mode.') : null);
                            loadHouses();
                        });
                    }));
            });
        });
    }
    var housesTimer = null;
    function showTab(name) {
        var tabs = document.querySelectorAll('.tab');
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].className = 'tab' + (tabs[i].getAttribute('data-tab') === name ? ' on' : '') +
                (tabs[i].className.indexOf(' alert') >= 0 ? ' alert' : '');
        }
        ['people', 'houses', 'mods', 'settings'].forEach(function (p) {
            $('pane-' + p).className = 'pane' + (p === name ? ' on' : '');
        });
        if (housesTimer) { clearInterval(housesTimer); housesTimer = null; }
        if (name === 'houses') { loadHouses(); housesTimer = setInterval(loadHouses, 5000); }
    }
    (function () {
        var tabs = document.querySelectorAll('.tab');
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].addEventListener('click', function (e) { showTab(e.currentTarget.getAttribute('data-tab')); });
        }
    })();

    poll();
    setInterval(function () { if (!root._minimized) { poll(); } }, 1000);
    setInterval(function () { if (root._minimized) { poll(); } }, 3000);
})();
