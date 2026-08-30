// TEST-ONLY: mocks window.pywebview.api with real data captured from a live
// Api() call, so the UI can be visually previewed in a normal browser without
// a running pywebview backend. Not loaded by index.html / the real app -
// referenced only from a separate preview harness. Delete once visual
// verification is done, or keep for future quick iteration - not shipped.
let mockAddonInstalled = false; // flip to true to preview the "up to date" / no-banner state

window.pywebview = {
  api: {
    list_characters: async () => ([
      {
        name_realm: "Béarforceone-Thunderstrike", source_used: "wse",
        identity: { name: "Béarforceone", realm: "Thunderstrike", race: "NightElf", class: "druid", level: 70, spec: "balance",
          professions: [{ name: "Enchanting", level: 355 }, { name: "Engineering", level: 375 }] },
        wse_timestamp: 1787174482, gt_timestamp: null, has_wse: true, has_gtcompanion: false, has_profile: false
      },
      {
        name_realm: "Lerynia-Thunderstrike", source_used: "wse",
        identity: { name: "Lerynia", realm: "Thunderstrike", race: "NightElf", class: "hunter", level: 70, spec: "survival",
          professions: [{ name: "Herbalism", level: 375 }, { name: "Mining", level: 375 }] },
        wse_timestamp: 1787512875, gt_timestamp: 1787512999, has_wse: true, has_gtcompanion: true, has_profile: true
      },
      {
        name_realm: "Rubán-Thunderstrike", source_used: "wse",
        identity: { name: "Rubán", realm: "Thunderstrike", race: "Human", class: "warrior", level: 70, spec: "arms",
          professions: [{ name: "Blacksmithing", level: 375 }, { name: "Mining", level: 375 }] },
        wse_timestamp: 1787517345, gt_timestamp: 1787517350, has_wse: true, has_gtcompanion: true, has_profile: false
      },
      {
        name_realm: "FreshAlt-Thunderstrike", source_used: "gtcompanion",
        identity: {}, wse_timestamp: null, gt_timestamp: 1787578000, has_wse: false, has_gtcompanion: true, has_profile: false
      },
    ]),
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
    get_report_output_dir: async () => ({ path: "C:\\Users\\Matthias\\AppData\\Local\\GearingTool\\characters\\<character>\\reports", is_configured: false }),
    pick_report_folder: async () => null,
    reset_report_output_dir: async () => {},
    get_wow_root: async () => ({ path: "C:\\Games\\World of Warcraft\\_anniversary_", is_configured: false }),
    pick_wow_root_folder: async () => null,
    reset_wow_root: async () => {},
    get_run_status: async () => ({ active: false, done: false, error: null }),
    run_report: async () => ({ started: true }),
    get_addon_status: async () => ({
      install_path: "C:\\Games\\World of Warcraft\\_anniversary_\\Interface\\AddOns\\GearingToolCompanion",
      installed: mockAddonInstalled,
      up_to_date: mockAddonInstalled,
    }),
    install_companion_addon: async () => {
      mockAddonInstalled = true;
      return { success: true, error: null, install_path: "C:\\Games\\World of Warcraft\\_anniversary_\\Interface\\AddOns\\GearingToolCompanion" };
    },
    get_sim_credits: async () => ({
      version_label: "v0.0.119",
      commit_sha: "3267f8dfa4a20746d4982c1522fdec1d4eb77f4c",
      github_url: "https://github.com/wowsims/tbc-new",
      patreon_url: "https://www.patreon.com/wowsims",
      discord_url: "https://discord.gg/jJMPr9JWwx",
    }),
  }
};
setTimeout(() => window.dispatchEvent(new Event("pywebviewready")), 50);
