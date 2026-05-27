const state = {
  report: null,
  examples: [],
  history: [],
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
  strictnessHelp: document.querySelector("#strictnessHelp"),
  scoreValue: document.querySelector("#scoreValue"),
  scoreLabel: document.querySelector("#scoreLabel"),
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
  themeButtons: document.querySelectorAll("[data-theme-choice]"),
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
  els.themeButtons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.themeChoice === nextTheme));
  });
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
      }),
    });
    state.report = report;
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
    issueCount: report.issues.length,
    delta: previous ? report.score - previous.score : 0,
    specText,
    at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  });
  state.history = state.history.slice(0, 6);
}

function renderReport() {
  const report = state.report;
  if (!report) return;
  els.scoreValue.textContent = report.score;
  els.scoreLabel.textContent = `${verdictLabel(report.verdict)} out of 100`;
  els.verdictText.textContent = `${report.score} / 100 - ${verdictLabel(report.verdict)}`;
  els.summaryText.textContent = report.summary;
  els.strictnessHelp.textContent = report.strictness_note || strictnessCopy[els.strictnessSelect.value];
  renderSeverityCounts(report.severity_counts);
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
  els.scoreValue.textContent = "--";
  els.scoreLabel.textContent = "Improper input";
  els.verdictText.textContent = "IMPROPER INPUT";
  els.summaryText.textContent = "Write a real product requirement before running SpecLint.";
  els.rubricText.textContent = "No score generated. This input was rejected before analysis.";
  els.strictnessHelp.textContent = strictnessCopy[els.strictnessSelect.value];
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
  els.issueCount.textContent = `${issues.length} issue${issues.length === 1 ? "" : "s"}`;
  if (!issues.length) {
    els.issuesList.className = "issue-list empty-state";
    els.issuesList.textContent = "No lint issues found.";
    return;
  }
  els.issuesList.className = "issue-list";
  els.issuesList.innerHTML = issues
    .map(
      (issue) => `
        <article class="issue-item">
          <div class="issue-topline">
            <div class="tag-row">
              <span class="severity-pill severity-${escapeHtml(issue.severity)}">${humanize(issue.severity)}</span>
              <span class="tag">${humanize(issue.type)}</span>
            </div>
            <button class="ghost-button compact apply-fix" type="button" data-issue-id="${escapeHtml(issue.id)}">Add fix to draft</button>
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
        </article>
      `,
    )
    .join("");
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
  const issues = report.issues
    .map((issue) => `- [${issue.severity}] ${issue.title}: ${issue.suggestion}`)
    .join("\n");
  const tests = report.acceptance_tests
    .map((test) => `- ${test.name}: Given ${test.given}, when ${test.when}, then ${test.then}.`)
    .join("\n");
  return `# ${report.title}\n\nScore: ${report.score}/100 - ${verdictLabel(report.verdict)}\n\n${report.summary}\n\n## Issues\n${issues || "None"}\n\n## Acceptance Tests\n${tests || "None"}\n\n## Rewritten Spec\n${report.rewritten_spec}\n`;
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
    els.strictnessHelp.textContent = strictnessCopy[els.strictnessSelect.value];
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
  els.strictnessHelp.textContent = strictnessCopy[els.strictnessSelect.value];
});

els.themeButtons.forEach((button) => {
  button.addEventListener("click", () => setTheme(button.dataset.themeChoice));
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
  const button = event.target.closest(".apply-fix");
  if (!button) return;
  applyIssueFix(button.dataset.issueId);
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
