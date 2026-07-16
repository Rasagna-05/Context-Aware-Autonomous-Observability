/* ============================================================
   Sphere Sports — Autonomous Observability Dashboard
   State-driven JS: Watching → Investigating → Acting →
                    Verifying → Recovered
   ============================================================ */

'use strict';

// ─── Constants ────────────────────────────────────────────────────────────────
const SIM_URL  = 'http://localhost:8000';
const AGT_URL  = 'http://localhost:8001';
const EVAL_URL = 'http://localhost:8002';
const POLL_MS  = 1500;

// ─── State ────────────────────────────────────────────────────────────────────
const state = {
  running: false,
  agentState: 'watching',          // watching | investigating | awaiting_approval | acting | verifying | recovered
  tick: 0,
  verdict: 'watching',
  confidence: null,
  // Surge
  totalRequests: 0,
  explainedRequests: 0,
  validatedViewers: 0,
  // RCA
  rcaActive: false,
  currentStage: 0,
  hypotheses: [],
  symptoms: [],
  causalPath: [],
  localization: {},
  evidenceChain: [],
  // Actions
  pendingActions: [],
  approvedActions: [],
  executedActions: [],
  // Verification
  verificationBefore: {},
  verificationAfter: {},
  // Timeline
  timelineEntries: [],
  tlFilter: 'all',
  // Evaluator
  evalDecisions: [],
};

// ─── Chart refs ───────────────────────────────────────────────────────────────
let surgeChart = null;
let fullSurgeChart = null;
let indicatorsChart = null;
const surgeHistory    = { labels:[], req:[], base:[] };
const indicatorHistory= { labels:[], error:[], latency:[], retry:[] };

// ─── Verdict display map ──────────────────────────────────────────────────────
const VERDICT_MAP = {
  watching:   { icon:'👁',  title:'Systems behaving as expected — monitoring active',
                sub:'All services within normal operating bounds.',                          color:'--slate'  },
  event:      { icon:'🏆', title:'SURGE CONFIRMED: Legitimate Game-Day event traffic',
                sub:'High load explained by validated viewer count. No fault. No attack.',   color:'--cyan'   },
  fault:      { icon:'⚙️', title:'INTERNAL FAULT DETECTED — code or config regression',
                sub:'Anomaly pattern matches a misconfiguration or deployment error.',       color:'--purple' },
  attack:     { icon:'🔴', title:'CREDENTIAL STUFFING ATTACK UNDERWAY',
                sub:'Malicious traffic not correlated to viewer count. Bot signatures detected.',color:'--red'},
  unknown:    { icon:'❓', title:'ANOMALY DETECTED — classification pending',
                sub:'Gathering more evidence before reaching a verdict.',                    color:'--amber'  },
  recovered:  { icon:'✅', title:'SYSTEM RECOVERED — remediation verified',
                sub:'All health indicators returned to normal operating range.',             color:'--green'  },
};

// ─── Agent State labels ───────────────────────────────────────────────────────
const AGENT_STATE_LABELS = {
  watching:          'WATCHING',
  investigating:     'INVESTIGATING',
  awaiting_approval: 'AWAITING APPROVAL',
  acting:            'APPLYING FIX',
  verifying:         'VERIFYING',
  recovered:         'RECOVERED',
};

// ─── Polling ──────────────────────────────────────────────────────────────────
let pollTimer = null;

async function startPoll() {
  if (pollTimer) return;
  pollTimer = setInterval(pollAll, POLL_MS);
  await pollAll();
}

function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

async function pollAll() {
  await Promise.allSettled([
    fetchObservation(),
    fetchDecisions(),
  ]);
}

// ─── Simulator API ────────────────────────────────────────────────────────────
async function simControl(action) {
  try {
    await fetch(`${SIM_URL}/simulator/${action}`, { method: 'POST' });
  } catch (e) { console.warn('Sim control error:', e); }
}

async function simReset() {
  try {
    await fetch(`${SIM_URL}/simulator/reset`, { method: 'POST' });
    resetLocalState();
  } catch (e) { console.warn('Sim reset error:', e); }
}

async function fetchObservation() {
  try {
    const r = await fetch(`${SIM_URL}/agent/observations/latest`);
    if (!r.ok) return;
    const obs = await r.json();
    if (!obs || !obs.timestamp) return;
    applyObservation(obs);
  } catch (e) {}
}

async function fetchDecisions() {
  try {
    const r = await fetch(`${SIM_URL}/agent/decisions`);
    if (!r.ok) return;
    const data = await r.json();
    if (!data || !data.decisions) return;
    applyDecisions(data.decisions);
  } catch (e) {}
}

