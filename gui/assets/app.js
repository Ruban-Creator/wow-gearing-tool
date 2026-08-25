const PHASE_LABELS = { phase1: "Phase 1", phase2: "Phase 2", phase3: "Phase 3", phase4: "Phase 4", phase5: "Phase 5" };

// Populated from Api.get_supported_phases() on load, rather than a second
// hardcoded literal here that could drift from gui/api.py's own PHASES list
// (which is itself gated on real reference_bis/<phase>.json data existing -
// phase1 isn't offered because that file doesn't exist yet).
let PHASES = [];

const CLASS_COLORS = {
  warrior: "#C79C6E",
  druid: "#FF7D0A",
  hunter: "#ABD473",
  paladin: "#F58CBA",
  priest: "#FFFFFF",
  shaman: "#0070DE",
  mage: "#69CCF0",
  warlock: "#9482C9",
  rogue: "#FFF569",
};

let characters = [];
let selectedNameRealm = null;
let selectedHasProfile = false;
let runReportPollTimer = null;
let runReportStartedAt = null;

const charListEl = document.getElementById("char-list");
const refreshBtn = document.getElementById("refresh-btn");
const detailEmpty = document.getElementById("detail-empty");
const detailContent = document.getElementById("detail-content");
const detailName = document.getElementById("detail-name");
const detailMeta = document.getElementById("detail-meta");
const profileBanner = document.getElementById("profile-banner");
const reportsGrid = document.getElementById("reports-grid");

const settingsBtn = document.getElementById("settings-btn");
const settingsModal = document.getElementById("settings-modal");
const settingsOutputDir = document.getElementById("settings-output-dir");
const settingsChangeBtn = document.getElementById("settings-change-btn");
const settingsResetBtn = document.getElementById("settings-reset-btn");

const runReportBtn = document.getElementById("run-report-btn");
const runReportModal = document.getElementById("run-report-modal");
const runReportCharacter = document.getElementById("run-report-character");
const runReportPhaseSelect = document.getElementById("run-report-phase");
const runReportStartBtn = document.getElementById("run-report-start-btn");
const runReportForm = document.getElementById("run-report-form");
const runReportError = document.getElementById("run-report-error");
const runReportProgress = document.getElementById("run-report-progress");
const runReportStage = document.getElementById("run-report-stage");
const runReportBar = document.getElementById("run-report-bar");
const runReportElapsed = document.getElementById("run-report-elapsed");
const runReportDone = document.getElementById("run-report-done");
const runReportViewBtn = document.getElementById("run-report-view-btn");

function openModal(el) { el.hidden = false; }
function closeModal(el) { el.hidden = true; }

document.querySelectorAll(".modal-close").forEach((btn) => {
  btn.addEventListener("click", () => closeModal(document.getElementById(btn.dataset.close)));
});
document.querySelectorAll(".modal-overlay").forEach((overlay) => {
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeModal(overlay);
  });
});

