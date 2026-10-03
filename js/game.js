/* PvZ Craft - Infinite Craft, but Plants vs. Zombies. */
(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  // ------------------------------------------------------------- storage --
  const store = {
    get(key, fallback) {
      try {
        const v = localStorage.getItem('pvzcraft:' + key);
        return v == null ? fallback : JSON.parse(v);
      } catch (e) { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem('pvzcraft:' + key, JSON.stringify(value)); } catch (e) { /* private mode */ }
    },
    del(key) {
      try { localStorage.removeItem('pvzcraft:' + key); } catch (e) { /* ignore */ }
    },
  };

  // ------------------------------------------------------------ entities --
  const BASE = {};
  for (const e of window.ENTITIES) {
    BASE[e.id] = Object.assign({ icon: `assets/icons/${e.id}.png`, kind: e.goal ? 'goal' : 'element' }, e);
  }

  const pairKey = (a, b) => (a < b ? a + '+' + b : b + '+' + a);

  const RECIPES = {};
  const MADE_FROM = {}; // result -> list of [a, b]
  for (const [mode, cfg] of Object.entries(window.MODES)) {
    RECIPES[mode] = {};
    for (const [a, b, r] of cfg.recipes) {
      for (const id of [a, b, r]) if (!BASE[id]) console.warn('unknown id in recipe', id);
      RECIPES[mode][pairKey(a, b)] = r;
      (MADE_FROM[r] = MADE_FROM[r] || []).push([a, b]);
    }
  }

  // ---------------------------------------------------------------- state --
  let mode = null;
  let S = null;           // per-mode save state
  const fresh = new Set(); // ids discovered this session (NEW badge)
  let soundOn = store.get('sound', true);

  function blankState(m) {
    return { discovered: window.MODES[m].start.slice(), how: {}, hybrids: {}, board: [], won: false };
  }

  function loadState(m) {
    const s = store.get('state:' + m, null);
    if (!s || !Array.isArray(s.discovered)) return blankState(m);
    return Object.assign(blankState(m), s);
  }

  function save() {
    if (!mode) return;
    S.board = $$('.board > .item').map(el => ({ id: el.dataset.id, x: parseFloat(el.style.left), y: parseFloat(el.style.top) }));
    store.set('state:' + mode, S);
  }

  function ent(id) {
    return BASE[id] || (S && S.hybrids[id]) || null;
  }

  // ---------------------------------------------------------------- sound --
  const audioCache = {};
  function play(name) {
    if (!soundOn || !name) return;
    if (Array.isArray(name)) name = name[Math.floor(Math.random() * name.length)];
    try {
      let a = audioCache[name];
      if (!a) a = audioCache[name] = new Audio(`assets/sounds/${name}.ogg`);
      const c = a.cloneNode();
      c.volume = 0.55;
      c.play().catch(() => {});
    } catch (e) { /* no audio */ }
  }

  // ------------------------------------------------------------- hybrids --
  function hash(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }

  const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
  function head(n) {
    const m = /^[^aeiouy]*[aeiouy]+[^aeiouy]?/i.exec(n);
    return m ? m[0] : n;
  }
  function tail(n) {
    const m = /[^aeiouy]*[aeiouy]+[^aeiouy]*$/i.exec(n);
    return m ? m[0] : n;
  }

  function hybridName(A, B) {
    const wa = A.split(' '), wb = B.split(' ');
    let name;
    if (A === B) return null;
    if (wb.length > 1) name = wa[0] + ' ' + wb[wb.length - 1];
    else if (wa.length > 1) name = wa[0] + ' ' + B;
    else if (A.includes('-')) name = A.split('-')[0] + '-' + (B.length <= 7 ? B : tail(B)).toLowerCase();
    else if (B.includes('-')) name = head(A) + '-' + B.split('-').pop();
    else {
      name = cap(head(A) + tail(B).toLowerCase());
      if (name.length < 4 || name === A || name === B) name = A + ' ' + B;
    }
    if (name.length > 22) name = wa[0] + ' ' + wb[wb.length - 1];
    if (name === A || name === B || name.length < 3) return null;
    // no "Zombie Zombie" or "Sunsun"
    const parts = name.toLowerCase().split(/[ -]/);
    if (new Set(parts).size < parts.length) return null;
    if (!/[ -]/.test(name) && head(A).toLowerCase() === tail(B).toLowerCase()) return null;
    return name;
  }

  function allNames() {
    const names = new Set();
    for (const e of Object.values(BASE)) if (e.mode === mode) names.add(e.name.toLowerCase());
    for (const e of Object.values(S.hybrids)) names.add(e.name.toLowerCase());
    return names;
  }

  function rootIcon(id) {
    const e = ent(id);
    return e.kind === 'hybrid' ? e.base : e.icon;
  }

  function makeHybrid(a, b) {
    const key = pairKey(a, b);
    const h = hash(mode + ':' + key);
    const id = 'hy_' + h.toString(36);
    if (S.hybrids[id]) return id;
    let [x, y] = h & 1 ? [a, b] : [b, a];
    if (ent(x).kind === 'hybrid' && ent(y).kind !== 'hybrid') [x, y] = [y, x];
    const A = ent(x).name, B = ent(y).name;
    const adjectives = window.MODES[mode].adjectives;
    const names = allNames();
    let name = hybridName(A, B);
    if (!name || names.has(name.toLowerCase())) {
      const base = name || A;
      for (let i = 0; i < adjectives.length; i++) {
        const cand = adjectives[(h + i) % adjectives.length] + ' ' + base;
        if (!names.has(cand.toLowerCase()) && !base.startsWith(adjectives[(h + i) % adjectives.length])) { name = cand; break; }
      }
    }
    if (!name || names.has(name.toLowerCase())) {
      let n = 2;
      while (names.has(`${A} ${n}`.toLowerCase())) n++;
      name = `${A} ${n}`;
    }
    const hues = [0, 0, 35, 90, 150, 200, 260, 320];
    S.hybrids[id] = {
      id, name, kind: 'hybrid', mode,
      parents: [x, y],
      base: rootIcon(x),
      badge: x === y ? null : rootIcon(y),
      hue: hues[(h >>> 3) % hues.length],
      tip: x === y ? `Twice the ${A}, twice the fun.` : `A mysterious mix of ${A} and ${B}.`,
      stats: [], flavor: '',
    };
    return id;
  }

  function combine(a, b) {
    return RECIPES[mode][pairKey(a, b)] || makeHybrid(a, b);
  }

  // ------------------------------------------------------------- rendering --
  function chip(id, cls = '') {
    const e = ent(id);
    const el = document.createElement('div');
    el.className = `item ${e.kind} ${cls}`.trim();
    el.dataset.id = id;
    const ic = document.createElement('span');
    ic.className = 'ic';
    const img = new Image();
    img.src = e.kind === 'hybrid' ? e.base : e.icon;
    img.alt = '';
    img.draggable = false;
    if (e.kind === 'hybrid' && e.hue) img.style.filter = `hue-rotate(${e.hue}deg) saturate(1.3)`;
    if (e.kind === 'hybrid' && !e.badge) img.style.transform = 'scale(1.15)';
    ic.appendChild(img);
    if (e.kind === 'hybrid' && e.badge) {
      const bd = new Image();
      bd.src = e.badge;
      bd.className = 'badge';
      bd.alt = '';
      bd.draggable = false;
      ic.appendChild(bd);
    }
    el.appendChild(ic);
    el.appendChild(document.createTextNode(e.name));
    el.title = e.tip || '';
    return el;
  }

  const board = $('#board');
  const items = $('#items');
  let filter = 'all';

  function renderSidebar() {
    const q = $('#search').value.trim().toLowerCase();
    const sort = $('#sort').value;
    let list = S.discovered.filter(id => ent(id));
    if (sort === 'name') list = list.slice().sort((x, y) => ent(x).name.localeCompare(ent(y).name));
    items.textContent = '';
    for (const id of list) {
      const e = ent(id);
      if (q && !e.name.toLowerCase().includes(q)) continue;
      if (filter !== 'all' && e.kind !== filter) continue;
      items.appendChild(chip(id, fresh.has(id) ? 'new' : ''));
    }
    $('#search').placeholder = `Search (${S.discovered.length} items)…`;
    renderMeter();
  }

  function goals() {
    return Object.values(BASE).filter(e => e.mode === mode && e.goal);
  }

  function renderMeter() {
    const g = goals();
    const have = g.filter(e => S.discovered.includes(e.id)).length;
    $('#goal-count').textContent = `${have} / ${g.length} ${window.MODES[mode].noun}`;
    $('#meter-fill').style.width = (100 * have / g.length) + '%';
    return { have, total: g.length };
  }

  function addToBoard(id, x, y, cls) {
    const el = chip(id, cls);
    el.style.left = x + 'px';
    el.style.top = y + 'px';
    board.appendChild(el);
    $('#board-help').style.display = 'none';
    // keep inside the board once we know the size
    const bw = board.clientWidth, bh = board.clientHeight;
    const w = el.offsetWidth, h = el.offsetHeight;
    el.style.left = Math.max(0, Math.min(bw - w, x)) + 'px';
    el.style.top = Math.max(0, Math.min(bh - h, y)) + 'px';
    return el;
  }

  function ring(x, y) {
    const r = document.createElement('div');
    r.className = 'ring';
    r.style.left = x + 'px';
    r.style.top = y + 'px';
    board.appendChild(r);
    setTimeout(() => r.remove(), 600);
  }

  // ---------------------------------------------------------------- toasts --
  function toast({ icon, t1, t2, t3, cls = '', ms = 3200 }) {
    const el = document.createElement('div');
    el.className = 'toast ' + cls;
    el.innerHTML = `${icon ? '<img alt="">' : ''}<div><div class="t1"></div><div class="t2"></div><div class="t3"></div></div>`;
    if (icon) el.querySelector('img').src = icon;
    el.querySelector('.t1').textContent = t1 || '';
    el.querySelector('.t2').textContent = t2 || '';
    el.querySelector('.t3').textContent = t3 || '';
    const stack = $('#toasts');
    stack.appendChild(el);
    while (stack.children.length > 3) stack.firstChild.remove();
    setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 300); }, ms);
  }

  // ------------------------------------------------------------ discovery --
  function discover(id, a, b) {
    if (S.discovered.includes(id)) return false;
    S.discovered.push(id);
    S.how[id] = [a, b];
    fresh.add(id);
    const e = ent(id);
    const cfg = window.MODES[mode];
    if (e.kind === 'goal') {
      play(cfg.sounds.goal);
      toast({ icon: e.icon, t1: `New ${mode === 'plant' ? 'plant' : 'zombie'}!`, t2: e.name, t3: e.tip || firstSentence(e.flavor) });
    } else {
      play(cfg.sounds.discover);
      toast({ icon: e.kind === 'hybrid' ? e.base : e.icon, t1: e.kind === 'hybrid' ? 'New hybrid!' : 'New discovery!', t2: e.name, t3: e.tip, ms: 2200 });
    }
    const { have, total } = renderMeter();
    if (have === total && !S.won) {
      S.won = true;
      play(cfg.sounds.win);
      setTimeout(() => toast({
        icon: mode === 'plant' ? BASE.twin_sunflower.icon : BASE.dr_zomboss.icon,
        t1: 'You did it!', t2: `All ${total} ${cfg.noun.toLowerCase()} found!`,
        t3: 'Keep going - there are endless hybrids to discover.', cls: 'win', ms: 7000,
      }), 900);
    }
    return true;
  }

  const firstSentence = s => (s || '').split(/(?<=[.!?])\s/)[0];

  // --------------------------------------------------------------- dragging --
  let drag = null;

  function boardRect() { return board.getBoundingClientRect(); }

  function startDrag(ev, id, fromEl, fromBoard) {
    const r = fromEl.getBoundingClientRect();
    const ghost = chip(id, 'ghost held');
    ghost.style.left = r.left + 'px';
    ghost.style.top = r.top + 'px';
    document.body.appendChild(ghost);
    if (fromBoard) fromEl.remove();
    drag = { id, ghost, dx: ev.clientX - r.left, dy: ev.clientY - r.top, target: null, pointerId: ev.pointerId };
    document.body.classList.add('dragging');
    moveDrag(ev);
  }

  function itemUnder(x, y) {
    for (const el of document.elementsFromPoint(x, y)) {
      if (el.closest && el.closest('.board > .item')) return el.closest('.board > .item');
    }
    return null;
  }

  function moveDrag(ev) {
    if (!drag) return;
    drag.ghost.style.left = (ev.clientX - drag.dx) + 'px';
    drag.ghost.style.top = (ev.clientY - drag.dy) + 'px';
    const t = itemUnder(ev.clientX, ev.clientY);
    if (t !== drag.target) {
      if (drag.target) drag.target.classList.remove('target');
      drag.target = t;
      if (t) t.classList.add('target');
    }
    const tr = $('#trash').getBoundingClientRect();
    $('#trash').classList.toggle('hot', ev.clientX >= tr.left && ev.clientX <= tr.right && ev.clientY >= tr.top && ev.clientY <= tr.bottom);
  }

  function endDrag(ev) {
    if (!drag) return;
    const { id, ghost, target } = drag;
    drag = null;
    document.body.classList.remove('dragging');
    const trashHot = $('#trash').classList.contains('hot');
    $('#trash').classList.remove('hot');
    const br = boardRect();
    const gr = ghost.getBoundingClientRect();
    ghost.remove();
    const overBoard = ev.clientX >= br.left && ev.clientX <= br.right && ev.clientY >= br.top && ev.clientY <= br.bottom;
    if (!overBoard || trashHot) {
      if (target) target.classList.remove('target');
      play('tap');
      save();
      return;
    }
    if (target) {
      target.classList.remove('target');
      const tr = target.getBoundingClientRect();
      const other = target.dataset.id;
      target.remove();
      const result = combine(id, other);
      const cx = (tr.left + tr.right) / 2 - br.left;
      const cy = (tr.top + tr.bottom) / 2 - br.top;
      const el = addToBoard(result, cx, cy, 'pop');
      el.style.left = Math.max(0, Math.min(br.width - el.offsetWidth, cx - el.offsetWidth / 2)) + 'px';
      el.style.top = Math.max(0, Math.min(br.height - el.offsetHeight, cy - el.offsetHeight / 2)) + 'px';
      ring(cx, cy);
      play(window.MODES[mode].sounds.combine);
      if (discover(result, id, other)) renderSidebar();
    } else {
      addToBoard(id, gr.left - br.left, gr.top - br.top);
      play('tap');
    }
    save();
  }

  // pending press: becomes a drag once the pointer moves far enough
  let press = null;

  function onPressStart(ev) {
    if (ev.button !== undefined && ev.button !== 0) return;
    const el = ev.target.closest('.item');
    if (!el || el.classList.contains('ghost')) return;
    const fromBoard = !!el.closest('.board');
    press = { el, id: el.dataset.id, x: ev.clientX, y: ev.clientY, fromBoard, type: ev.pointerType };
    if (fromBoard) {
      ev.preventDefault();
      startDrag(ev, press.id, el, true);
      press = null;
    }
  }

  window.addEventListener('pointerdown', onPressStart);
  window.addEventListener('pointermove', ev => {
    if (drag) { ev.preventDefault(); moveDrag(ev); return; }
    if (press) {
      const dx = ev.clientX - press.x, dy = ev.clientY - press.y;
      const far = Math.hypot(dx, dy) > 6;
      // on touch, vertical swipes in the sidebar scroll the list instead
      if (far && (press.type === 'mouse' || Math.abs(dx) > Math.abs(dy))) {
        startDrag(ev, press.id, press.el, false);
        fresh.delete(press.id);
        press.el.classList.remove('new');
        press = null;
      } else if (far) {
        press = null;
      }
    }
  }, { passive: false });
  window.addEventListener('pointerup', ev => {
    if (drag) { endDrag(ev); return; }
    if (press) {
      // a tap on a sidebar item drops it onto the lawn
      const p = press;
      press = null;
      fresh.delete(p.id);
      p.el.classList.remove('new');
      spawnSomewhere(p.id);
    }
  });
  window.addEventListener('pointercancel', () => {
    press = null;
    if (drag) {
      // put it back where it was
      const br = boardRect(), gr = drag.ghost.getBoundingClientRect();
      if (drag.target) drag.target.classList.remove('target');
      drag.ghost.remove();
      addToBoard(drag.id, gr.left - br.left, gr.top - br.top);
      drag = null;
      document.body.classList.remove('dragging');
      save();
    }
  });

  function spawnSomewhere(id) {
    const bw = board.clientWidth, bh = board.clientHeight;
    const x = bw * (0.25 + Math.random() * 0.45);
    const y = bh * (0.2 + Math.random() * 0.55);
    const el = addToBoard(id, x, y, 'pop');
    play('tap');
    save();
    return el;
  }

  board.addEventListener('dblclick', ev => {
    const el = ev.target.closest('.item');
    if (!el) return;
    addToBoard(el.dataset.id, parseFloat(el.style.left) + 18, parseFloat(el.style.top) + 18, 'pop');
    save();
  });
  board.addEventListener('contextmenu', ev => {
    const el = ev.target.closest('.item');
    if (!el) return;
    ev.preventDefault();
    el.remove();
    save();
  });
  items.addEventListener('contextmenu', ev => {
    const el = ev.target.closest('.item');
    if (!el) return;
    ev.preventDefault();
    openAlmanac(el.dataset.id);
  });

  // --------------------------------------------------------------- almanac --
  function openAlmanac(selectId) {
    const cfg = window.MODES[mode];
    $('#almanac-title').textContent = mode === 'plant' ? 'Suburban Almanac - Plants' : 'Suburban Almanac - Zombies';
    const grid = $('#almanac-grid');
    grid.textContent = '';
    const list = goals().concat(Object.values(BASE).filter(e => e.mode === mode && !e.goal));
    for (const e of list) {
      const known = S.discovered.includes(e.id);
      const c = document.createElement('button');
      c.className = 'alm-cell' + (known ? '' : ' locked');
      c.dataset.id = e.id;
      c.title = known ? e.name : '???';
      c.innerHTML = '<img alt="">';
      c.querySelector('img').src = e.icon;
      c.addEventListener('click', () => showCard(e.id));
      grid.appendChild(c);
    }
    $('#almanac').hidden = false;
    showCard(selectId && ent(selectId) ? selectId : (S.discovered.slice().reverse().find(id => BASE[id] && BASE[id].goal) || cfg.start[0]));
  }

  function showCard(id) {
    const e = ent(id);
    const known = S.discovered.includes(id);
    $$('.alm-cell').forEach(c => c.classList.toggle('sel', c.dataset.id === id));
    const card = $('#almanac-card');
    card.textContent = '';
    const img = new Image();
    img.className = 'big';
    img.src = e.kind === 'hybrid' ? e.base : e.icon;
    if (!known) img.style.filter = 'brightness(0) opacity(.35)';
    card.appendChild(img);
    const h = document.createElement('h3');
    h.textContent = known ? e.name : '???';
    card.appendChild(h);
    const tip = document.createElement('div');
    tip.className = 'tip';
    tip.textContent = known ? (e.tip || '') : 'Not discovered yet. Keep combining!';
    card.appendChild(tip);
    if (known && e.stats && e.stats.length) {
      const ul = document.createElement('ul');
      ul.className = 'stats';
      for (const s of e.stats) { const li = document.createElement('li'); li.textContent = s; ul.appendChild(li); }
      card.appendChild(ul);
    }
    if (known && e.flavor) {
      const p = document.createElement('p');
      p.className = 'flavor';
      p.textContent = e.flavor;
      card.appendChild(p);
    }
    const how = known && S.how[id];
    if (how) {
      const r = document.createElement('div');
      r.className = 'recipe';
      r.append('Made from ', chip(how[0]), '+', chip(how[1]));
      card.appendChild(r);
    } else if (known && window.MODES[mode].start.includes(id)) {
      const r = document.createElement('div');
      r.className = 'recipe';
      r.textContent = 'A starting element.';
      card.appendChild(r);
    }
  }

  $$('[data-close]').forEach(b => b.addEventListener('click', () => { $('#almanac').hidden = true; }));
  $('#almanac').addEventListener('click', ev => { if (ev.target.id === 'almanac') $('#almanac').hidden = true; });
  document.addEventListener('keydown', ev => { if (ev.key === 'Escape') $('#almanac').hidden = true; });

  // ------------------------------------------------------------------ hint --
  function hint() {
    const known = new Set(S.discovered);
    const options = [];
    for (const [a, b, r] of window.MODES[mode].recipes) {
      if (!known.has(r) && known.has(a) && known.has(b)) options.push([a, b, r]);
    }
    if (!options.length) {
      toast({ t1: 'Hint', t2: 'Nothing left!', t3: 'Every recipe is discovered. Go make weird hybrids!' });
      return;
    }
    // prefer recipes that lead toward an undiscovered goal
    const goalish = options.filter(([, , r]) => BASE[r].goal);
    const pool = goalish.length && Math.random() < 0.6 ? goalish : options;
    const [a, b, r] = pool[Math.floor(Math.random() * pool.length)];
    play('bleep');
    toast({ icon: BASE[a].icon, t1: 'Crazy Dave says...', t2: `Try ${BASE[a].name} + ${BASE[b].name}`, t3: BASE[r].goal ? 'Something big might grow out of it!' : 'Could be useful...', ms: 4500 });
  }

  // ------------------------------------------------------------ mode switch --
  function enterMode(m) {
    mode = m;
    S = loadState(m);
    fresh.clear();
    const cfg = window.MODES[m];
    const game = $('#game');
    game.className = 'screen active ' + m;
    $('#title').classList.remove('active');
    $('#mode-label').textContent = '- ' + cfg.title;
    board.style.backgroundImage = `url(${cfg.background})`;
    $('#goal-icon').src = m === 'plant' ? BASE.sunflower.icon : BASE.z_zombie.icon;
    $('#filter-goal').textContent = cfg.noun;
    $$('.board > .item').forEach(el => el.remove());
    $('#board-help').style.display = '';
    requestAnimationFrame(() => {
      for (const it of S.board || []) if (ent(it.id)) addToBoard(it.id, it.x, it.y);
    });
    renderSidebar();
    store.set('lastMode', m);
    play(m === 'plant' ? 'plant' : 'groan');
  }

  function goHome() {
    save();
    mode = null;
    $('#game').classList.remove('active');
    $('#title').classList.add('active');
    renderTitleProgress();
  }

  function renderTitleProgress() {
    for (const m of Object.keys(window.MODES)) {
      const s = store.get('state:' + m, null);
      const total = Object.values(BASE).filter(e => e.mode === m && e.goal).length;
      const have = s ? s.discovered.filter(id => BASE[id] && BASE[id].goal).length : 0;
      const el = $(`[data-progress="${m}"]`);
      el.textContent = s ? `${have} / ${total} found · ${s.discovered.length} items` : 'New game';
    }
  }

  $$('.mode-card').forEach(b => b.addEventListener('click', () => enterMode(b.dataset.mode)));
  $('#btn-home').addEventListener('click', goHome);
  $('#btn-almanac').addEventListener('click', () => openAlmanac());
  $('#goal-meter').addEventListener('click', () => openAlmanac());
  $('#btn-hint').addEventListener('click', hint);
  $('#btn-clear').addEventListener('click', () => {
    $$('.board > .item').forEach(el => el.remove());
    $('#board-help').style.display = '';
    play('shovel');
    save();
  });
  $('#btn-reset').addEventListener('click', () => {
    if (!confirm(`Reset ${window.MODES[mode].title}? You will lose everything you discovered in this mode.`)) return;
    store.del('state:' + mode);
    enterMode(mode);
  });
  const soundBtn = $('#btn-sound');
  soundBtn.classList.toggle('off', !soundOn);
  soundBtn.addEventListener('click', () => {
    soundOn = !soundOn;
    store.set('sound', soundOn);
    soundBtn.classList.toggle('off', !soundOn);
    play('tap');
  });
  $('#search').addEventListener('input', renderSidebar);
  $('#sort').addEventListener('change', renderSidebar);
  $$('#filters .chip-btn').forEach(b => b.addEventListener('click', () => {
    filter = b.dataset.filter;
    $$('#filters .chip-btn').forEach(x => x.classList.toggle('active', x === b));
    renderSidebar();
  }));
  window.addEventListener('beforeunload', save);
  window.addEventListener('resize', () => {
    const bw = board.clientWidth, bh = board.clientHeight;
    for (const el of $$('.board > .item')) {
      el.style.left = Math.max(0, Math.min(bw - el.offsetWidth, parseFloat(el.style.left))) + 'px';
      el.style.top = Math.max(0, Math.min(bh - el.offsetHeight, parseFloat(el.style.top))) + 'px';
    }
  });

  renderTitleProgress();

  // expose a little for debugging / tests
  window.PvZCraft = { combine: (a, b) => combine(a, b), enterMode, state: () => S, ent };
})();
