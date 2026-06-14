/* Copyright 2026 SZL Holdings — SPDX-License-Identifier: Apache-2.0
   yarqa Space front-end. Sovereign: global THREE r160 (vendored, zero CDN).
   One code path per tab; LIVE/SAMPLE badges follow REAL backend reachability. */
'use strict';

const REDUCED = window.matchMedia('(prefers-reduced-motion:reduce)').matches;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* Universal fetch hardening: every request carries an AbortController timeout so
   a hung/slow endpoint can NEVER produce a perpetual spinner. On timeout or any
   error the caller's catch fires and the panel honest-degrades to SAMPLE/
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
  el.textContent = state === 'LIVE' ? 'LIVE' : 'SAMPLE';
  el.className = 'badge ' + (state === 'LIVE' ? 'live' : 'sample');
}

/* compartment palette */
const PALETTE = ['#40e0c5','#ffb13f','#5ad1ff','#c89bff','#ff6b8f','#9ef0c0',
  '#ffd166','#7c9cff','#ff9e6d','#6df0d6','#d28bff','#8be0a0','#ffc24d','#62c4ff','#ff85a8','#a0f0c8'];
const colorFor = (id) => PALETTE[((id % PALETTE.length) + PALETTE.length) % PALETTE.length];

/* ===================== TAB NAV ===================== */
function activate(tab) {
  document.body.dataset.tab = tab;
  $$('.panel').forEach(p => p.classList.toggle('is-active', p.id === 'panel-' + tab));
  $$('.tab').forEach(t => t.classList.toggle('is-active', t.dataset.go === tab));
  $$('.sheet-item').forEach(t => t.classList.toggle('is-active', t.dataset.go === tab));
  closeSheet();
  if (tab === 'flow' && Flow.ready) Flow.onResize();
  if (tab === 'flow' && !Flow.loaded) Flow.refresh();
  if (tab === 'agent' && !Agent.loaded) Agent.run();
  if (tab === 'chain' && !Chain.loaded) Chain.build();
  if (tab === 'forecast' && !Forecast.loaded) Forecast.refresh();
  if (tab === 'live' && !Live.loaded) Live.refresh();
}
$$('[data-go]').forEach(b => b.addEventListener('click', () => activate(b.dataset.go)));

/* mobile sheet */
const sheet = $('#sheet'), backdrop = $('#sheetBackdrop'), fab = $('#fab');
function openSheet() { sheet.hidden = false; backdrop.hidden = false; fab.setAttribute('aria-expanded', 'true'); }
function closeSheet() { sheet.hidden = true; backdrop.hidden = true; fab.setAttribute('aria-expanded', 'false'); }
fab.addEventListener('click', () => sheet.hidden ? openSheet() : closeSheet());
backdrop.addEventListener('click', closeSheet);

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
  group: null, raf: 0, align: 0.2, topk: 8,
  init() {
    const canvas = $('#scene');
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color('#06091a');
    this.scene.fog = new THREE.FogExp2('#06091a', 0.018);
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
    const mv = e => { if (!drag) return; const t = e.touches ? e.touches[0] : e; rotY += (t.clientX - px) * 0.006; rotX += (t.clientY - py) * 0.006; rotX = Math.max(-1.1, Math.min(1.1, rotX)); px = t.clientX; py = t.clientY; this.group.rotation.y = rotY; this.group.rotation.x = rotX; };
    const up = () => { drag = false; };
    canvas.addEventListener('mousedown', dn); window.addEventListener('mousemove', mv); window.addEventListener('mouseup', up);
    canvas.addEventListener('touchstart', dn, { passive: true }); canvas.addEventListener('touchmove', mv, { passive: true }); canvas.addEventListener('touchend', up);
    this.ready = true;
    this.animate();
  },
  onResize() {
    const c = $('#scene'); const w = c.clientWidth || 1, h = c.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  },
  animate() {
    const tick = () => {
      this.raf = requestAnimationFrame(tick);
      if (!REDUCED && this.group) this.group.rotation.y += 0.0016;
      this.renderer.render(this.scene, this.camera);
    };
    tick();
  },
  build(data) {
    while (this.group.children.length) this.group.remove(this.group.children[0]);
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
      d.innerHTML = `<span class="sw" style="background:${colorFor(id)}"></span>c${id}`;
      leg.appendChild(d);
    });
  },
  async refresh() {
    if (!this.ready) this.init();
    try {
      const d = await api(`/api/compartments?align_threshold=${this.align}&top_k=${this.topk}`);
      setBadge($('#flowBadge'), d.state);
      $('#flowCount').textContent = `${d.n_compartments} compartments`;
      $('#flowDigest').textContent = d.receipt_digest;
      this.build(d);
      this.loaded = true;
    } catch (e) { setBadge($('#flowBadge'), 'SAMPLE'); $('#flowCount').textContent = 'unreachable'; }
  }
};
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
        const wt = s.topk_weights.length ? ` · weights [${s.topk_weights.join(', ')}]` : '';
        el.innerHTML = `<span class="sidx">#${i}</span>
          <span class="smeta">obs <b>[${s.observation.map(x=>x.toFixed(2)).join(', ')}]</b> →
          route c<b>${s.routed_compartment}</b> (score ${s.route_score.toFixed(3)}, top-k [${s.topk_compartments.join(', ')}]${wt})<br>
          receipt <span class="dim">${s.yarqa_receipt_digest.slice(0,24)}…</span></span>
          <span class="dec ${s.decision}">${s.decision}</span>`;
        if (REDUCED) el.style.animation = 'none';
        log.appendChild(el);
      });
      this.loaded = true;
    } catch (e) { setBadge($('#agentBadge'), 'SAMPLE'); log.innerHTML = '<div class="step"><span class="smeta">loop unreachable</span></div>'; }
  }
};
$('#runLoop').addEventListener('click', () => Agent.run());

