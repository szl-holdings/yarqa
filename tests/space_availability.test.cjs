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
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', className: '', addEventListener() {}, appendChild() {} });
    return elements.get(id);
  };
  const context = vm.createContext({
    window: { matchMedia: () => ({ matches: true }), addEventListener() {} },
    document: { querySelector: get, querySelectorAll: () => [], createElement: () => ({}) },
    AbortController, setTimeout, clearTimeout,
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
