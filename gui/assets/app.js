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
// Smooth client-side countdown for "Stage finishes in" (per the user,
// 2026-08-25: "the number should always count down while working, it can
// be fixed on a recheck" - rather than replacing the displayed number with
// a fresh, possibly-noisier backend estimate on every 1.5s poll tick, a
// separate 1s ticker counts this down locally, and each new poll response
// just "rechecks"/corrects it to the latest real backend value for the
// SAME stage. A stage change (or the backend having no estimate yet)
// resets it outright - no reason to count down toward a now-irrelevant
// number.
let runReportEtaTicker = null;
let runReportEtaSeconds = null;
let runReportEtaStage = null;

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
const settingsDebugToggle = document.getElementById("settings-debug-toggle");
const settingsWowRoot = document.getElementById("settings-wow-root");
const settingsWowRootChangeBtn = document.getElementById("settings-wow-root-change-btn");
const settingsWowRootResetBtn = document.getElementById("settings-wow-root-reset-btn");
const settingsAddonStatus = document.getElementById("settings-addon-status");
const settingsAddonInstallBtn = document.getElementById("settings-addon-install-btn");

const addonBanner = document.getElementById("addon-banner");
const addonBannerText = document.getElementById("addon-banner-text");
const addonBannerInstallBtn = document.getElementById("addon-banner-install-btn");
const addonBannerDismissBtn = document.getElementById("addon-banner-dismiss-btn");
let addonBannerDismissed = false;

const runReportBtn = document.getElementById("run-report-btn");
const runReportModal = document.getElementById("run-report-modal");
const runReportCharacter = document.getElementById("run-report-character");
const runReportPhaseSelect = document.getElementById("run-report-phase");
const runReportDurationInput = document.getElementById("run-report-duration");
const runReportStartBtn = document.getElementById("run-report-start-btn");
const runReportForm = document.getElementById("run-report-form");
const runReportError = document.getElementById("run-report-error");
const runReportProgress = document.getElementById("run-report-progress");
const runReportStage = document.getElementById("run-report-stage");
const runReportBar = document.getElementById("run-report-bar");
const runReportElapsed = document.getElementById("run-report-elapsed");
const runReportStageEta = document.getElementById("run-report-stage-eta");
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

const SOURCE_LABELS = { wse: "WSE", gtcompanion: "GT Companion", synthetic: "Synthetic" };

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
        <span class="badge source-${c.source_used}">${SOURCE_LABELS[c.source_used] || c.source_used}</span>
        ${c.has_profile ? "" : `<span class="badge no-profile">No profile</span>`}
      </div>
      <div class="staleness">${c.synthetic ? "synthetic test character" : `saved ${relativeTime(staleTs)}`}</div>
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
  const outputDir = await window.pywebview.api.get_report_output_dir();
  settingsOutputDir.textContent = outputDir.path + (outputDir.is_configured ? "" : " (default)");
  settingsDebugToggle.checked = await window.pywebview.api.get_debug_mode();

  const wowRoot = await window.pywebview.api.get_wow_root();
  settingsWowRoot.textContent = wowRoot.path + (wowRoot.is_configured ? "" : " (auto-detected)");

  await refreshAddonStatus();
}

// ---- Companion addon install (not on CurseForge yet - see gui/api.py's
// own comment on why this ships directly from the repo instead) ----

async function refreshAddonStatus() {
  const status = await window.pywebview.api.get_addon_status();
  if (!status.installed) {
    settingsAddonStatus.textContent = "Not installed";
    settingsAddonInstallBtn.textContent = "Install";
  } else if (status.up_to_date) {
    settingsAddonStatus.textContent = "Installed, up to date";
    settingsAddonInstallBtn.textContent = "Reinstall";
  } else {
    settingsAddonStatus.textContent = "Installed, but out of date";
    settingsAddonInstallBtn.textContent = "Update";
  }
  return status;
}