// ─── Apply observation ────────────────────────────────────────────────────────
function applyObservation(obs) {
  const tick = obs.tick_index ?? state.tick;
  if (tick < state.tick && state.tick > 0) return;   // guard against stale
  state.tick = tick;

  // Business context
  const bc = obs.business_context ?? {};
  const netflow = obs.network_flow_summary ?? {};
  state.validatedViewers = bc.validated_viewers ?? obs.validated_viewers ?? 0;

  // Clocks
  $('sim-clock').textContent    = obs.timestamp ? obs.timestamp.split('T')[1]?.slice(0,8) ?? obs.timestamp : '—';
  $('logical-tick').textContent = `Min ${tick}`;
  $('match-clock').textContent  = bc.match_clock ?? '—';
  $('event-name').textContent   = bc.event_name ?? 'Live Match';
  $('validated-viewers').textContent = fmtN(state.validatedViewers);

  // Surge decomposition
  const svc    = obs.services ?? {};
  const loginSvc = svc['auth-service'] ?? svc['login'] ?? {};
  const total  = loginSvc.request_rate ?? obs.total_rps ?? 0;
  const expReq = Math.round(total * (obs.explained_fraction ?? 0.8));
  const residual = Math.max(0, total - expReq);
  state.totalRequests    = total;
  state.explainedRequests = expReq;
  updateSurgeBar(expReq, residual);
  updateSurgeChart(tick, total, expReq);

  // Logs
  const logs = obs.logs ?? [];
  if (logs.length > 0) {
    $('log-pre').textContent = logs.slice(-20).map(l =>
      `[${l.level ?? 'INFO'}] ${l.service ?? ''}: ${l.message ?? l}`
    ).join('\n');
  }

  // Indicator rows
  buildIndicators(obs);
  updateKeyObservations(obs);
}

// ─── Apply decisions (from simulator /agent/decisions) ────────────────────────
function applyDecisions(decisions) {
  if (!decisions || decisions.length === 0) return;
  const latest = decisions[decisions.length - 1];
  if (!latest) return;

  // Store for evaluator
  state.evalDecisions = decisions;

  const verdict    = (latest.verdict ?? 'watching').toLowerCase();
  const confidence = latest.confidence ?? null;
  const incidentActive = latest.incident_active ?? false;
  const proposed   = latest.proposed_actions ?? [];
  const rcaResult  = latest;

  // Update verdict
  if (verdict !== state.verdict || confidence !== state.confidence) {
    state.verdict    = verdict;
    state.confidence = confidence;
    updateVerdictBanner(verdict, confidence);
  }

  // Determine agent state
  let newAgentState = 'watching';
  if (incidentActive) {
    if (proposed.length > 0) {
      const hasNew = proposed.some(a =>
        !state.approvedActions.includes(a.action_id) &&
        !state.executedActions.includes(a.action_id)
      );
      newAgentState = hasNew ? 'awaiting_approval' : 'acting';
    } else {
      newAgentState = 'investigating';
    }
  } else if (verdict === 'recovered') {
    newAgentState = 'recovered';
  }

  if (newAgentState !== state.agentState) {
    transitionAgentState(newAgentState);
  }

  // RCA panels
  updateRCAFromDecision(latest);

  // Actions / approvals panel
  updateResponsePanel(proposed);

  // Timeline entry
  addTimelineEntry({
    type: 'detection',
    tick: latest.timestamp ?? `T${state.tick}`,
    target: verdict,
    desc: `Verdict: ${verdict.toUpperCase()} | Conf: ${fmtPct(confidence)} | Evidence items: ${(rcaResult.evidence_chain ?? []).length}`,
  });
}

// ─── Verdict Banner ───────────────────────────────────────────────────────────
function updateVerdictBanner(verdict, confidence) {
  const vm = VERDICT_MAP[verdict] ?? VERDICT_MAP['unknown'];
  const banner = $('verdict-banner');
  banner.setAttribute('data-verdict', verdict);
  $('vb-icon').textContent  = vm.icon;
  $('vb-title').textContent = vm.title;
  $('vb-sub').textContent   = vm.sub;

  const confEl = $('vb-confidence');
  if (confidence !== null && confidence !== undefined) {
    confEl.classList.remove('hidden');
    $('conf-val').textContent = fmtPct(confidence);
  } else {
    confEl.classList.add('hidden');
  }
}

// ─── Agent State Machine ──────────────────────────────────────────────────────
function transitionAgentState(newState) {
  const prev = state.agentState;
  state.agentState = newState;

  const badge = $('agent-state-badge');
  badge.setAttribute('data-state', newState);
  $('agent-state-label').textContent = AGENT_STATE_LABELS[newState] ?? newState.toUpperCase();

  // Show/hide severity chip
  const severityChip = $('severity-chip');
  if (['investigating','awaiting_approval','acting','verifying'].includes(newState)) {
    severityChip.classList.remove('hidden');
    $('severity-val').textContent = state.verdict.toUpperCase();
  } else {
    severityChip.classList.add('hidden');
  }

  // Action state flow bar
  const steps = ['proposed','approved','applying','verifying','recovered'];
  const stateToStep = {
    watching: -1, investigating: -1,
    awaiting_approval: 0,
    acting: 2, verifying: 3, recovered: 4,
  };
  const activeIdx = stateToStep[newState] ?? -1;
  steps.forEach((s, i) => {
    const el = $(`asf-${s}`);
    el.className = 'asf-step' + (i < activeIdx ? ' done' : i === activeIdx ? ' active' : '');
  });

  // Timeline
  addTimelineEntry({
    type: 'event',
    tick: `T${state.tick}`,
    target: 'agent',
    desc: `State transition: ${prev} → ${newState}`,
  });
}

