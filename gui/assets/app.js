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
const profileBannerText = document.getElementById("profile-banner-text");
const profileAssignSelect = document.getElementById("profile-assign-select");
const profileAssignBtn = document.getElementById("profile-assign-btn");
const profileAssignCancelBtn = document.getElementById("profile-assign-cancel-btn");
const changeProfileBtn = document.getElementById("change-profile-btn");
const assignedProfileBadge = document.getElementById("assigned-profile-badge");
const reportsGrid = document.getElementById("reports-grid");

const settingsBtn = document.getElementById("settings-btn");
const settingsModal = document.getElementById("settings-modal");
const settingsOutputDir = document.getElementById("settings-output-dir");
const settingsChangeBtn = document.getElementById("settings-change-btn");
const settingsResetBtn = document.getElementById("settings-reset-btn");
const settingsDebugToggle = document.getElementById("settings-debug-toggle");
const settingsShowLowLevelToggle = document.getElementById("settings-show-low-level-toggle");
const settingsResolveIterationsInput = document.getElementById("settings-resolve-iterations-input");
const settingsResolveIterationsSaveBtn = document.getElementById("settings-resolve-iterations-save-btn");
const settingsResolveIterationsResetBtn = document.getElementById("settings-resolve-iterations-reset-btn");
const settingsWowRoot = document.getElementById("settings-wow-root");
const settingsWowRootChangeBtn = document.getElementById("settings-wow-root-change-btn");
const settingsWowRootResetBtn = document.getElementById("settings-wow-root-reset-btn");
const settingsAddonStatus = document.getElementById("settings-addon-status");
const settingsAddonInstallBtn = document.getElementById("settings-addon-install-btn");
const settingsAddonCurseforgeLink = document.getElementById("settings-addon-curseforge-link");
const settingsToolVersion = document.getElementById("settings-tool-version");
const creditsVersion = document.getElementById("credits-version");
const creditsGithubLink = document.getElementById("credits-github-link");
const creditsPatreonLink = document.getElementById("credits-patreon-link");
const creditsDiscordLink = document.getElementById("credits-discord-link");

const addonBanner = document.getElementById("addon-banner");
const addonBannerText = document.getElementById("addon-banner-text");
const addonBannerInstallBtn = document.getElementById("addon-banner-install-btn");
const addonBannerCurseforgeLink = document.getElementById("addon-banner-curseforge-link");
const addonBannerDismissBtn = document.getElementById("addon-banner-dismiss-btn");
let addonBannerDismissed = false;

const settingsUpdateStatus = document.getElementById("settings-update-status");
const settingsUpdateCheckBtn = document.getElementById("settings-update-check-btn");
const settingsUpdateViewBtn = document.getElementById("settings-update-view-btn");
const updateBanner = document.getElementById("update-banner");
const updateBannerText = document.getElementById("update-banner-text");
const updateBannerViewBtn = document.getElementById("update-banner-view-btn");
const updateBannerDismissBtn = document.getElementById("update-banner-dismiss-btn");
let updateBannerDismissed = false;

const toastBanner = document.getElementById("toast-banner");
const toastBannerText = document.getElementById("toast-banner-text");
let toastHideTimer = null;

function showToast(text, ms = 3500) {
  toastBannerText.textContent = text;
  toastBanner.hidden = false;
  if (toastHideTimer) clearTimeout(toastHideTimer);
  toastHideTimer = setTimeout(() => { toastBanner.hidden = true; }, ms);
}

