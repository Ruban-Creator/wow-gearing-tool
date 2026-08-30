# Build Output

Everything under here is compiled/generated, gitignored, and safe to delete and regenerate at
any time - nothing here is a source of truth for anything. See `CLAUDE.md`'s "Repo layout"
section for how this bucket fits alongside The Tool / The Sim we downloaded / The Data we have /
Production Data.

```
build/bin/    wowsimcli.exe, bridge.exe, simserver.exe - Go binaries the Python tool calls as
              subprocesses at runtime. Rebuild via the commands in CLAUDE.md's "Local setup"
              section (each `go build -o ../../build/bin/<name>.exe .`, run from that binary's
              own source directory - sim/tbc-new/ for wowsimcli, adapters/tbc/bridge/ for bridge,
              adapters/tbc/simserver/ for simserver).
build/bin/sim_commit_sha.txt   The sim submodule's commit SHA, baked at build time. Real fallback
              for core/repo_root.py's sim_commit_sha() when a live `git rev-parse` isn't possible
              (a packaged install has no `.git`) - see CLAUDE.md's Local Setup section for the
              one-line command that writes it. Not needed for dev-machine use (the live git call
              always wins when it's available) but keep it current before packaging.
build/dist/   gearing-tool-gui.exe - PyInstaller's final packaged output. Rebuild via
              packaging/README.md's Build section.
```

`build/_pyinstaller_work/`, if present, is PyInstaller's own intermediate work directory
(`--workpath`) - never inspect or rely on its contents, it's not part of either bucket above.

Nothing under here except this README is ever committed (`.gitignore`'s `build/*` +
`!build/README.md`) - an installer or a fresh build script is expected to populate this directory
from source before the app can actually run.