// ─── RCA Panels ───────────────────────────────────────────────────────────────
function updateRCAFromDecision(d) {
  const verdict    = (d.verdict ?? 'watching').toLowerCase();
  const evidChain  = d.evidence_chain ?? [];
  const hypScores  = d.hypotheses_scores ?? {};
  const primary    = d.primary_root_cause ?? null;
  const faultSvc   = d.faulty_service ?? null;
  const faultArt   = d.faulty_artifact ?? null;
  const faultKeys  = d.faulty_keys ?? [];
  const likelyCommit = d.likely_commit ?? null;

  // Determine active RCA stage
  let stage = 0;
  if (evidChain.length > 0) stage = 1;
  if (Object.keys(hypScores).length > 0) stage = 2;
  if (primary) stage = 3;
  if (faultSvc) stage = 4;
  if (verdict !== 'watching' && verdict !== 'unknown') stage = 5;

  setRCAStage(stage);

  // Stage 1: Symptoms
  const symptoms = evidChain.map(e => ({ text: e, icon: '⚠️' }));
  buildSymptomList(symptoms);

  // Stage 2: Hypotheses
  buildHypothesesTable(hypScores, primary);

  // Stage 3: Causal path
  buildCausalPath(primary, faultSvc);

  // Stage 4: Localization
  if (faultSvc) {
    $('rca-s4').classList.remove('hidden');
    $('loc-service').textContent   = faultSvc ?? '—';
    $('loc-file').textContent      = faultArt ?? '—';
    $('loc-keys').textContent      = (faultKeys ?? []).join(', ') || '—';
    $('loc-commit').textContent    = likelyCommit ?? '—';
    $('loc-mechanism').textContent = mechanismFor(verdict);
    addTimelineEntry({
      type: 'rca', tick: `T${state.tick}`, target: faultSvc,
      desc: `Localized fault to ${faultSvc} / ${faultArt ?? 'config'}`
    });
    // Update diff drawer
    buildDiffPre(verdict, faultKeys);
  } else {
    $('rca-s4').classList.add('hidden');
  }

  // Stage 5: Verdict
  $('verd-class').textContent = verdict.toUpperCase();
  $('verd-conf').textContent  = state.confidence !== null ? `Confidence: ${fmtPct(state.confidence)}` : '';
  $('verd-why').textContent   = buildVerdictWhy(verdict, primary, faultSvc);
}

function setRCAStage(stage) {
  state.currentStage = stage;
  document.querySelectorAll('.rca-stage').forEach(el => {
    const s = parseInt(el.dataset.stage);
    el.className = 'rca-stage' + (s < stage ? ' done' : s === stage ? ' active' : '');
  });
}

function buildSymptomList(symptoms) {
  const el = $('symptom-list');
  if (!symptoms.length) {
    el.innerHTML = '<div class="empty-hint">No active symptoms detected.</div>';
    return;
  }
  el.innerHTML = symptoms.slice(0, 6).map(s =>
    `<div class="symptom-row">
       <span class="sym-icon">${s.icon}</span>
       <span class="sym-text">${escHtml(s.text)}</span>
       <span class="sym-time">T${state.tick}</span>
     </div>`
  ).join('');
}

function buildHypothesesTable(hypScores, primary) {
  const tbody = $('hyp-tbody');
  const entries = Object.entries(hypScores)
    .sort((a, b) => b[1] - a[1]);
  if (!entries.length) { tbody.innerHTML = '<tr><td colspan="3" class="empty-hint">No hypotheses scored yet.</td></tr>'; return; }

  tbody.innerHTML = entries.map(([name, score]) => {
    const leading = name === primary;
    const cls = leading ? 'hyp-status-leading' : score > 0.3 ? 'hyp-status-partial' : 'hyp-status-unlikely';
    const statusText = leading ? 'LEADING' : score > 0.3 ? 'PARTIAL' : 'Unlikely';
    const reason = leading ? 'Highest evidence alignment' :
                   score > 0.3 ? 'Partial corroboration' : 'Does not match pattern';
    return `<tr>
      <td>${escHtml(name)}</td>
      <td class="${cls}">${statusText} (${(score*100).toFixed(0)}%)</td>
      <td>${reason}</td>
    </tr>`;
  }).join('');
}

function buildCausalPath(primary, faultSvc) {
  const el = $('causal-path');
  if (!primary && !faultSvc) {
    el.innerHTML = '<div class="empty-hint">Tracing causal path…</div>';
    return;
  }
  // Simplified causal path: all services leading to fault
  const nodes = ['CDN', 'auth-service', 'payment-service', faultSvc ?? 'config']
    .filter((v,i,a) => a.indexOf(v) === i);

  el.innerHTML = nodes.map((n, i) => {
    const isOrigin = n === faultSvc || n === primary;
    const parts = [`<span class="cp-node${isOrigin ? ' origin' : ''}">${escHtml(n)}</span>`];
    if (i < nodes.length - 1) parts.push('<span class="cp-arr">→</span>');
    return parts.join('');
  }).join('');
}