async function checkAddonBanner() {
  if (addonBannerDismissed) return;
  const status = await window.pywebview.api.get_addon_status();
  if (status.installed && status.up_to_date) {
    addonBanner.hidden = true;
    return;
  }
  addonBannerText.textContent = status.installed
    ? "A newer version of GearingToolCompanion is available - it's not on CurseForge, so this tool ships it directly."
    : "GearingToolCompanion isn't installed yet - it's not on CurseForge, so this tool ships it directly.";
  addonBanner.hidden = false;
}

settingsAddonInstallBtn.addEventListener("click", async () => {
  settingsAddonInstallBtn.disabled = true;
  try {
    await window.pywebview.api.install_companion_addon();
    await refreshAddonStatus();
    await checkAddonBanner();
  } finally {
    settingsAddonInstallBtn.disabled = false;
  }
});

addonBannerInstallBtn.addEventListener("click", async () => {
  addonBannerInstallBtn.disabled = true;
  try {
    await window.pywebview.api.install_companion_addon();
    await checkAddonBanner();
  } finally {
    addonBannerInstallBtn.disabled = false;
  }
});

addonBannerDismissBtn.addEventListener("click", () => {
  addonBannerDismissed = true;
  addonBanner.hidden = true;
});

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

settingsDebugToggle.addEventListener("change", async () => {
  await window.pywebview.api.set_debug_mode(settingsDebugToggle.checked);
  await loadCharacters();
});

settingsWowRootChangeBtn.addEventListener("click", async () => {
  await window.pywebview.api.pick_wow_root_folder();
  await refreshSettingsDisplay();
  await loadCharacters();
});

