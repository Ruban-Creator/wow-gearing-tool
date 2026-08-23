// simserver: a persistent version of `wowsimcli sim`. The CLI reloads and
// unmarshals the whole embedded item DB (db.bin, ~2.3MB protobuf) fresh on
// every single invocation - fine for one-off runs, wasteful for a pipeline
// making hundreds of calls (the MV report / optimizer). This loads once and
// serves many requests over its lifetime: one line of RaidSimRequest
// protojson in on stdin, one line of RaidSimResult protojson out on stdout,
// per request. Mirrors cmd/wowsimcli/cmd/basic_sim.go's actual call path
// (core.RunRaidSimConcurrentAsync) exactly - not a reimplementation.
//
// Also serves ComputeStatsRequest/-Result on the same stdin/stdout line
// protocol (see NOTES.md, "Root cause found: raid AP contribution column
// still isn't wired in" - RaidSimResult carries no stat breakdown at all;
// getting a config's Agility for expose_weakness.go needs this separate
// RPC, core.ComputeStats, which nothing in this pipeline called before).
// Request lines are routed by shape: a RaidSimRequest always carries
// simOptions, a ComputeStatsRequest never does - cheap enough to check
// without a wire-format change, and it leaves runOne/the RaidSim path
// (every DPS number this tool has ever produced) completely untouched.
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"

	"github.com/wowsims/tbc/sim"
	"github.com/wowsims/tbc/sim/core"
	"github.com/wowsims/tbc/sim/core/proto"
	"google.golang.org/protobuf/encoding/protojson"
	protoiface "google.golang.org/protobuf/proto"
)

func init() {
	sim.RegisterAll()
}

func main() {
	reader := bufio.NewReaderSize(os.Stdin, 1024*1024)
	writer := bufio.NewWriter(os.Stdout)
	defer writer.Flush()

	fmt.Fprintln(os.Stderr, "simserver: ready")

	for {
		line, err := reader.ReadString('\n')
		if len(line) == 0 && err != nil {
			break // EOF, nothing left to process
		}

		var msg protoiface.Message
		if isRaidSimRequest(line) {
			msg = runOne(line)
		} else {
			msg = runComputeStats(line)
		}
		out, marshalErr := protojson.MarshalOptions{EmitUnpopulated: true}.Marshal(msg)
		if marshalErr != nil {
			fmt.Fprintf(os.Stderr, "simserver: marshal error: %v\n", marshalErr)
			continue
		}
		writer.Write(out)
		writer.WriteByte('\n')
		writer.Flush()

		if err != nil {
			break // ReadString returned the last line plus EOF
		}
	}
}

func isRaidSimRequest(line string) bool {
	var probe struct {
		SimOptions json.RawMessage `json:"simOptions"`
	}
	// A parse failure here just falls through to runComputeStats, which
	// will itself fail to unmarshal and report the real error - no need
	// to duplicate error handling for a malformed line in two places.
	_ = json.Unmarshal([]byte(line), &probe)
	return probe.SimOptions != nil
}

func runComputeStats(line string) *proto.ComputeStatsResult {
	input := &proto.ComputeStatsRequest{}
	if err := (protojson.UnmarshalOptions{DiscardUnknown: true}).Unmarshal([]byte(line), input); err != nil {
		return &proto.ComputeStatsResult{ErrorResult: "unmarshal request: " + err.Error()}
	}
	return core.ComputeStats(input)
}

func runOne(line string) *proto.RaidSimResult {
	input := &proto.RaidSimRequest{}
	if err := (protojson.UnmarshalOptions{DiscardUnknown: true}).Unmarshal([]byte(line), input); err != nil {
		return &proto.RaidSimResult{Error: &proto.ErrorOutcome{
			Type: proto.ErrorOutcomeType_ErrorOutcomeError, Message: "unmarshal request: " + err.Error(),
		}}
	}
	if input.SimOptions == nil {
		return &proto.RaidSimResult{Error: &proto.ErrorOutcome{
			Type: proto.ErrorOutcomeType_ErrorOutcomeError, Message: "missing simOptions",
		}}
	}

	reporter := make(chan *proto.ProgressMetrics, 10)
	core.RunRaidSimConcurrentAsync(input, reporter, "simserver")

	for v := range reporter {
		if v.FinalRaidResult != nil {
			return v.FinalRaidResult
		}
	}
	return &proto.RaidSimResult{Error: &proto.ErrorOutcome{
		Type: proto.ErrorOutcomeType_ErrorOutcomeError, Message: "no final result received",
	}}
}
