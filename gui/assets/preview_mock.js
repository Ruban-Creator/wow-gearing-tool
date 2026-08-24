// TEST-ONLY: mocks window.pywebview.api with real data captured from a live
// Api() call, so the UI can be visually previewed in a normal browser without
// a running pywebview backend. Not loaded by index.html / the real app -
// referenced only from a separate preview harness. Delete once visual
// verification is done, or keep for future quick iteration - not shipped.
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
  }
};
setTimeout(() => window.dispatchEvent(new Event("pywebviewready")), 50);
