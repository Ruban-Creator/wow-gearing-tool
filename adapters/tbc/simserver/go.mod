module github.com/lastknight90/gearing-tool/simserver

go 1.25.0

require (
	github.com/wowsims/tbc v0.0.0-00010101000000-000000000000
	google.golang.org/protobuf v1.36.12
)

require golang.org/x/exp v0.0.0-20250408133849-7e4ce0ab07d0 // indirect

replace github.com/wowsims/tbc => ../../../sim/tbc-new
