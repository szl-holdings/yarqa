/* Copyright 2026 SZL Holdings — SPDX-License-Identifier: Apache-2.0
   yarqa Space front-end. Sovereign: global THREE r160 (vendored, zero CDN).
   LIVE/SAMPLE describe returned data; failed requests remain UNAVAILABLE. */
'use strict';

const motionQuery = window.matchMedia('(prefers-reduced-motion:reduce)');
let REDUCED = motionQuery.matches;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const escapeText = value => String(value ?? '').replace(/[&<>"']/g, character =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
function publicLink(value, label) {
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) throw new Error('unsupported source URL');
    return `<a href="${escapeText(url.href)}" target="_blank" rel="noopener noreferrer">${escapeText(label)}</a>`;
  } catch (_) { return `<span class="invalid-link">${escapeText(label)} · URL unavailable</span>`; }
}

/* Universal fetch hardening: every request carries an AbortController timeout so
   a hung/slow endpoint can NEVER produce a perpetual spinner. On timeout or any
   error the caller's catch fires and the panel honest-degrades to UNAVAILABLE/
   unreachable — never blank, never a forever-loading state. */
const API_TIMEOUT_MS = 8000;
async function api(path, opts) {
  const o = Object.assign({}, opts);
  let ctl = null, timer = null;
  if (typeof AbortController !== 'undefined' && !o.signal) {
    ctl = new AbortController();
    o.signal = ctl.signal;
    timer = setTimeout(() => { try { ctl.abort(); } catch (e) {} }, o.timeoutMs || API_TIMEOUT_MS);
  }
  try {
    const r = await fetch(path, o);
    if (!r.ok) throw new Error(path + ' -> ' + r.status);
    return await r.json();
  } finally {
    if (timer) clearTimeout(timer);
  }
}
function setBadge(el, state) {
  if (!el) return;
  const label = state === 'LIVE' || state === 'SAMPLE' ? state : 'UNAVAILABLE';
  el.textContent = label;
  el.className = 'badge ' + label.toLowerCase();
}

/* compartment palette */
const PALETTE = ['#40e0c5','#ffb13f','#5ad1ff','#c89bff','#ff6b8f','#9ef0c0',
  '#ffd166','#7c9cff','#ff9e6d','#6df0d6','#d28bff','#8be0a0','#ffc24d','#62c4ff','#ff85a8','#a0f0c8'];
const colorFor = (id) => PALETTE[((id % PALETTE.length) + PALETTE.length) % PALETTE.length];

/* ===================== TAB NAV ===================== */
function activate(tab, focusPanel = false) {
  if (!['flow', 'agent', 'chain', 'forecast', 'live'].includes(tab)) return;
  document.body.dataset.tab = tab;
  $$('.panel').forEach(p => p.classList.toggle('is-active', p.id === 'panel-' + tab));
  $$('.tab').forEach(t => {
    const selected = t.dataset.go === tab;
    t.classList.toggle('is-active', selected);
    t.setAttribute('aria-selected', String(selected));
    t.tabIndex = selected ? 0 : -1;
  });
  $$('.sheet-item').forEach(t => {
    const selected = t.dataset.go === tab;
    t.classList.toggle('is-active', selected);
    if (selected) t.setAttribute('aria-current', 'page');
    else t.removeAttribute('aria-current');
  });
  closeSheet(false);
  if (focusPanel) $('#panel-' + tab).focus();
  if (tab === 'flow' && Flow.ready) Flow.onResize();
  if (tab === 'flow' && !Flow.loaded) Flow.refresh();
  if (tab === 'agent' && !Agent.loaded) Agent.run();
  if (tab === 'chain' && !Chain.loaded) Chain.build();
  if (tab === 'forecast' && !Forecast.loaded) Forecast.refresh();
  if (tab === 'live' && !Live.loaded) Live.refresh();
}
$$('[data-go]').forEach(b => b.addEventListener('click', event => {
  event.preventDefault();
  activate(b.dataset.go, !b.classList.contains('tab'));
}));
$('#tabs').addEventListener('keydown', event => {
  const tabs = $$('.tab');
  const current = tabs.indexOf(document.activeElement);
  if (current < 0) return;
  const index = { ArrowLeft: (current + tabs.length - 1) % tabs.length,
    ArrowRight: (current + 1) % tabs.length, Home: 0, End: tabs.length - 1 }[event.key];
  if (index === undefined) return;
  event.preventDefault();
  tabs.forEach((tab, i) => { tab.tabIndex = i === index ? 0 : -1; });
  tabs[index].focus(); // Manual activation: Enter/Space uses the native button click.
});