function relativeTime(unixSeconds) {
  if (!unixSeconds) return "never";
  const deltaMs = Date.now() - unixSeconds * 1000;
  const mins = Math.floor(deltaMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function classColor(className) {
  if (!className) return "var(--class-default)";
  return CLASS_COLORS[className.toLowerCase()] || "var(--class-default)";
}

function renderCharList() {
  if (characters.length === 0) {
    charListEl.innerHTML = `<div class="empty-state">No characters found.<br><br>
      Run <code>/gtexport</code> and export via WowSimsExporter in-game, then Refresh.</div>`;
    return;
  }

  charListEl.innerHTML = "";
  for (const c of characters) {
    const id = c.identity || {};
    const card = document.createElement("div");
    card.className = "char-card" + (c.name_realm === selectedNameRealm ? " selected" : "");
    card.dataset.nameRealm = c.name_realm;

    const raceClass = [id.race, id.class].filter(Boolean).join(" ") || "identity not captured yet";
    const staleTs = c.source_used === "wse" ? c.wse_timestamp : c.gt_timestamp;

    card.innerHTML = `
      <div class="char-card-top">
        <span class="char-name">${escapeHtml(c.name_realm)}</span>
        ${id.level ? `<span class="char-level">Lv ${id.level}</span>` : ""}
      </div>
      <div class="char-sub">
        <span class="class-dot" style="background:${classColor(id.class)}"></span>
        <span>${escapeHtml(raceClass)}</span>
      </div>
      <div class="char-meta-row">
        <span class="badge source-${c.source_used}">${c.source_used === "wse" ? "WSE" : "GT Companion"}</span>
        ${c.has_profile ? "" : `<span class="badge no-profile">No profile</span>`}
      </div>
      <div class="staleness">saved ${relativeTime(staleTs)}</div>
    `;
    card.addEventListener("click", () => selectCharacter(c.name_realm));
    charListEl.appendChild(card);
  }
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

async function selectCharacter(nameRealm) {
  selectedNameRealm = nameRealm;
  renderCharList();

  const c = characters.find((x) => x.name_realm === nameRealm);
  if (!c) return;

  detailEmpty.hidden = true;
  detailContent.hidden = false;

  const id = c.identity || {};
  detailName.textContent = c.name_realm;
  const metaParts = [];
  if (id.race || id.class) metaParts.push([id.race, id.class].filter(Boolean).join(" "));
  if (id.level) metaParts.push(`Level ${id.level}`);
  if (id.faction) metaParts.push(id.faction);
  if (id.professions && id.professions.length) {
    metaParts.push(id.professions.map((p) => `${p.name} ${p.level}`).join(", "));
  }
  detailMeta.textContent = metaParts.join(" · ") || "No identity captured yet - export in-game.";

  profileBanner.hidden = c.has_profile;
  selectedHasProfile = c.has_profile;
  runReportBtn.disabled = !c.has_profile;
  runReportBtn.title = c.has_profile ? "" : "No sim profile yet for this character.";

  const reports = await window.pywebview.api.get_reports(nameRealm);
  renderReports(reports);
}

function renderReports(reports) {
  reportsGrid.innerHTML = "";
  for (const phase of PHASES) {
    const r = reports[phase];
    const card = document.createElement("div");
    card.className = "report-card";

    if (r) {
      card.innerHTML = `
        <div class="report-phase">${PHASE_LABELS[phase]}</div>
        <div class="report-body">${r.notes ? escapeHtml(r.notes) : "Upgrade ledger report"}</div>
        <button class="report-btn">View Report</button>
        <div class="report-generated">generated ${new Date(r.generated_at).toLocaleString()}</div>
      `;
      card.querySelector(".report-btn").addEventListener("click", () => {
        window.pywebview.api.open_url(r.artifact_url);
      });
    } else {
      card.innerHTML = `
        <div class="report-phase">${PHASE_LABELS[phase]}</div>
        <div class="report-body report-empty">No report published yet</div>
      `;
    }
    reportsGrid.appendChild(card);
  }
}

async function loadCharacters() {
  refreshBtn.classList.add("spinning");
  try {
    characters = await window.pywebview.api.list_characters();
  } finally {
    refreshBtn.classList.remove("spinning");
  }
  renderCharList();
  if (selectedNameRealm && characters.some((c) => c.name_realm === selectedNameRealm)) {
    selectCharacter(selectedNameRealm);
  } else if (characters.length > 0) {
    selectCharacter(characters[0].name_realm);
  }
}

refreshBtn.addEventListener("click", loadCharacters);

// ---- Settings modal ----

async function refreshSettingsDisplay() {
  const dir = await window.pywebview.api.get_report_output_dir();
  settingsOutputDir.textContent = dir || "(default) data/characters/<character>/reports/";
}

settingsBtn.addEventListener("click", async () => {
  await refreshSettingsDisplay();
  openModal(settingsModal);
});

settingsChangeBtn.addEventListener("click", async () => {
  await window.pywebview.api.pick_report_folder();
  await refreshSettingsDisplay();
});

settingsResetBtn.addEventListener("click", async () => {
  await window.pywebview.api.reset_report_output_dir();
  await refreshSettingsDisplay();
});

// ---- Run Report modal ----

function resetRunReportModal() {
  runReportForm.hidden = false;
  runReportProgress.hidden = true;
  runReportDone.hidden = true;
  runReportError.hidden = true;
  runReportStartBtn.disabled = false;
  runReportBar.classList.remove("indeterminate");
  runReportBar.style.width = "0%";
  if (runReportPollTimer) {
    clearInterval(runReportPollTimer);
    runReportPollTimer = null;
  }
}

runReportBtn.addEventListener("click", () => {
  if (!selectedNameRealm || !selectedHasProfile) return;
  resetRunReportModal();
  runReportCharacter.textContent = selectedNameRealm;
  runReportPhaseSelect.innerHTML = PHASES.map((p) => `<option value="${p}">${PHASE_LABELS[p]}</option>`).join("");
  openModal(runReportModal);
});

function formatElapsed(ms) {
  const secs = Math.floor(ms / 1000);
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, "0")} elapsed`;
}

function pollRunStatus() {
  runReportPollTimer = setInterval(async () => {
    const st = await window.pywebview.api.get_run_status();

    runReportStage.textContent = st.stage || "Working…";
    if (st.detail) {
      const m = st.detail.match(/\((\d+)%\)/);
      if (m) {
        runReportBar.classList.remove("indeterminate");
        runReportBar.style.width = m[1] + "%";
      }
      runReportStage.textContent = `${st.stage} — ${st.detail}`;
    } else {
      runReportBar.classList.add("indeterminate");
    }
    runReportElapsed.textContent = formatElapsed(Date.now() - runReportStartedAt);

    if (st.done) {
      clearInterval(runReportPollTimer);
      runReportPollTimer = null;
      runReportProgress.hidden = true;

      if (st.error) {
        runReportForm.hidden = false;
        runReportStartBtn.disabled = false;
        runReportError.hidden = false;
        runReportError.textContent = st.error;
      } else {
        runReportDone.hidden = false;
        runReportViewBtn.onclick = () => window.pywebview.api.open_url(st.report_url);
        if (selectedNameRealm === st.name_realm) {
          const reports = await window.pywebview.api.get_reports(st.name_realm);
          renderReports(reports);
        }
      }
    }
  }, 1500);
}

runReportStartBtn.addEventListener("click", async () => {
  const phase = runReportPhaseSelect.value;
  runReportStartBtn.disabled = true;
  runReportError.hidden = true;

  const res = await window.pywebview.api.run_report(selectedNameRealm, phase);
  if (!res.started) {
    runReportStartBtn.disabled = false;
    runReportError.hidden = false;
    runReportError.textContent = res.error;
    return;
  }

  runReportForm.hidden = true;
  runReportProgress.hidden = false;
  runReportStartedAt = Date.now();
  pollRunStatus();
});

async function init() {
  PHASES = await window.pywebview.api.get_supported_phases();
  await loadCharacters();
}

window.addEventListener("pywebviewready", init);