const runReportBtn = document.getElementById("run-report-btn");
const runReportModal = document.getElementById("run-report-modal");
const runReportCharacter = document.getElementById("run-report-character");
const runReportPhaseSelect = document.getElementById("run-report-phase");
const runReportDurationInput = document.getElementById("run-report-duration");
const runReportDurationWarning = document.getElementById("run-report-duration-warning");
const runReportStartBtn = document.getElementById("run-report-start-btn");
const runReportForm = document.getElementById("run-report-form");
const runReportError = document.getElementById("run-report-error");
const runReportOomCheck = document.getElementById("run-report-oom-check");
const runReportOomText = document.getElementById("run-report-oom-text");
const runReportOomUseRecommendedBtn = document.getElementById("run-report-oom-use-recommended-btn");
const runReportOomRunAnywayBtn = document.getElementById("run-report-oom-run-anyway-btn");
const runReportProgress = document.getElementById("run-report-progress");
const runReportStage = document.getElementById("run-report-stage");
const runReportBar = document.getElementById("run-report-bar");
const runReportElapsed = document.getElementById("run-report-elapsed");
const runReportStageEta = document.getElementById("run-report-stage-eta");
const runReportDone = document.getElementById("run-report-done");
const runReportViewBtn = document.getElementById("run-report-view-btn");

const runReportWeaveRow = document.getElementById("run-report-weave-row");
const runReportWeaveWarning = document.getElementById("run-report-weave-warning");
const runReportWeaveModeSelect = document.getElementById("run-report-weave-mode");
// Backlog #20 follow-up (2026-09-06) - real playstyle choice only exists
// for Survival/Beastmastery Hunter (a real weave rotation mechanic - see
// local_config.melee_weave_mode()'s own docstring) - per the user's own
// reminder, every other class must never see this control at all.
const WEAVE_CAPABLE_PROFILES = ["survival_hunter", "beastmastery_hunter"];

const runReportPotionRow = document.getElementById("run-report-potion-row");
const runReportPotionModeSelect = document.getElementById("run-report-potion-mode");
// Combat Potion toggle (2026-09-06, per the user: "some classes like arcane
// mage gain more dps from mana pot over destro pot") - real, curated list,
// same pattern as WEAVE_CAPABLE_PROFILES, matching
// run_upgrade_sweep.CASTER_POTION_PROFILES exactly.
const CASTER_POTION_PROFILES = [
  "balance_druid", "elemental_shaman", "shadow_priest", "arcane_mage",
  "affliction_warlock", "demonology_warlock", "destruction_warlock",
];

async function refreshPotionModeRow() {
  const c = characters.find((x) => x.name_realm === selectedNameRealm);
  const isCaster = c && CASTER_POTION_PROFILES.includes(c.profile_dir_name);
  runReportPotionRow.hidden = !isCaster;
  if (!isCaster) return;
  const result = await window.pywebview.api.get_potion_options(selectedNameRealm);
  runReportPotionModeSelect.innerHTML = result.options
    .map((o) => `<option value="${o.item_id}">${o.name}</option>`)
    .join("");
  runReportPotionModeSelect.value = result.current;
}

runReportPotionModeSelect.addEventListener("change", async () => {
  if (!selectedNameRealm) return;
  await window.pywebview.api.set_potion_choice(selectedNameRealm, parseInt(runReportPotionModeSelect.value, 10));
});

// Real duration-typo guard (2026-09-06, per the user: "fights under 30
// seconds could also trigger the typo warning - too short fights won't
// result in real numbers"). Client-side only, no backend call - purely a
// caution, never blocks Run (matches gui/api.py's own run_report() comment
// explicitly declining a hard upper bound for the same reason - a real,
// deliberately long or short test is still the user's call).
const DURATION_WARNING_MIN = 30;
const DURATION_WARNING_MAX = 600;

function refreshDurationWarning() {
  const duration = parseInt(runReportDurationInput.value, 10);
  if (!duration || duration < DURATION_WARNING_MIN) {
    runReportDurationWarning.hidden = false;
    runReportDurationWarning.textContent =
      `${runReportDurationInput.value || 0}s is unusually short for a raid encounter - too short a ` +
      "fight won't produce real numbers. Double check this isn't a typo.";
  } else if (duration > DURATION_WARNING_MAX) {
    runReportDurationWarning.hidden = false;
    runReportDurationWarning.textContent =
      `${duration}s is unusually long for a raid encounter - double check this isn't a typo ` +
      "(e.g. an extra digit) before running.";
  } else {
    runReportDurationWarning.hidden = true;
  }
}
runReportDurationInput.addEventListener("input", refreshDurationWarning);

