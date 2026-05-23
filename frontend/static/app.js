const state = {
  report: null,
  examples: [],
};

const els = {
  titleInput: document.querySelector("#titleInput"),
  specInput: document.querySelector("#specInput"),
  specForm: document.querySelector("#specForm"),
  analyzeButton: document.querySelector("#analyzeButton"),
  exampleSelect: document.querySelector("#exampleSelect"),
  strictnessSelect: document.querySelector("#strictnessSelect"),
  scoreValue: document.querySelector("#scoreValue"),
  scoreLabel: document.querySelector("#scoreLabel"),
  verdictText: document.querySelector("#verdictText"),
  summaryText: document.querySelector("#summaryText"),
  intentGrid: document.querySelector("#intentGrid"),
  issueCount: document.querySelector("#issueCount"),
  issuesList: document.querySelector("#issuesList"),
  testsList: document.querySelector("#testsList"),
  rewriteBox: document.querySelector("#rewriteBox"),
  traceList: document.querySelector("#traceList"),
  copyRewriteButton: document.querySelector("#copyRewriteButton"),
  toast: document.querySelector("#toast"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed: ${response.status}`);
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

function severityLabel(value) {
  return String(value || "").replaceAll("_", " ");
}

function tags(items) {
  if (!items?.length) return `<span class="empty-state">None detected</span>`;
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

async function analyze() {
  const title = els.titleInput.value.trim() || "Untitled spec";
  const specText = els.specInput.value.trim();
  if (specText.length < 20) {
    toast("Spec needs at least 20 characters.");
    return;
  }
  els.analyzeButton.disabled = true;
  els.analyzeButton.textContent = "Analyzing";
  try {
    state.report = await api("/api/analyze", {
      method: "POST",
      body: JSON.stringify({
        title,
        spec_text: specText,
        strictness: els.strictnessSelect.value,
      }),
    });
    renderReport();
  } finally {
    els.analyzeButton.disabled = false;
    els.analyzeButton.textContent = "Analyze";
  }
}

function renderReport() {
  const report = state.report;
  if (!report) return;
  els.scoreValue.textContent = report.score;
  els.scoreLabel.textContent = verdictLabel(report.verdict);
  els.verdictText.textContent = verdictLabel(report.verdict);
  els.summaryText.textContent = report.summary;
  renderIntent(report.intent);
  renderIssues(report.issues);
  renderTests(report.acceptance_tests);
  renderTrace(report.traceability);
  els.rewriteBox.className = "rewrite-box";
  els.rewriteBox.textContent = report.rewritten_spec;
}

function renderIntent(intent) {
  const blocks = [
    ["Actors", intent.actors],
    ["Entities", intent.entities],
    ["Actions", intent.actions],
    ["States", intent.states],
    ["Hard Rules", intent.explicit_rules],
  ];
  els.intentGrid.className = "intent-grid";
  els.intentGrid.innerHTML = blocks
    .map(
      ([label, values]) => `
        <section class="intent-block">
          <h3>${label}</h3>
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
          <div class="tag-row">
            <span class="severity-pill severity-${escapeHtml(issue.severity)}">${severityLabel(issue.severity)}</span>
            <span class="tag">${severityLabel(issue.type)}</span>
          </div>
          <h3>${escapeHtml(issue.title)}</h3>
          <div class="issue-grid">
            <span class="issue-label">Evidence</span>
            <p>${escapeHtml(issue.evidence)}</p>
            <span class="issue-label">Why it matters</span>
            <p>${escapeHtml(issue.why_it_matters)}</p>
            <span class="issue-label">Fix</span>
            <p>${escapeHtml(issue.suggestion)}</p>
            <span class="issue-label">Question</span>
            <p>${escapeHtml(issue.test_prompt)}</p>
          </div>
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
              ? `<div class="tag-row">${test.covers_issue_ids.map((id) => `<span class="tag">${escapeHtml(id)}</span>`).join("")}</div>`
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
          <p><strong>Tests:</strong> ${escapeHtml(item.tests.join(", ") || "none")}</p>
          <p><strong>Open questions:</strong> ${escapeHtml(item.open_questions.join(" | ") || "none")}</p>
        </article>
      `,
    )
    .join("");
}

els.specForm.addEventListener("submit", (event) => {
  event.preventDefault();
  analyze().catch((error) => toast(error.message));
});

els.analyzeButton.addEventListener("click", () => {
  analyze().catch((error) => toast(error.message));
});

els.exampleSelect.addEventListener("change", () => {
  const index = Number(els.exampleSelect.value);
  const example = state.examples[index];
  if (!example) return;
  els.titleInput.value = example.title;
  els.specInput.value = example.spec_text;
  analyze().catch((error) => toast(error.message));
});

els.copyRewriteButton.addEventListener("click", async () => {
  if (!state.report?.rewritten_spec) {
    toast("Run analysis first.");
    return;
  }
  await navigator.clipboard.writeText(state.report.rewritten_spec);
  toast("Rewritten spec copied.");
});

loadExamples()
  .then(() => analyze())
  .catch((error) => toast(error.message));

