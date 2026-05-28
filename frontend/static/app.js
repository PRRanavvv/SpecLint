const SUPPRESSIONS_STORAGE_KEY = "speclint-suppressions";
const DECISIONS_STORAGE_KEY = "speclint-decisions";

const state = {
  report: null,
  examples: [],
  history: [],
  suppressions: loadSuppressions(),
  decisions: loadDecisions(),
  suppressingIssueId: null,
  decidingIssueId: null,
  issueFilter: "action",
  rewriteView: "formatted",
  sourceSpecText: null,
  preserveSourceForNextRun: false,
};

const API_BASE_URL = (window.SPECLINT_CONFIG?.apiBaseUrl || "").replace(/\/$/, "");
const THEME_STORAGE_KEY = "speclint-theme";

const strictnessCopy = {
  lenient: "Lenient - early-stage ideas, ignores minor gaps, flags only blockers.",
  balanced: "Balanced - close to planning, default rubric, catches real holes.",
  ruthless: "Ruthless - pre-engineering handoff, flags everything, expect 8-12 issues on any real spec.",
};

const productSignalTerms = new Set([
  "accept",
  "account",
  "admin",
  "allow",
  "approve",
  "app",
  "assign",
  "cancel",
  "connect",
  "create",
  "customer",
  "delete",
  "download",
  "edit",
  "email",
  "enable",
  "export",
  "feature",
  "file",
  "invite",
  "login",
  "member",
  "notify",
  "order",
  "owner",
  "password",
  "payment",
  "permission",
  "project",
  "reset",
  "role",
  "search",
  "send",
  "share",
  "signup",
  "system",
  "team",
  "token",
  "upload",
  "user",
  "view",
  "workspace",
]);

const requirementLanguagePattern =
  /\b(can|cannot|can't|must|should|shall|will|may|only|never|required|requires|allow|allows|enable|enables|let|lets|prevent|prevents)\b/i;
const productActionPattern =
  /\b(accept|approve|assign|cancel|connect|create|delete|download|edit|export|filter|invite|login|notify|pay|purchase|remove|request|reset|search|send|share|sign[ -]?up|submit|transfer|update|upload|view)\b/i;

const els = {
  titleInput: document.querySelector("#titleInput"),
  specInput: document.querySelector("#specInput"),
  specForm: document.querySelector("#specForm"),
  analyzeButton: document.querySelector("#analyzeButton"),
  clearButton: document.querySelector("#clearButton"),
  exampleSelect: document.querySelector("#exampleSelect"),
  strictnessSelect: document.querySelector("#strictnessSelect"),
  domainSelect: document.querySelector("#domainSelect"),
  riskOverlayInputs: document.querySelectorAll("[name='riskOverlay']"),
  strictnessHelp: document.querySelector("#strictnessHelp"),
  scoreValue: document.querySelector("#scoreValue"),
  scoreLabel: document.querySelector("#scoreLabel"),
  scoreProgress: document.querySelector("#scoreProgress"),
  criticalCount: document.querySelector("#criticalCount"),
  highCount: document.querySelector("#highCount"),
  mediumCount: document.querySelector("#mediumCount"),
  lowCount: document.querySelector("#lowCount"),
  verdictText: document.querySelector("#verdictText"),
  summaryText: document.querySelector("#summaryText"),
  rubricText: document.querySelector("#rubricText"),
  intentNarrative: document.querySelector("#intentNarrative"),
  intentGrid: document.querySelector("#intentGrid"),
  issueCount: document.querySelector("#issueCount"),
  issueFilters: document.querySelectorAll("[data-issue-filter]"),
  issuesList: document.querySelector("#issuesList"),
  categoryGuide: document.querySelector("#categoryGuide"),
  testsList: document.querySelector("#testsList"),
  rewriteBox: document.querySelector("#rewriteBox"),
  traceList: document.querySelector("#traceList"),
  historyList: document.querySelector("#historyList"),
  formattedButton: document.querySelector("#formattedButton"),
  diffButton: document.querySelector("#diffButton"),
  useRewriteButton: document.querySelector("#useRewriteButton"),
  copyRewriteButton: document.querySelector("#copyRewriteButton"),
  shareButton: document.querySelector("#shareButton"),
  downloadButton: document.querySelector("#downloadButton"),
  themeToggle: document.querySelector("#themeToggle"),
  themeToggleLabel: document.querySelector("#themeToggleLabel"),
  toast: document.querySelector("#toast"),
};

function getStoredTheme() {
  try {
    const theme = window.localStorage.getItem(THEME_STORAGE_KEY);
    return theme === "dark" || theme === "light" ? theme : null;
  } catch {
    return null;
  }
}

function storeTheme(theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // The selected theme still applies for this page load if storage is blocked.
  }
}