/* mobile sheet */
const sheet = $('#sheet'), backdrop = $('#sheetBackdrop'), fab = $('#fab');
function sheetBackground(inert) {
  $$('#main, .topbar, .tabs, .szl-space-skip-link, szl-space-ecosystem-bar').forEach(element => { element.inert = inert; });
  fab.inert = inert;
}
function openSheet() {
  sheet.hidden = false; backdrop.hidden = false; fab.setAttribute('aria-expanded', 'true');
  sheetBackground(true);
  ($('.sheet-item[data-go="' + document.body.dataset.tab + '"]') || $('#closeSheet')).focus();
}
function closeSheet(restoreFocus = true) {
  const wasOpen = !sheet.hidden;
  sheet.hidden = true; backdrop.hidden = true; fab.setAttribute('aria-expanded', 'false');
  sheetBackground(false);
  if (wasOpen && restoreFocus) fab.focus();
}
fab.addEventListener('click', () => sheet.hidden ? openSheet() : closeSheet());
backdrop.addEventListener('click', () => closeSheet());
$('#closeSheet').addEventListener('click', () => closeSheet());
sheet.addEventListener('keydown', event => {
  if (event.key === 'Escape') { event.preventDefault(); closeSheet(); return; }
  if (event.key !== 'Tab') return;
  const controls = $$('button, a[href]', sheet), first = controls[0], last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});
/* Crossing to the desktop layout hides the modal sheet with CSS. Close it and
   hand focus to the selected desktop tab (the FAB is hidden at this width), so
   keyboard focus never stays inside a hidden subtree. */
function focusDesktopTab() {
  const tab = $('.tab[aria-selected="true"]') || $('.tab');
  if (!tab) return;
  $$('.tab').forEach(other => { other.tabIndex = other === tab ? 0 : -1; }); // one roving tab stop
  tab.dataset.focusRestored = '';
  tab.addEventListener('blur', () => { delete tab.dataset.focusRestored; }, { once: true });
  tab.focus();
}
window.addEventListener('resize', () => {
  if (window.innerWidth > 860 && !sheet.hidden) { closeSheet(false); focusDesktopTab(); }
});

/* ===================== HEALTH ===================== */
async function health() {
  try {
    const h = await api('/healthz');
    $('#hdot').className = 'hdot ok';
    $('#htxt').textContent = 'healthz ok · yarqa ' + h.yarqa_version;
  } catch (e) {
    $('#hdot').className = 'hdot bad';
    $('#htxt').textContent = 'healthz unreachable';
  }
}

