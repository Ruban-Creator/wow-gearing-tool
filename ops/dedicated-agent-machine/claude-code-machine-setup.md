---
title: Dedicated Sim-Update Machines — Setup Guide
machines: "Watcher: Dell OptiPlex 3050 Micro (i5-7500T, 16 GB RAM, 512 GB NVMe), Ubuntu Server 26.04.1 LTS. Verifier: Windows 11 Pro, minimal install."
---

# Dedicated Sim-Update Machines

Two machines, two real jobs, for `wow-gearing-tool` backlog #14 (a daily agent that checks
`wowsims/tbc-new` for a new version and runs `CLAUDE.md`'s "Sim update procedure" runbook
end-to-end). Split into two machines, not one, because of a real constraint found while scoping
this (2026-09-06): a Linux machine can happily *build* the sim's Windows binaries via Go's
cross-compilation (`GOOS=windows GOARCH=amd64 go build` produces a real, genuine `.exe`, no
Windows needed for that step) - but it can't *run* one to actually verify it works, since a
`.exe` needs a real Windows environment to execute, and the runbook's whole point at that stage is
running real sim calls, not just confirming the code compiles.

- **Watcher (Linux, already built - see Part 1 below)**: runs daily, unattended. Checks for a new
  tag, does the real risk-assessing `git diff`, bumps the submodule, cross-compiles the new
  binaries as a cheap "does it even build" pre-flight check, and pushes the bump to a staging
  branch (`sim-update-pending`) rather than `master` - it never verifies or merges anything itself.
