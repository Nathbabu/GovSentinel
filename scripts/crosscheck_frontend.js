/* Replays the benchmark through the browser port and the Python simulator, then
 * compares them field by field.
 *
 * frontend/src/contract.js is a hand port of the contract's decoder and policy, and a
 * hand port is only worth anything while it still matches. This is what keeps the demo
 * from quietly disagreeing with the thing it demonstrates.
 *
 *   node scripts/crosscheck_frontend.js
 */
'use strict';

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const REPO_ROOT = path.resolve(__dirname, '..');
const { GovSentinelClient } = require(path.join(REPO_ROOT, 'frontend', 'src', 'contract.js'));

const doc = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, 'tests', 'scenarios.json'), 'utf8'));
const dao = doc.dao;

const python = process.env.PYTHON || 'python';
const reference = JSON.parse(execFileSync(
  python,
  [path.join('scripts', 'simulate_eval.py'), '--json'],
  { cwd: REPO_ROOT, encoding: 'utf8' }
)).results;

const client = new GovSentinelClient({
  name: dao.name,
  constitutionRules: dao.constitution_rules,
  maxSingleSpend: dao.max_single_spend,
  treasuryToken: dao.treasury_token,
  whitelistedTargets: dao.whitelisted_targets
});

const byId = new Map(reference.map((row) => [row.id, row]));
const mismatches = [];

for (const scenario of doc.scenarios) {
  const expected = byId.get(scenario.id);
  if (!expected) {
    mismatches.push([scenario.id, 'present', 'the Python simulator never reported this scenario']);
    continue;
  }

  const actual = client.evaluateProposal({
    proposalId: scenario.id,
    title: scenario.title,
    description: scenario.description,
    targetContract: scenario.target_contract,
    calldataHex: scenario.calldata_hex,
    claimedRecipient: scenario.claimed_recipient,
    claimedAmount: scenario.claimed_amount,
    auditorVerdict: scenario.auditor_verdict
  });

  const comparisons = [
    ['status', expected.actual_status, actual.status],
    ['risk_score', expected.risk_score, actual.risk_score],
    ['decoded_method', expected.decoded_method, actual.decoded_method],
    ['consensus', expected.consensus, actual.consensus.agreed],
    ['discrepancies', JSON.stringify(expected.discrepancies), JSON.stringify(actual.discrepancies)],
    ['decoded_recipient', scenario.expected_recipient, actual.decoded_recipient],
    ['decoded_amount', scenario.expected_amount, actual.decoded_amount]
  ];

  let ok = true;
  for (const [field, want, got] of comparisons) {
    if (want !== got) {
      ok = false;
      mismatches.push([`${scenario.id}.${field}`, want, got]);
    }
  }
  console.log(`  ${ok ? 'ok      ' : 'MISMATCH'} ${scenario.id.padEnd(31)} ${actual.status} at risk ${actual.risk_score}`);
}

console.log();
if (mismatches.length) {
  console.log(`${mismatches.length} field(s) diverge between the browser port and the contract:`);
  for (const [field, want, got] of mismatches) {
    console.log(`  ${field}\n    python ${want}\n    js     ${got}`);
  }
  process.exit(1);
}
console.log(`${doc.scenarios.length}/${doc.scenarios.length} scenarios agree with the Python implementation.`);