/* ===================== TAB 3: RECEIPT CHAIN ===================== */
const Chain = {
  loaded: false, json: null,
  render(links, verify) {
    const v = $('#chainView'); v.innerHTML = '';
    const broken = verify.first_broken_index;
    links.forEach(l => {
      const el = document.createElement('div');
      const isBroken = broken !== null && l.index >= broken;
      el.className = 'link' + (isBroken ? ' broken' : '');
      el.innerHTML = `<div class="lh"><b>link #${l.index} · c${l.routed_compartment} · ${l.decision} · score ${l.route_score}</b><span class="okdot"></span></div>
        <div class="ld"><span class="prevd">prev ${l.prev_digest.slice(0,18)}…</span> → <b>${l.digest.slice(0,18)}…</b></div>`;
      v.appendChild(el);
    });
    const vd = $('#chainVerdict');
    if (verify.ok) { vd.textContent = `✓ intact · ${verify.n_links} links`; vd.className = 'verdict ok'; }
    else { vd.textContent = `✗ TAMPER at link ${verify.first_broken_index}`; vd.className = 'verdict bad'; }
  },
  async build() {
    try {
      const d = await api(`/api/chain?n_obs=5&align_threshold=${Flow.align}`);
      setBadge($('#chainBadge'), d.state);
      this.json = d.chain_json;
      this.render(d.links, d.verify);
      this.loaded = true;
    } catch (e) { setBadge($('#chainBadge'), 'SAMPLE'); $('#chainVerdict').textContent = 'unreachable'; }
  },
  async verify() {
    if (!this.json) return this.build();
    const d = await api('/api/chain/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ chain_json: this.json }) });
    const links = JSON.parse(this.json).links.map(l => ({ index: l.index, prev_digest: l.prev_digest, digest: l.digest, decision: l.step.decision, routed_compartment: l.step.routed_compartment, route_score: (+l.step.route_score).toFixed(4) }));
    this.render(links, d.verify);
  },
  async tamper() {
    if (!this.json) await this.build();
    const n = JSON.parse(this.json).links.length;
    const idx = Math.floor(n / 2);
    const d = await api('/api/chain/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ chain_json: this.json, tamper_index: idx, tamper_field: 'route_score' }) });
    const links = JSON.parse(this.json).links.map(l => ({ index: l.index, prev_digest: l.prev_digest, digest: l.digest, decision: l.step.decision, routed_compartment: l.step.routed_compartment, route_score: (+l.step.route_score).toFixed(4) }));
    this.render(links, d.verify);
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
    ctx.fillStyle = '#5d6a8f'; ctx.font = '10px ui-monospace,monospace';
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
    let h = '<tr><th>t</th><th>kind</th><th>compartments</th><th>mean flow</th></tr>';
    history.concat(projected).forEach(p => {
      h += `<tr class="${p.kind === 'PROJECTED' ? 'proj' : ''}"><td>${p.t}</td><td>${p.kind}</td><td>${p.n_compartments}</td><td>${p.mean_flow.toFixed(4)}</td></tr>`;
    });
    t.innerHTML = h;
  },
  async refresh() {
    try {
      const d = await api(`/api/forecast?align_threshold=${Flow.align}&horizon=${this.hz}`);
      setBadge($('#fcBadge'), d.state);
      this.draw(d.history, d.projected);
      this.table(d.history, d.projected);
      this.loaded = true;
    } catch (e) { setBadge($('#fcBadge'), 'SAMPLE'); }
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
      const anyLive = d.any_live;
      setBadge($('#liveBadge'), anyLive ? 'LIVE' : 'SAMPLE');
      wrap.innerHTML = '';
      Object.values(d.sources).forEach(s => {
        const el = document.createElement('div'); el.className = 'feed';
        const badge = `<span class="badge ${s.state === 'LIVE' ? 'live' : 'sample'}">${s.state}</span>`;
        el.innerHTML = `<div class="fhead"><h3>${s.name}</h3>${badge}</div>
          <div class="fdetail">${s.detail}</div>
          <div class="fmeta">${s.speed_ms.toFixed(3)} m/s @ ${s.direction_deg.toFixed(0)}° · ${s.fetched_utc}<br>
          source: <a href="${s.url}" target="_blank" rel="noopener">${s.url}</a><br>
          ${s.attribution} · <a href="${s.license_url}" target="_blank" rel="noopener">license</a></div>
          ${s.error ? `<div class="ferr">SAMPLE reason: ${s.error}</div>` : ''}`;
        wrap.appendChild(el);
      });
      this.loaded = true;
    } catch (e) { setBadge($('#liveBadge'), 'SAMPLE'); wrap.innerHTML = '<div class="feed"><div class="ferr">feeds endpoint unreachable</div></div>'; }
  }
};
$('#refreshFeeds').addEventListener('click', () => Live.refresh(true));

/* ===================== BOOT ===================== */
window.addEventListener('DOMContentLoaded', async () => {
  // Guarantee the loader is dismissed no matter what: a hard watchdog hides it
  // even if any boot step hangs past the fetch timeout, so the UI is never stuck
  // behind a perpetual spinner. Each panel then carries its own LIVE/SAMPLE badge.
  const hideLoader = () => { const l = $('#loader'); if (l) l.classList.add('hidden'); };
  const watchdog = setTimeout(hideLoader, API_TIMEOUT_MS + 1500);
  try {
    await health();
    Flow.init();
    await Flow.refresh();
  } catch (e) {
    /* honest-degrade: panels already render SAMPLE/unreachable on their own */
  } finally {
    clearTimeout(watchdog);
    hideLoader();
  }
});