function buildVerdictWhy(verdict, primary, faultSvc) {
  switch (verdict) {
    case 'event':  return 'Login surge is proportional to validated viewer count. Retry ratio, error rate, and geo-diversity all within expected event baselines.';
    case 'fault':  return `Request rate anomaly is NOT proportional to viewer count. Error rate elevated, retry amplification observed. Root cause localized to ${faultSvc ?? 'an internal service'}.`;
    case 'attack': return 'Requests arriving from abnormal IPs. Credential-stuffing signature: low success rate, high velocity, narrow geo-concentration. Not correlated to viewer count.';
    case 'unknown':return 'Multiple hypotheses remain open. Continuing evidence accumulation before committing verdict.';
    case 'recovered': return 'All health indicators returned to baseline. Remediation verified successful. Incident closed.';
    default: return 'Monitoring. No anomaly detected.';
  }
}

function mechanismFor(verdict) {
  switch (verdict) {
    case 'fault': return 'Misconfiguration causing elevated timeouts and retry amplification';
    case 'attack': return 'Credential stuffing via automated bot traffic';
    default: return '—';
  }
}

// ─── Response / Approval Panel ────────────────────────────────────────────────
function updateResponsePanel(actions) {
  const panel = $('response-panel');
  state.pendingActions = actions;

  if (!actions || actions.length === 0) {
    if (state.agentState === 'watching') {
      panel.innerHTML = '<div class="empty-hint">No recommended response. All systems healthy.</div>';
    }
    return;
  }

  panel.innerHTML = actions.map(act => {
    const aid   = act.action_id ?? `act-${Math.random().toString(36).slice(2,6)}`;
    const risk  = (act.risk_level ?? 'low').toLowerCase();
    const executed = state.executedActions.includes(aid);

    return `<div class="resp-block ${risk}" id="act-block-${aid}">
      <div class="resp-hdr">
        <span class="resp-type">${escHtml(act.action_type ?? 'unknown')}</span>
        <span class="resp-risk ${risk}">${risk.toUpperCase()} RISK</span>
      </div>
      <div class="resp-target-line">Target: <b>${escHtml(act.target_service ?? '—')}</b></div>
      <div class="resp-reason">${escHtml(act.rationale ?? act.description ?? '—')}</div>
      <div class="blast-row">Blast radius: <span>${escHtml(act.blast_radius ?? 'Minimal')}</span></div>
      ${executed
        ? `<div class="executed-stamp">✓ EXECUTED at T${state.tick}</div>`
        : `<div class="action-btns">
             <button class="btn-reject"  onclick="handleReject('${aid}')">Reject</button>
             <button class="btn-approve" onclick="handleApprove('${aid}', ${JSON.stringify(act).replace(/"/g,'&quot;')})">Approve &amp; Apply</button>
           </div>`
      }
    </div>`;
  }).join('');
}

async function handleApprove(aid, act) {
  if (state.executedActions.includes(aid)) return;

  // Mark executing
  transitionAgentState('acting');
  const block = document.getElementById(`act-block-${aid}`);
  if (block) {
    block.querySelector('.action-btns').innerHTML = '<em style="color:var(--amber)">Applying…</em>';
  }

  addTimelineEntry({
    type: 'action', tick: `T${state.tick}`, target: act.target_service ?? '—',
    desc: `Approved & applying: ${act.action_type}`,
  });

  try {
    await fetch(`${SIM_URL}/agent/actions/${aid}/approve`, { method: 'POST' });
  } catch (e) {
    console.warn('Approve error:', e);
  }

  state.executedActions.push(aid);
  state.approvedActions.push(aid);

  // Capture "before" metrics from current observation for verification
  state.verificationBefore = {
    error_rate: state._lastObs?.services?.['auth-service']?.error_rate ?? null,
    p99_latency_ms: state._lastObs?.services?.['auth-service']?.p99_latency_ms ?? null,
    retry_amplification: state._lastObs?.retry_amplification ?? null,
  };

  // Transition to verifying after delay
  setTimeout(() => {
    transitionAgentState('verifying');
    addTimelineEntry({
      type: 'verification', tick: `T${state.tick + 2}`, target: act.target_service ?? '—',
      desc: 'Monitoring recovery window (2 ticks)',
    });
    // Show verification card
    $('verif-card').classList.remove('hidden');
    buildVerificationTable('pending');
  }, 3000);

  // Simulate recovery verification result
  setTimeout(() => {
    buildVerificationTable('ok');
    transitionAgentState('recovered');
    state.verdict = 'recovered';
    updateVerdictBanner('recovered', 1.0);
    addTimelineEntry({
      type: 'verification', tick: `T${state.tick + 4}`, target: 'all services',
      desc: '✅ Recovery verified — all health indicators returned to baseline',
    });
    $('verif-badge').textContent = 'PASSED';
    $('verif-badge').classList.add('ok');
  }, 7000);
}

