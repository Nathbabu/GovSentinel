/* Browser port of contracts/calldata_decoder.py and contracts/policy.py.
 *
 * Kept deliberately line-for-line with the Python so the demo cannot drift from the
 * contract it is demonstrating. scripts/crosscheck_frontend.js replays the whole
 * benchmark through both and fails on any divergence.
 *
 * Amounts are BigInt everywhere: MAX_UINT256 is far past Number.MAX_SAFE_INTEGER, and
 * a uint256 silently rounded to a float is exactly the bug this tool exists to catch.
 */
(function (global) {
  'use strict';

  const SELECTOR_HEX = 8;
  const WORD_HEX = 64;
  const ZERO_ADDRESS = '0x' + '0'.repeat(40);
  const MAX_UINT256 = (1n << 256n) - 1n;

  const UNKNOWN_METHOD = 'unknown';
  const MALFORMED_METHOD = 'malformed';

  const METHODS = {
    '0xa9059cbb': { signature: 'transfer(address,uint256)', argTypes: ['address', 'uint256'], recipientArg: 0, amountArg: 1 },
    '0x095ea7b3': { signature: 'approve(address,uint256)', argTypes: ['address', 'uint256'], recipientArg: 0, amountArg: 1 },
    '0xf2fde38b': { signature: 'transferOwnership(address)', argTypes: ['address'], recipientArg: 0, amountArg: null },
    '0x2f2ff15d': { signature: 'grantRole(bytes32,address)', argTypes: ['bytes32', 'address'], recipientArg: 1, amountArg: null },
    '0x3659cfe6': { signature: 'upgradeTo(address)', argTypes: ['address'], recipientArg: 0, amountArg: null },
    '0x4f1ef286': { signature: 'upgradeToAndCall(address,bytes)', argTypes: ['address', 'bytes'], recipientArg: 0, amountArg: null }
  };

  // These hand over control of the target instead of moving value, so no amount check
  // will ever catch them. They need their own rule downstream.
  const PRIVILEGED_METHODS = new Set(['transferOwnership', 'grantRole', 'upgradeTo', 'upgradeToAndCall']);
  const VALUE_METHODS = new Set(['transfer', 'approve']);

  const FINDING_CODES = {
    AMOUNT_MISMATCH: 'the amount in the proposal text differs from the amount in the calldata',
    CONSTITUTION_BREACH: 'the action breaks a rule in the DAO constitution',
    HIDDEN_TRANSFER: 'the calldata moves value the proposal text never mentions',
    INTENT_MISMATCH: 'the written proposal does not describe what the calldata executes',
    OWNERSHIP_TRANSFER: 'the call hands ownership of the target contract to another address',
    PROXY_UPGRADE: 'the call repoints a proxy at a new implementation',
    RECIPIENT_MISMATCH: 'the beneficiary named in the text is not the address being paid',
    ROLE_GRANT: 'the call grants a privileged role',
    UNLIMITED_APPROVAL: 'an unbounded allowance would let the spender drain the treasury later',
    VAGUE_DESCRIPTION: 'the proposal is too vague to audit against its own calldata'
  };

  const RISK_BANDS = [0, 20, 40, 60, 80, 100];
  const INTENT_VALUES = ['MATCH', 'PARTIAL', 'MISMATCH'];
  const VETO_RISK_FLOOR = 90;
  const FLAG_RISK_FLOOR = 50;

  function normAddress(address) {
    return String(address == null ? '' : address).trim().toLowerCase();
  }

  function methodName(signature) {
    return signature.split('(')[0];
  }

  function stripPrefix(calldataHex) {
    let body = String(calldataHex == null ? '' : calldataHex).trim();
    if (body.slice(0, 2).toLowerCase() === '0x') {
      body = body.slice(2);
    }
    return body.toLowerCase();
  }

  function isHex(body) {
    return body.length % 2 === 0 && /^[0-9a-f]*$/.test(body);
  }

  function readWord(body, index) {
    const start = index * WORD_HEX;
    const word = body.slice(start, start + WORD_HEX);
    if (word.length < WORD_HEX) {
      throw new Error(`calldata ends mid-word at argument slot ${index}`);
    }
    return word;
  }

  function readDynamicBytes(body, offset) {
    const head = offset * 2n;
    const limit = BigInt(body.length);
    if (head + BigInt(WORD_HEX) > limit) {
      throw new Error(`bytes offset ${offset} points past the end of the payload`);
    }
    const at = Number(head);
    const size = BigInt('0x' + body.slice(at, at + WORD_HEX)) * 2n;
    const start = head + BigInt(WORD_HEX);
    if (start + size > limit) {
      throw new Error(`bytes payload at offset ${offset} is truncated`);
    }
    return '0x' + body.slice(Number(start), Number(start + size));
  }

  function decodeArgs(body, argTypes) {
    return argTypes.map(function (kind, slot) {
      const word = readWord(body, slot);
      switch (kind) {
        // The EVM ignores the upper 12 bytes of an address word, so we do too;
        // normalising here keeps whitelist comparisons honest.
        case 'address': return '0x' + word.slice(-40);
        case 'uint256': return BigInt('0x' + word);
        case 'bytes32': return '0x' + word;
        case 'bytes': return readDynamicBytes(body, BigInt('0x' + word));
        default: throw new Error(`no decoder for argument type ${kind}`);
      }
    });
  }

  function failedCall(name, signature, target, raw, note) {
    return {
      signature: signature,
      method_name: name,
      target: target,
      recipient: ZERO_ADDRESS,
      amount: 0n,
      extra_params: [note],
      raw_calldata: raw
    };
  }

  /* Never throws. Calldata that cannot be parsed comes back tagged `malformed` or
   * `unknown` so the caller can veto it, which is the safe reading: a payload no
   * auditor can read is not a payload anyone should execute. */
  function decodeCalldata(target, calldataHex) {
    const raw = String(calldataHex == null ? '' : calldataHex).trim();
    const normalisedTarget = normAddress(target);
    const body = stripPrefix(raw);

    if (body.length < SELECTOR_HEX || !isHex(body)) {
      return failedCall(MALFORMED_METHOD, '', normalisedTarget, raw, 'calldata is not a well-formed hex payload');
    }

    const selector = '0x' + body.slice(0, SELECTOR_HEX);
    const args = body.slice(SELECTOR_HEX);
    const method = METHODS[selector];

    if (!method) {
      const call = failedCall(UNKNOWN_METHOD, selector, normalisedTarget, raw, `unrecognised selector ${selector}`);
      call.extra_params.push(`${Math.floor(args.length / WORD_HEX)} argument word(s) supplied`);
      return call;
    }

    let values;
    try {
      values = decodeArgs(args, method.argTypes);
    } catch (err) {
      return failedCall(MALFORMED_METHOD, method.signature, normalisedTarget, raw, err.message);
    }

    const recipient = method.recipientArg === null ? ZERO_ADDRESS : values[method.recipientArg];
    const amount = method.amountArg === null ? 0n : values[method.amountArg];
    const consumed = new Set([method.recipientArg, method.amountArg]);
    const extra = values
      .map(function (value, index) { return { index: index, value: value }; })
      .filter(function (entry) { return !consumed.has(entry.index); })
      .map(function (entry) { return `${method.argTypes[entry.index]}=${entry.value}`; });

    // Trailing words are ignored by the EVM on a static-argument call, but their
    // presence usually means the payload was built for a different ABI, or for a
    // fallback that reads past the declared arguments.
    if (!method.argTypes.includes('bytes') && args.length > method.argTypes.length * WORD_HEX) {
      extra.push('trailing bytes past the declared arguments');
    }

    return {
      signature: method.signature,
      method_name: methodName(method.signature),
      target: normalisedTarget,
      recipient: recipient,
      amount: amount,
      extra_params: extra,
      raw_calldata: raw
    };
  }

  function snapBand(value) {
    let score;
    try {
      score = Number.parseInt(value, 10);
    } catch (err) {
      return 100;
    }
    if (!Number.isFinite(score)) return 100;
    score = Math.max(0, Math.min(100, score));
    // First-minimum wins on a tie, matching Python's min(key=...) so a band exactly
    // between two stops resolves the same way on both sides.
    return RISK_BANDS.reduce(function (best, band) {
      return Math.abs(band - score) < Math.abs(best - score) ? band : best;
    }, RISK_BANDS[0]);
  }

  /* Collapse the model's answer onto a small fixed lattice. Anything unreadable
   * resolves to the pessimistic end, so a validator that got garbage back still
   * agrees with one that got nothing back. */
  function canonicalVerdict(payload) {
    const source = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : {};
    let intent = String(source.intent_match == null ? '' : source.intent_match).trim().toUpperCase();
    if (!INTENT_VALUES.includes(intent)) {
      intent = 'MISMATCH';
    }

    const reported = Array.isArray(source.findings) ? source.findings : [];
    const findings = Array.from(new Set(reported.map(function (code) {
      return String(code).trim().toUpperCase();
    }))).filter(function (code) {
      return Object.prototype.hasOwnProperty.call(FINDING_CODES, code);
    }).sort();

    return {
      intent_match: intent,
      risk_band: snapBand(source.risk_band === undefined ? 100 : source.risk_band),
      findings: findings
    };
  }

  /* An empty payload canonicalises to MISMATCH at risk 100, so a model that rambles
   * instead of answering costs the proposal its pass rather than reverting. */
  function parseAuditorReply(raw) {
    const fence = '`'.repeat(3);
    const cleaned = String(raw == null ? '' : raw).split(fence + 'json').join('').split(fence).join('').trim();
    let payload;
    try {
      payload = JSON.parse(cleaned);
    } catch (err) {
      payload = {};
    }
    return canonicalVerdict(payload);
  }

  /* Three surface forms of the same judgement, as different validators would emit it.
   * A model that answers in a different key order, wraps the JSON in a fence, or picks
   * a risk number a few points off the band must still land on identical canonical
   * bytes, otherwise strict_eq never reaches consensus. */
  function validatorReplies(verdict) {
    const fence = '`'.repeat(3);
    const plain = JSON.stringify(verdict);
    const shuffled = JSON.stringify({
      findings: verdict.findings.slice().reverse(),
      risk_band: Math.max(0, verdict.risk_band - 3),
      intent_match: verdict.intent_match.toLowerCase()
    });
    return [plain, `${fence}json\n${plain}\n${fence}`, shuffled];
  }

  function runConsensus(verdict) {
    const replies = validatorReplies(canonicalVerdict(verdict));
    const canonical = replies.map(parseAuditorReply);
    const encoded = new Set(canonical.map(function (v) { return JSON.stringify(v); }));
    return {
      verdict: canonical[0],
      validators: canonical.length,
      agreed: encoded.size === 1,
      replies: replies
    };
  }

  function applyPolicy(config, call, options) {
    const claimedTo = normAddress(options.claimedRecipient);
    const claimed = BigInt(options.claimedAmount || 0);
    const cap = BigInt(config.maxSingleSpend);
    const treasury = normAddress(config.treasuryToken);
    const verdict = options.verdict;

    const movesValue = VALUE_METHODS.has(call.method_name);
    const touchesTreasury = call.target === treasury;
    const unreadable = call.method_name === UNKNOWN_METHOD || call.method_name === MALFORMED_METHOD;

    const spendingLimitExceeded = movesValue && call.amount > cap;
    const unwhitelistedTarget = !config.whitelisted(call.target);
    const privilegeEscalation = PRIVILEGED_METHODS.has(call.method_name);
    const unlimitedApproval = call.method_name === 'approve' && call.amount === MAX_UINT256;
    const recipientMismatch = Boolean(claimedTo) && call.recipient !== ZERO_ADDRESS && claimedTo !== call.recipient;
    const amountMismatch = movesValue && claimed !== call.amount;

    // Hard overrides, decided from the bytes alone. They outrank whatever the model
    // concluded, because the persuasive description is exactly the part an attacker
    // controls.
    const blocking = [];
    if (unreadable) {
      blocking.push('calldata does not decode to a known governance action: ' + call.extra_params.join('; '));
    }
    if (unwhitelistedTarget) {
      blocking.push(`target ${call.target} is not on the approved contract whitelist`);
    }
    if (spendingLimitExceeded) {
      blocking.push(`${call.method_name} moves ${call.amount}, over the per-proposal cap of ${cap}`);
    }
    if (recipientMismatch) {
      blocking.push(`proposal names ${claimedTo} but the calldata addresses ${call.recipient}`);
    }
    if (amountMismatch) {
      blocking.push(`proposal claims ${claimed} but the calldata moves ${call.amount}`);
    }
    if (unlimitedApproval && touchesTreasury) {
      blocking.push(`unbounded allowance on the treasury token for ${call.recipient}`);
    }
    if (privilegeEscalation && (unwhitelistedTarget || verdict.intent_match === 'MISMATCH')) {
      blocking.push(`${call.signature} takes control of ${call.target} without a matching mandate in the text`);
    }

    const warnings = [];
    if (privilegeEscalation && blocking.length === 0) {
      warnings.push(`${call.signature} changes who controls ${call.target}`);
    }
    if (unlimitedApproval && !touchesTreasury) {
      warnings.push(`unbounded allowance granted to ${call.recipient}`);
    }
    if (touchesTreasury && movesValue && !spendingLimitExceeded && call.amount > cap / 2n) {
      warnings.push(`spends ${call.amount}, over half the per-proposal cap in one go`);
    }

    const discrepancies = blocking
      .concat(warnings)
      .concat(verdict.findings.map(function (code) { return FINDING_CODES[code]; }));

    let status;
    let riskScore = verdict.risk_band;
    if (blocking.length) {
      status = 'VETOED';
      riskScore = Math.max(riskScore, VETO_RISK_FLOOR);
    } else if (warnings.length || verdict.findings.length || verdict.intent_match !== 'MATCH' || riskScore >= FLAG_RISK_FLOOR) {
      status = 'FLAGGED';
      riskScore = Math.max(riskScore, FLAG_RISK_FLOOR);
    } else {
      status = 'PASSED';
    }

    const summary = discrepancies.length
      ? `${status}: ` + discrepancies.slice(0, 3).join('; ')
      : `${status}: calldata matches the proposal text and stays inside the whitelist and spending cap`;

    return {
      proposal_id: options.proposalId,
      title: options.title,
      status: status,
      risk_score: Math.max(0, Math.min(100, riskScore)),
      summary: summary,
      discrepancies: discrepancies,
      spending_limit_exceeded: spendingLimitExceeded,
      unwhitelisted_target: unwhitelistedTarget,
      privilege_escalation_detected: privilegeEscalation,
      decoded_method: call.method_name,
      decoded_recipient: call.recipient,
      // String, not BigInt: JSON.stringify refuses BigInt outright and a Number would
      // lose the top bits of a uint256.
      decoded_amount: call.amount.toString()
    };
  }

  /* Stands in for the GenVM's LLM round, which the browser has no way to run.
   *
   * It reads the same evidence the real prompt hands the model, the proposal text
   * against the decoded bytes, and answers in the same closed vocabulary. Presets
   * carry the verdict pinned in the benchmark instead, so the numbers on screen for
   * those match what CI asserts. Anything typed by hand lands here and is labelled
   * as simulated in the UI.
   */
  function simulateAuditor(proposal, call, config) {
    const findings = new Set();
    const claimedTo = normAddress(proposal.claimedRecipient);
    const claimed = BigInt(proposal.claimedAmount || 0);
    const cap = BigInt(config.maxSingleSpend);
    const text = `${proposal.title || ''} ${proposal.description || ''}`.toLowerCase();

    if (call.method_name === UNKNOWN_METHOD || call.method_name === MALFORMED_METHOD) {
      findings.add('VAGUE_DESCRIPTION');
      findings.add('INTENT_MISMATCH');
    }
    if (Boolean(claimedTo) && call.recipient !== ZERO_ADDRESS && claimedTo !== call.recipient) {
      findings.add('RECIPIENT_MISMATCH');
    }
    const foundAddresses = (text.match(/0x[a-f0-9]{40}/gi) || []).map(normAddress);
    foundAddresses.forEach(function (addr) {
      if (call.recipient !== ZERO_ADDRESS && addr !== call.recipient && addr !== call.target) {
        findings.add('RECIPIENT_MISMATCH');
        findings.add('INTENT_MISMATCH');
      }
    });
    if (VALUE_METHODS.has(call.method_name)) {
      if (claimed !== call.amount) findings.add('AMOUNT_MISMATCH');
      if (claimed === 0n && call.amount > 0n) findings.add('HIDDEN_TRANSFER');
      if (call.amount > cap) findings.add('CONSTITUTION_BREACH');
    }
    if (call.method_name === 'approve' && call.amount === MAX_UINT256) {
      findings.add('UNLIMITED_APPROVAL');
    }

    const disclosureWords = {
      transferOwnership: ['ownership', 'owner', 'transfer control', 'hand over'],
      grantRole: ['role', 'permission', 'admin', 'grant'],
      upgradeTo: ['upgrade', 'implementation', 'proxy'],
      upgradeToAndCall: ['upgrade', 'implementation', 'proxy']
    };
    const privilegeFinding = {
      transferOwnership: 'OWNERSHIP_TRANSFER',
      grantRole: 'ROLE_GRANT',
      upgradeTo: 'PROXY_UPGRADE',
      upgradeToAndCall: 'PROXY_UPGRADE'
    };
    if (PRIVILEGED_METHODS.has(call.method_name)) {
      const disclosed = disclosureWords[call.method_name].some(function (word) { return text.includes(word); });
      if (!disclosed) {
        findings.add(privilegeFinding[call.method_name]);
        findings.add('INTENT_MISMATCH');
      }
    }
    if ((proposal.description || '').trim().length < 40) {
      findings.add('VAGUE_DESCRIPTION');
    }

    const list = Array.from(findings);
    const severe = ['RECIPIENT_MISMATCH', 'AMOUNT_MISMATCH', 'INTENT_MISMATCH', 'HIDDEN_TRANSFER'];
    let intent = 'MATCH';
    if (list.some(function (code) { return severe.includes(code); })) {
      intent = 'MISMATCH';
    } else if (list.length) {
      intent = 'PARTIAL';
    }

    return canonicalVerdict({
      intent_match: intent,
      risk_band: Math.min(100, list.length * 20 + (intent === 'MISMATCH' ? 40 : 0)),
      findings: list
    });
  }

  class GovSentinelClient {
    constructor(dao) {
      this.dao = dao;
      this.allowed = new Set((dao.whitelistedTargets || []).map(normAddress));
      const self = this;
      this.config = {
        daoName: dao.name,
        constitutionRules: dao.constitutionRules,
        maxSingleSpend: BigInt(dao.maxSingleSpend),
        treasuryToken: normAddress(dao.treasuryToken),
        whitelisted: function (target) { return self.allowed.has(normAddress(target)); }
      };
    }

    isWhitelisted(target) {
      return this.config.whitelisted(target);
    }

    evaluateProposal(proposalData) {
      const call = decodeCalldata(proposalData.targetContract, proposalData.calldataHex);
      const source = proposalData.auditorVerdict ? 'pinned' : 'simulated';
      const raw = proposalData.auditorVerdict || simulateAuditor(proposalData, call, this.config);
      const consensus = runConsensus(raw);

      const evaluation = applyPolicy(this.config, call, {
        proposalId: proposalData.proposalId || proposalData.id || 'ad-hoc',
        title: proposalData.title || '',
        claimedRecipient: proposalData.claimedRecipient,
        claimedAmount: proposalData.claimedAmount,
        verdict: consensus.verdict
      });

      return Object.assign(evaluation, {
        decoded: Object.assign({}, call, { amount: call.amount.toString() }),
        consensus: {
          agreed: consensus.agreed,
          validators: consensus.validators,
          auditor_source: source,
          intent_match: consensus.verdict.intent_match,
          risk_band: consensus.verdict.risk_band,
          findings: consensus.verdict.findings
        }
      });
    }
  }

  global.GovSentinel = {
    GovSentinelClient,
    decodeCalldata,
    applyPolicy,
    canonicalVerdict,
    parseAuditorReply,
    runConsensus,
    simulateAuditor,
    normAddress,
    FINDING_CODES,
    METHODS,
    PRIVILEGED_METHODS,
    VALUE_METHODS,
    RISK_BANDS,
    MAX_UINT256,
    ZERO_ADDRESS,
    UNKNOWN_METHOD,
    MALFORMED_METHOD
  };

  if (typeof module === 'object' && module.exports) {
    module.exports = global.GovSentinel;
  }
})(typeof window !== 'undefined' ? window : globalThis);