const runReportSourcesSummary = document.getElementById("run-report-sources-summary");
const runReportSourcesBtn = document.getElementById("run-report-sources-btn");
const sourceScopeModal = document.getElementById("source-scope-modal");
const sourceScopeGroups = document.getElementById("source-scope-groups");
const sourceScopeSelectAllBtn = document.getElementById("source-scope-select-all-btn");
const sourceScopeSelectNoneBtn = document.getElementById("source-scope-select-none-btn");
const sourceScopeSaveBtn = document.getElementById("source-scope-save-btn");
const sourceScopeCancelBtn = document.getElementById("source-scope-cancel-btn");

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
  profileAssignCancelBtn.hidden = true;
  selectedHasProfile = c.has_profile;
  runReportBtn.disabled = !c.has_profile;
  runReportBtn.title = c.has_profile ? "" : "No sim profile yet for this character.";
  // Real gap found and fixed 2026-08-31: always visible once a character is
  // selected, not just when she has no profile yet - a respec (e.g.
  // Elemental -> Enhancement) had no way back into the assign UI at all
  // once she already had one.
  changeProfileBtn.hidden = false;
  if (c.has_profile) {
    // Per the user (2026-08-31): show which sim profile is actually
    // assigned at a glance, not just discoverable by opening "Change
    // profile…" - depends on the real assignment, not her raw identity.spec
    // (the addon-reported spec and the assigned sim profile could diverge).
    const profiles = await ensureAvailableProfilesCache();
    const assigned = profiles.find((p) => p.dir_name === c.profile_dir_name);
    assignedProfileBadge.textContent = assigned ? assigned.label : c.profile_dir_name;
    assignedProfileBadge.hidden = false;
  } else {
    assignedProfileBadge.hidden = true;
    profileBannerText.textContent = "No sim profile assigned to this character yet.";
    await populateProfileAssignSelect(id.class);
  }

  const reports = await window.pywebview.api.get_reports(nameRealm);
  renderReports(reports, c.profile_dir_name);
}

let availableProfilesCache = null;

async function ensureAvailableProfilesCache() {
  // Cached across calls - the profile list only changes with a new build
  // of the tool, never within a single running session.
  if (!availableProfilesCache) {
    availableProfilesCache = await window.pywebview.api.get_available_profiles();
  }
  return availableProfilesCache;
}

async function populateProfileAssignSelect(charClass, currentDirName) {
  await ensureAvailableProfilesCache();
  // Real bug found and fixed 2026-08-31: this used to list every real
  // profile (any class) for every character, so a real Shaman could be
  // offered - and picked - an Affliction Warlock profile with nothing to
  // stop it. Filter to the character's own detected class when known;
  // fall back to the full list if her identity has no class yet (no
  // export captured) or no profile matches her class at all (not one of
  // the 15 currently supported) - never leave the dropdown empty.
  const cls = (charClass || "").toLowerCase();
  const matching = cls ? availableProfilesCache.filter((p) => p.class === cls) : [];
  const list = matching.length ? matching : availableProfilesCache;
  profileAssignSelect.innerHTML = list
    .map((p) => `<option value="${escapeHtml(p.dir_name)}">${escapeHtml(p.label)}</option>`)
    .join("");
  // Pre-select her current assignment when reopening to change it (a
  // respec, e.g.) - Assign then reads as "confirm/update", not "start over".
  if (currentDirName && list.some((p) => p.dir_name === currentDirName)) {
    profileAssignSelect.value = currentDirName;
  }
}

