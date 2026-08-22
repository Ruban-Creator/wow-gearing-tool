module github.com/lastknight90/gearing-tool/bridge

go 1.25.0

require (
	github.com/wowsims/tbc v0.0.0-00010101000000-000000000000
	google.golang.org/protobuf v1.36.12
)

replace github.com/wowsims/tbc => ../../../sim/tbc-new