function systemTheme() {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function currentTheme() {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function setTheme(theme, { persist = true } = {}) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = nextTheme;
  if (persist) storeTheme(nextTheme);
  const isDark = nextTheme === "dark";
  els.themeToggle?.setAttribute("aria-pressed", String(isDark));
  els.themeToggle?.setAttribute("aria-label", isDark ? "Switch to day mode" : "Switch to dark mode");
  els.themeToggle?.setAttribute("title", isDark ? "Switch to day mode" : "Switch to dark mode");
  if (els.themeToggleLabel) {
    els.themeToggleLabel.textContent = isDark ? "Dark mode" : "Day mode";
  }
}

function loadSuppressions() {
  try {
    const raw = window.localStorage.getItem(SUPPRESSIONS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function storeSuppressions() {
  try {
    window.localStorage.setItem(SUPPRESSIONS_STORAGE_KEY, JSON.stringify(state.suppressions));
  } catch {
    toast("Suppression saved for this session, but browser storage is blocked.");
  }
}

function loadDecisions() {
  try {
    const raw = window.localStorage.getItem(DECISIONS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function storeDecisions() {
  try {
    window.localStorage.setItem(DECISIONS_STORAGE_KEY, JSON.stringify(state.decisions));
  } catch {
    toast("Decision saved for this session, but browser storage is blocked.");
  }
}

function todayIso() {
  const today = new Date();
  today.setMinutes(today.getMinutes() - today.getTimezoneOffset());
  return today.toISOString().slice(0, 10);
}

function formatDate(value) {
  if (!value) return "no expiry";
  return new Date(`${value}T00:00:00`).toLocaleDateString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function activeSuppression(issueId) {
  const suppression = state.suppressions[issueId];
  if (!suppression?.expiresAt) return null;
  if (suppression.status && suppression.status !== "active") return null;
  return suppression.expiresAt >= todayIso() ? suppression : null;
}

function pendingSuppression(issueId) {
  const suppression = state.suppressions[issueId];
  return suppression?.status === "pending_review" ? suppression : null;
}

function activeDecision(issueId) {
  const decision = state.decisions[issueId];
  if (!decision) return null;
  return !decision.status || decision.status === "decided" ? decision : null;
}

function pendingDecision(issueId) {
  const decision = state.decisions[issueId];
  return decision?.status === "pending_review" ? decision : null;
}

function openIssues(issues = []) {
  return issues.filter(
    (issue) =>
      !activeSuppression(issue.id) &&
      !activeDecision(issue.id) &&
      !pendingSuppression(issue.id) &&
      !pendingDecision(issue.id),
  );
}

function acceptedRiskRecords(issues = []) {
  return issues
    .map((issue) => ({ issue, suppression: activeSuppression(issue.id) }))
    .filter((record) => record.suppression);
}

function decisionRecords(issues = []) {
  return issues
    .map((issue) => ({ issue, decision: activeDecision(issue.id) }))
    .filter((record) => record.decision);
}

function pendingReviewRecords(issues = []) {
  return issues
    .flatMap((issue) => {
      const records = [];
      const suppression = pendingSuppression(issue.id);
      const decision = pendingDecision(issue.id);
      if (suppression) records.push({ issue, kind: "suppression", record: suppression });
      if (decision) records.push({ issue, kind: "decision", record: decision });
      return records;
    });
}

function severityCountsForIssues(issues = []) {
  return issues.reduce(
    (counts, issue) => {
      counts[issue.severity] = (counts[issue.severity] || 0) + 1;
      return counts;
    },
    { critical: 0, high: 0, medium: 0, low: 0 },
  );
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error = new Error(payload.detail || `Request failed: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function normalizeSuppression(record) {
  if (!record) return null;
  return {
    suppressionId: record.id || record.suppressionId || null,
    specVersionId: record.spec_version_id || record.specVersionId || null,
    issueId: record.issue_id || record.issueId || null,
    owner: record.owner || "",
    reason: record.reason || "",
    expiresAt: record.expires_at || record.expiresAt || "",
    title: record.issue_title || record.title || "",
    type: record.issue_type || record.type || "",
    severity: record.severity || "",
    evidenceSnapshot: record.evidence_snapshot || record.evidenceSnapshot || "",
    evidenceHash: record.evidence_hash || record.evidenceHash || "",
    rawEvidenceHash: record.raw_evidence_hash || record.rawEvidenceHash || "",
    normalizedEvidenceHash: record.normalized_evidence_hash || record.normalizedEvidenceHash || "",
    acceptedAt: record.created_at || record.acceptedAt || "",
    status: record.status || "active",
  };
}

function applySuppressionRecord(record) {
  const normalized = normalizeSuppression(record);
  if (!normalized?.issueId) return;
  state.suppressions[normalized.issueId] = normalized;
}

function normalizeDecision(record) {
  if (!record) return null;
  return {
    decisionId: record.id || record.decisionId || null,
    specVersionId: record.spec_version_id || record.specVersionId || null,
    issueId: record.issue_id || record.issueId || null,
    owner: record.owner || "",
    decisionNote: record.decision_note || record.decisionNote || "",
    title: record.issue_title || record.title || "",
    type: record.issue_type || record.type || "",
    severity: record.severity || "",
    evidenceSnapshot: record.evidence_snapshot || record.evidenceSnapshot || "",
    evidenceHash: record.evidence_hash || record.evidenceHash || "",
    rawEvidenceHash: record.raw_evidence_hash || record.rawEvidenceHash || "",
    normalizedEvidenceHash: record.normalized_evidence_hash || record.normalizedEvidenceHash || "",
    createdAt: record.created_at || record.createdAt || "",
    status: record.status || "decided",
  };
}

function applyDecisionRecord(record) {
  const normalized = normalizeDecision(record);
  if (!normalized?.issueId) return;
  state.decisions[normalized.issueId] = normalized;
}

async function hydrateSuppressions(report) {
  if (!report?.spec_version_id) return;
  try {
    const records = await api(`/api/suppressions?spec_version_id=${encodeURIComponent(report.spec_version_id)}`);
    records.forEach(applySuppressionRecord);
    storeSuppressions();
  } catch {
    // Local suppressions still work when the backend decision log is unavailable.
  }
}

async function hydrateDecisions(report) {
  if (!report?.spec_version_id) return;
  try {
    const records = await api(`/api/decisions?spec_version_id=${encodeURIComponent(report.spec_version_id)}`);
    records.forEach(applyDecisionRecord);
    storeDecisions();
  } catch {
    // Local decisions still work when the backend requirements log is unavailable.
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => els.toast.classList.remove("show"), 2600);
}

function verdictLabel(verdict) {
  return {
    compiles: "Compiles",
    compiles_with_warnings: "Compiles with warnings",
    does_not_compile: "Does not compile",
  }[verdict] || "Waiting for input";
}

function humanize(value) {
  return String(value || "").replaceAll("_", " ");
}

function tags(items, empty = "None detected") {
  if (!items?.length) return `<span class="empty-state">${empty}</span>`;
  return items.map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("");
}

function selectedRiskOverlays() {
  return [...els.riskOverlayInputs].filter((input) => input.checked).map((input) => input.value);
}

function currentModeCopy() {
  const domain = humanize(els.domainSelect?.value || "general");
  const overlays = selectedRiskOverlays();
  const overlayText = overlays.length ? ` Risk overlays: ${overlays.map(humanize).join(", ")}.` : " No risk overlays selected.";
  return `${strictnessCopy[els.strictnessSelect.value]} Domain: ${domain}.${overlayText}`;
}

function setRiskOverlays(overlays = []) {
  const selected = new Set(overlays);
  els.riskOverlayInputs.forEach((input) => {
    input.checked = selected.has(input.value);
  });
}

async function loadExamples() {
  state.examples = await api("/api/examples");
  els.exampleSelect.innerHTML =
    `<option value="">Examples</option>` +
    state.examples
      .map((example, index) => `<option value="${index}">${escapeHtml(example.title)}</option>`)
      .join("");
}

async function analyze({ recordHistory = true } = {}) {
  const title = els.titleInput.value.trim() || "Untitled spec";
  const specText = els.specInput.value.trim();
  if (specText.length < 20) {
    renderInputRejected();
    toast("IMPROPER INPUT");
    return;
  }
  if (isImproperInput(title, specText)) {
    renderInputRejected();
    toast("IMPROPER INPUT");
    return;
  }
  if (!state.preserveSourceForNextRun) {
    state.sourceSpecText = specText;
  }
  els.analyzeButton.disabled = true;
  els.analyzeButton.textContent = "Analyzing";
  try {
    const report = await api("/api/analyze", {
      method: "POST",
      body: JSON.stringify({
        title,
        spec_text: specText,
        source_spec_text: state.sourceSpecText,
        strictness: els.strictnessSelect.value,
        domain: els.domainSelect.value,
        risk_overlays: selectedRiskOverlays(),
      }),
    });
    state.report = report;
    await hydrateSuppressions(report);
    await hydrateDecisions(report);
    if (recordHistory) addHistory(report, specText);
    renderReport();
  } catch (error) {
    if (error.status === 422) {
      renderInputRejected();
      toast("IMPROPER INPUT");
    } else {
      toast(error.message);
    }
  } finally {
    state.preserveSourceForNextRun = false;
    els.analyzeButton.disabled = false;
    els.analyzeButton.textContent = "Analyze";
  }
}

function isImproperInput(title, specText) {
  const tokens = rawTokens(specText);
  const combined = `${title} ${specText}`;
  if (tokens.length < 6) return true;
  if (weirdTokenRatio(tokens) >= 0.34) return true;
  if (productSignalCount(rawTokens(combined)) > 0) return false;
  return !(requirementLanguagePattern.test(combined) && productActionPattern.test(combined));
}

function rawTokens(text) {
  return String(text || "").toLowerCase().match(/[a-z][a-z0-9_-]{1,}/g) || [];
}

function productSignalCount(tokens) {
  return new Set(tokens.map(normalizeToken).filter((token) => productSignalTerms.has(token))).size;
}

function normalizeToken(token) {
  if (token.endsWith("ies") && token.length > 5) return `${token.slice(0, -3)}y`;
  if (token.endsWith("ing") && token.length > 5) return token.slice(0, -3);
  if (token.endsWith("ed") && token.length > 4) return token.slice(0, -2);
  if (token.endsWith("s") && token.length > 3) return token.slice(0, -1);
  return token;
}

function weirdTokenRatio(tokens) {
  const candidates = tokens.filter((token) => token.length >= 4);
  if (!candidates.length) return 0;
  return candidates.filter(looksLikeNoise).length / candidates.length;
}

function looksLikeNoise(token) {
  return (
    (token.length >= 6 && !/[aeiouy]/.test(token)) ||
    /[bcdfghjklmnpqrstvwxyz]{4,}/.test(token) ||
    /(.)\1\1/.test(token)
  );
}

function addHistory(report, specText) {
  const previous = state.history[0];
  state.history.unshift({
    title: report.title,
    score: report.score,
    verdict: report.verdict,
    issueCount: openIssues(report.issues).length,
    delta: previous ? report.score - previous.score : 0,
    specText,
    at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  });
  state.history = state.history.slice(0, 6);
}

function renderReport() {
  const report = state.report;
  if (!report) return;
  const visibleIssues = openIssues(report.issues);
  els.scoreValue.textContent = report.score;
  els.scoreLabel.textContent = `${verdictLabel(report.verdict)} out of 100`;
  els.verdictText.textContent = `${report.score} / 100 - ${verdictLabel(report.verdict)}`;
  els.summaryText.textContent = report.summary;
  updateScoreProgress(report.score);
  els.strictnessHelp.textContent = [
    report.strictness_note || strictnessCopy[els.strictnessSelect.value],
    report.domain_note,
  ]
    .filter(Boolean)
    .join(" ");
  renderSeverityCounts(severityCountsForIssues(visibleIssues));
  renderRubric(report.score_breakdown);
  renderIntent(report.intent);
  renderIssues(report.issues);
  renderCategoryGuide(report.category_docs);
  renderTests(report.acceptance_tests);
  renderTrace(report.traceability);
  renderRewrite();
  renderHistory();
}

function renderInputRejected() {
  state.report = null;
  state.suppressingIssueId = null;
  state.decidingIssueId = null;
  els.scoreValue.textContent = "--";
  els.scoreLabel.textContent = "Improper input";
  els.verdictText.textContent = "IMPROPER INPUT";
  els.summaryText.textContent = "Write a real product requirement before running SpecLint.";
  updateScoreProgress(0);
  els.rubricText.textContent = "No score generated. This input was rejected before analysis.";
  els.strictnessHelp.textContent = currentModeCopy();
  els.intentNarrative.className = "intent-narrative empty-state";
  els.intentNarrative.textContent = "No intent extracted.";
  els.intentGrid.className = "intent-grid empty-state";
  els.intentGrid.textContent = "IMPROPER INPUT";
  els.issueCount.textContent = "0 issues";
  els.issuesList.className = "issue-list empty-state";
  els.issuesList.textContent = "IMPROPER INPUT";
  els.testsList.className = "test-list empty-state";
  els.testsList.textContent = "No tests generated.";
  els.traceList.className = "trace-list empty-state";
  els.traceList.textContent = "No traceability map generated.";
  els.rewriteBox.className = "rewrite-box empty-state";
  els.rewriteBox.textContent = "IMPROPER INPUT";
  state.history = [];
  renderHistory();
  renderSeverityCounts({});
}

function renderSeverityCounts(counts = {}) {
  els.criticalCount.textContent = counts.critical || 0;
  els.highCount.textContent = counts.high || 0;
  els.mediumCount.textContent = counts.medium || 0;
  els.lowCount.textContent = counts.low || 0;
}

function scoreStatus(score) {
  if (score < 50) return "low";
  if (score <= 80) return "medium";
  return "high";
}

function updateScoreProgress(score = 0) {
  const safeScore = Math.max(0, Math.min(100, Number(score) || 0));
  const status = scoreStatus(safeScore);
  if (els.scoreProgress) {
    els.scoreProgress.value = safeScore;
    els.scoreProgress.setAttribute("aria-valuenow", String(safeScore));
    els.scoreProgress.setAttribute("data-status", status);
  }
}

function renderRubric(breakdown) {
  if (!breakdown) return;
  const weights = breakdown.weights || {};
  const penaltyText = breakdown.penalties.length
    ? breakdown.penalties
        .map((item) => `${item.count} ${item.severity} x ${item.weight}`)
        .join(" + ")
    : "no penalties";
  els.rubricText.textContent = `${breakdown.explanation} Weights: critical ${weights.critical}, high ${weights.high}, medium ${weights.medium}, low ${weights.low}. Current math: 100 - (${penaltyText}) x ${breakdown.strictness_multiplier} = ${state.report.score}.`;
}

function renderIntent(intent) {
  const actorText = intent.actors.length ? intent.actors.join(", ") : "an unspecified actor";
  const actionText = intent.actions.length ? intent.actions.join(", ") : "an unspecified action";
  const entityText = intent.entities.length ? intent.entities.join(", ") : "an unspecified object";
  els.intentNarrative.className = "intent-narrative";
  els.intentNarrative.textContent = `SpecLint reads this as: ${actorText} can ${actionText} ${entityText}. Use this to spot missing relationships, not as final truth.`;

  const blocks = [
    ["Who", intent.actors, "Roles or people named in the spec."],
    ["Objects", intent.entities, "Things the feature changes or exposes."],
    ["Actions", intent.actions, "Verbs that need permission, failure, and test behavior."],
    ["States", intent.states, "Lifecycle labels that need transitions."],
    [
      "Explicit rules",
      intent.explicit_rules,
      "Hard rules use words like must, cannot, only, required, or not allowed. If this is empty, the spec is mostly soft intent.",
    ],
  ];
  els.intentGrid.className = "intent-grid";
  els.intentGrid.innerHTML = blocks
    .map(
      ([label, values, help]) => `
        <section class="intent-block">
          <h3>${label}</h3>
          <p>${escapeHtml(help)}</p>
          <div class="tag-row">${tags(values)}</div>
        </section>
      `,
    )
    .join("");
}

function renderIssues(issues) {
  const visibleIssues = openIssues(issues);
  const acceptedRisks = acceptedRiskRecords(issues);
  const decisions = decisionRecords(issues);
  const pendingReviews = pendingReviewRecords(issues);
  const acceptedCount = acceptedRisks.length;
  renderIssueFilterState();
  els.issueCount.textContent = `${visibleIssues.length} open${pendingReviews.length ? ` + ${pendingReviews.length} review` : ""}${decisions.length ? ` + ${decisions.length} decided` : ""}${acceptedCount ? ` + ${acceptedCount} accepted` : ""}`;
  if (!issues.length) {
    els.issuesList.className = "issue-list empty-state";
    els.issuesList.textContent = "No lint issues found.";
    return;
  }
  els.issuesList.className = "issue-list";
  const sections = [];
  if (state.issueFilter === "action" || state.issueFilter === "all") {
    sections.push(visibleIssues.map((issue) => issueMarkupFor(issue)).join(""));
  }
  if (state.issueFilter === "review" || state.issueFilter === "all") {
    sections.push(pendingReviewMarkup(pendingReviews));
  }
  if (state.issueFilter === "all") {
    sections.push(decisionMarkup(decisions));
  }
  if (state.issueFilter === "accepted" || state.issueFilter === "all") {
    sections.push(acceptedRiskMarkup(acceptedRisks));
  }
  const markup = sections.join("");
  els.issuesList.innerHTML = markup || `<div class="empty-state">${emptyIssueFilterCopy()}</div>`;
}

function issueMarkupFor(issue) {
  const existing = state.suppressions[issue.id] || {};
  const isSuppressing = state.suppressingIssueId === issue.id;
  const isDeciding = state.decidingIssueId === issue.id;
  return `
        <article class="issue-item">
          <div class="issue-topline">
            <div class="tag-row">
              <span class="severity-pill severity-${escapeHtml(issue.severity)}">${humanize(issue.severity)}</span>
              ${
                issue.base_severity
                  ? `<span class="tag context-tag">${humanize(issue.base_severity)} -> ${humanize(issue.severity)}</span>`
                  : ""
              }
              <span class="tag">${humanize(issue.type)}</span>
              ${issue.context_note ? `<span class="tag context-tag">${escapeHtml(issue.context_note)}</span>` : ""}
            </div>
            <div class="issue-actions">
              <button class="cta-button compact apply-fix" type="button" data-issue-id="${escapeHtml(issue.id)}">Fix</button>
              <button class="cta-button compact decide-issue" type="button" data-issue-id="${escapeHtml(issue.id)}">Decide</button>
              <button class="cta-button compact suppress-issue" type="button" data-issue-id="${escapeHtml(issue.id)}">Accept</button>
            </div>
          </div>
          <h3>${escapeHtml(issue.title)}</h3>
          <div class="issue-grid">
            <span class="issue-label">Evidence</span>
            <p>${escapeHtml(issue.evidence)}</p>
            <span class="issue-label">Why it matters</span>
            <p>${escapeHtml(issue.why_it_matters)}</p>
            <span class="issue-label">Suggested fix</span>
            <p>${escapeHtml(issue.suggestion)}</p>
            <span class="issue-label">Question to answer</span>
            <p>${escapeHtml(issue.test_prompt)}</p>
          </div>
          ${
            isDeciding
              ? `
                <form class="decision-form" data-issue-id="${escapeHtml(issue.id)}">
                  <div>
                    <strong>Decide on this requirement</strong>
                    <p>Capture the product or security call that resolves this warning.</p>
                  </div>
                  <div class="decision-fields">
                    <label>
                      <span>Owner</span>
                      <input name="owner" maxlength="80" value="" placeholder="Decision owner" required />
                    </label>
                    <label class="decision-note">
                      <span>Decision</span>
                      <textarea name="decisionNote" maxlength="620" rows="3" placeholder="What did the team decide?" required></textarea>
                    </label>
                  </div>
                  <div class="button-row">
                    <button class="primary compact" type="submit">Save decision</button>
                    <button class="ghost-button compact cancel-decision" type="button">Cancel</button>
                  </div>
                </form>
              `
              : ""
          }
          ${
            isSuppressing
              ? `
                <form class="suppression-form" data-issue-id="${escapeHtml(issue.id)}">
                  <div>
                    <strong>Accept this risk</strong>
                    <p>Record why the team is choosing not to fix this warning right now.</p>
                  </div>
                  <div class="suppression-fields">
                    <label>
                      <span>Owner</span>
                      <input name="owner" maxlength="80" value="${escapeHtml(existing.owner || "")}" placeholder="Risk owner" required />
                    </label>
                    <label>
                      <span>Expires</span>
                      <input name="expiresAt" type="date" min="${todayIso()}" value="${escapeHtml(existing.expiresAt || "")}" required />
                    </label>
                    <label class="suppression-reason">
                      <span>Reason</span>
                      <textarea name="reason" maxlength="420" rows="3" placeholder="Why is this acceptable for now?" required>${escapeHtml(existing.reason || "")}</textarea>
                    </label>
                  </div>
                  <div class="button-row">
                    <button class="primary compact" type="submit">Save suppression</button>
                    <button class="ghost-button compact cancel-suppression" type="button">Cancel</button>
                  </div>
                </form>
              `
              : ""
          }
        </article>
      `;
}

function renderIssueFilterState() {
  els.issueFilters.forEach((button) => {
    const active = button.dataset.issueFilter === state.issueFilter;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function emptyIssueFilterCopy() {
  if (state.issueFilter === "accepted") return "No accepted risks for this run.";
  if (state.issueFilter === "review") return "No pending reviews for this run.";
  if (state.issueFilter === "all") return "No diagnostics in this view.";
  return "No action-required issues. Decisions, pending reviews, and accepted risks are still available in All.";
}

function pendingReviewMarkup(records) {
  if (!records.length) return "";
  return `
    <section class="pending-review-group" aria-label="Pending reviews">
      <div class="accepted-risk-header">
        <div>
          <strong>Needs review</strong>
          <p>The warning text changed, so the prior decision needs a quick human check.</p>
        </div>
        <span class="count-pill">${records.length}</span>
      </div>
      ${records
        .map(
          ({ issue, kind, record }) => `
            <article class="issue-item pending-review">
              <div class="issue-topline">
                <div class="tag-row">
                  <span class="severity-pill severity-${escapeHtml(issue.severity)}">${humanize(issue.severity)}</span>
                  ${
                    issue.base_severity
                      ? `<span class="tag context-tag">${humanize(issue.base_severity)} -> ${humanize(issue.severity)}</span>`
                      : ""
                  }
                  <span class="tag">${humanize(issue.type)}</span>
                  <span class="tag">Needs review</span>
                  <span class="tag">${kind === "decision" ? "Decision" : "Accepted risk"}</span>
                </div>
                <div class="issue-actions">
                  <button class="ghost-button compact reconfirm-review" type="button" data-review-kind="${escapeHtml(kind)}" data-issue-id="${escapeHtml(issue.id)}">Reconfirm</button>
                  <button class="ghost-button compact reopen-review" type="button" data-review-kind="${escapeHtml(kind)}" data-issue-id="${escapeHtml(issue.id)}">Reopen</button>
                </div>
              </div>
              <h3>${escapeHtml(issue.title)}</h3>
              <div class="issue-grid">
                <span class="issue-label">Owner</span>
                <p>${escapeHtml(record.owner)}</p>
                <span class="issue-label">Previous call</span>
                <p>${escapeHtml(kind === "decision" ? record.decisionNote : record.reason)}</p>
                <span class="issue-label">Current evidence</span>
                <p>${escapeHtml(record.evidenceSnapshot || issue.evidence)}</p>
              </div>
            </article>
          `,
        )
        .join("")}
    </section>
  `;
}

function acceptedRiskMarkup(records) {
  if (!records.length) return "";
  return `
    <section class="accepted-risk-group" aria-label="Accepted risks">
      <div class="accepted-risk-header">
        <div>
          <strong>Accepted risks</strong>
          <p>These warnings are documented decisions, not silent ignores.</p>
        </div>
        <span class="count-pill">${records.length}</span>
      </div>
      ${records
        .map(
          ({ issue, suppression }) => `
            <article class="issue-item accepted-risk">
              <div class="issue-topline">
                <div class="tag-row">
                  <span class="severity-pill severity-${escapeHtml(issue.severity)}">${humanize(issue.severity)}</span>
                  ${
                    issue.base_severity
                      ? `<span class="tag context-tag">${humanize(issue.base_severity)} -> ${humanize(issue.severity)}</span>`
                      : ""
                  }
                  <span class="tag">${humanize(issue.type)}</span>
                  <span class="tag">Accepted risk</span>
                </div>
                <button class="ghost-button compact restore-issue" type="button" data-issue-id="${escapeHtml(issue.id)}">Reopen</button>
              </div>
              <h3>${escapeHtml(issue.title)}</h3>
              <div class="issue-grid">
                <span class="issue-label">Owner</span>
                <p>${escapeHtml(suppression.owner)}</p>
                <span class="issue-label">Expires</span>
                <p>${escapeHtml(formatDate(suppression.expiresAt))}</p>
                <span class="issue-label">Reason</span>
                <p>${escapeHtml(suppression.reason)}</p>
              </div>
            </article>
          `,
        )
        .join("")}
    </section>
  `;
}

function decisionMarkup(records) {
  if (!records.length) return "";
  return `
    <section class="decision-group" aria-label="Requirements decisions">
      <div class="accepted-risk-header">
        <div>
          <strong>Requirements log</strong>
          <p>These warnings were resolved by an explicit product or security decision.</p>
        </div>
        <span class="count-pill">${records.length}</span>
      </div>
      ${records
        .map(
          ({ issue, decision }) => `
            <article class="issue-item decided-issue">
              <div class="issue-topline">
                <div class="tag-row">
                  <span class="severity-pill severity-${escapeHtml(issue.severity)}">${humanize(issue.severity)}</span>
                  ${
                    issue.base_severity
                      ? `<span class="tag context-tag">${humanize(issue.base_severity)} -> ${humanize(issue.severity)}</span>`
                      : ""
                  }
                  <span class="tag">${humanize(issue.type)}</span>
                  <span class="tag">Decided</span>
                </div>
              </div>
              <h3>${escapeHtml(issue.title)}</h3>
              <div class="issue-grid">
                <span class="issue-label">Owner</span>
                <p>${escapeHtml(decision.owner)}</p>
                <span class="issue-label">Decision</span>
                <p>${escapeHtml(decision.decisionNote)}</p>
                <span class="issue-label">Evidence</span>
                <p>${escapeHtml(decision.evidenceSnapshot || issue.evidence)}</p>
              </div>
            </article>
          `,
        )
        .join("")}
    </section>
  `;
}

function renderCategoryGuide(categories = []) {
  if (!categories.length) {
    els.categoryGuide.className = "category-guide empty-state";
    els.categoryGuide.textContent = "Run analysis to see the lint categories.";
    return;
  }
  els.categoryGuide.className = "category-guide";
  els.categoryGuide.innerHTML = categories
    .map(
      (item) => `
        <article>
          <h3>${escapeHtml(item.label)}</h3>
          <p>${escapeHtml(item.checks_for)}</p>
        </article>
      `,
    )
    .join("");
}

function renderTests(tests) {
  if (!tests.length) {
    els.testsList.className = "test-list empty-state";
    els.testsList.textContent = "No tests generated.";
    return;
  }
  els.testsList.className = "test-list";
  els.testsList.innerHTML = tests
    .map(
      (test) => `
        <article class="test-item">
          <h3>${escapeHtml(test.name)}</h3>
          <p><strong>Given</strong> ${escapeHtml(test.given)}</p>
          <p><strong>When</strong> ${escapeHtml(test.when)}</p>
          <p><strong>Then</strong> ${escapeHtml(test.then)}</p>
          ${
            test.covers_issue_ids.length
              ? `<div class="tag-row"><span class="tag">Covers ${test.covers_issue_ids.length} lint issue${test.covers_issue_ids.length === 1 ? "" : "s"}</span></div>`
              : ""
          }
        </article>
      `,
    )
    .join("");
}

function renderTrace(items) {
  if (!items.length) {
    els.traceList.className = "trace-list empty-state";
    els.traceList.textContent = "No traceability map generated.";
    return;
  }
  els.traceList.className = "trace-list";
  els.traceList.innerHTML = items
    .map(
      (item) => `
        <article class="trace-item">
          <h3>${escapeHtml(item.requirement)}</h3>
          <p><strong>Suggested tests:</strong> ${item.tests.length}</p>
          <p><strong>Open questions:</strong> ${escapeHtml(item.open_questions.join(" | ") || "none")}</p>
        </article>
      `,
    )
    .join("");
}

function renderRewrite() {
  const report = state.report;
  if (!report?.rewritten_spec) {
    els.rewriteBox.className = "rewrite-box empty-state";
    els.rewriteBox.textContent = "Run analysis to generate a tighter version.";
    return;
  }
  els.formattedButton.classList.toggle("active", state.rewriteView === "formatted");
  els.diffButton.classList.toggle("active", state.rewriteView === "diff");
  els.rewriteBox.className = `rewrite-box ${state.rewriteView === "diff" ? "diff-box" : "markdown-doc"}`;
  if (state.rewriteView === "diff") {
    els.rewriteBox.innerHTML = renderDiff(els.specInput.value, report.rewritten_spec);
  } else {
    els.rewriteBox.innerHTML = renderMarkdown(report.rewritten_spec);
  }
}

function renderMarkdown(markdown) {
  const lines = markdown.split("\n");
  let html = "";
  let inList = false;
  for (const line of lines) {
    if (line.startsWith("# ")) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      html += `<h3>${escapeHtml(line.slice(2))}</h3>`;
    } else if (line.startsWith("- ")) {
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      html += `<li>${escapeHtml(line.slice(2))}</li>`;
    } else if (line.trim()) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      html += `<p>${escapeHtml(line)}</p>`;
    }
  }
  if (inList) html += "</ul>";
  return html;
}

function renderDiff(original, rewritten) {
  const originalLines = original.split("\n").map((line) => line.trim()).filter(Boolean);
  const rewrittenLines = rewritten.split("\n").map((line) => line.trim()).filter(Boolean);
  const originalSet = new Set(originalLines);
  const rewrittenSet = new Set(rewrittenLines);
  const removed = originalLines
    .filter((line) => !rewrittenSet.has(line))
    .map((line) => `<div class="diff-line removed">- ${escapeHtml(line)}</div>`)
    .join("");
  const added = rewrittenLines
    .filter((line) => !originalSet.has(line))
    .map((line) => `<div class="diff-line added">+ ${escapeHtml(line)}</div>`)
    .join("");
  return removed + added || `<div class="empty-state">No text changes detected.</div>`;
}

function renderHistory() {
  if (!state.history.length) {
    els.historyList.className = "history-list empty-state";
    els.historyList.textContent = "No previous runs yet.";
    return;
  }
  els.historyList.className = "history-list";
  els.historyList.innerHTML = state.history
    .map(
      (run, index) => `
        <button class="history-item" type="button" data-index="${index}">
          <span>${escapeHtml(run.at)}</span>
          <strong>${run.score}/100</strong>
          <small>${run.delta > 0 ? "+" : ""}${run.delta} from previous</small>
          <small>${run.issueCount} issue${run.issueCount === 1 ? "" : "s"}</small>
        </button>
      `,
    )
    .join("");
}

function applyIssueFix(issueId) {
  const issue = state.report?.issues.find((item) => item.id === issueId);
  if (!issue) return;
  const line = `- ${issue.suggestion}`;
  if (els.specInput.value.includes(issue.suggestion)) {
    toast("That fix is already in the draft.");
    return;
  }
  const divider = els.specInput.value.includes("Clarifications to add:")
    ? ""
    : "\n\nClarifications to add:";
  els.specInput.value = `${els.specInput.value.trim()}${divider}\n${line}`;
  els.specInput.focus();
  toast("Fix added to the draft. Re-run SpecLint to check the score.");
}

function openSuppressionForm(issueId) {
  if (!state.report?.issues.some((issue) => issue.id === issueId)) return;
  state.suppressingIssueId = issueId;
  state.decidingIssueId = null;
  renderReport();
}

function cancelSuppressionForm() {
  state.suppressingIssueId = null;
  renderReport();
}

function openDecisionForm(issueId) {
  if (!state.report?.issues.some((issue) => issue.id === issueId)) return;
  state.decidingIssueId = issueId;
  state.suppressingIssueId = null;
  renderReport();
}

function cancelDecisionForm() {
  state.decidingIssueId = null;
  renderReport();
}

async function saveDecision(issueId, form) {
  const formData = new FormData(form);
  const owner = String(formData.get("owner") || "").trim();
  const decisionNote = String(formData.get("decisionNote") || "").trim();
  if (!owner || !decisionNote) {
    toast("Owner and decision are required.");
    return;
  }
  const issue = state.report?.issues.find((item) => item.id === issueId);
  if (!issue) return;
  const localRecord = {
    owner,
    decisionNote,
    title: issue.title,
    type: issue.type,
    severity: issue.severity,
    evidenceSnapshot: issue.evidence,
    createdAt: new Date().toISOString(),
    status: "decided",
  };
  let backendLogged = false;
  if (state.report?.spec_version_id) {
    try {
      const remoteRecord = await api("/api/decisions", {
        method: "POST",
        body: JSON.stringify({
          spec_version_id: state.report.spec_version_id,
          issue_id: issue.id,
          issue_type: issue.type,
          severity: issue.severity,
          issue_title: issue.title,
          evidence_snapshot: issue.evidence,
          owner,
          decision_note: decisionNote,
          created_by: owner,
        }),
      });
      applyDecisionRecord(remoteRecord);
      backendLogged = true;
    } catch {
      state.decisions[issueId] = localRecord;
    }
  } else {
    state.decisions[issueId] = localRecord;
  }
  state.decidingIssueId = null;
  storeDecisions();
  renderReport();
  toast(backendLogged ? "Decision saved to requirements log." : "Decision saved locally.");
}

async function saveSuppression(issueId, form) {
  const formData = new FormData(form);
  const owner = String(formData.get("owner") || "").trim();
  const reason = String(formData.get("reason") || "").trim();
  const expiresAt = String(formData.get("expiresAt") || "").trim();
  if (!owner || !reason || !expiresAt) {
    toast("Owner, reason, and expiry are required.");
    return;
  }
  if (expiresAt < todayIso()) {
    toast("Choose an expiry date that has not passed.");
    return;
  }
  const issue = state.report?.issues.find((item) => item.id === issueId);
  if (!issue) return;
  const localRecord = {
    owner,
    reason,
    expiresAt,
    title: issue.title,
    type: issue.type,
    severity: issue.severity,
    evidenceSnapshot: issue.evidence,
    acceptedAt: new Date().toISOString(),
    status: "active",
  };
  let backendLogged = false;
  if (state.report?.spec_version_id) {
    try {
      const remoteRecord = await api("/api/suppressions", {
        method: "POST",
        body: JSON.stringify({
          spec_version_id: state.report.spec_version_id,
          issue_id: issue.id,
          issue_type: issue.type,
          severity: issue.severity,
          issue_title: issue.title,
          evidence_snapshot: issue.evidence,
          owner,
          reason,
          expires_at: expiresAt,
          created_by: owner,
        }),
      });
      applySuppressionRecord(remoteRecord);
      backendLogged = true;
    } catch {
      state.suppressions[issueId] = localRecord;
    }
  } else {
    state.suppressions[issueId] = localRecord;
  }
  state.suppressingIssueId = null;
  storeSuppressions();
  renderReport();
  toast(backendLogged ? "Risk accepted and logged." : "Risk accepted locally.");
}

async function restoreIssue(issueId) {
  const suppression = state.suppressions[issueId];
  if (!suppression) return;
  if (suppression.suppressionId) {
    try {
      await api(`/api/suppressions/${encodeURIComponent(suppression.suppressionId)}/reopen`, {
        method: "PATCH",
        body: JSON.stringify({
          reopened_by: suppression.owner || "Unknown",
          reopened_reason: "Reopened from the SpecLint report.",
        }),
      });
    } catch (error) {
      toast(error.message || "Could not reopen this warning.");
      return;
    }
  }
  delete state.suppressions[issueId];
  storeSuppressions();
  renderReport();
  toast("Warning reopened.");
}

async function reconfirmReview(kind, issueId) {
  const record = kind === "decision" ? state.decisions[issueId] : state.suppressions[issueId];
  if (!record) return;
  if (kind === "decision") {
    if (record.decisionId) {
      const remoteRecord = await api(`/api/decisions/${encodeURIComponent(record.decisionId)}/reconfirm`, {
        method: "PATCH",
        body: JSON.stringify({
          reviewed_by: record.owner || "Unknown",
          review_note: "Reconfirmed from the SpecLint report.",
        }),
      });
      applyDecisionRecord(remoteRecord);
    } else {
      state.decisions[issueId] = { ...record, status: "decided" };
    }
    storeDecisions();
  } else {
    if (record.suppressionId) {
      const remoteRecord = await api(`/api/suppressions/${encodeURIComponent(record.suppressionId)}/reconfirm`, {
        method: "PATCH",
        body: JSON.stringify({
          reviewed_by: record.owner || "Unknown",
          review_note: "Reconfirmed from the SpecLint report.",
        }),
      });
      applySuppressionRecord(remoteRecord);
    } else {
      state.suppressions[issueId] = { ...record, status: "active" };
    }
    storeSuppressions();
  }
  renderReport();
  toast("Review reconfirmed.");
}

async function reopenReview(kind, issueId) {
  if (kind === "decision") {
    await reopenDecision(issueId);
    return;
  }
  await restoreIssue(issueId);
}

async function reopenDecision(issueId) {
  const decision = state.decisions[issueId];
  if (!decision) return;
  if (decision.decisionId) {
    try {
      await api(`/api/decisions/${encodeURIComponent(decision.decisionId)}/reopen`, {
        method: "PATCH",
        body: JSON.stringify({
          reopened_by: decision.owner || "Unknown",
          reopened_reason: "Reopened from the SpecLint report.",
        }),
      });
    } catch (error) {
      toast(error.message || "Could not reopen this decision.");
      return;
    }
  }
  delete state.decisions[issueId];
  storeDecisions();
  renderReport();
  toast("Decision reopened.");
}

function useRewrite({ rerun = false } = {}) {
  if (!state.report?.rewritten_spec) {
    toast("Run analysis first.");
    return;
  }
  state.sourceSpecText = state.sourceSpecText || els.specInput.value.trim();
  state.preserveSourceForNextRun = true;
  els.specInput.value = state.report.rewritten_spec;
  els.titleInput.value = state.report.title;
  toast(rerun ? "Using rewrite and re-running." : "Rewrite moved into the editor.");
  if (rerun) analyze().catch((error) => toast(error.message));
}

function reportMarkdown() {
  const report = state.report;
  if (!report) return "";
  const issues = openIssues(report.issues)
    .map((issue) => `- [${issue.severity}] ${issue.title}: ${issue.suggestion}`)
    .join("\n");
  const acceptedRisks = acceptedRiskRecords(report.issues)
    .map(
      ({ issue, suppression }) =>
        `- [${issue.severity}] ${issue.title}: accepted by ${suppression.owner} until ${suppression.expiresAt}. Reason: ${suppression.reason}`,
    )
    .join("\n");
  const decisions = decisionRecords(report.issues)
    .map(
      ({ issue, decision }) =>
        `- [${issue.severity}] ${issue.title}: decided by ${decision.owner}. Decision: ${decision.decisionNote}`,
    )
    .join("\n");
  const pendingReviews = pendingReviewRecords(report.issues)
    .map(
      ({ issue, kind, record }) =>
        `- [${issue.severity}] ${issue.title}: ${kind === "decision" ? "decision" : "accepted risk"} needs review by ${record.owner}.`,
    )
    .join("\n");
  const tests = report.acceptance_tests
    .map((test) => `- ${test.name}: Given ${test.given}, when ${test.when}, then ${test.then}.`)
    .join("\n");
  return `# ${report.title}\n\nScore: ${report.score}/100 - ${verdictLabel(report.verdict)}\n\n${report.summary}\n\n## Open Issues\n${issues || "None"}\n\n## Pending Reviews\n${pendingReviews || "None"}\n\n## Requirements Decisions\n${decisions || "None"}\n\n## Accepted Risks\n${acceptedRisks || "None"}\n\n## Acceptance Tests\n${tests || "None"}\n\n## Rewritten Spec\n${report.rewritten_spec}\n`;
}

function downloadMarkdown() {
  if (!state.report) {
    toast("Run analysis first.");
    return;
  }
  const blob = new Blob([reportMarkdown()], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${state.report.title.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "speclint-report"}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function copyShareLink() {
  const payload = {
    title: els.titleInput.value,
    spec: els.specInput.value,
    strictness: els.strictnessSelect.value,
    domain: els.domainSelect.value,
    riskOverlays: selectedRiskOverlays(),
  };
  const hash = encodeURIComponent(JSON.stringify(payload));
  const url = `${location.origin}${location.pathname}#spec=${hash}`;
  await navigator.clipboard.writeText(url);
  history.replaceState(null, "", `#spec=${hash}`);
  toast("Share link copied.");
}

function loadFromHash() {
  if (!location.hash.startsWith("#spec=")) return false;
  try {
    const payload = JSON.parse(decodeURIComponent(location.hash.slice(6)));
    els.titleInput.value = payload.title || "Untitled spec";
    els.specInput.value = payload.spec || "";
    state.sourceSpecText = payload.spec || null;
    els.strictnessSelect.value = payload.strictness || "balanced";
    els.domainSelect.value = payload.domain || "general";
    setRiskOverlays(payload.riskOverlays || payload.risk_overlays || []);
    els.strictnessHelp.textContent = currentModeCopy();
    return Boolean(payload.spec);
  } catch {
    return false;
  }
}

els.specForm.addEventListener("submit", (event) => {
  event.preventDefault();
  analyze().catch((error) => toast(error.message));
});

els.analyzeButton.addEventListener("click", () => {
  analyze().catch((error) => toast(error.message));
});

els.clearButton.addEventListener("click", () => {
  els.specInput.value = "";
  state.sourceSpecText = null;
  state.preserveSourceForNextRun = false;
  els.specInput.focus();
});

els.strictnessSelect.addEventListener("change", () => {
  els.strictnessHelp.textContent = currentModeCopy();
});

els.domainSelect?.addEventListener("change", () => {
  els.strictnessHelp.textContent = currentModeCopy();
});

els.riskOverlayInputs.forEach((input) => {
  input.addEventListener("change", () => {
    els.strictnessHelp.textContent = currentModeCopy();
  });
});

els.themeToggle?.addEventListener("click", () => {
  setTheme(currentTheme() === "dark" ? "light" : "dark");
});

els.issueFilters.forEach((button) => {
  button.addEventListener("click", () => {
    state.issueFilter = button.dataset.issueFilter || "action";
    renderReport();
  });
});

els.exampleSelect.addEventListener("change", () => {
  const index = Number(els.exampleSelect.value);
  const example = state.examples[index];
  if (!example) return;
  els.titleInput.value = example.title;
  els.specInput.value = example.spec_text;
  state.sourceSpecText = example.spec_text;
  analyze().catch((error) => toast(error.message));
});

els.issuesList.addEventListener("click", (event) => {
  const applyButton = event.target.closest(".apply-fix");
  if (applyButton) {
    applyIssueFix(applyButton.dataset.issueId);
    return;
  }
  const suppressButton = event.target.closest(".suppress-issue");
  if (suppressButton) {
    openSuppressionForm(suppressButton.dataset.issueId);
    return;
  }
  const decideButton = event.target.closest(".decide-issue");
  if (decideButton) {
    openDecisionForm(decideButton.dataset.issueId);
    return;
  }
  const restoreButton = event.target.closest(".restore-issue");
  if (restoreButton) {
    restoreIssue(restoreButton.dataset.issueId).catch((error) => toast(error.message));
    return;
  }
  const reconfirmButton = event.target.closest(".reconfirm-review");
  if (reconfirmButton) {
    reconfirmReview(reconfirmButton.dataset.reviewKind, reconfirmButton.dataset.issueId).catch((error) =>
      toast(error.message),
    );
    return;
  }
  const reopenReviewButton = event.target.closest(".reopen-review");
  if (reopenReviewButton) {
    reopenReview(reopenReviewButton.dataset.reviewKind, reopenReviewButton.dataset.issueId).catch((error) =>
      toast(error.message),
    );
    return;
  }
  if (event.target.closest(".cancel-suppression")) {
    cancelSuppressionForm();
    return;
  }
  if (event.target.closest(".cancel-decision")) {
    cancelDecisionForm();
  }
});

els.issuesList.addEventListener("submit", (event) => {
  const suppressionForm = event.target.closest(".suppression-form");
  const decisionForm = event.target.closest(".decision-form");
  const form = suppressionForm || decisionForm;
  if (!form) return;
  event.preventDefault();
  if (decisionForm) {
    saveDecision(form.dataset.issueId, form).catch((error) => toast(error.message));
  } else {
    saveSuppression(form.dataset.issueId, form).catch((error) => toast(error.message));
  }
});

els.formattedButton.addEventListener("click", () => {
  state.rewriteView = "formatted";
  renderRewrite();
});

els.diffButton.addEventListener("click", () => {
  state.rewriteView = "diff";
  renderRewrite();
});

els.useRewriteButton.addEventListener("click", () => useRewrite({ rerun: true }));

els.copyRewriteButton.addEventListener("click", async () => {
  if (!state.report?.rewritten_spec) {
    toast("Run analysis first.");
    return;
  }
  await navigator.clipboard.writeText(state.report.rewritten_spec);
  toast("Rewritten spec copied.");
});

els.downloadButton.addEventListener("click", downloadMarkdown);
els.shareButton.addEventListener("click", () => copyShareLink().catch((error) => toast(error.message)));

els.historyList.addEventListener("click", (event) => {
  const button = event.target.closest(".history-item");
  if (!button) return;
  const run = state.history[Number(button.dataset.index)];
  if (!run) return;
  els.specInput.value = run.specText;
  state.sourceSpecText = run.specText;
  toast("Previous draft restored.");
});

const storedTheme = getStoredTheme();
setTheme(storedTheme || currentTheme() || systemTheme(), { persist: Boolean(storedTheme) });

const themePreference = window.matchMedia?.("(prefers-color-scheme: dark)");
themePreference?.addEventListener?.("change", (event) => {
  if (!getStoredTheme()) setTheme(event.matches ? "dark" : "light", { persist: false });
});

loadExamples()
  .then(() => {
    const loaded = loadFromHash();
    return analyze({ recordHistory: true && loaded });
  })
  .catch((error) => toast(error.message));