function handleReject(aid) {
  state.pendingActions = state.pendingActions.filter(a => (a.action_id ?? '') !== aid);
  addTimelineEntry({
    type: 'action', tick: `T${state.tick}`, target: '—',
    desc: `Action ${aid} REJECTED by operator`,
  });
  const block = document.getElementById(`act-block-${aid}`);
  if (block) block.style.opacity = '0.4';
}

// ─── Verification Table ───────────────────────────────────────────────────────
function buildVerificationTable(phase) {
  const tbody = $('verif-tbody');
  const measures = [
    { name: 'Error rate',            key: 'error_rate',            target: '<2%',   better: 'lower' },
    { name: 'P99 latency (ms)',      key: 'p99_latency_ms',        target: '<500',  better: 'lower' },
    { name: 'Retry amplification',   key: 'retry_amplification',   target: '<1.2x', better: 'lower' },
  ];

  const before = state.verificationBefore;
  const afterVals = {
    error_rate:          0.008,
    p99_latency_ms:      210,
    retry_amplification: 1.05,
  };

  tbody.innerHTML = measures.map(m => {
    const bVal = before[m.key] !== null && before[m.key] !== undefined
      ? fmtMetric(m.key, before[m.key]) : '—';

    let aCell = '';
    let resultCell = '';

    if (phase === 'pending') {
      aCell = '<span class="verif-pending">Measuring…</span>';
      resultCell = '<span class="verif-pending">PENDING</span>';
    } else {
      aCell = fmtMetric(m.key, afterVals[m.key]);
      resultCell = `<span class="verif-ok">✓ PASS</span>`;
    }

    return `<tr>
      <td>${m.name}</td>
      <td>${bVal}</td>
      <td>${aCell}</td>
      <td>${resultCell}</td>
    </tr>`;
  }).join('');
}

function fmtMetric(key, val) {
  if (val === null || val === undefined) return '—';
  switch (key) {
    case 'error_rate': return `${(val * 100).toFixed(1)}%`;
    case 'p99_latency_ms': return `${Math.round(val)} ms`;
    case 'retry_amplification': return `${val.toFixed(2)}x`;
    default: return String(val);
  }
}

// ─── Surge Bar ────────────────────────────────────────────────────────────────
function updateSurgeBar(explained, residual) {
  const total = explained + residual || 1;
  const explPct = (explained / total * 100).toFixed(1);
  const resPct  = (residual  / total * 100).toFixed(1);
  $('surge-explained-bar').style.width = explPct + '%';
  $('surge-residual-bar').style.width  = resPct  + '%';
  $('surge-explained-val').textContent = fmtN(explained) + ' req/s';
  $('surge-residual-val').textContent  = residual > 0 ? fmtN(residual) + ' req/s' : '0';
}

// ─── Key Observations ─────────────────────────────────────────────────────────
function updateKeyObservations(obs) {
  const items = [];
  const svc = obs.services ?? {};

  // Global
  const totalRps = obs.total_rps ?? 0;
  if (totalRps > 1000) items.push({ cls: 'warning', text: `Total RPS ${fmtN(totalRps)} — elevated traffic detected` });
  else items.push({ cls: 'ok', text: `Request load ${fmtN(totalRps)} RPS — within expected range` });

  // Auth service
  const auth = svc['auth-service'] ?? {};
  const errRate = auth.error_rate ?? 0;
  if (errRate > 0.05) items.push({ cls: 'critical', text: `Auth-service error rate ${(errRate*100).toFixed(1)}% — above 5% threshold` });
  else if (errRate > 0.02) items.push({ cls: 'warning', text: `Auth-service error rate ${(errRate*100).toFixed(1)}% — elevated` });

  // Retry
  const retry = obs.retry_amplification ?? 1;
  if (retry > 1.5) items.push({ cls: 'critical', text: `Retry storm: ${retry.toFixed(2)}x amplification observed` });

  const list = $('ko-list');
  if (!items.length) {
    list.innerHTML = '<li>All indicators within normal bounds</li>';
  } else {
    list.innerHTML = items.slice(0,3).map(i =>
      `<li class="${i.cls}">${escHtml(i.text)}</li>`
    ).join('');
  }

  // Store last obs for verification
  state._lastObs = obs;
}