settingsWowRootResetBtn.addEventListener("click", async () => {
  await window.pywebview.api.reset_wow_root();
  await refreshSettingsDisplay();
  await loadCharacters();
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
  runReportStageEta.textContent = "";
  if (runReportPollTimer) {
    clearInterval(runReportPollTimer);
    runReportPollTimer = null;
  }
  if (runReportEtaTicker) {
    clearInterval(runReportEtaTicker);
    runReportEtaTicker = null;
  }
  runReportEtaSeconds = null;
  runReportEtaStage = null;
}

runReportBtn.addEventListener("click", async () => {
  if (!selectedNameRealm || !selectedHasProfile) return;

  // Real bug, found live by the user 2026-08-25: the modal's "x" only ever
  // hid the dialog (closeModal() is just `el.hidden = true`) - it never
  // stopped the real background job, which keeps running server-side
  // regardless of whether anything is polling it. Reopening used to always
  // call resetRunReportModal() unconditionally, which tore down the poll
  // timers that WERE still tracking that live job and put the plain form
  // back up - so clicking Run again just hit Api.run_report()'s own "a
  // report is already running" guard, with no way back into the real
  // progress view. Now checks for a still-active job first and reattaches
  // to it instead of assuming a fresh form is always correct.
  const st = await window.pywebview.api.get_run_status();
  if (st.active) {
    resetRunReportModal();
    runReportCharacter.textContent = st.name_realm;
    runReportForm.hidden = true;
    runReportProgress.hidden = false;
    runReportStartedAt = Date.now();
    openModal(runReportModal);
    pollRunStatus();
    return;
  }

  resetRunReportModal();
  runReportCharacter.textContent = selectedNameRealm;
  runReportPhaseSelect.innerHTML = PHASES.map((p) => `<option value="${p}">${PHASE_LABELS[p]}</option>`).join("");
  runReportDurationInput.value = 180;
  openModal(runReportModal);
});

function formatElapsed(ms) {
  const secs = Math.floor(ms / 1000);
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, "0")} elapsed`;
}

// Per-stage only, not a whole-run estimate (per the user, 2026-08-25) - see
// run_with_progress()'s own comment for why a whole-run number was dropped
// as more guess than estimate. null covers both "this stage has no
// done/total at all" (a milestone) and "too early in this stage to trust
// the rate yet" (run_with_progress only starts sending eta_seconds once
// done > 0).
function formatStageEta(seconds) {
  if (seconds === null || seconds === undefined) return "";
  // Real bug, caught live via a user screenshot, 2026-08-25: showed
  // "Stage finishes in: -1:-1". Math.floor/modulo both round toward
  // negative infinity for a negative input (Math.floor(-0.02) is -1, not
  // 0; -1 % 60 is -1, not 59) - a small negative seconds value (see the
  // ticker fix below for how one snuck through) produced exactly that
  // "-1:-1" text. Clamped here too, not just at the source, since a
  // display formatter should never trust its input is already valid.
  const secs = Math.max(0, Math.round(seconds));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `Stage finishes in: ${m}:${String(s).padStart(2, "0")}`;
}

function pollRunStatus() {
  runReportEtaTicker = setInterval(() => {
    if (runReportEtaSeconds !== null && runReportEtaSeconds > 0) {
      // Real bug: this used to be a bare `-= 1`, which overshoots below
      // zero whenever the current value is already under 1 (e.g. 0.5
      // ticks to -0.5) - the `> 0` guard above only checks BEFORE the
      // subtraction, not after. Clamping the result at 0 is what actually
      // stops the countdown there instead of running through it.
      runReportEtaSeconds = Math.max(0, runReportEtaSeconds - 1);
      runReportStageEta.textContent = formatStageEta(runReportEtaSeconds);
    }
  }, 1000);

  runReportPollTimer = setInterval(async () => {
    const st = await window.pywebview.api.get_run_status();

    // "(Stage X of Y)" so people know there's something else coming, not
    // just a bare label that could as easily be the whole run (per the
    // user, 2026-08-25). Y is a real, profile-aware count built once per
    // run (see run_full_sweep_mv.py's own stage_sequence) - not shown at
    // all for the handful of non-progress stages (syncing, building the
    // report) that sit outside that sequence.
    const stageCount = (st.stage_index && st.stage_total) ? ` (Stage ${st.stage_index} of ${st.stage_total})` : "";
    runReportStage.textContent = (st.stage || "Working…") + stageCount;
    if (st.detail) {
      const m = st.detail.match(/\((\d+)%\)/);
      if (m) {
        runReportBar.classList.remove("indeterminate");
        runReportBar.style.width = m[1] + "%";
      }
      runReportStage.textContent = `${st.stage}${stageCount} — ${st.detail}`;
    } else {
      runReportBar.classList.add("indeterminate");
    }
    runReportElapsed.textContent = formatElapsed(Date.now() - runReportStartedAt);

    // "Recheck": a stage change (or no estimate yet) resets the countdown
    // outright - a new stage's number has nothing to do with the old one.
    // Same stage: just take the backend's fresh value directly. A blended
    // "move partway toward it" correction was tried first and made things
    // worse, not better - root-caused live from a screen recording,
    // 2026-08-25 (see gui/api.py's _get_status() docstring): the backend
    // value used to go stale for many real seconds between actual progress
    // ticks (run_with_progress() only calls back every ~5% of items), so
    // blending toward that same frozen number every 1.5s was fighting the
    // local ticker's own countdown instead of filling the gap between real
    // updates. Now that _get_status() itself age-adjusts for time elapsed
    // since the last real measurement, the backend value is always live -
    // a direct set is both simpler and correct.
    if (st.stage !== runReportEtaStage) {
      runReportEtaStage = st.stage;
      runReportEtaSeconds = st.eta_seconds;
    } else if (st.eta_seconds !== null && st.eta_seconds !== undefined) {
      runReportEtaSeconds = st.eta_seconds;
    }
    runReportStageEta.textContent = formatStageEta(runReportEtaSeconds);

    if (st.done) {
      clearInterval(runReportPollTimer);
      runReportPollTimer = null;
      clearInterval(runReportEtaTicker);
      runReportEtaTicker = null;
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

  const duration = parseInt(runReportDurationInput.value, 10) || 180;
  const res = await window.pywebview.api.run_report(selectedNameRealm, phase, duration);
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
  await checkAddonBanner();
}

window.addEventListener("pywebviewready", init);
