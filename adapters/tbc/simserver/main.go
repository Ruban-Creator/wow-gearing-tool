// simserver: a persistent version of `wowsimcli sim`. The CLI reloads and
// unmarshals the whole embedded item DB (db.bin, ~2.3MB protobuf) fresh on
// every single invocation - fine for one-off runs, wasteful for a pipeline
// making hundreds of calls (the MV report / optimizer). This loads once and
// serves many requests over its lifetime: one line of RaidSimRequest
// protojson in on stdin, one line of RaidSimResult protojson out on stdout,
// per request. Mirrors cmd/wowsimcli/cmd/basic_sim.go's actual call path
// (core.RunRaidSimConcurrentAsync) exactly - not a reimplementation.
package main

import (
	"bufio"
	"fmt"
	"os"

	"github.com/wowsims/tbc/sim"
	"github.com/wowsims/tbc/sim/core"
	"github.com/wowsims/tbc/sim/core/proto"
	"google.golang.org/protobuf/encoding/protojson"
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

		result := runOne(line)
		out, marshalErr := protojson.MarshalOptions{EmitUnpopulated: true}.Marshal(result)
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
