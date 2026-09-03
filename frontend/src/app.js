/* UI coordinator: preset wiring, form state, and rendering of the audit result. */
(function () {
  'use strict';

  const { GovSentinelClient, decodeCalldata, FINDING_CODES, MAX_UINT256,
          UNKNOWN_METHOD, MALFORMED_METHOD } = window.GovSentinel;

  const GAUGE_CIRCUMFERENCE = 2 * Math.PI * 60;
  const VERDICT_ICONS = { PASSED: 'verified', VETOED: 'gavel', FLAGGED: 'warning' };
  const GAUGE_STROKE = { PASSED: '#10b981', VETOED: '#ef4444', FLAGGED: '#f59e0b' };
  const BAND_NAMES = { 0: 'None', 20: 'Low', 40: 'Moderate', 60: 'Elevated', 80: 'High', 100: 'Severe' };
  const MODEL_FINDINGS = new Set(Object.values(FINDING_CODES));

  const dao = window.DAO_CONFIG;
  const presets = window.PRESET_SCENARIOS;
  const client = new GovSentinelClient(dao);

  const $ = (id) => document.getElementById(id);

  const el = {
    presets: $('presets'),
    form: $('audit-form'),
    daoLine: $('dao-line'),
    title: $('proposal-title'),
    description: $('proposal-description'),
    target: $('target-contract'),
    targetNote: $('target-note'),
    recipient: $('claimed-recipient'),
    amount: $('claimed-amount'),
    calldata: $('calldata-hex'),
    calldataNote: $('calldata-note'),
    run: $('run-audit'),
    runLabel: document.querySelector('.run-label'),
    empty: $('result-empty'),
    body: $('result-body'),
    resultSub: $('result-sub'),
    banner: $('verdict-banner'),
    verdictIcon: $('verdict-icon'),
    verdictStatus: $('verdict-status'),
    verdictSummary: $('verdict-summary'),
    arc: $('gauge-arc'),
    riskValue: $('risk-value'),
    factBand: $('fact-band'),
    factIntent: $('fact-intent'),
    factSource: $('fact-source'),
    factId: $('fact-id'),
    method: $('decoded-method'),
    decodedRecipient: $('decoded-recipient'),
    decodedAmount: $('decoded-amount'),
    whitelist: $('decoded-whitelist'),
    decodedExtra: $('decoded-extra'),
    discrepancies: $('discrepancies'),
    discrepancyCount: $('discrepancy-count'),
    pipeline: $('pipeline'),
    metricAudited: $('metric-audited'),
    metricBlocked: $('metric-blocked'),
    metricRisk: $('metric-risk'),
    metricWhitelist: $('metric-whitelist')
  };

  const session = { audited: 0, blocked: 0, riskTotal: 0 };
  let activePreset = null;
  let running = false;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function groupDigits(value) {
    return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function describeAmount(raw) {
    if (raw === MAX_UINT256.toString()) {
      return 'unlimited (2^256 âˆ’ 1)';
    }
    return groupDigits(raw);
  }

  /* ---------- presets ---------- */

  function buildPresets() {
    presets.forEach(function (scenario) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'preset-btn';
      button.dataset.scenario = scenario.id;
      button.title = scenario.notes;
      button.innerHTML =
        `<span class="preset-dot ${scenario.severity}"></span><span>${scenario.label}</span>`;
      button.addEventListener('click', function () { loadPreset(scenario); });
      el.presets.appendChild(button);
    });
  }

  function loadPreset(scenario) {
    el.title.value = scenario.title;
    el.description.value = scenario.description;
    el.target.value = scenario.targetContract;
    el.recipient.value = scenario.claimedRecipient;
    el.amount.value = scenario.claimedAmount;
    el.calldata.value = scenario.calldataHex;
    activePreset = scenario;
    markActivePreset(scenario.id);
    refreshHints();
  }

  function markActivePreset(id) {
    el.presets.querySelectorAll('.preset, .preset-btn').forEach(function (button) {
      button.classList.toggle('active', button.dataset.scenario === id); button.classList.toggle('is-active', button.dataset.scenario === id);
    });
  }

  /* ---------- live hints ---------- */

  function refreshHints() {
    const target = el.target.value.trim();
    if (target) {
      const known = client.isWhitelisted(target);
      el.targetNote.hidden = false;
      el.targetNote.textContent = known
        ? 'On the DAO whitelist'
        : 'Not on the DAO whitelist. The gate fails closed on unknown targets.';
      el.targetNote.className = 'field-note ' + (known ? 'is-good' : 'is-bad');
    } else {
      el.targetNote.hidden = true;
    }

    const calldata = el.calldata.value.trim();
    if (calldata) {
      const call = decodeCalldata(target, calldata);
      const bad = call.method_name === UNKNOWN_METHOD || call.method_name === MALFORMED_METHOD;
      el.calldataNote.hidden = false;
      el.calldataNote.textContent = bad
        ? `Does not decode: ${call.extra_params[0]}`
        : `Decodes as ${call.signature}`;
      el.calldataNote.className = 'field-note ' + (bad ? 'is-bad' : 'is-good');
    } else {
      el.calldataNote.hidden = true;
    }
  }

  /* ---------- pipeline ---------- */

  function pipelineStep(name) {
    return el.pipeline.querySelector(`[data-step="${name}"]`);
  }

  function resetPipeline() {
    el.pipeline.querySelectorAll('.step').forEach(function (step) {
      step.classList.remove('is-running', 'is-done', 'is-failed');
    });
  }

  function setStep(name, state, detail) {
    const step = pipelineStep(name);
    step.classList.remove('is-running', 'is-done', 'is-failed');
    if (state) step.classList.add(`is-${state}`);
    if (detail) step.querySelector('.step-detail').textContent = detail;
  }

  /* ---------- rendering ---------- */

  function renderVerdict(result) {
    el.banner.className = `verdict ${result.status}`;
    el.verdictIcon.textContent = VERDICT_ICONS[result.status];
    el.verdictStatus.textContent = result.status;
    el.verdictSummary.textContent = result.summary.replace(`${result.status}: `, '');
  }

  function renderGauge(result) {
    el.arc.style.stroke = GAUGE_STROKE[result.status];
    el.arc.style.strokeDashoffset =
      GAUGE_CIRCUMFERENCE * (1 - result.risk_score / 100);

    // Count up rather than snapping, so the number tracks the arc sweeping round.
    const target = result.risk_score;
    const started = performance.now();
    const duration = 850;
    (function tick(now) {
      const progress = Math.min(1, (now - started) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      el.riskValue.textContent = progress < 1 ? Math.round(target * eased) : target;
      if (progress < 1) requestAnimationFrame(tick);
    })(started);
    // · hidden or backgrounded tab gets no animation frames at all, which would leave
    // the number stuck at zero under · full arc. Timers still fire, so this lands the
    // real score either way.
    setTimeout(function () { el.riskValue.textContent = target; }, duration + 60);

    el.factBand.textContent = `${BAND_NAMES[result.consensus.risk_band]} (${result.consensus.risk_band})`;
    el.factIntent.textContent = result.consensus.intent_match;
    el.factSource.textContent =
      result.consensus.auditor_source === 'pinned' ? 'Pinned benchmark verdict' : 'Simulated locally';
    el.factId.textContent = result.proposal_id;
  }

  function renderDecoded(result) {
    const call = result.decoded;
    const readable = call.method_name !== UNKNOWN_METHOD && call.method_name !== MALFORMED_METHOD;

    el.method.textContent = readable ? call.signature : `${call.method_name} (${call.signature || 'no selector'})`;
    el.decodedRecipient.textContent = readable ? call.recipient : 'n/a';
    el.decodedAmount.textContent = readable ? describeAmount(call.amount) : 'n/a';

    const whitelisted = !result.unwhitelisted_target;
    el.whitelist.innerHTML =
      `<span class="tag ${whitelisted ? 'ok' : 'bad'}">` +
      `<span class="material-symbols-rounded" style="font-size:14px">${whitelisted ? 'check_circle' : 'block'}</span>` +
      `${whitelisted ? 'Approved target' : 'Not whitelisted'}</span>`;

    if (call.extra_params.length) {
      el.decodedExtra.hidden = false;
      el.decodedExtra.textContent = call.extra_params.join(' • ');
    } else {
      el.decodedExtra.hidden = true;
    }
  }

  function renderDiscrepancies(result) {
    el.discrepancies.innerHTML = '';
    el.discrepancyCount.textContent = result.discrepancies.length;
    el.discrepancyCount.classList.toggle('is-hot', result.discrepancies.length > 0);

    if (!result.discrepancies.length) {
      el.discrepancies.className = 'alert-box is-clean';
      el.discrepancies.innerHTML =
        '<div class="alert-item is-clean"><span class="material-symbols-rounded">check_circle</span>' +
        '<span>Nothing flagged. The calldata does what the proposal says it does.</span></div>';
      return;
    }

    el.discrepancies.className = 'alert-box';
    result.discrepancies.forEach(function (text, index) {
      // Findings sourced from the auditor are advisory; everything else was decided
      // from the bytes and is what actually moved the verdict.
      const soft = MODEL_FINDINGS.has(text);
      const item = document.createElement('div');
      item.className = 'alert-item' + (soft ? ' is-soft' : '');
      item.style.animationDelay = `${index * 45}ms`;
      item.innerHTML =
        `<span class="material-symbols-rounded">${soft ? 'psychology_alt' : 'report'}</span><span></span>`;
      item.lastElementChild.textContent = text;
      el.discrepancies.appendChild(item);
    });
  }

  function renderMetrics(result) {
    session.audited += 1;
    session.riskTotal += result.risk_score;
    if (result.status !== 'PASSED') session.blocked += 1;

    el.metricAudited.textContent = session.audited;
    el.metricBlocked.textContent = session.blocked;
    el.metricRisk.textContent = Math.round(session.riskTotal / session.audited);
  }

  /* ---------- run ---------- */

  async function runAudit(event) {
    event.preventDefault();
    if (running) return;

    const calldata = el.calldata.value.trim();
    if (!calldata) {
      el.calldataNote.hidden = false;
      el.calldataNote.className = 'field-note is-bad';
      el.calldataNote.textContent = 'Paste calldata or pick · preset before running the audit.';
      el.calldata.focus();
      return;
    }

    running = true;
    el.run.disabled = true;
    el.run.classList.add('is-busy');
    el.runLabel.textContent = 'Running consensus roundâ€¦';
    el.empty.hidden = true;
    el.body.hidden = false;
    resetPipeline();

    const proposal = {
      proposalId: activePreset ? activePreset.id : 'ad-hoc',
      title: el.title.value.trim(),
      description: el.description.value.trim(),
      targetContract: el.target.value.trim(),
      calldataHex: calldata,
      claimedRecipient: el.recipient.value.trim(),
      claimedAmount: (el.amount.value.trim().replace(/[,\s]/g, '') || '0'),
      // · pinned verdict only describes the proposal it was pinned to. Editing any
      // field drops it and falls back to the local stand-in auditor.
      auditorVerdict: activePreset ? activePreset.auditorVerdict : null
    };

    setStep('leader', 'running');
    await sleep(320);
    const result = client.evaluateProposal(proposal);
    setStep('leader', 'done', `Decoded ${result.decoded.signature || result.decoded.method_name}`);

    setStep('equivalence', 'running');
    await sleep(360);
    const { agreed, validators, auditor_source: source } = result.consensus;
    setStep(
      'equivalence',
      agreed ? 'done' : 'failed',
      agreed
        ? `${validators}/${validators} validators produced identical canonical bytes`
        : 'Validators disagreed, the round would be retried on chain'
    );

    setStep('finality', 'running');
    await sleep(300);
    // session.audited has not been incremented yet, so it is the 0-based slot this
    // record would land in, matching get_evaluation(index) on the contract.
    setStep('finality', 'done',
      `Stored at evaluations[${session.audited}] with status ${result.status}`);

    renderVerdict(result);
    renderGauge(result);
    renderDecoded(result);
    renderDiscrepancies(result);
    renderMetrics(result);

    el.resultSub.textContent = `${source === "pinned" ? "Benchmark scenario" : "Ad-hoc proposal"} • Risk ${result.risk_score}/100`;

    running = false;
    el.run.disabled = false;
    el.run.classList.remove('is-busy');
    el.runLabel.textContent = 'Run Multi-Validator Consensus Audit';
  }

  /* ---------- boot ---------- */

  function init() {
    el.daoLine.textContent = `${dao.name} • Spend Cap: ${groupDigits(dao.maxSingleSpend)} USDC • ${dao.whitelistedTargets.length} Whitelisted Targets`;
    el.metricWhitelist.textContent = dao.whitelistedTargets.length;

    buildPresets();
    el.form.addEventListener('submit', runAudit);

    [el.title, el.description, el.target, el.recipient, el.amount, el.calldata]
      .forEach(function (input) {
        input.addEventListener('input', function () {
          if (activePreset) {
            activePreset = null;
            markActivePreset(null);
          }
          refreshHints();
        });
      });

    // Start clean without prefilled data
  }

  document.addEventListener('DOMContentLoaded', init);
})();




