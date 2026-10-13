// SPDX-License-Identifier: Apache-2.0
// Execute the shipped UI with no DOM boot, WebGL, network or backend computation.
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const script = readFileSync(process.env.YARQA_TEST_SCRIPT || path.join(__dirname, '../space/static/js/app.js'), 'utf8');

function fixture(payload) {
  const elements = new Map();
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', className: '', children: [], addEventListener() {}, appendChild(child) { this.children.push(child); } });
    return elements.get(id);
  };
  const context = vm.createContext({
    window: { matchMedia: () => ({ matches: true }), addEventListener() {} },
    document: { querySelector: get, querySelectorAll: () => [], createElement: () => ({}) },
    AbortController, URL, setTimeout, clearTimeout,
    fetch: async () => { if (payload === undefined) throw new Error('fixture offline'); return { ok: true, json: async () => payload }; },
  });
  vm.runInContext(script, context);
  return { get, context, run: (code) => vm.runInContext(code, context) };
}

test('only explicit returned LIVE/SAMPLE evidence uses those labels', () => {
  const f = fixture();
  for (const state of ['LIVE', 'SAMPLE', 'UNAVAILABLE', 'invalid', null]) {
    f.context.statusFixture = state;
    f.run("setBadge(document.querySelector('#test'), statusFixture)");
    assert.equal(f.get('#test').textContent, ['LIVE', 'SAMPLE'].includes(state) ? state : 'UNAVAILABLE');
  }
});

for (const [method, badge] of [['Flow.refresh()', 'flowBadge'], ['Agent.run()', 'agentBadge'],
  ['Chain.build()', 'chainBadge'], ['Forecast.refresh()', 'fcBadge'], ['Live.refresh()', 'liveBadge']]) {
  test(`${method} reports unavailable when no response exists`, async () => {
    const f = fixture();
    f.run('Flow.ready = true; Chain.json = "old evidence";');
    await f.run(method);
    assert.equal(f.get('#' + badge).textContent, 'UNAVAILABLE');
    assert.equal(f.get('#' + badge).className, 'badge unavailable');
    if (badge === 'chainBadge') assert.equal(f.run('Chain.json'), null);
  });
}

test('an unavailable WebGL renderer is handled without claiming a sample result', async () => {
  const f = fixture();
  f.run('Flow.init = () => { throw new Error("WebGL unavailable"); };');
  await f.run('Flow.refresh()');
  assert.equal(f.get('#flowBadge').textContent, 'UNAVAILABLE');
});

function feed(state) { return { state, name: 'fixture', detail: 'fixture', speed_ms: 1, direction_deg: 0, url: 'https://example.test', license_url: 'https://example.test', attribution: 'fixture' }; }
for (const [name, payload, expected] of [
  ['returned synthetic fallback', { any_live: false, sources: { one: feed('SAMPLE') } }, 'SAMPLE'],
  ['returned live result', { any_live: true, sources: { one: feed('LIVE') } }, 'LIVE'],
  ['empty evidence', { any_live: false, sources: {} }, 'UNAVAILABLE'],
  ['unknown source state', { any_live: false, sources: { one: feed('UNKNOWN') } }, 'UNAVAILABLE'],
  ['contradictory aggregate', { any_live: true, sources: { one: feed('SAMPLE') } }, 'UNAVAILABLE'],
]) {
  test(name, async () => { const f = fixture(payload); await f.run('Live.refresh()'); assert.equal(f.get('#liveBadge').textContent, expected); });
}

test('returned numerical evidence remains accessible when WebGL is unavailable', async () => {
  const f = fixture({ state: 'SAMPLE', n_compartments: 1, receipt_digest: 'fixture-digest',
    top_compartments: [{id: 0, n_cells: 3, mean_velocity: [0.25, 0.5]}] });
  f.run('Flow.init = () => { throw new Error("local WebGL-unavailable fixture"); };');
  await f.run('Flow.refresh()');
  assert.equal(f.get('#flowBadge').textContent, 'SAMPLE');
  assert.equal(f.get('#flowDigest').textContent, 'fixture-digest');
  assert.match(f.get('#flowTable').innerHTML, /0.2500, 0.5000/);
  assert.equal(f.get('#scene').hidden, true);
  assert.match(f.get('#flowRenderState').textContent, /3D view unavailable/);
});

