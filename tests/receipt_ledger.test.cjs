// Copyright 2026 SZL Holdings
// SPDX-License-Identifier: Apache-2.0
// Offline fixtures for .github/scripts/publish_receipt_ledger.cjs: an in-memory
// GitHub REST double, no network and no token.
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');

const publish = require('../.github/scripts/publish_receipt_ledger.cjs');

const DIGEST = 'a'.repeat(64);
const CONTEXT = { repo: { owner: 'szl-holdings', repo: 'yarqa' }, ref: 'refs/heads/main' };

function httpError(status) {
  const error = new Error(`HTTP ${status}`);
  error.status = status;
  return error;
}

function envelopeDir(envelopes) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'yarqa-ledger-'));
  envelopes.forEach((envelope, index) => {
    fs.writeFileSync(path.join(dir, `${index}.dsse.json`), JSON.stringify(envelope));
  });
  return dir;
}

function keyless(digest = DIGEST) {
  return { _mode: 'SIGSTORE-KEYLESS', payload: 'cGF5bG9hZA==', signatures: [{ sig: 'x' }], _szl: { receipt_sha256: digest } };
}

// Minimal in-memory double of the REST calls the publisher makes.
function fakeGitHub({ branches = ['main', 'governance-receipts'], files = {}, failures = {} } = {}) {
  const calls = [];
  const fail = (name) => {
    const queue = failures[name];
    if (queue && queue.length) throw httpError(queue.shift());
  };
  const github = {
    rest: {
      git: {
        async getRef({ ref }) {
          calls.push(['getRef', ref]); fail('getRef');
          const name = ref.replace(/^heads\//, '');
          if (!branches.includes(name)) throw httpError(404);
          return { data: { object: { sha: `${name}-sha` } } };
        },
        async createRef({ ref, sha }) {
          calls.push(['createRef', ref, sha]); fail('createRef');
          branches.push(ref.replace(/^refs\/heads\//, ''));
          return { data: {} };
        },
      },
      repos: {
        async get() { calls.push(['get']); return { data: { default_branch: 'main' } }; },
        async getContent({ path: filePath, ref }) {
          calls.push(['getContent', filePath, ref]); fail('getContent');
          if (!(filePath in files)) throw httpError(404);
          return { data: { sha: 'blob', content: Buffer.from(files[filePath]).toString('base64').replace(/(.{60})/g, '$1\n') } };
        },
        async createOrUpdateFileContents(args) {
          calls.push(['write', args.path, args.branch, args.sha]); fail('write');
          files[args.path] = Buffer.from(args.content, 'base64').toString('utf8');
          return { data: {} };
        },
      },
    },
  };
  return { github, calls, files, branches };
}

function fakeCore() {
  const messages = { info: [], warning: [] };
  return { messages, info: (m) => messages.info.push(m), warning: (m) => messages.warning.push(m) };
}

const noSleep = async () => {};

test('appends a new keyless envelope with the signer identity', async () => {
  const gh = fakeGitHub();
  const result = await publish({ github: gh.github, context: CONTEXT, core: fakeCore(), envelopeDir: envelopeDir([keyless()]), sleep: noSleep });
  const ledgerPath = `receipts/${DIGEST}.dsse.json`;
  assert.deepEqual(result, { path: ledgerPath, written: true });
  const writes = gh.calls.filter((call) => call[0] === 'write');
  assert.deepEqual(writes, [['write', ledgerPath, 'governance-receipts', undefined]]);
  const stored = JSON.parse(gh.files[ledgerPath]);
  assert.equal(stored._signer_identity, 'https://github.com/szl-holdings/yarqa/.github/workflows/receipt-sign.yml@refs/heads/main');
  assert.equal(stored._signer_issuer, 'https://token.actions.githubusercontent.com');
});

test('creates the ledger branch from the default branch on first use', async () => {
  const gh = fakeGitHub({ branches: ['main'] });
  await publish({ github: gh.github, context: CONTEXT, core: fakeCore(), envelopeDir: envelopeDir([keyless()]), sleep: noSleep });
  assert.deepEqual(gh.calls.find((call) => call[0] === 'createRef'), ['createRef', 'refs/heads/governance-receipts', 'main-sha']);
});

test('an unexpected branch lookup error fails without writing', async () => {
  const gh = fakeGitHub({ failures: { getRef: [403] } });
  await assert.rejects(
    publish({ github: gh.github, context: CONTEXT, core: fakeCore(), envelopeDir: envelopeDir([keyless()]), sleep: noSleep }),
    { status: 403 },
  );
  assert.equal(gh.calls.some((call) => call[0] === 'write' || call[0] === 'createRef'), false);
});

test('refuses a placeholder or malformed envelope before any API call', async () => {
  for (const envelope of [{ ...keyless(), _mode: 'PLACEHOLDER' }, keyless('not-a-digest'), { _mode: 'SIGSTORE-KEYLESS' }]) {
    const gh = fakeGitHub();
    await assert.rejects(publish({ github: gh.github, context: CONTEXT, core: fakeCore(), envelopeDir: envelopeDir([envelope]), sleep: noSleep }));
    assert.deepEqual(gh.calls, []);
  }
});

test('requires exactly one envelope', async () => {
  for (const envelopes of [[], [keyless(), keyless('b'.repeat(64))]]) {
    const gh = fakeGitHub();
    await assert.rejects(
      publish({ github: gh.github, context: CONTEXT, core: fakeCore(), envelopeDir: envelopeDir(envelopes), sleep: noSleep }),
      /exactly one signed envelope/,
    );
    assert.deepEqual(gh.calls, []);
  }
});

test('an identical receipt already on the ledger is a no-op', async () => {
  const first = fakeGitHub();
  const dir = envelopeDir([keyless()]);
  await publish({ github: first.github, context: CONTEXT, core: fakeCore(), envelopeDir: dir, sleep: noSleep });
  const rerun = fakeGitHub({ files: { ...first.files } });
  const result = await publish({ github: rerun.github, context: CONTEXT, core: fakeCore(), envelopeDir: dir, sleep: noSleep });
  assert.equal(result.written, false);
  assert.equal(rerun.calls.some((call) => call[0] === 'write'), false);
});

test('never overwrites a different envelope at the same ledger path', async () => {
  const gh = fakeGitHub({ files: { [`receipts/${DIGEST}.dsse.json`]: '{"other":true}' } });
  await assert.rejects(
    publish({ github: gh.github, context: CONTEXT, core: fakeCore(), envelopeDir: envelopeDir([keyless()]), sleep: noSleep }),
    /append-only/,
  );
  assert.equal(gh.calls.some((call) => call[0] === 'write'), false);
});

test('retries a concurrent-write conflict, then succeeds', async () => {
  const gh = fakeGitHub({ failures: { write: [409] } });
  const core = fakeCore();
  const delays = [];
  const result = await publish({ github: gh.github, context: CONTEXT, core, envelopeDir: envelopeDir([keyless()]), sleep: async (ms) => { delays.push(ms); } });
  assert.equal(result.written, true);
  assert.equal(gh.calls.filter((call) => call[0] === 'write').length, 2);
  assert.deepEqual(delays, [2000]);
  assert.equal(core.messages.warning.length, 1);
});

test('gives up after bounded retries and surfaces the error', async () => {
  const gh = fakeGitHub({ failures: { write: [409, 409, 409, 409, 409] } });
  await assert.rejects(
    publish({ github: gh.github, context: CONTEXT, core: fakeCore(), envelopeDir: envelopeDir([keyless()]), sleep: noSleep }),
    { status: 409 },
  );
  assert.equal(gh.calls.filter((call) => call[0] === 'write').length, 5);
});

test('a non-retryable write or read error fails immediately', async () => {
  for (const failures of [{ write: [403] }, { getContent: [500] }]) {
    const gh = fakeGitHub({ failures });
    await assert.rejects(publish({ github: gh.github, context: CONTEXT, core: fakeCore(), envelopeDir: envelopeDir([keyless()]), sleep: noSleep }));
    assert.ok(gh.calls.filter((call) => call[0] === 'write').length <= 1);
  }
});
