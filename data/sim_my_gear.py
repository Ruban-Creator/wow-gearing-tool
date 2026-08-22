"""One-off: substitute Lerynia's real equipped gear/race/talents/professions
into the phase_3 SV BiS preset template (same buffs/debuffs/consumables/
encounter/rotation as the Stage 1 baseline, for direct comparability), run
through the adapter, and report DPS. NOT `gear best` - no optimization, no
ranking, just "what does my currently-equipped set do under the same
conditions as the baseline preset."
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "adapters", "tbc"))
import adapter  # noqa: E402

RACE_MAP = {"NightElf": "RaceNightElf"}

char = json.load(open(os.path.join(REPO_ROOT, "data", "character.json"), encoding="utf-8"))
template = json.load(open(
    os.path.join(REPO_ROOT, "sim", "tbc-new", "ui", "hunter", "dps", "builds", "phase_3", "sv", "2h_9p.build.json"),
    encoding="utf-8",
))

p = template["player"]
p["race"] = RACE_MAP[char["character"]["race"]]
p["equipment"]["items"] = [
    {k: v for k, v in it.items() if k != "name"} for it in char["equipped"]["items"]
]
p["talentsString"] = char["character"]["talents"]
profs = [pr["name"] for pr in char["character"]["professions"]]
p["profession1"] = profs[0] if len(profs) > 0 else "ProfessionUnknown"
p["profession2"] = profs[1] if len(profs) > 1 else "ProfessionUnknown"

out_path = os.path.join(REPO_ROOT, "data", "cache", "my_gear_settings.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(template, f, indent=2)

result = adapter.run(out_path, iterations=10000, seed=1)
dps = adapter.player_and_pet_dps(result)
total_pet = sum(pt["avg"] for pt in dps["pets"])
print(f"player DPS: {dps['player']['avg']:.1f} (stdev {dps['player']['stdev']:.2f})")
for pt in dps["pets"]:
    print(f"pet {pt['name']} DPS: {pt['avg']:.1f} (stdev {pt['stdev']:.2f})")
print(f"combined: {dps['player']['avg'] + total_pet:.1f}")