/* ===================== TAB 1: FLOW COMPARTMENTS 3D ===================== */
const Flow = {
  ready: false, loaded: false, renderer: null, scene: null, camera: null,
  group: null, raf: 0, align: 0.2, topk: 8, dirty: true, motionPaused: REDUCED,
  init() {
    const canvas = $('#scene');
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color('#080b12');
    this.scene.fog = new THREE.FogExp2('#080b12', 0.018);
    this.camera = new THREE.PerspectiveCamera(46, 1, 0.1, 400);
    this.camera.position.set(0, 9, 15);
    this.camera.lookAt(0, 0.4, 0);
    this.scene.add(new THREE.AmbientLight('#3a4a72', 0.7));
    const key = new THREE.DirectionalLight('#cfe0ff', 1.1); key.position.set(6, 12, 9); this.scene.add(key);
    const rim = new THREE.PointLight('#40e0c5', 0.8, 60); rim.position.set(-10, 4, 6); this.scene.add(rim);
    this.group = new THREE.Group(); this.scene.add(this.group);
    this.onResize();
    window.addEventListener('resize', () => this.onResize());
    // simple drag-orbit
    let drag = false, px = 0, py = 0, rotY = 0, rotX = 0;
    const dn = e => { drag = true; const t = e.touches ? e.touches[0] : e; px = t.clientX; py = t.clientY; };
    const mv = e => { if (!drag) return; const t = e.touches ? e.touches[0] : e; rotY += (t.clientX - px) * 0.006; rotX += (t.clientY - py) * 0.006; rotX = Math.max(-1.1, Math.min(1.1, rotX)); px = t.clientX; py = t.clientY; this.group.rotation.y = rotY; this.group.rotation.x = rotX; this.dirty = true; };
    const up = () => { drag = false; };
    canvas.addEventListener('mousedown', dn); window.addEventListener('mousemove', mv); window.addEventListener('mouseup', up);
    canvas.addEventListener('touchstart', dn, { passive: true }); canvas.addEventListener('touchmove', mv, { passive: true }); canvas.addEventListener('touchend', up);
    canvas.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
      event.preventDefault();
      if (event.key === 'ArrowLeft') this.group.rotation.y -= 0.12;
      if (event.key === 'ArrowRight') this.group.rotation.y += 0.12;
      if (event.key === 'ArrowUp') this.group.rotation.x = Math.max(-1.1, this.group.rotation.x - 0.12);
      if (event.key === 'ArrowDown') this.group.rotation.x = Math.min(1.1, this.group.rotation.x + 0.12);
      rotY = this.group.rotation.y; rotX = this.group.rotation.x; this.dirty = true;
    });
    this.ready = true;
    this.animate();
  },
  onResize() {
    if (!this.renderer || !this.camera) return;
    const c = $('#scene'); const w = c.clientWidth || 1, h = c.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
    this.dirty = true;
  },
  animate() {
    const tick = () => {
      this.raf = requestAnimationFrame(tick);
      if (!this.loaded || document.hidden || document.body.dataset.tab !== 'flow') return;
      if (!this.motionPaused && this.group) { this.group.rotation.y += 0.0016; this.dirty = true; }
      if (this.dirty) { this.renderer.render(this.scene, this.camera); this.dirty = false; }
    };
    tick();
  },
  build(data) {
    const geometries = new Set(), materials = new Set();
    this.group.children.forEach(child => {
      if (child.geometry) geometries.add(child.geometry);
      (Array.isArray(child.material) ? child.material : [child.material]).filter(Boolean).forEach(material => materials.add(material));
    });
    while (this.group.children.length) this.group.remove(this.group.children[0]);
    geometries.forEach(geometry => geometry.dispose()); materials.forEach(material => material.dispose());
    const { centers, velocities, labels, nx, ny } = data;
    const cx = (nx - 1) / 2, cy = (ny - 1) / 2;
    const used = new Set();
    // glyphs: a small box per cell + an arrow line for velocity, colored by label
    const boxGeo = new THREE.BoxGeometry(0.34, 0.34, 0.34);
    const matCache = {};
    for (let i = 0; i < centers.length; i++) {
      const lab = labels[i]; used.add(lab);
      const col = colorFor(lab);
      if (!matCache[lab]) matCache[lab] = new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.25, roughness: 0.4, metalness: 0.1 });
      const m = new THREE.Mesh(boxGeo, matCache[lab]);
      const x = (centers[i][0] - cx) * 0.85, z = (centers[i][1] - cy) * 0.85;
      const vmag = Math.hypot(velocities[i][0], velocities[i][1]);
      const yh = (vmag - 0.3) * 1.2;   // center around 0 so the field fills frame
      m.position.set(x, yh, z);
      this.group.add(m);
      // velocity arrow
      const v = velocities[i]; const sc = 0.8;
      const pts = [new THREE.Vector3(x, yh, z), new THREE.Vector3(x + v[0] * sc, yh, z + v[1] * sc)];
      const lg = new THREE.BufferGeometry().setFromPoints(pts);
      const lm = new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.7 });
      this.group.add(new THREE.Line(lg, lm));
    }
    // base grid plane
    const span = Math.max(nx, ny) + 2;
    const grid = new THREE.GridHelper(span, span, '#1d2950', '#121a33');
    grid.position.y = -3.0; this.group.add(grid);
    // legend
    const leg = $('#flowLegend'); leg.innerHTML = '';
    [...used].sort((a, b) => a - b).slice(0, 16).forEach(id => {
      const d = document.createElement('div'); d.className = 'lg';
      d.innerHTML = `<span class="sw" style="background:${colorFor(id)}"></span>c${escapeText(id)}`;
      leg.appendChild(d);
    });
    this.dirty = true;
  },
  evidence(data) {
    $('#flowTable').innerHTML = '<caption>Top compartments · returned API summary, ordered by cell count</caption>' +
      '<thead><tr><th scope="col">Compartment</th><th scope="col">Cells</th><th scope="col">Mean velocity</th></tr></thead><tbody>' +
      data.top_compartments.map(c => `<tr><th scope="row">c${escapeText(c.id)}</th><td>${escapeText(c.n_cells)}</td><td>${escapeText(c.mean_velocity.map(value => value.toFixed(4)).join(', '))}</td></tr>`).join('') + '</tbody>';
  },
  async refresh() {
    try {
      const d = await api(`/api/compartments?align_threshold=${this.align}&top_k=${this.topk}`);
      setBadge($('#flowBadge'), d.state);
      $('#flowCount').textContent = `${d.n_compartments} compartments`;
      $('#flowDigest').textContent = d.receipt_digest;
      this.evidence(d);
      try {
        $('#scene').hidden = false;
        if (!this.ready) this.init();
        this.build(d);
        $('#flowRenderState').textContent = '3D view available · same response as the numerical summary';
      } catch (_) {
        $('#scene').hidden = true;
        $('#flowRenderState').textContent = '3D view unavailable · returned numerical evidence remains accessible below';
      }
      this.loaded = true;
    } catch (e) {
      this.loaded = false; setBadge($('#flowBadge'), 'UNAVAILABLE'); $('#flowCount').textContent = 'unreachable'; $('#flowDigest').textContent = 'UNAVAILABLE';
      $('#scene').hidden = true; $('#flowLegend').innerHTML = '';
      $('#flowTable').innerHTML = '<caption>Compartment data UNAVAILABLE</caption>';
      $('#flowRenderState').textContent = 'Compartment endpoint unavailable · no result is substituted';
    }
  }
};
function paintMotion() {
  $('#toggleMotion').textContent = Flow.motionPaused ? 'Resume rotation' : 'Pause rotation';
  $('#toggleMotion').setAttribute('aria-pressed', String(Flow.motionPaused));
}
$('#toggleMotion').addEventListener('click', () => { Flow.motionPaused = !Flow.motionPaused; paintMotion(); });
if (motionQuery.addEventListener) motionQuery.addEventListener('change', event => {
  REDUCED = event.matches; Flow.motionPaused = REDUCED; Flow.dirty = true; paintMotion();
});
$('#align').addEventListener('input', e => { Flow.align = +e.target.value; $('#alignOut').textContent = Flow.align.toFixed(2); });
$('#align').addEventListener('change', () => Flow.refresh());
$('#topk').addEventListener('input', e => { Flow.topk = +e.target.value; $('#kOut').textContent = Flow.topk; });
$('#topk').addEventListener('change', () => Flow.refresh());

