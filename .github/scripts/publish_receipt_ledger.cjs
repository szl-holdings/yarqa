// Copyright 2026 SZL Holdings
// SPDX-License-Identifier: Apache-2.0
//
// Append one Sigstore-keyless yarqa receipt envelope to the governance-receipts
// ledger branch. Run by the `publish-ledger` job of
// .github/workflows/receipt-sign.yml through actions/github-script, after the
// sign job has minted and independently verified the envelope. That job is the
// only one holding `contents: write`; it installs nothing and runs no package
// code besides this file.
//
// Fail-closed: every unexpected API error, a missing or non-keyless envelope,
// and a different receipt already stored at the same ledger path fail the job.
// The ledger is append-only, so an existing path is never overwritten.
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const LEDGER_BRANCH = 'governance-receipts';
const OIDC_ISSUER = 'https://token.actions.githubusercontent.com';
const MAX_WRITE_ATTEMPTS = 5;

const isStatus = (error, status) => Boolean(error) && error.status === status;

function readSingleEnvelope(envelopeDir) {
  const names = fs.readdirSync(envelopeDir).filter((name) => name.endsWith('.dsse.json'));
  if (names.length !== 1) {
    throw new Error(`expected exactly one signed envelope in ${envelopeDir}, found ${names.length}`);
  }
  return JSON.parse(fs.readFileSync(path.join(envelopeDir, names[0]), 'utf8'));
}

async function ensureLedgerBranch({ github, owner, repo, core }) {
  try {
    await github.rest.git.getRef({ owner, repo, ref: `heads/${LEDGER_BRANCH}` });
    return;
  } catch (error) {
    if (!isStatus(error, 404)) throw error;
  }
  // First use: branch the ledger from the default branch.
  const meta = await github.rest.repos.get({ owner, repo });
  const base = await github.rest.git.getRef({ owner, repo, ref: `heads/${meta.data.default_branch}` });
  await github.rest.git.createRef({ owner, repo, ref: `refs/heads/${LEDGER_BRANCH}`, sha: base.data.object.sha });
  core.info(`Created ledger branch ${LEDGER_BRANCH}`);
}

async function readLedgerFile({ github, owner, repo, ledgerPath }) {
  try {
    const current = await github.rest.repos.getContent({ owner, repo, path: ledgerPath, ref: LEDGER_BRANCH });
    return Buffer.from(current.data.content, 'base64').toString('utf8');
  } catch (error) {
    if (isStatus(error, 404)) return null;
    throw error;
  }
}

async function publishReceiptLedger({ github, context, core, envelopeDir, sleep }) {
  const wait = sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const { owner, repo } = context.repo;
  const envelope = readSingleEnvelope(envelopeDir);
  if (envelope._mode !== 'SIGSTORE-KEYLESS') {
    throw new Error(`envelope mode is '${envelope._mode}', not a Sigstore keyless signature; refusing to publish it`);
  }
  const digest = envelope._szl && envelope._szl.receipt_sha256;
  if (typeof digest !== 'string' || !/^[0-9a-f]{64}$/.test(digest)) {
    throw new Error('envelope has no valid _szl.receipt_sha256');
  }
  envelope._signer_identity = `https://github.com/${owner}/${repo}/.github/workflows/receipt-sign.yml@${context.ref}`;
  envelope._signer_issuer = OIDC_ISSUER;

  await ensureLedgerBranch({ github, owner, repo, core });

  const ledgerPath = `receipts/${digest}.dsse.json`;
  const body = JSON.stringify(envelope, null, 2);
  const message = `receipt: publish signed yarqa receipt ${digest.slice(0, 12)}`;
  for (let attempt = 1; ; attempt += 1) {
    const existing = await readLedgerFile({ github, owner, repo, ledgerPath });
    if (existing !== null) {
      if (existing === body) {
        core.info(`${ledgerPath} is already on ${LEDGER_BRANCH}; nothing to append`);
        return { path: ledgerPath, written: false };
      }
      throw new Error(`${ledgerPath} already holds a different envelope; the ledger is append-only, refusing to overwrite`);
    }
    try {
      await github.rest.repos.createOrUpdateFileContents({
        owner, repo, path: ledgerPath, branch: LEDGER_BRANCH, message,
        content: Buffer.from(body).toString('base64'),
      });
      core.info(`Published ${ledgerPath} to ${LEDGER_BRANCH}`);
      return { path: ledgerPath, written: true };
    } catch (error) {
      // The contents API answers 409 when another write moved the branch head
      // and 422 when the path appeared meanwhile; re-read and retry, bounded.
      const retryable = isStatus(error, 409) || isStatus(error, 422);
      if (!retryable || attempt >= MAX_WRITE_ATTEMPTS) throw error;
      core.warning(`ledger write attempt ${attempt} answered HTTP ${error.status}; retrying`);
      await wait(2000 * attempt);
    }
  }
}

module.exports = publishReceiptLedger;
module.exports.LEDGER_BRANCH = LEDGER_BRANCH;