- **Verifier (Windows, this session's addition - see Part 2 below)**: triggered after the Watcher
  pushes a staging branch. Pulls it, rebuilds all three binaries natively (the exact commands
  `CLAUDE.md`'s own "Local setup" section already documents - nothing new to invent here), runs
  the runbook's real verification steps (live sim calls, `check_ledger_consistency.py` across all
  15 profiles), and only on a clean pass merges the staging branch into `master` and pushes.
  Nothing gets committed to `master` without something actually running the new binaries first.

No GUI is needed on either machine for any of this - every step here is a command-line tool
(`wowsimcli.exe`/`bridge.exe`/`simserver.exe` are console programs, the verification scripts are
plain Python, git is git). "Windows" here means "an environment that can execute a `.exe`," not
"a desktop anyone sits at."

## Part 1 — Watcher (Linux)

Setup guide — Dell OptiPlex 3050 Micro  ·  Ubuntu Server 26.04 LTS

|                  |                                                                            |
|------------------|----------------------------------------------------------------------------|
| Hardware         | Dell OptiPlex 3050 Micro — Intel Core i5-7500T, 16 GB RAM, 512 GB NVMe SSD |
| Operating system | Ubuntu Server 26.04.1 LTS (headless, supported to April 2031)              |
| Access           | SSH from your laptop; no monitor or keyboard after installation            |
| Boot keys        | F2 = BIOS setup  ·  F12 = boot menu                                        |

Claude Code's work happens on Anthropic's servers, so this machine only needs to run a terminal, git, your toolchains, and your test suite. The published requirement is 4 GB RAM and an x64 processor, which this comfortably exceeds. Ubuntu Server rather than Desktop keeps idle memory use around 1 GB instead of 4 GB or more.

**Micro chassis notes.** This model has no PCIe slot, so a graphics card is not an option — that's fine, since nothing in this guide needs one. Memory is SODIMM across two slots, maximum 32 GB. Idle draw is roughly 15 W, which makes leaving it running permanently effectively free.

### Phase 0 — BIOS and hardware preparation

Do this before touching the installer. Power on and press `F2`.

1.  **Set SATA Operation to AHCI.** These machines very often ship set to `RAID On`, and the Ubuntu installer will then show no disks whatsoever. This is by far the most common way this install goes wrong.
2.  **Power Management → AC Recovery → Power On.** The machine then comes back by itself after a power cut, which matters for a box you rely on being reachable.
3.  **Disable Deep Sleep Control.** Deep Sleep prevents Wake-on-LAN and remote power-on from working.
4.  **Enable Wake-on-LAN** if you want to be able to wake it remotely. Optional.
5.  **Leave Secure Boot enabled.** Ubuntu handles it without any special steps.
6.  **Update the BIOS** while you still have a screen attached. Download the latest `.exe` from Dell's OptiPlex 3050 support page, copy it to a FAT32 USB stick, then press `F12` at boot and choose *BIOS Flash Update*. No operating system required.

### Phase 1 — Install Ubuntu Server

1.  Download **Ubuntu Server 26.04.1 LTS** — the server ISO, not Desktop — from `ubuntu.com/download/server`.

2.  Write it to a USB stick. Rufus on Windows, or on Linux:

        sudo dd if=ubuntu-26.04.1-live-server-amd64.iso of=/dev/sdX bs=4M status=progress conv=fsync

3.  Boot the machine, press `F12`, select the USB stick.

4.  Work through the installer:
    - **Network:** accept DHCP, then afterwards set a *DHCP reservation on your router* so the address never changes. Simpler and more robust than configuring a static address on the host.
    - **Storage:** choose "Use an entire disk" and tick **Set up this disk as an LVM group**. LVM lets you snapshot before risky operations later.
    - **Profile:** pick a short hostname you won't mind typing often, such as `agent`.
    - **Tick "Install OpenSSH server."** Do not skip this — everything from here on is headless.
    - **Import SSH identity → from GitHub,** entering your GitHub username. This pulls your public keys automatically.
    - **Featured snaps:** skip all of them.

5.  Reboot, remove the USB stick, disconnect the monitor. Connect from your laptop:

        ssh yourname@agent.local     # or the IP address

### Phase 2 — Base system

    # Updates
    sudo apt update && sudo apt full-upgrade -y

    # Automatic security updates
    sudo apt install -y unattended-upgrades
    sudo dpkg-reconfigure --priority=low unattended-upgrades

    # Timezone
    sudo timedatectl set-timezone Europe/Vienna

    # Firewall
    sudo ufw allow OpenSSH
    sudo ufw enable

Then restrict SSH to key authentication. Edit `/etc/ssh/sshd_config`:

    PasswordAuthentication no
    PermitRootLogin no

    sudo systemctl restart ssh

**Before closing this terminal,** open a second one and confirm you can still log in. If key authentication isn't working, the first session is your only way back in.

### Phase 3 — Development toolchain

    sudo apt install -y build-essential git curl wget unzip \
                        ripgrep fd-find jq tmux htop ncdu

    # GitHub CLI
    sudo apt install -y gh
    gh auth login          # also offers to configure git credentials

Git identity:

    git config --global user.name  "Your Name"
    git config --global user.email "you@example.com"
    git config --global init.defaultBranch main
    git config --global pull.rebase true

#### Node.js

Use a version manager rather than apt, so individual projects can pin their own versions.

    curl -fsSL https://fnm.vercel.app/install | bash
    exec $SHELL
    fnm install --lts
    fnm default lts-latest

#### Python

`uv` handles interpreters and virtual environments in a single tool.

    curl -LsSf https://astral.sh/uv/install.sh | sh

#### Docker (optional)

The cleanest way to contain a risky agent run to a single directory.

    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    newgrp docker

Add anything else your projects need — Go, Rust via rustup, a database, and so on.

### Phase 4 — Install Claude Code

Two options. Pick one.

#### Option A — Native installer (auto-updates in the background)

    curl -fsSL https://claude.ai/install.sh | bash

#### Option B — apt repository (updates arrive through `apt upgrade`)

    sudo apt install -y curl gnupg
    sudo install -d -m 0755 /etc/apt/keyrings
    sudo curl -fsSL https://downloads.claude.ai/keys/claude-code.asc \
      -o /etc/apt/keyrings/claude-code.asc

    # Verify the key before trusting it. Expected fingerprint:
    # 31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE
    gpg --show-keys /etc/apt/keyrings/claude-code.asc

    echo "deb [signed-by=/etc/apt/keyrings/claude-code.asc] https://downloads.claude.ai/claude-code/apt/stable stable main" \
      | sudo tee /etc/apt/sources.list.d/claude-code.list
    sudo apt update && sudo apt install claude-code

For an unattended machine, Option B has the advantage that the version won't change under you between sessions. Verify either way:

    claude --version     # prints e.g. 2.1.211 (Claude Code)
    claude doctor        # read-only diagnostics: install health, settings errors

If you get `claude: command not found`, add this to `~/.bashrc`:

    export PATH="$HOME/.local/bin:$PATH"

#### Authenticate

Claude Code requires a Pro, Max, Team, Enterprise, or Console account. The free Claude.ai plan does not include access.

    cd ~/some-project
    claude

On a headless machine it prints a login URL. Open that in the browser on your laptop, complete the flow, and paste the code back. The session token is stored in `~/.claude.json`.

### Phase 5 — Remote workflow

The point of a dedicated machine is that a long run keeps going after your laptop sleeps. That requires a terminal multiplexer.

    sudo apt install -y tmux

A minimal `~/.tmux.conf`:

    set -g mouse on
    set -g history-limit 50000
    set -g default-terminal "tmux-256color"

    tmux new -s wow          # one named session per project
    # Ctrl-b then d          -> detach; work continues running
    tmux ls                  # list sessions
    tmux attach -t wow       # reattach later, from anywhere

#### Access from outside your network

Tailscale avoids opening any port on your router.

    curl -fsSL https://tailscale.com/install.sh | sh
    sudo tailscale up --ssh

#### Editor integration

Install the *Remote - SSH* extension in VS Code on your laptop, connect to the machine, and run `claude` in the integrated terminal. Files are edited directly on the server, with no syncing or mounted network drives.

#### Unreliable connections

    sudo apt install -y mosh    # then connect with mosh instead of ssh

### Phase 6 — Guardrails

A machine dedicated to running an agent should be one you'd be relaxed about losing.

1.  **Keep secrets off it.** No password manager exports, no unrelated SSH keys, no production `.env` files. Where a repository needs credentials, scope them to that repository.

2.  **Everything in git, pushed often.** This is your best undo button. Use `git worktree` to give parallel sessions separate directories on the same repository.

3.  **Configure updates deliberately** in `~/.claude/settings.json`:

        {
          "autoUpdatesChannel": "stable"
        }

    The stable channel trails by about a week and skips releases with known major regressions — a sensible trade for a machine you don't watch closely.

4.  **Run genuinely risky work in a container.** A devcontainer, or plain `docker run -v $PWD:/work`, limits the blast radius to one directory.

5.  **Back up.** At minimum a nightly job pushing to a NAS or object storage:

        sudo apt install -y restic

    With LVM from Phase 1 you can also snapshot before a large refactor and roll back if it goes badly.

### Phase 7 — Clone the project and confirm the cross-compile path

    mkdir -p ~/code && cd ~/code
    gh repo clone Ruban-Creator/wow-gearing-tool
    cd wow-gearing-tool
    git submodule update --init --recursive

This repo already has its own thorough `CLAUDE.md` - no need to run `/init` for real, just confirm
`claude` reads it correctly:

    tmux new -s watcher
    claude
    # inside the session: ask it to summarize CLAUDE.md's "Sim update procedure" section back to
    # you, as a real check that it loaded correctly - then Ctrl-b, d to detach.

Install the Go/protoc toolchain `CLAUDE.md`'s own "Local setup" section documents (same real
prerequisite chain as the Windows dev machine, Ubuntu's own package names):

    sudo apt install -y golang-go protobuf-compiler
    go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
    go version && protoc --version

**Real, one-time smoke test before wiring up scheduling** - cross-compile a real Windows binary
from this Linux machine and confirm it's an actual PE executable, not just a build error that
happened to exit 0:

    cd sim/tbc-new
    GOOS=windows GOARCH=amd64 go build -o /tmp/wowsimcli_test.exe --tags=with_db ./cmd/wowsimcli/cli_main.go
    file /tmp/wowsimcli_test.exe   # expect: "PE32+ executable (console) x86-64, for MS Windows"
    rm /tmp/wowsimcli_test.exe

### Phase 8 — Wire up the daily check

The Watcher's real job, end to end: check for a new `wowsims/tbc-new` tag, and if one exists, do
`CLAUDE.md`'s runbook steps 1-4 (assess risk via `git diff`, bump the submodule, cross-compile all
three binaries as a pre-flight sanity check) and push the result to a staging branch - never
`master`. A small wrapper script plus `claude -p` (Claude Code's non-interactive "print mode" -
runs one prompt to completion and exits, no session to babysit) is enough; no separate scheduler
framework needed beyond cron.

    mkdir -p ~/code/wow-gearing-tool-watcher-logs

