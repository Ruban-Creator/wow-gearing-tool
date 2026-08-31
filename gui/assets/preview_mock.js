// TEST-ONLY: mocks window.pywebview.api with real data captured from a live
// Api() call, so the UI can be visually previewed in a normal browser without
// a running pywebview backend. Not loaded by index.html / the real app -
// referenced only from a separate preview harness. Delete once visual
// verification is done, or keep for future quick iteration - not shipped.
let mockAddonInstalled = false; // flip to true to preview the "up to date" / no-banner state
let mockUpdateAvailable = true; // flip to false to preview the "up to date" / no-banner state
let mockResolveIterations = null; // null = default (30000), matches local_config's override-or-default shape

// Backlog #5 - representative multi-category fake data, real TBC zone/phase
// mapping (see core/source_scope.py's own real DB-derived table) so the
// preview demonstrates the "shifts with phase" behavior honestly.
let mockSourceExclusions = new Set();
const MOCK_ZONES_BY_PHASE = {
  1: ["Karazhan", "Gruul's Lair", "Magtheridon's Lair", "Hellfire Ramparts"],
  2: ["Serpentshrine Cavern", "Tempest Keep"],
  3: ["Hyjal Summit", "Black Temple"],
  4: ["Zul'Aman"],
  5: ["Sunwell Plateau", "Magisters' Terrace"],
};
function mockZonesUpToPhase(phaseNum) {
  const zones = [];
  for (let p = 1; p <= phaseNum; p++) zones.push(...(MOCK_ZONES_BY_PHASE[p] || []));
  return zones;
}

const MOCK_CHARACTERS_BASE = [
  {
    name_realm: "Béarforceone-Thunderstrike", source_used: "wse",
    identity: { name: "Béarforceone", realm: "Thunderstrike", race: "NightElf", class: "druid", level: 70, spec: "balance",
      professions: [{ name: "Enchanting", level: 355 }, { name: "Engineering", level: 375 }] },
    wse_timestamp: 1787174482, gt_timestamp: null, has_wse: true, has_gtcompanion: false,
  },
  {
    name_realm: "Lerynia-Thunderstrike", source_used: "wse",
    identity: { name: "Lerynia", realm: "Thunderstrike", race: "NightElf", class: "hunter", level: 70, spec: "survival",
      professions: [{ name: "Herbalism", level: 375 }, { name: "Mining", level: 375 }] },
    wse_timestamp: 1787512875, gt_timestamp: 1787512999, has_wse: true, has_gtcompanion: true,
  },
  {
    name_realm: "Rubán-Thunderstrike", source_used: "wse",
    identity: { name: "Rubán", realm: "Thunderstrike", race: "Human", class: "warrior", level: 70, spec: "arms",
      professions: [{ name: "Blacksmithing", level: 375 }, { name: "Mining", level: 375 }] },
    wse_timestamp: 1787517345, gt_timestamp: 1787517350, has_wse: true, has_gtcompanion: true,
  },
  {
    name_realm: "FreshAlt-Thunderstrike", source_used: "gtcompanion",
    identity: {}, wse_timestamp: null, gt_timestamp: 1787578000, has_wse: false, has_gtcompanion: true,
  },
];
// Stateful, per the same pattern as mockAddonInstalled/mockResolveIterations
// above - so the "Change profile…" flow (backlog, 2026-08-31: a respec, e.g.
// Elemental -> Enhancement, needs a real way back into the assign UI) is
// actually demonstrable in the no-backend preview harness, not just static.
const mockProfileAssignments = { "Lerynia-Thunderstrike": "survival_hunter" };