changeProfileBtn.addEventListener("click", async () => {
  const c = characters.find((x) => x.name_realm === selectedNameRealm);
  if (!c) return;
  const id = c.identity || {};
  await populateProfileAssignSelect(id.class, c.profile_dir_name);
  const currentLabel = availableProfilesCache.find((p) => p.dir_name === c.profile_dir_name);
  profileBannerText.textContent = c.has_profile
    ? `Current profile: ${currentLabel ? currentLabel.label : c.profile_dir_name}. Choose a different one below if she's respecced.`
    : "No sim profile assigned to this character yet.";
  profileAssignCancelBtn.hidden = !c.has_profile;
  profileBanner.hidden = false;
});

profileAssignCancelBtn.addEventListener("click", () => {
  profileBanner.hidden = true;
});

profileAssignBtn.addEventListener("click", async () => {
  if (!selectedNameRealm || !profileAssignSelect.value) return;
  profileAssignBtn.disabled = true;
  try {
    const result = await window.pywebview.api.assign_character_profile(selectedNameRealm, profileAssignSelect.value);
    if (result.ok) {
      showToast(`Profile assigned - ${selectedNameRealm} is ready to run.`);
      await loadCharacters();  // re-selects selectedNameRealm itself, now with has_profile:true
    } else {
      showToast(`Couldn't assign profile: ${result.error}`);
    }
  } finally {
    profileAssignBtn.disabled = false;
  }
});