/* ===================== TAB 2: AGENTIC LOOP ===================== */
const Agent = {
  loaded: false,
  async run() {
    const log = $('#agentLog'); log.innerHTML = '<div class="step"><span class="smeta dim">sensing field…</span></div>';
    try {
      const d = await api(`/api/agentic?align_threshold=${Flow.align}&n_obs=6`);
      setBadge($('#agentBadge'), d.state);
      $('#agentExperts').textContent = `${d.n_experts} experts (compartments)`;
      log.innerHTML = '';
      d.steps.forEach((s, i) => {
        const el = document.createElement('div'); el.className = 'step';
        const wt = s.topk_weights.length ? ` · weights [${escapeText(s.topk_weights.join(', '))}]` : '';
        const decisionClass = ['ALLOW', 'DENY'].includes(s.decision) ? s.decision : 'UNAVAILABLE';
        el.innerHTML = `<span class="sidx">#${i}</span>
          <span class="smeta">obs <b>[${escapeText(s.observation.map(x=>x.toFixed(2)).join(', '))}]</b> →
          route c<b>${escapeText(s.routed_compartment)}</b> (score ${escapeText(s.route_score.toFixed(3))}, top-k [${escapeText(s.topk_compartments.join(', '))}]${wt})<br>
          receipt <span class="dim">${escapeText(s.yarqa_receipt_digest.slice(0,24))}…</span></span>
          <span class="dec ${decisionClass}">${escapeText(s.decision)}</span>`;
        if (REDUCED) el.style.animation = 'none';
        log.appendChild(el);
      });
      this.loaded = true;
    } catch (e) { this.loaded = false; setBadge($('#agentBadge'), 'UNAVAILABLE'); $('#agentExperts').textContent = '— experts'; log.innerHTML = '<div class="step"><span class="smeta">loop unreachable</span></div>'; }
  }
};
$('#runLoop').addEventListener('click', () => Agent.run());

