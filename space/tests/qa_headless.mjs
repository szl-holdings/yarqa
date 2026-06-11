// Copyright 2026 SZL Holdings — SPDX-License-Identifier: Apache-2.0
// Headless QA for the yarqa Space: desktop/390/820, 0 console errors,
// all 5 tabs render, LIVE/SAMPLE badges correct, 3D renders, receipt verify.
import { chromium } from 'playwright';

const BASE = process.env.QA_BASE || 'http://127.0.0.1:7860';
const OUT = process.env.QA_OUT || '/home/user/workspace';
const TABS = ['flow', 'agent', 'chain', 'forecast', 'live'];
const VIEWPORTS = [
  { name: 'desktop', width: 1280, height: 800 },
  { name: 'phone390', width: 390, height: 844 },
  { name: 'tablet820', width: 820, height: 1180 },
];

const results = [];
let hardFail = false;

function rec(name, ok, detail = '') {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
  if (!ok) hardFail = true;
}

const browser = await chromium.launch();

for (const vp of VIEWPORTS) {
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));

  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1800); // boot + first fetch + 3D

  // navigate each tab (desktop uses rail; mobile uses FAB sheet)
  for (const tab of TABS) {
    if (vp.width <= 860) {
      await page.click('#fab');
      await page.waitForTimeout(150);
      await page.click(`.sheet-item[data-go="${tab}"]`);
    } else {
      await page.click(`.tab[data-go="${tab}"]`);
    }
    await page.waitForTimeout(900);
    const visible = await page.isVisible(`#panel-${tab}`);
    rec(`${vp.name}:tab-${tab}-renders`, visible);

    // overflow check (no horizontal scroll)
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    rec(`${vp.name}:tab-${tab}-no-overflow`, overflow <= 1, `scrollX=${overflow}`);

    // badge must read LIVE or SAMPLE on data tabs (wait for async load to settle)
    const badgeSel = { flow: '#flowBadge', agent: '#agentBadge', chain: '#chainBadge', forecast: '#fcBadge', live: '#liveBadge' }[tab];
    if (badgeSel) {
      try {
        await page.waitForFunction(
          (sel) => { const t = (document.querySelector(sel)?.textContent || '').trim(); return t === 'LIVE' || t === 'SAMPLE'; },
          badgeSel, { timeout: 8000 });
      } catch (_) { /* fall through to assertion */ }
      const txt = (await page.textContent(badgeSel) || '').trim();
      rec(`${vp.name}:tab-${tab}-badge`, ['LIVE', 'SAMPLE'].includes(txt), `badge=${txt}`);
    }
    await page.screenshot({ path: `${OUT}/qa_yarqa_${vp.name}_${tab}.png` });
  }

  // 3D renders: canvas has a non-trivial drawing buffer + WebGL context
  await (vp.width <= 860 ? (async () => { await page.click('#fab'); await page.waitForTimeout(120); await page.click('.sheet-item[data-go="flow"]'); })() : page.click('.tab[data-go="flow"]'));
  await page.waitForTimeout(700);
  const glOk = await page.evaluate(() => {
    const c = document.querySelector('#scene');
    if (!c) return false;
    const gl = c.getContext('webgl2') || c.getContext('webgl');
    return !!gl && c.width > 0 && c.height > 0;
  });
  rec(`${vp.name}:3d-webgl-renders`, glOk);

  // receipt-chain verify + tamper round-trip
  await (vp.width <= 860 ? (async () => { await page.click('#fab'); await page.waitForTimeout(120); await page.click('.sheet-item[data-go="chain"]'); })() : page.click('.tab[data-go="chain"]'));
  await page.waitForTimeout(700);
  const waitVerdict = (pred) => page.waitForFunction(
    (p) => { const t = (document.querySelector('#chainVerdict')?.textContent || '').trim(); return p === 'intact' ? t.includes('intact') : t.toUpperCase().includes('TAMPER'); },
    pred, { timeout: 8000 }).catch(() => {});
  await page.click('#buildChain'); await waitVerdict('intact');
  await page.click('#verifyChain'); await waitVerdict('intact');
  let verdict = (await page.textContent('#chainVerdict') || '').trim();
  rec(`${vp.name}:chain-verify-ok`, verdict.includes('intact'), verdict);
  await page.click('#tamperChain'); await waitVerdict('tamper');
  verdict = (await page.textContent('#chainVerdict') || '').trim();
  rec(`${vp.name}:chain-tamper-detected`, verdict.toUpperCase().includes('TAMPER'), verdict);

  rec(`${vp.name}:zero-console-errors`, errors.length === 0, errors.slice(0, 3).join(' | '));
  await ctx.close();
}

await browser.close();

const passed = results.filter(r => r.ok).length;
console.log(`\n==== ${passed}/${results.length} checks passed ====`);
import { writeFileSync } from 'fs';
writeFileSync(`${OUT}/qa_yarqa_results.json`, JSON.stringify({ passed, total: results.length, results }, null, 2));
process.exit(hardFail ? 1 : 0);