window.pywebview = {
  api: {
    list_characters: async () => MOCK_CHARACTERS_BASE.map((c) => ({
      ...c,
      has_profile: Object.prototype.hasOwnProperty.call(mockProfileAssignments, c.name_realm),
      profile_dir_name: mockProfileAssignments[c.name_realm] || null,
    })),
    get_reports: async (nameRealm) => {
      if (nameRealm === "Lerynia-Thunderstrike") {
        return {
          phase3: { artifact_url: "https://claude.ai/code/artifact/81e5b616-0d28-45a5-a257-786b7774e810",
            generated_at: "2026-08-24T13:32:16.870611+00:00", notes: "Phase 3 Upgrade Ledger" }
        };
      }
      return {};
    },
    open_url: async (url) => { console.log("open_url:", url); },
    get_supported_phases: async () => (["phase1", "phase2", "phase3", "phase4", "phase5"]),
    get_debug_mode: async () => false,
    set_debug_mode: async (enabled) => enabled,
    get_resolve_iterations: async () => ({
      value: mockResolveIterations ?? 30000, default: 30000, is_configured: mockResolveIterations !== null
    }),
    set_resolve_iterations: async (n) => {
      mockResolveIterations = (n !== null && n !== undefined && n > 0) ? Math.max(1000, n) : null;
      return { value: mockResolveIterations ?? 30000, default: 30000, is_configured: mockResolveIterations !== null };
    },
    get_report_output_dir: async () => ({ path: "%LOCALAPPDATA%\\GearingTool\\characters\\<character>\\reports", is_configured: false }),
    pick_report_folder: async () => null,
    reset_report_output_dir: async () => {},
    get_wow_root: async () => ({ path: "C:\\Games\\World of Warcraft\\_anniversary_", is_configured: false }),
    pick_wow_root_folder: async () => null,
    reset_wow_root: async () => {},
    get_run_status: async () => ({ active: false, done: false, error: null }),
    run_report: async () => ({ started: true }),
    get_available_sources: async (nameRealm, phase) => {
      const phaseNum = parseInt(phase.replace("phase", ""), 10) || 3;
      const zones = mockZonesUpToPhase(phaseNum).map((name, i) => {
        const key = `zone:${1000 + i}`;
        return { key, label: name, enabled: !mockSourceExclusions.has(key) };
      });
      const crafts = ["Blacksmithing", "Leatherworking", "Tailoring", "Engineering"].map((name, i) => {
        const key = `craft:${i + 1}`;
        return { key, label: name, enabled: !mockSourceExclusions.has(key) };
      });
      const rep = [{ key: "rep", label: "Reputation rewards", enabled: !mockSourceExclusions.has("rep") }];
      return { zones, crafts, rep };
    },
    set_source_scope_exclusions: async (nameRealm, excludedKeys) => {
      mockSourceExclusions = new Set(excludedKeys);
      return { saved: true };
    },
    get_available_profiles: async () => ([
      { dir_name: "survival_hunter", label: "Survival Hunter", class: "hunter" },
      { dir_name: "beastmastery_hunter", label: "Beastmastery Hunter", class: "hunter" },
      { dir_name: "arms_warrior", label: "Arms Warrior", class: "warrior" },
      { dir_name: "fury_warrior", label: "Fury Warrior", class: "warrior" },
      { dir_name: "balance_druid", label: "Balance Druid", class: "druid" },
    ]),
    assign_character_profile: async (nameRealm, dirName) => {
      mockProfileAssignments[nameRealm] = dirName;
      return { ok: true, has_profile: true };
    },
    get_addon_status: async () => ({
      install_path: "C:\\Games\\World of Warcraft\\_anniversary_\\Interface\\AddOns\\GearingToolCompanion",
      installed: mockAddonInstalled,
      up_to_date: mockAddonInstalled,
      shipped_version: "1.0.0",
      installed_version: mockAddonInstalled ? "1.0.0" : null,
    }),
    install_companion_addon: async () => {
      mockAddonInstalled = true;
      return { success: true, error: null, install_path: "C:\\Games\\World of Warcraft\\_anniversary_\\Interface\\AddOns\\GearingToolCompanion" };
    },
    get_sim_credits: async () => ({
      version_label: "v0.0.124",
      commit_sha: "7963eeac179ecbc61dce4e40be945e8fe0fd2204",
      github_url: "https://github.com/wowsims/tbc-new",
      patreon_url: "https://www.patreon.com/wowsims",
      discord_url: "https://discord.gg/jJMPr9JWwx",
    }),
    check_for_sim_update: async () => (mockUpdateAvailable ? {
      checked: true, error: null, current_version: "v0.0.124", latest_version: "v0.0.125",
      update_available: true, release_url: "https://github.com/Ruban-Creator/wow-gearing-tool/releases/tag/v0.0.125",
    } : {
      checked: true, error: null, current_version: "v0.0.124", latest_version: null,
      update_available: false, release_url: null, note: "No release has been published yet.",
    }),
  }
};
setTimeout(() => window.dispatchEvent(new Event("pywebviewready")), 50);