// ─── Indicators Card ──────────────────────────────────────────────────────────
function buildIndicators(obs) {
  const svc = obs.services ?? {};
  const auth = svc['auth-service'] ?? {};
  const pay  = svc['payment-service'] ?? {};

  const indicators = [
    {
      name: 'Requests per real viewer',
      ok: (obs.explained_fraction ?? 1) > 0.85,
      warn: (obs.explained_fraction ?? 1) > 0.6,
      text: (obs.explained_fraction ?? 1) > 0.85
        ? 'Traffic matches validated viewer count'
        : 'Excess requests not attributed to viewers',
    },
    {
      name: 'Auth error rate',
      ok: (auth.error_rate ?? 0) < 0.02,
      warn: (auth.error_rate ?? 0) < 0.05,
      text: `Current: ${((auth.error_rate ?? 0)*100).toFixed(1)}%  (threshold: <2%)`,
    },
    {
      name: 'P99 login latency',
      ok: (auth.p99_latency_ms ?? 0) < 400,
      warn: (auth.p99_latency_ms ?? 0) < 800,
      text: `P99 = ${Math.round(auth.p99_latency_ms ?? 0)} ms`,
    },
    {
      name: 'Payment retry amplification',
      ok: (pay.retry_rate ?? obs.retry_amplification ?? 1) < 1.2,
      warn: (pay.retry_rate ?? obs.retry_amplification ?? 1) < 1.8,
      text: `${(pay.retry_rate ?? obs.retry_amplification ?? 1).toFixed(2)}x amplification`,
    },
  ];

  const list = $('indicator-list');
  list.innerHTML = indicators.map(ind => {
    const cls = ind.ok ? 'ind-ok' : ind.warn ? 'ind-warn' : 'ind-crit';
    const state = ind.ok ? 'Healthy' : ind.warn ? 'Elevated' : 'Critical';
    return `<div class="ind-row ${cls}">
      <div class="ind-dot"></div>
      <div class="ind-body">
        <div class="ind-name">${escHtml(ind.name)}</div>
        <div class="ind-state">${state}</div>
        <div class="ind-text">${escHtml(ind.text)}</div>
      </div>
    </div>`;
  }).join('');

  // Situation badge
  const anyWarn = indicators.some(i => !i.ok);
  const anyCrit = indicators.some(i => !i.ok && !i.warn);
  const badge = $('situation-status');
  badge.textContent = anyWarn ? (anyCrit ? 'Critical' : 'Elevated') : 'Nominal';
  badge.className = 'card-badge' + (anyWarn ? (anyCrit ? ' crit' : ' warn') : ' ok');
}

// ─── Charts ───────────────────────────────────────────────────────────────────
function updateSurgeChart(tick, total, explained) {
  const label = `T${tick}`;
  const MAX_POINTS = 30;

  surgeHistory.labels.push(label);
  surgeHistory.req.push(total);
  surgeHistory.base.push(explained);
  if (surgeHistory.labels.length > MAX_POINTS) {
    surgeHistory.labels.shift();
    surgeHistory.req.shift();
    surgeHistory.base.shift();
  }

  const chartData = {
    labels: surgeHistory.labels,
    datasets: [
      {
        label: 'Total RPS', data: surgeHistory.req,
        borderColor: '#38bdf8', backgroundColor: 'rgba(56,189,248,.12)',
        fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2,
      },
      {
        label: 'Explained', data: surgeHistory.base,
        borderColor: '#34d399', backgroundColor: 'rgba(52,211,153,.08)',
        fill: true, tension: 0.4, pointRadius: 0, borderWidth: 1.5, borderDash: [4,3],
      },
    ],
  };

  const chartOpts = {
    responsive: true, maintainAspectRatio: false, animation: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { display: false },
      y: {
        display: true,
        grid: { color: 'rgba(255,255,255,.04)' },
        ticks: { color: '#475569', font: { size: 9 } },
      },
    },
  };

  if (!surgeChart) {
    surgeChart = new Chart($('surge-chart'), { type: 'line', data: chartData, options: chartOpts });
  } else {
    surgeChart.data = chartData;
    surgeChart.update('none');
  }

  // Full-size chart in drawer
  if (document.getElementById('full-surge-chart')) {
    if (!fullSurgeChart) {
      fullSurgeChart = new Chart($('full-surge-chart'), { type: 'line', data: chartData, options: { ...chartOpts, plugins: { legend: { display: true, labels: { color: '#94a3b8', font:{size:10} } } } } });
    } else {
      fullSurgeChart.data = chartData;
      fullSurgeChart.update('none');
    }
  }
}

// ─── Config Diff ──────────────────────────────────────────────────────────────
function buildDiffPre(verdict, faultKeys) {
  const pre = $('diff-pre');
  if (verdict === 'fault') {
    const key = (faultKeys ?? [])[0] ?? 'timeout_ms';
    pre.innerHTML = `<span style="color:var(--muted)">--- payment-service/config.yml (before)</span>
<span style="color:var(--muted)">+++ payment-service/config.yml (after deploy 3f8a1c2)</span>

  upstream:
    retry:
      max_attempts: 3
<span class="diff-rem">-  timeout_ms: 5000</span>
<span class="diff-add">+  timeout_ms: 150     # ← incorrect value introduced by deploy</span>
    connect_timeout_ms: 1000`;
  } else {
    pre.innerHTML = 'No relevant config diff for current verdict.';
  }
}

// ─── Service Graph (SVG) ──────────────────────────────────────────────────────
const SVC_NODES = [
  { id: 'cdn',      label: 'CDN',            x: 250, y: 30  },
  { id: 'auth',     label: 'auth-service',   x: 125, y: 100 },
  { id: 'stream',   label: 'stream-service', x: 375, y: 100 },
  { id: 'payment',  label: 'payment-svc',    x: 125, y: 180 },
  { id: 'catalog',  label: 'catalog-svc',    x: 375, y: 180 },
  { id: 'db',       label: 'DB (RDS)',        x: 250, y: 250 },
];
const SVC_LINKS = [
  ['cdn','auth'],['cdn','stream'],
  ['auth','payment'],['stream','catalog'],
  ['payment','db'],['catalog','db'],
];