test('a failed flow refresh removes stale evidence and hides its old geometry', async () => {
  const f = fixture();
  f.get('#flowTable').innerHTML = 'previous result';
  f.get('#flowLegend').innerHTML = 'previous legend';
  await f.run('Flow.refresh()');
  assert.equal(f.get('#scene').hidden, true);
  assert.equal(f.get('#flowLegend').innerHTML, '');
  assert.match(f.get('#flowTable').innerHTML, /UNAVAILABLE/);
});

for (const method of ['Chain.verify()', 'Chain.tamper()']) {
  test(`${method} cannot leave an old intact verdict after a failed request`, async () => {
    const f = fixture();
    f.run('Chain.json = JSON.stringify({links:[{}]});');
    f.get('#chainVerdict').className = 'verdict ok';
    f.get('#chainVerdict').textContent = 'intact';
    await f.run(method);
    assert.equal(f.get('#chainVerdict').className, 'verdict unavailable');
    assert.match(f.get('#chainVerdict').textContent, /UNAVAILABLE/);
    assert.equal(f.run('Chain.json'), null);
  });
}

test('source text is escaped and source links admit only absolute public HTTP(S) URLs', () => {
  const f = fixture();
  assert.equal(f.run('escapeText(`<img onerror="x"> & \'` )'), '&lt;img onerror=&quot;x&quot;&gt; &amp; &#39;');
  for (const url of ['javascript:alert(1)', 'data:text/html,unsafe', 'https://name:secret@example.invalid', '/relative']) {
    f.context.urlFixture = url;
    assert.match(f.run('publicLink(urlFixture, "source")'), /class="invalid-link"/);
    assert.doesNotMatch(f.run('publicLink(urlFixture, "source")'), /<a /);
  }
  assert.match(f.run('publicLink("https://example.invalid/path", "source")'), /rel="noopener noreferrer"/);
});

test('an unknown feed state is not visually restyled as SAMPLE', async () => {
  const f = fixture({ any_live: false, sources: { one: feed('UNKNOWN') } });
  await f.run('Live.refresh()');
  const rendered = f.get('#feedCards').children[0].innerHTML;
  assert.match(rendered, /badge unavailable/);
  assert.doesNotMatch(rendered, /badge sample/);
});

function loaderFixture(f) {
  const attributes = new Map([['role', 'status']]), classes = new Set(), listeners = {};
  return Object.assign(f.get('#loader'), {
    hidden: false, inert: false,
    classList: { add: (name) => classes.add(name), contains: (name) => classes.has(name) },
    getAttribute: (name) => (attributes.has(name) ? attributes.get(name) : null),
    setAttribute: (name, value) => attributes.set(name, String(value)),
    removeAttribute: (name) => attributes.delete(name),
    addEventListener: (type, listener) => { listeners[type] = listener; },
    listeners,
  });
}

test('a dismissed loader leaves the accessibility tree at once and is idempotent', () => {
  const f = fixture();
  const loader = loaderFixture(f);
  f.run('dismissLoader()');
  assert.equal(loader.getAttribute('role'), null);
  assert.equal(loader.getAttribute('aria-hidden'), 'true');
  assert.equal(loader.inert, true);
  assert.equal(loader.hidden, true, 'reduced motion removes the loader without waiting for a fade');
  f.run('dismissLoader()');
  assert.equal(loader.hidden, true);
});

test('with motion, the loader is unexposed during its fade and hidden when it ends', () => {
  const f = fixture();
  const loader = loaderFixture(f);
  f.run('REDUCED = false; dismissLoader()');
  assert.equal(loader.getAttribute('aria-hidden'), 'true');
  assert.equal(loader.inert, true);
  assert.equal(loader.hidden, false);
  loader.listeners.transitionend();
  assert.equal(loader.hidden, true);
});

test('closing across the desktop breakpoint focuses the visible selected tab', () => {
  const f = fixture();
  let focused = 0, blur = null;
  const tab = Object.assign(f.get('.tab[aria-selected="true"]'), {
    tabIndex: -1, dataset: {}, focus() { focused += 1; },
    addEventListener(type, listener) { if (type === 'blur') blur = listener; },
  });
  f.run('focusDesktopTab()');
  assert.equal(focused, 1);
  assert.equal(tab.tabIndex, 0);
  assert.ok('focusRestored' in tab.dataset, 'restored focus carries an explicit visible ring');
  blur();
  assert.ok(!('focusRestored' in tab.dataset));
});