`~/code/run_watcher.sh`:

    #!/bin/bash
    set -euo pipefail
    cd ~/code/wow-gearing-tool
    git checkout master && git pull

    claude -p "Follow this repo's own CLAUDE.md 'Sim update procedure' section, steps 1 through 4
    ONLY (check the latest wowsims/tbc-new tag against the pinned commit, assess risk via a real
    git diff, bump the submodule if a new tag exists, and cross-compile all three binaries with
    GOOS=windows GOARCH=amd64 as a pre-flight build check - do NOT run or verify them, this
    machine can't execute a .exe). If a new version was found and the cross-compile succeeded,
    create/reset a branch named sim-update-pending from the bump, push it, and stop. If no new
    tag exists, or the cross-compile fails, do nothing to git and just report what you found -
    never touch master, never merge, never run steps 5 or later." \
      --output-format text \
      >> ~/code/wow-gearing-tool-watcher-logs/"$(date +%F).log" 2>&1

    chmod +x ~/code/run_watcher.sh

Cron entry (`crontab -e`), once a day is plenty - a new tag doesn't appear more than a few times a
month in practice:

    0 6 * * * /home/yourname/code/run_watcher.sh

Check `claude --help` for the exact current non-interactive flag name if this has drifted since -
CLI flags are the one part of this guide worth re-verifying against `claude doctor`'s own output
before trusting blindly, since they change between versions more often than the rest of this setup.

## Part 2 — Verifier (Windows)

The other half of backlog #14 - see this file's own intro above for why this can't live on the
Watcher. Real, minimal setup, no GUI actually used for any of the work itself.

### Phase 0 — Get Windows, the legitimate way

**Use Microsoft's own official Windows 11 Pro download** -
[microsoft.com/software-download/windows11](https://www.microsoft.com/en-us/software-download/windows11)
- "Create Windows 11 Installation Media," standard 64-bit edition.

Windows 11 IoT Enterprise LTSC (Microsoft's own actually-minimal edition - no Store, no
Copilot/Widgets, years of security-only updates) was considered and ruled out (checked 2026-09-06,
not assumed): it isn't a normal download for an individual - Microsoft only distributes it through
authorized OEM/volume-licensing distributors or a Visual Studio subscription, with just a 90-day
eval otherwise. **Do not substitute a third-party "debloated"/"tiny" Windows ISO from a forum or
reseller** - those are unverified, modified system images, a real, meaningful risk for a machine
that will hold this repo's GitHub credentials and run unattended builds. A stock, official Windows
11 Pro install, debloated using only Microsoft's own supported mechanisms below, is the real,
practical "minimal" here.

### Phase 1 — Debloat, using only Microsoft-supported mechanisms

After first boot and Windows Update:

    # Remove most bundled consumer apps (run in an elevated PowerShell)
    Get-AppxPackage -AllUsers | Where-Object {$_.Name -notmatch "Store|Notepad|Calculator"} | Remove-AppxPackage -ErrorAction SilentlyContinue

    # Disable Widgets, Copilot, Cortana via documented policy (Local Group Policy Editor -
    # gpedit.msc - or the equivalent registry keys under HKLM\SOFTWARE\Policies\Microsoft)
    # rather than any third-party "debloat script" pulled off GitHub sight-unseen.

Disable non-essential startup apps and services via Task Manager's Startup tab and
`services.msc` (Print Spooler, Fax, Windows Search - none of which this machine needs). This gets
genuinely close to a minimal footprint without touching anything unofficial.

### Phase 2 — Remote access, no monitor after this point

Enable Windows' own built-in OpenSSH Server (same real idea as the Linux Watcher's SSH access -
no RDP/GUI session ever needs to be opened for normal operation):

    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
    Start-Service sshd
    Set-Service -Name sshd -StartupType Automatic
    New-NetFirewallRule -Name sshd -DisplayName "OpenSSH Server" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22

Then, from the Watcher or your laptop: `ssh yourname@<this machine's IP>`.

Power settings - since this machine only needs to wake for occasional verification runs, not stay
on 24/7 like the Watcher: `powercfg` or Settings > Power, set "Sleep" to never while plugged in,
and enable Wake-on-LAN in both Device Manager (network adapter properties) and BIOS if you want to
wake it remotely rather than leaving it running constantly.

### Phase 3 — Toolchain

Same real prerequisite chain `CLAUDE.md`'s own "Local setup" section already documents for this
exact repo - nothing new to invent:

    winget install --id GoLang.Go
    winget install --id Google.Protobuf
    go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
    winget install --id Python.Python.3.13
    winget install --id Git.Git
    winget install --id GitHub.cli

Install Claude Code per Anthropic's own Windows instructions, then `claude doctor` to confirm.

### Phase 4 — The verify-and-merge job

Triggered after the Watcher pushes `sim-update-pending` (simplest real trigger: a scheduled task
a few hours after the Watcher's own cron job, giving it time to run first - or SSH-triggered
directly from the Watcher's own script once Phase 8 above is trusted).

`verify_and_merge.ps1`:

    cd C:\code\wow-gearing-tool
    git fetch origin
    $hasBranch = git ls-remote --heads origin sim-update-pending
    if (-not $hasBranch) { Write-Output "No pending sim update."; exit 0 }

    git checkout sim-update-pending
    git pull

    claude -p "Follow this repo's own CLAUDE.md 'Sim update procedure', steps 4 (rebuild, this
    time for real on Windows) through 6 (verify - the full real checklist: kill stale simserver
    processes, an import-sanity sweep, a real live sim call per weapon topology in use, and
    check_ledger_consistency.py --skip-html for all 15 profiles). Report the real pass/fail result
    plainly. Do NOT commit or push yet - stop after verification and report." --output-format text

Read the report. On a genuine clean pass:

    git checkout master
    git merge sim-update-pending
    git push origin master
    git push origin --delete sim-update-pending

On any real failure, per the runbook's own step 7: leave everything as-is on the
`sim-update-pending` branch (don't delete it, don't merge it) and go look at what broke - the
whole point of this two-machine split is that nothing reaches `master` without this step actually
passing.

### Phase 5 — Guardrails

Same real principles as the Watcher's own Phase 6, Windows-flavored:

1.  **Keep secrets scoped.** A GitHub token with push access to just this repo, not a
    broad/organization-wide credential.
2.  **Everything in git.** No local-only state this machine holds that isn't also on `origin`.
3.  **Windows Update stays on**, security-only where possible (Settings > Windows Update >
    Advanced options) - this machine spends most of its time asleep/idle, so update windows won't
    collide with a verification run often, but a real failure mid-verify is still possible; a
    failed run is safe (nothing merges), just re-run it.
4.  **Back up** the same way as the Watcher - a scheduled `robocopy`/`restic` job to the household
    NAS.

## Quick reference

### Watcher (Linux)

| Task                        | Command                                    |
|-----------------------------|--------------------------------------------|
| BIOS setup / boot menu      | `F2` / `F12`                               |
| Check installation health   | `claude doctor`                            |
| Update Claude Code manually | `claude update`                            |
| Start a named session       | `tmux new -s name`                         |
| Detach from a session       | `Ctrl-b` then `d`                          |
| Reattach to a session       | `tmux attach -t name`                      |
| List sessions               | `tmux ls`                                  |
| System update               | `sudo apt update && sudo apt full-upgrade` |
| Confirm chassis model       | `sudo dmidecode -s system-product-name`    |
| Run the daily check by hand | `~/code/run_watcher.sh`                    |
| Check today's watcher log   | `cat ~/code/wow-gearing-tool-watcher-logs/$(date +%F).log` |

### Verifier (Windows)

| Task                          | Command                                          |
|-------------------------------|---------------------------------------------------|
| Check installation health     | `claude doctor`                                    |
| Is a sim update pending?      | `git ls-remote --heads origin sim-update-pending`  |
| Run the verify job by hand    | `powershell -File verify_and_merge.ps1`            |
| Confirm no stale sim processes| `Get-Process simserver -ErrorAction SilentlyContinue` |
| SSH in                        | `ssh yourname@<verifier IP>`                       |

Claude Code documentation: `https://code.claude.com/docs/en/setup`

Later additions worth considering: 32 GB of SODIMM memory on the Watcher if 16 GB starts limiting builds and containers. A discrete GPU isn't relevant to either machine - nothing here runs a local model, and the Watcher's Micro chassis has no PCIe slot regardless.