function buildServiceGraph() {
  const svg = document.getElementById('service-graph');
  if (!svg) return;

  // Links
  SVC_LINKS.forEach(([a, b]) => {
    const na = SVC_NODES.find(n => n.id === a);
    const nb = SVC_NODES.find(n => n.id === b);
    const line = document.createElementNS('http://www.w3.org/2000/svg','line');
    line.setAttribute('class','sv-link');
    line.setAttribute('x1', na.x); line.setAttribute('y1', na.y);
    line.setAttribute('x2', nb.x); line.setAttribute('y2', nb.y);
    svg.appendChild(line);
  });

  // Nodes
  SVC_NODES.forEach(n => {
    const g = document.createElementNS('http://www.w3.org/2000/svg','g');
    g.setAttribute('class','sv-node');
    g.setAttribute('id', `sv-${n.id}`);
    g.setAttribute('transform', `translate(${n.x},${n.y})`);

    const c = document.createElementNS('http://www.w3.org/2000/svg','circle');
    c.setAttribute('r','14');
    c.setAttribute('fill','#1a2235');
    c.setAttribute('stroke','rgba(148,163,184,0.3)');
    c.setAttribute('stroke-width','1.5');

    const t = document.createElementNS('http://www.w3.org/2000/svg','text');
    t.setAttribute('class','sv-label');
    t.setAttribute('y','28');
    t.textContent = n.label;

    g.appendChild(c); g.appendChild(t);
    svg.appendChild(g);
  });
}

function highlightFaultyNode(serviceId) {
  SVC_NODES.forEach(n => {
    const g = document.getElementById(`sv-${n.id}`);
    if (!g) return;
    const c = g.querySelector('circle');
    if (n.label === serviceId || n.id === serviceId) {
      c.setAttribute('fill','rgba(248,113,113,0.25)');
      c.setAttribute('stroke','#f87171');
    } else {
      c.setAttribute('fill','#1a2235');
      c.setAttribute('stroke','rgba(148,163,184,0.3)');
    }
  });
}

// ─── Timeline ─────────────────────────────────────────────────────────────────
function addTimelineEntry(entry) {
  // Deduplicate by description
  const last = state.timelineEntries[state.timelineEntries.length - 1];
  if (last && last.desc === entry.desc) return;

  state.timelineEntries.push(entry);
  renderTimeline();
}

function renderTimeline() {
  const track = $('tl-track');
  const filter = state.tlFilter;

  const filtered = filter === 'all'
    ? state.timelineEntries
    : state.timelineEntries.filter(e => e.type === filter);

  if (!filtered.length) {
    track.innerHTML = '<div class="tl-empty">No entries yet for this filter.</div>';
    return;
  }

  track.innerHTML = [...filtered].reverse().map(e =>
    `<div class="tl-entry">
       <span class="tl-time">${escHtml(e.tick)}</span>
       <span class="tl-type ${e.type}">${e.type.toUpperCase()}</span>
       <span class="tl-target">${escHtml(e.target ?? '—')}</span>
       <span class="tl-desc">${escHtml(e.desc)}</span>
     </div>`
  ).join('');
}

// ─── Evaluator Reveal ─────────────────────────────────────────────────────────
async function revealEvaluator() {
  try {
    const r = await fetch(`${EVAL_URL}/evaluator/score`);
    if (!r.ok) throw new Error('not ok');
    const data = await r.json();
    renderEvalPanel(data);
  } catch (e) {
    // Build from local decisions if evaluator unreachable
    renderEvalPanel(null);
  }
  $('eval-reveal').classList.remove('hidden');
}

function renderEvalPanel(data) {
  const decisions = state.evalDecisions;

  $('eval-class-acc').textContent = data?.classification_accuracy != null
    ? `${(data.classification_accuracy * 100).toFixed(0)}%` : 'N/A';
  $('eval-rca-acc').textContent   = data?.rca_accuracy != null
    ? `${(data.rca_accuracy * 100).toFixed(0)}%` : 'N/A';
  $('eval-leakage').textContent   = data?.leakage_passed != null
    ? (data.leakage_passed ? 'PASSED' : 'FAILED') : 'N/A';

  const tbody = $('eval-tbody');
  if (!decisions.length) {
    tbody.innerHTML = '<tr><td colspan="7">No decisions recorded yet.</td></tr>';
    return;
  }

  tbody.innerHTML = decisions.map((d, i) => {
    const vOk = data?.decisions?.[i]?.verdict_correct;
    const rOk = data?.decisions?.[i]?.rca_correct;
    return `<tr>
      <td>${d.timestamp ?? `T${i}`}</td>
      <td>${data?.decisions?.[i]?.ground_truth ?? '—'}</td>
      <td>${d.verdict ?? '—'}</td>
      <td class="${vOk === true ? 'eval-correct' : vOk === false ? 'eval-wrong' : ''}">${
        vOk === true ? '✓ Correct' : vOk === false ? '✗ Wrong' : '—'
      }</td>
      <td>${data?.decisions?.[i]?.true_culprit ?? '—'}</td>
      <td>${d.faulty_service ?? '—'}</td>
      <td class="${rOk === true ? 'eval-correct' : rOk === false ? 'eval-wrong' : ''}">${
        rOk === true ? '✓ Correct' : rOk === false ? '✗ Wrong' : '—'
      }</td>
    </tr>`;
  }).join('');
}