function renderReports(reports, profileDirName) {
  // Backlog #13 - `reports` is now nested {profile_dir_name: {phase: {...}}}
  // (report_storage.py) so a character reassigned to a different sim
  // profile doesn't overwrite her prior spec's reports; only the currently
  // assigned profile's own branch is ever shown here - the loop below is
  // otherwise unchanged from before this change.
  const profileReports = (profileDirName && reports[profileDirName]) || {};
  reportsGrid.innerHTML = "";
  for (const phase of PHASES) {
    const r = profileReports[phase];
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
  settingsShowLowLevelToggle.checked = await window.pywebview.api.get_show_low_level_characters();

  const resolveIterations = await window.pywebview.api.get_resolve_iterations();
  settingsResolveIterationsInput.value = resolveIterations.value;

  const wowRoot = await window.pywebview.api.get_wow_root();
  settingsWowRoot.textContent = wowRoot.path + (wowRoot.is_configured ? "" : " (auto-detected)");

  settingsToolVersion.textContent = await window.pywebview.api.get_tool_version();

  await refreshAddonStatus();
  await refreshSimCredits();
  await refreshUpdateStatus();
}

// ---- Sim credits (real links from sim/tbc-new/README.md - see
// gui/api.py's get_sim_credits() docstring for why this exists) ----

async function refreshSimCredits() {
  const credits = await window.pywebview.api.get_sim_credits();
  creditsVersion.textContent = `(${credits.version_label})`;
  creditsVersion.title = credits.commit_sha;
}

// ---- Sim update check (against this repo's own GitHub Releases - see
// gui/api.py's check_for_sim_update() docstring; no release exists yet,
// since the scheduled update agent isn't running yet, so "no release
// published" is the real, honest, expected state today) ----

let lastUpdateCheck = null;

function describeUpdateStatus(r) {
  if (!r.checked) return `Check failed (${r.error}) - you're on ${r.current_version}`;
  if (r.update_available === true) return `Update available: ${r.latest_version} (you have ${r.current_version})`;
  if (r.update_available === null) return `Can't compare versions - you have ${r.current_version}, latest release is ${r.latest_version}`;
  if (r.latest_version) return `Up to date (${r.current_version})`;
  return r.note ? `${r.note} You're on ${r.current_version}.` : `You're on ${r.current_version}.`;
}

async function refreshUpdateStatus() {
  settingsUpdateStatus.textContent = "Checking…";
  const r = await window.pywebview.api.check_for_sim_update();
  lastUpdateCheck = r;
  settingsUpdateStatus.textContent = describeUpdateStatus(r);
  settingsUpdateViewBtn.hidden = !r.release_url;
  return r;
}

async function checkUpdateBanner() {
  if (updateBannerDismissed) return;
  const r = await window.pywebview.api.check_for_sim_update();
  lastUpdateCheck = r;
  if (r.update_available !== true) {
    updateBanner.hidden = true;
    return;
  }
  updateBannerText.textContent = `Sim update available: ${r.latest_version} (you have ${r.current_version}).`;
  updateBanner.hidden = false;
}

settingsUpdateCheckBtn.addEventListener("click", () => refreshUpdateStatus());

settingsUpdateViewBtn.addEventListener("click", () => {
  if (lastUpdateCheck && lastUpdateCheck.release_url) {
    window.pywebview.api.open_url(lastUpdateCheck.release_url);
  }
});

updateBannerViewBtn.addEventListener("click", () => {
  if (lastUpdateCheck && lastUpdateCheck.release_url) {
    window.pywebview.api.open_url(lastUpdateCheck.release_url);
  }
});

updateBannerDismissBtn.addEventListener("click", () => {
  updateBannerDismissed = true;
  updateBanner.hidden = true;
});

for (const link of [creditsGithubLink, creditsPatreonLink, creditsDiscordLink,
                     settingsAddonCurseforgeLink, addonBannerCurseforgeLink]) {
  link.addEventListener("click", (e) => {
    e.preventDefault();
    window.pywebview.api.open_url(link.href);
  });
}

// ---- Companion addon install (also on CurseForge as of 2026-08-31:
// https://www.curseforge.com/wow/addons/gt-companion - this tool still
// offers a direct one-click install too, see gui/api.py's own comment) ----

async function refreshAddonStatus() {
  const status = await window.pywebview.api.get_addon_status();
  const shippedV = status.shipped_version ? ` (v${status.shipped_version})` : "";
  const installedV = status.installed_version ? ` (v${status.installed_version})` : "";
  if (!status.installed) {
    settingsAddonStatus.textContent = `Not installed${shippedV ? " - latest is v" + status.shipped_version : ""}`;
    settingsAddonInstallBtn.textContent = "Install";
  } else if (status.up_to_date) {
    settingsAddonStatus.textContent = `Installed, up to date${installedV}`;
    settingsAddonInstallBtn.textContent = "Reinstall";
  } else {
    settingsAddonStatus.textContent = `Installed${installedV}, but out of date${shippedV ? " - latest is v" + status.shipped_version : ""}`;
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
    ? "A newer version of GearingToolCompanion is available."
    : "GearingToolCompanion isn't installed yet.";
  addonBanner.hidden = false;
}

settingsAddonInstallBtn.addEventListener("click", async () => {
  settingsAddonInstallBtn.disabled = true;
  try {
    const result = await window.pywebview.api.install_companion_addon();
    await refreshAddonStatus();
    await checkAddonBanner();
    showToast(result.success ? "GT Companion installed successfully." : `Install failed: ${result.error}`);
  } finally {
    settingsAddonInstallBtn.disabled = false;
  }
});

addonBannerInstallBtn.addEventListener("click", async () => {
  addonBannerInstallBtn.disabled = true;
  try {
    const result = await window.pywebview.api.install_companion_addon();
    await checkAddonBanner();
    showToast(result.success ? "GT Companion installed successfully." : `Install failed: ${result.error}`);
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

settingsShowLowLevelToggle.addEventListener("change", async () => {
  await window.pywebview.api.set_show_low_level_characters(settingsShowLowLevelToggle.checked);
  await loadCharacters();
});

settingsResolveIterationsSaveBtn.addEventListener("click", async () => {
  const n = parseInt(settingsResolveIterationsInput.value, 10);
  await window.pywebview.api.set_resolve_iterations(Number.isFinite(n) ? n : null);
  await refreshSettingsDisplay();
});

settingsResolveIterationsResetBtn.addEventListener("click", async () => {
  await window.pywebview.api.set_resolve_iterations(null);
  await refreshSettingsDisplay();
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
  runReportOomCheck.hidden = true;
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
  refreshDurationWarning();
  await refreshSourcesSummary();
  await refreshWeaveModeRow();
  await refreshPotionModeRow();
  openModal(runReportModal);
});

// Backlog #20 follow-up (2026-09-06) - only shown for a real weave-capable
// profile (Survival/Beastmastery Hunter). Per the user: default to Turret
// (matches this tool's own real, historical behavior for every existing
// report - nothing changes for an existing character unless they actually
// touch this), with a real, un-missable red warning next to it rather than
// silently assuming either playstyle - "we should not assume if the use is
// weaving or not."
async function refreshWeaveModeRow() {
  const c = characters.find((x) => x.name_realm === selectedNameRealm);
  const isWeaveCapable = c && WEAVE_CAPABLE_PROFILES.includes(c.profile_dir_name);
  runReportWeaveRow.hidden = !isWeaveCapable;
  runReportWeaveWarning.hidden = !isWeaveCapable;
  if (!isWeaveCapable) return;
  const current = await window.pywebview.api.get_melee_weave_mode(selectedNameRealm);
  runReportWeaveModeSelect.value = current.mode;
}

runReportWeaveModeSelect.addEventListener("change", async () => {
  if (!selectedNameRealm) return;
  await window.pywebview.api.set_melee_weave_mode(selectedNameRealm, runReportWeaveModeSelect.value);
});

// ---- Loot-source scope (backlog #5) ----

// Available sources shift with the selected Phase (e.g. Black Temple only
// exists at Phase 3+), so the summary label re-fetches whenever the phase
// changes, not just when the Run Report modal first opens.
runReportPhaseSelect.addEventListener("change", refreshSourcesSummary);

async function refreshSourcesSummary() {
  if (!selectedNameRealm || !runReportPhaseSelect.value) return;
  const sources = await window.pywebview.api.get_available_sources(selectedNameRealm, runReportPhaseSelect.value);
  const all = [...sources.zones, ...sources.crafts, ...sources.rep];
  const enabledCount = all.filter((s) => s.enabled).length;
  runReportSourcesSummary.textContent = all.length === 0
    ? "No sources found for this phase"
    : enabledCount === all.length
      ? `All ${all.length} sources included`
      : `${enabledCount} of ${all.length} sources included`;
}

function renderSourceScopeGroups(sources) {
  const groupDefs = [
    { key: "zones", title: "Raid & Dungeon Zones" },
    { key: "crafts", title: "Crafting Professions" },
    { key: "rep", title: "Reputation" },
  ];
  sourceScopeGroups.innerHTML = groupDefs
    .filter((g) => sources[g.key] && sources[g.key].length)
    .map((g) => {
      const items = sources[g.key].map((s) => `
        <label class="source-scope-item">
          <input type="checkbox" data-source-key="${escapeHtml(s.key)}" ${s.enabled ? "checked" : ""}>
          ${escapeHtml(s.label)}
        </label>
      `).join("");
      return `
        <div class="source-scope-group">
          <div class="source-scope-group-title">${escapeHtml(g.title)}</div>
          <div class="source-scope-grid">${items}</div>
        </div>
      `;
    }).join("");
}

runReportSourcesBtn.addEventListener("click", async () => {
  if (!selectedNameRealm || !runReportPhaseSelect.value) return;
  const sources = await window.pywebview.api.get_available_sources(selectedNameRealm, runReportPhaseSelect.value);
  renderSourceScopeGroups(sources);
  openModal(sourceScopeModal);
});

sourceScopeSelectAllBtn.addEventListener("click", () => {
  sourceScopeGroups.querySelectorAll("input[type=checkbox]").forEach((cb) => { cb.checked = true; });
});
sourceScopeSelectNoneBtn.addEventListener("click", () => {
  sourceScopeGroups.querySelectorAll("input[type=checkbox]").forEach((cb) => { cb.checked = false; });
});

sourceScopeCancelBtn.addEventListener("click", () => {
  closeModal(sourceScopeModal);
});

sourceScopeSaveBtn.addEventListener("click", async () => {
  const excluded = Array.from(sourceScopeGroups.querySelectorAll("input[type=checkbox]"))
    .filter((cb) => !cb.checked)
    .map((cb) => cb.dataset.sourceKey);
  await window.pywebview.api.set_source_scope_exclusions(selectedNameRealm, excluded);
  closeModal(sourceScopeModal);
  await refreshSourcesSummary();
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
    // run (see run_upgrade_sweep.py's own stage_sequence) - not shown at
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
          const c = characters.find((x) => x.name_realm === st.name_realm);
          renderReports(reports, c && c.profile_dir_name);
        }
      }
    }
  }, 1500);
}

// Real, actual "kick off the sweep" step - split out from the Run button's
// own click handler (below) so both the plain path (no OOM issue) and the
// two OOM-decision-panel buttons can reach it without duplicating logic.
async function startRunReport(phase, duration) {
  const res = await window.pywebview.api.run_report(selectedNameRealm, phase, duration);
  if (!res.started) {
    runReportStartBtn.disabled = false;
    runReportOomCheck.hidden = true;
    runReportForm.hidden = false;
    runReportError.hidden = false;
    runReportError.textContent = res.error;
    return;
  }

  runReportOomCheck.hidden = true;
  runReportForm.hidden = true;
  runReportProgress.hidden = false;
  runReportStartedAt = Date.now();
  pollRunStatus();
}

runReportStartBtn.addEventListener("click", async () => {
  const phase = runReportPhaseSelect.value;
  runReportStartBtn.disabled = true;
  runReportError.hidden = true;

  const duration = parseInt(runReportDurationInput.value, 10) || 180;
  if (!runReportWeaveRow.hidden) {
    await window.pywebview.api.set_melee_weave_mode(selectedNameRealm, runReportWeaveModeSelect.value);
  }
  if (!runReportPotionRow.hidden) {
    await window.pywebview.api.set_potion_choice(selectedNameRealm, parseInt(runReportPotionModeSelect.value, 10));
  }

  // Real, cheap pre-sweep OOM check (2026-09-06) - see core/oom_check.py's
  // own docstring. Never blocks Run silently - if flagged, hands the user a
  // real choice (shorter duration vs. run anyway) instead of quietly
  // producing a skewed report; part 2's real baseline OOM readout still
  // ends up in the delivered report either way, so the caveat is never
  // lost even on override.
  const oom = await window.pywebview.api.check_oom(selectedNameRealm, phase, duration);
  if (oom.flagged) {
    runReportForm.hidden = true;
    runReportOomCheck.hidden = false;
    const pct = (oom.oom_fraction * 100).toFixed(1);
    runReportOomText.textContent = `At ${duration}s, this character is out of mana for ` +
      `${oom.oom_seconds.toFixed(1)}s (${pct}%) of the fight - mana/spirit item values would be ` +
      "skewed by this.";
    if (oom.recommended_duration != null) {
      runReportOomUseRecommendedBtn.hidden = false;
      runReportOomUseRecommendedBtn.textContent = `Use ${oom.recommended_duration}s instead`;
      runReportOomUseRecommendedBtn.onclick = () => {
        runReportDurationInput.value = oom.recommended_duration;
        refreshDurationWarning();
        startRunReport(phase, oom.recommended_duration);
      };
    } else {
      runReportOomUseRecommendedBtn.hidden = true;
    }
    runReportOomRunAnywayBtn.textContent = `Run at ${duration}s anyway`;
    runReportOomRunAnywayBtn.onclick = () => startRunReport(phase, duration);
    return;
  }

  await startRunReport(phase, duration);
});

async function init() {
  PHASES = await window.pywebview.api.get_supported_phases();
  await loadCharacters();
  await checkAddonBanner();
  await checkUpdateBanner();
}

window.addEventListener("pywebviewready", init);
