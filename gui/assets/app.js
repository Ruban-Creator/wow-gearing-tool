const PHASES = ["phase2", "phase3", "phase4", "phase5"];
const PHASE_LABELS = { phase2: "Phase 2", phase3: "Phase 3", phase4: "Phase 4", phase5: "Phase 5" };

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

const charListEl = document.getElementById("char-list");
const refreshBtn = document.getElementById("refresh-btn");
const detailEmpty = document.getElementById("detail-empty");
const detailContent = document.getElementById("detail-content");
const detailName = document.getElementById("detail-name");
const detailMeta = document.getElementById("detail-meta");
const profileBanner = document.getElementById("profile-banner");
const reportsGrid = document.getElementById("reports-grid");

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

window.addEventListener("pywebviewready", loadCharacters);