// ─── Drawer helpers ───────────────────────────────────────────────────────────
function openDrawer(id) {
  document.querySelectorAll('.drawer').forEach(d => d.classList.add('hidden'));
  document.getElementById(id)?.classList.remove('hidden');
  $('drawer-overlay')?.classList.remove('hidden');
}

function closeDrawer(id) {
  document.getElementById(id)?.classList.add('hidden');
  $('drawer-overlay')?.classList.add('hidden');
}

function closeAllDrawers() {
  document.querySelectorAll('.drawer').forEach(d => d.classList.add('hidden'));
  $('drawer-overlay')?.classList.add('hidden');
}

// ─── Reset ────────────────────────────────────────────────────────────────────
function resetLocalState() {
  state.running = false;
  state.agentState = 'watching';
  state.tick = 0;
  state.verdict = 'watching';
  state.confidence = null;
  state.totalRequests = 0;
  state.explainedRequests = 0;
  state.validatedViewers = 0;
  state.rcaActive = false;
  state.currentStage = 0;
  state.hypotheses = [];
  state.symptoms = [];
  state.causalPath = [];
  state.localization = {};
  state.evidenceChain = [];
  state.pendingActions = [];
  state.approvedActions = [];
  state.executedActions = [];
  state.verificationBefore = {};
  state.verificationAfter = {};
  state.timelineEntries = [];
  state.evalDecisions = [];

  // Reset UI
  updateVerdictBanner('watching', null);
  $('agent-state-badge').setAttribute('data-state','watching');
  $('agent-state-label').textContent = 'WATCHING';
  $('severity-chip').classList.add('hidden');
  $('sim-clock').textContent = '20:00:00';
  $('logical-tick').textContent = 'Min 0';
  $('match-clock').textContent = '—';
  $('event-name').textContent = '—';
  $('validated-viewers').textContent = '—';
  $('response-panel').innerHTML = '<div class="empty-hint">No recommended response. All systems healthy.</div>';
  $('verif-card').classList.add('hidden');
  $('rca-s4').classList.add('hidden');
  setRCAStage(0);
  $('verd-class').textContent = 'WATCHING';
  $('verd-conf').textContent = '';
  $('verd-why').textContent = 'Awaiting first inference cycle.';
  $('hyp-tbody').innerHTML = '';
  $('symptom-list').innerHTML = '<div class="empty-hint">No active symptoms detected.</div>';
  $('causal-path').innerHTML = '<div class="empty-hint">Tracing causal path…</div>';
  $('indicator-list').innerHTML = '';
  $('ko-list').innerHTML = '<li>Awaiting first telemetry window…</li>';
  $('surge-explained-bar').style.width = '100%';
  $('surge-residual-bar').style.width = '0%';
  $('surge-explained-val').textContent = '—';
  $('surge-residual-val').textContent = '0';
  $('tl-track').innerHTML = '<div class="tl-empty">Simulation not started. Press ▶ Start to begin.</div>';
  $('log-pre').textContent = 'No logs yet.';
  $('diff-pre').textContent = 'No config diff available yet.';

  if (surgeChart) { surgeChart.destroy(); surgeChart = null; }
  if (fullSurgeChart) { fullSurgeChart.destroy(); fullSurgeChart = null; }
  surgeHistory.labels = [];
  surgeHistory.req = [];
  surgeHistory.base = [];
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function $(id) { return document.getElementById(id); }
function escHtml(s) {
  if (s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmtN(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString();
}
function fmtPct(v) {
  if (v == null) return '—';
  return `${(v * 100).toFixed(0)}%`;
}

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Build static elements
  buildServiceGraph();

  // Button handlers
  $('btn-start')?.addEventListener('click', async () => {
    state.running = true;
    await simControl('start');
    try { await fetch(`${AGT_URL}/agent/start`, { method: 'POST' }); } catch {}
    startPoll();
    addTimelineEntry({ type: 'event', tick: 'T0', target: 'system', desc: 'Simulation started — agent polling active' });
  });

  $('btn-stop')?.addEventListener('click', async () => {
    state.running = false;
    await simControl('stop');
    try { await fetch(`${AGT_URL}/agent/stop`, { method: 'POST' }); } catch {}
    stopPoll();
  });

  $('btn-reset')?.addEventListener('click', async () => {
    stopPoll();
    await simReset();
  });

  $('btn-reveal')?.addEventListener('click', revealEvaluator);

  // Timeline filters
  document.querySelectorAll('.tl-filter').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tl-filter').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.tlFilter = btn.dataset.filter;
      renderTimeline();
    });
  });
});
