// bridge expands an IndividualSimSettings protojson document (the same shape
// as the repo's .build.json presets, and what individual_cli_exporter.tsx
// produces from the web UI) into a RaidSimRequest protojson document (what
// `wowsimcli sim --infile` actually consumes). There is no Go-side function
// upstream that does this - it's TypeScript-only (ui/core/sim.ts,
// makeRaidSimRequest); this mirrors it field-for-field. See NOTES.md in the
// repo root ("Resolved: the CLI's actual input contract") for the mapping
// this was derived from.
package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/wowsims/tbc/sim/core/proto"
	"google.golang.org/protobuf/encoding/protojson"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "bridge:", err)
		os.Exit(1)
	}
}

func run() error {
	inPath := flag.String("in", "", "path to IndividualSimSettings protojson (required)")
	outPath := flag.String("out", "", "path to write RaidSimRequest protojson (default stdout)")
	iterations := flag.Int("iterations", 0, "override sim_options.iterations (0 = keep the input settings' value)")
	seed := flag.Int64("seed", 0, "override sim_options.random_seed (required unless -keep-seed is set)")
	keepSeed := flag.Bool("keep-seed", false, "use the input settings' own seed instead of -seed")
	flag.Parse()

	if *inPath == "" {
		return fmt.Errorf("-in is required")
	}
	if !*keepSeed && *seed == 0 {
		return fmt.Errorf("-seed is required (pass -keep-seed to use the input file's seed instead, e.g. 0 meaning \"random\" - avoid that for determinism)")
	}

	raw, err := os.ReadFile(*inPath)
	if err != nil {
		return fmt.Errorf("reading %s: %w", *inPath, err)
	}

	settings := &proto.IndividualSimSettings{}
	if err := protojson.Unmarshal(raw, settings); err != nil {
		return fmt.Errorf("unmarshal IndividualSimSettings: %w", err)
	}

	player := settings.GetPlayer()
	if player == nil {
		return fmt.Errorf("input has no player")
	}
	// Mirrors individual_cli_exporter.tsx: `delete raidSimJson.raid.parties[0].players[0].database`.
	// The CLI has the full item DB embedded (--tags=with_db); a per-player database blob is
	// only needed by DB-less web builds and isn't expected here.
	player.Database = nil

	padUnitStats(player.GetBonusStats())
	padUnitStats(player.GetItemSwap().GetPrepullBonusStats())

	party := &proto.Party{
		Players: []*proto.Player{player},
		Buffs:   settings.GetPartyBuffs(),
	}
	raid := &proto.Raid{
		Parties: []*proto.Party{party},
		Buffs:   settings.GetRaidBuffs(),
		Debuffs: settings.GetDebuffs(),
		Tanks:   settings.GetTanks(),
	}

	iters := settings.GetSettings().GetIterations()
	if *iterations != 0 {
		iters = int32(*iterations)
	}
	randomSeed := settings.GetSettings().GetFixedRngSeed()
	if !*keepSeed {
		randomSeed = *seed
	}

	req := &proto.RaidSimRequest{
		Raid:      raid,
		Encounter: settings.GetEncounter(),
		SimOptions: &proto.SimOptions{
			Iterations:          iters,
			RandomSeed:          randomSeed,
			DebugFirstIteration: true,
		},
		Type: proto.SimType_SimTypeIndividual,
	}

	out, err := protojson.MarshalOptions{UseProtoNames: false}.Marshal(req)
	if err != nil {
		return fmt.Errorf("marshal RaidSimRequest: %w", err)
	}

	if *outPath == "" {
		_, err = os.Stdout.Write(out)
		return err
	}
	return os.WriteFile(*outPath, out, 0o644)
}

// padUnitStats zero-pads Stats/PseudoStats to the current length of the
// proto.Stat/PseudoStat enums. Some shipped .gear.json/.build.json presets
// predate a PseudoStat enum addition and ship a too-short array (observed:
// 26 elements vs. the current 27 PseudoStat values), which panics
// core.NewCharacter with an index-out-of-range on the missing slot. Zero is
// always the semantically correct value for a stat the preset predates, so
// padding is safe - this never invents a nonzero bonus.
func padUnitStats(us *proto.UnitStats) {
	if us == nil {
		return
	}
	if want := len(proto.Stat_name); len(us.Stats) < want {
		fmt.Fprintf(os.Stderr, "bridge: padding UnitStats.stats %d -> %d\n", len(us.Stats), want)
		us.Stats = append(us.Stats, make([]float64, want-len(us.Stats))...)
	}
	if want := len(proto.PseudoStat_name); len(us.PseudoStats) < want {
		fmt.Fprintf(os.Stderr, "bridge: padding UnitStats.pseudoStats %d -> %d\n", len(us.PseudoStats), want)
		us.PseudoStats = append(us.PseudoStats, make([]float64, want-len(us.PseudoStats))...)
	}
}