/* ===================== TAB 3: RECEIPT CHAIN ===================== */
const Chain = {
  loaded: false, json: null,
  render(links, verify) {
    if (!verify || typeof verify.ok !== 'boolean') { this.unavailable(); return; }
    const v = $('#chainView'); v.innerHTML = '';
    const broken = verify.first_broken_index;
    links.forEach(l => {
      const el = document.createElement('div');
      const isBroken = broken !== null && l.index >= broken;
      el.className = 'link' + (isBroken ? ' broken' : '');
      el.innerHTML = `<div class="lh"><b>link #${escapeText(l.index)} · c${escapeText(l.routed_compartment)} · ${escapeText(l.decision)} · score ${escapeText(l.route_score)}</b><span class="okdot"></span></div>
        <div class="ld"><span class="prevd">prev ${escapeText(l.prev_digest.slice(0,18))}…</span> → <b>${escapeText(l.digest.slice(0,18))}…</b></div>`;
      v.appendChild(el);
    });
    const vd = $('#chainVerdict');
    if (verify.ok === true) { vd.textContent = `✓ intact · ${verify.n_links} links`; vd.className = 'verdict ok'; }
    else { vd.textContent = `✗ TAMPER at link ${verify.first_broken_index}`; vd.className = 'verdict bad'; }
  },
  unavailable() {
    this.loaded = false; this.json = null; setBadge($('#chainBadge'), 'UNAVAILABLE');
    $('#chainVerdict').textContent = 'Verification UNAVAILABLE';
    $('#chainVerdict').className = 'verdict unavailable';
    $('#chainView').innerHTML = '';
  },
  async build() {
    try {
      const d = await api(`/api/chain?n_obs=5&align_threshold=${Flow.align}`);
      setBadge($('#chainBadge'), d.state);
      this.json = d.chain_json;
      this.render(d.links, d.verify);
      this.loaded = true;
    } catch (e) { this.json = null; this.unavailable(); }
  },
  async verify() {
    if (!this.json) return this.build();
    try {
    const d = await api('/api/chain/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ chain_json: this.json }) });
    const links = JSON.parse(this.json).links.map(l => ({ index: l.index, prev_digest: l.prev_digest, digest: l.digest, decision: l.step.decision, routed_compartment: l.step.routed_compartment, route_score: (+l.step.route_score).toFixed(4) }));
    this.render(links, d.verify);
    } catch (_) { this.unavailable(); }
  },
  async tamper() {
    if (!this.json) await this.build();
    if (!this.json) return;
    try {
    const n = JSON.parse(this.json).links.length;
    const idx = Math.floor(n / 2);
    const d = await api('/api/chain/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ chain_json: this.json, tamper_index: idx, tamper_field: 'route_score' }) });
    const links = JSON.parse(this.json).links.map(l => ({ index: l.index, prev_digest: l.prev_digest, digest: l.digest, decision: l.step.decision, routed_compartment: l.step.routed_compartment, route_score: (+l.step.route_score).toFixed(4) }));
    this.render(links, d.verify);
    } catch (_) { this.unavailable(); }
  }
};
$('#buildChain').addEventListener('click', () => Chain.build());
$('#verifyChain').addEventListener('click', () => Chain.verify());
$('#tamperChain').addEventListener('click', () => Chain.tamper());

/* ===================== TAB 4: FORECAST ===================== */
const Forecast = {
  loaded: false, hz: 6,
  draw(history, projected) {
    const cv = $('#fcChart'); const dpr = Math.min(devicePixelRatio, 2);
    const W = cv.clientWidth, H = 240; cv.width = W * dpr; cv.height = H * dpr;
    const ctx = cv.getContext('2d'); ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, W, H);
    const all = history.concat(projected);
    const ts = all.map(p => p.t), mf = all.map(p => p.mean_flow);
    const tmin = Math.min(...ts), tmax = Math.max(...ts);
    const vmin = Math.min(...mf) * 0.95, vmax = Math.max(...mf) * 1.05;
    const pad = 38;
    const X = t => pad + (t - tmin) / (tmax - tmin || 1) * (W - pad * 1.5);
    const Y = v => H - pad - (v - vmin) / (vmax - vmin || 1) * (H - pad * 1.6);
    // axes
    ctx.strokeStyle = '#1d2950'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad, H - pad); ctx.lineTo(W - pad * 0.5, H - pad); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(pad, pad * 0.6); ctx.lineTo(pad, H - pad); ctx.stroke();
    ctx.fillStyle = '#aab7c9'; ctx.font = '11px ui-monospace,monospace';
    ctx.fillText('mean flow (m/s)', pad + 2, pad * 0.5);
    ctx.fillText('t →', W - pad * 1.4, H - pad + 14);
    // DATA solid
    ctx.strokeStyle = '#40e0c5'; ctx.lineWidth = 2.4; ctx.beginPath();
    history.forEach((p, i) => { const x = X(p.t), y = Y(p.mean_flow); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    ctx.stroke();
    // PROJECTED dashed (connect from last DATA point)
    ctx.strokeStyle = '#c89bff'; ctx.lineWidth = 2.2; ctx.setLineDash([6, 5]); ctx.beginPath();
    const last = history[history.length - 1];
    ctx.moveTo(X(last.t), Y(last.mean_flow));
    projected.forEach(p => ctx.lineTo(X(p.t), Y(p.mean_flow)));
    ctx.stroke(); ctx.setLineDash([]);
    // points
    all.forEach(p => { ctx.fillStyle = p.kind === 'DATA' ? '#40e0c5' : '#c89bff'; ctx.beginPath(); ctx.arc(X(p.t), Y(p.mean_flow), 3, 0, 7); ctx.fill(); });
  },
  table(history, projected) {
    const t = $('#fcTable');
    let h = '<caption>Returned history and PROJECTED values · mean flow in m/s</caption><thead><tr><th scope="col">t</th><th scope="col">kind</th><th scope="col">compartments</th><th scope="col">mean flow</th></tr></thead><tbody>';
    history.concat(projected).forEach(p => {
      h += `<tr class="${p.kind === 'PROJECTED' ? 'proj' : ''}"><td>${escapeText(p.t)}</td><td>${escapeText(p.kind)}</td><td>${escapeText(p.n_compartments)}</td><td>${escapeText(p.mean_flow.toFixed(4))}</td></tr>`;
    });
    t.innerHTML = h + '</tbody>';
  },
  async refresh() {
    try {
      const d = await api(`/api/forecast?align_threshold=${Flow.align}&horizon=${this.hz}`);
      setBadge($('#fcBadge'), d.state);
      this.draw(d.history, d.projected);
      this.table(d.history, d.projected);
      this.loaded = true;
    } catch (e) {
      this.loaded = false; setBadge($('#fcBadge'), 'UNAVAILABLE');
      $('#fcTable').innerHTML = '<caption>Forecast data UNAVAILABLE</caption>';
      const canvas = $('#fcChart');
      if (canvas.getContext) canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
    }
  }
};
$('#hz').addEventListener('input', e => { Forecast.hz = +e.target.value; $('#hzOut').textContent = Forecast.hz; });
$('#refreshFc').addEventListener('click', () => Forecast.refresh());

/* ===================== TAB 5: LIVE DATA ===================== */
const Live = {
  loaded: false,
  async refresh(force) {
    const wrap = $('#feedCards'); wrap.innerHTML = '<div class="feed"><div class="fdetail dim">fetching feeds…</div></div>';
    try {
      const d = await api('/api/feeds' + (force ? '?force=true' : ''));
      const sources = Object.values(d.sources);
      const allKnown = sources.length > 0 && sources.every(s => s.state === 'LIVE' || s.state === 'SAMPLE');
      const anyLive = sources.some(s => s.state === 'LIVE');
      setBadge($('#liveBadge'), allKnown && d.any_live === anyLive ? (anyLive ? 'LIVE' : 'SAMPLE') : 'UNAVAILABLE');
      wrap.innerHTML = '';
      Object.values(d.sources).forEach(s => {
        const el = document.createElement('div'); el.className = 'feed';
        const state = ['LIVE', 'SAMPLE'].includes(s.state) ? s.state : 'UNAVAILABLE';
        const badge = `<span class="badge ${state.toLowerCase()}">${state}</span>`;
        el.innerHTML = `<div class="fhead"><h3>${escapeText(s.name)}</h3>${badge}</div>
          <div class="fdetail">${escapeText(s.detail)}</div>
          <div class="fmeta">${escapeText(s.speed_ms.toFixed(3))} m/s @ ${escapeText(s.direction_deg.toFixed(0))}° · ${escapeText(s.fetched_utc)}<br>
          source: ${publicLink(s.url, s.url)}<br>
          ${escapeText(s.attribution)} · ${publicLink(s.license_url, 'license')}</div>
          ${s.error ? `<div class="ferr">${state === 'SAMPLE' ? 'SAMPLE reason' : 'Source error'}: ${escapeText(s.error)}</div>` : ''}`;
        wrap.appendChild(el);
      });
      this.loaded = true;
    } catch (e) { this.loaded = false; setBadge($('#liveBadge'), 'UNAVAILABLE'); wrap.innerHTML = '<div class="feed"><div class="ferr">feeds endpoint unreachable</div></div>'; }
  }
};
$('#refreshFeeds').addEventListener('click', () => Live.refresh(true));

/* ===================== BOOT ===================== */
/* Dismissal removes the loader from the accessibility tree and focus order at
   once; the visual fade then ends in display:none (immediately under reduced
   motion). Normal completion and the watchdog share this one path. */
function dismissLoader() {
  const l = $('#loader');
  if (!l || l.classList.contains('hidden')) return;
  l.classList.add('hidden');
  l.removeAttribute('role');
  l.setAttribute('aria-hidden', 'true');
  l.inert = true;
  const finish = () => { l.hidden = true; };
  if (REDUCED) { finish(); return; }
  l.addEventListener('transitionend', finish, { once: true });
  setTimeout(finish, 700); // transitionend is not guaranteed (hidden tab, no layout)
}
window.addEventListener('DOMContentLoaded', async () => {
  // Guarantee the loader is dismissed no matter what: a hard watchdog hides it
  // even if any boot step hangs past the fetch timeout, so the UI is never stuck
  // behind a perpetual spinner. Each panel then carries its own LIVE/SAMPLE badge.
  const watchdog = setTimeout(dismissLoader, API_TIMEOUT_MS + 1500);
  try {
    paintMotion();
    await health();
    await Flow.refresh();
  } catch (e) {
    /* Failed panels retain UNAVAILABLE; no sample result is invented. */
  } finally {
    clearTimeout(watchdog);
    dismissLoader();
  }
});
