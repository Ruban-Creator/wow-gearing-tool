---
title: Dedicated Sim-Update Machine — Setup Guide
machine: "HP EliteDesk 800 G6 Mini (10th-gen Intel Core, refurbished) or equivalent - see Phase 0. Not yet purchased/built."
---

# Dedicated Sim-Update Machine

One machine, one real job, for `wow-gearing-tool` backlog #14: a daily agent that checks
`wowsims/tbc-new` for a new version and runs `CLAUDE.md`'s "Sim update procedure" runbook
end-to-end, unattended - no dependency on any other machine being on.

**Real design history, 2026-09-06 (kept here so the reasoning isn't lost):** this went through two
earlier drafts before landing here. The first assumed a single Linux machine could do the whole
job - wrong, because a Linux machine can *build* the sim's Windows binaries via cross-compilation
(`GOOS=windows GOARCH=amd64 go build` produces a real `.exe`, no Windows needed for that step) but
can't *run* one to verify it actually works, since a `.exe` needs a real Windows environment to
execute. The second draft split the work across two machines (a new Linux "Watcher" plus the
user's own existing Windows PC as "Verifier") - workable, but it made the whole pipeline depend on
the user's everyday production machine being on and logged into, which it usually isn't on any
given day. The real fix, once asked directly "isn't it better to have the dev machine be Windows
instead of Linux?": yes - one new, dedicated **Windows** machine does the entire runbook itself
(check, build, verify, merge, push), with nothing dependent on any other machine's uptime.

No GUI is needed for any of this - every real step is a command-line tool
(`wowsimcli.exe`/`bridge.exe`/`simserver.exe` are console programs, the verification scripts are
plain Python, git is git).

## Phase 0 — Pick the hardware

Real, current pick: **HP EliteDesk 800 G6 Mini** (10th-gen Intel Core, Q470 chipset - officially
on Windows 11's supported CPU list, no workaround needed) - a real, available refurbished listing
exists at ~€259 (i5-10500, 8 GB RAM/250 GB SSD base config; worth taking the +€69 upgrade to
16 GB, since 8 GB is tight running Go builds + Python + git + Windows together). Small, quiet,
low-power business Mini form factor, same role this whole guide has always assumed.

Any similar small-form-factor business PC (Dell OptiPlex Micro, Lenovo ThinkCentre Tiny, Intel
NUC) works equally well - the category matters more than the specific model.

**On reusing hardware you already have (e.g. an older, 7th-gen-class Micro PC) instead:** Windows
11 will genuinely install and run on CPUs Microsoft doesn't officially list as supported - this is
routine, not a fragile hack, done via a well-known one-time bypass at install time (a registry key,
or Rufus's own built-in option for this). The real, honest tradeoff isn't "will it work" - it
does - it's that Microsoft doesn't formally guarantee updates keep arriving on unsupported
hardware indefinitely, though in practice this keeps working for most people for years. A
perfectly reasonable way to start today on hardware already on hand, with the option to move this
same setup onto newer hardware later without redoing anything except the one-time OS install
itself - everything from Phase 4 onward is identical either way.

16 GB RAM / 256+ GB NVMe SSD is comfortably enough - this project's own build+verify work isn't
resource-heavy, it's the *waiting for a new tag to exist* that takes the real calendar time.

## Phase 1 — BIOS and hardware preparation

Do this before touching the installer. Power on and press the machine's BIOS-setup key (`F2` on
Dell, `F1`/`F2` on Lenovo, `F2` on most NUCs - check the specific model).

1.  **Set SATA/storage mode to AHCI** (or NVMe, if that's the drive) - a `RAID On` default is a
    common reason an installer shows no disks at all.
2.  **Power Management → AC Recovery → Power On.** The machine comes back by itself after a power
    cut, which matters for a box you rely on being reachable.
3.  **Disable Deep Sleep Control / enable Wake-on-LAN** if you want to wake it remotely rather
    than leaving it fully powered on all the time. Optional - see Phase 6's scheduling section for
    why this matters less than it might seem, since missed runs catch up on their own.
4.  **Leave Secure Boot enabled** - Windows 11 wants it, no special steps needed.
5.  **Update the BIOS** while a screen is still attached, from the manufacturer's own support
    page, before installing Windows.

## Phase 2 — Install Windows, the legitimate way

**Use Microsoft's own official Windows 11 Pro download** -
[microsoft.com/software-download/windows11](https://www.microsoft.com/en-us/software-download/windows11)
- "Create Windows 11 Installation Media," standard 64-bit edition.

Windows 11 IoT Enterprise LTSC (Microsoft's own actually-minimal edition - no Store, no
Copilot/Widgets, years of security-only updates) was considered and ruled out (checked
2026-09-06): it isn't a normal download for an individual - Microsoft only distributes it through
authorized OEM/volume-licensing distributors or a Visual Studio subscription, with just a 90-day
eval otherwise. **Do not substitute a third-party "debloated"/"tiny" Windows ISO from a forum or
reseller** - those are unverified, modified system images, a real, meaningful risk for a machine
that will hold this repo's GitHub credentials and run unattended builds. A stock, official Windows
11 Pro install, debloated in Phase 3 using only Microsoft's own supported mechanisms, is the real,
practical "minimal" here.

## Phase 3 — Debloat and remote access

After first boot and Windows Update, in an elevated PowerShell:

    # Remove most bundled consumer apps
    Get-AppxPackage -AllUsers | Where-Object {$_.Name -notmatch "Store|Notepad|Calculator"} | Remove-AppxPackage -ErrorAction SilentlyContinue

Disable Widgets/Copilot/Cortana via documented policy (Local Group Policy Editor - `gpedit.msc` -
or the equivalent registry keys under `HKLM\SOFTWARE\Policies\Microsoft`), and non-essential
startup apps/services via Task Manager's Startup tab and `services.msc` (Print Spooler, Fax,
Windows Search - none of which this machine needs). Genuinely close to a minimal footprint,
official mechanisms only.

Enable Windows' own built-in OpenSSH Server, so this machine never needs a monitor after setup:

    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
    Start-Service sshd
    Set-Service -Name sshd -StartupType Automatic
    New-NetFirewallRule -Name sshd -DisplayName "OpenSSH Server" -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22

Then, from your laptop: `ssh yourname@<this machine's IP>` - set a DHCP reservation on your router
so that IP never changes.

Power settings: Settings > Power, set "Sleep" to never while plugged in, since this machine is
meant to be reachable at any time.

## Phase 4 — Toolchain

The exact same prerequisite chain `CLAUDE.md`'s own "Local setup" section already documents for
this repo - nothing new to invent:

    winget install --id GoLang.Go
    winget install --id Google.Protobuf
    go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
    winget install --id Python.Python.3.13
    winget install --id Git.Git
    winget install --id GitHub.cli
    gh auth login

Git identity:

    git config --global user.name  "Your Name"
    git config --global user.email "you@example.com"

Install Claude Code per Anthropic's own Windows instructions, then confirm:

    claude --version
    claude doctor

Authenticate: `claude` requires a Pro, Max, Team, Enterprise, or Console account (the free
Claude.ai plan doesn't include access). Run `claude` once interactively, complete the login flow
in a browser, and the session token is stored locally - after that, non-interactive runs (Phase 5)
don't need to re-authenticate.

Clone the project:

    mkdir C:\code
    cd C:\code
    gh repo clone Ruban-Creator/wow-gearing-tool
    cd wow-gearing-tool
    git submodule update --init --recursive

This repo already has its own thorough `CLAUDE.md` - confirm `claude` reads it correctly (ask it
to summarize the "Sim update procedure" section back to you) rather than assuming.

## Phase 5 — The daily job

One script does the entire real runbook now that one machine can both build and run the result -
no staging branch or cross-machine handoff needed. `claude -p` is Claude Code's non-interactive
"print mode": runs one prompt to completion and exits, nothing to babysit.

`run_sim_update.ps1`:

    cd C:\code\wow-gearing-tool
    git checkout master
    git pull

    claude -p "Follow this repo's own CLAUDE.md 'Sim update procedure' section, all steps, start
    to finish. Step 1: check the latest wowsims/tbc-new tag against the pinned commit - if it
    matches, report 'no update' and stop here, do nothing else. Otherwise: assess risk via a real
    git diff (step 2), bump the submodule (step 3), rebuild all three binaries per the Local Setup
    section's real commands - remember simserver.exe needs --tags=with_db too, not just
    wowsimcli.exe (step 4), kill any stale simserver.exe processes first (step 5), then run the
    real verification checklist: an import-sanity sweep, a live sim call for at least one profile
    per weapon topology in use, and check_ledger_consistency.py --skip-html for all 15 profiles
    (step 6). On a genuine clean pass, commit the submodule bump and push to master (step 8). On
    any real failure, per step 7: do NOT commit or push anything - leave the submodule bump and
    rebuilt binaries in the working tree, and write what broke into a new dated NOTES.md entry the
    same way this file's own other entries are written, so the next run (or a human) can pick up
    the diagnosis without re-deriving it. Report the real outcome plainly either way." `
      --output-format text `
      *>> "C:\code\sim-update-logs\$(Get-Date -Format yyyy-MM-dd).log"

    mkdir -Force C:\code\sim-update-logs | Out-Null

(Create the log directory once, or move that `mkdir` line above the `cd` - order doesn't matter,
just needs to exist before the first real run.)

Check `claude --help` for the exact current non-interactive flag name if this has drifted since -
CLI flags are the one part of this guide worth re-verifying against `claude doctor`'s own output
before trusting blindly, since they change between versions more often than the rest of this
setup.

## Phase 6 — Scheduling, with real catch-up for a machine that isn't always on

Even a machine "meant to be always on" can be off for a stretch (a power cut, a reboot for
updates). Windows Task Scheduler has a real, built-in answer so a missed run doesn't just vanish:

1.  Open Task Scheduler > Create Task.
2.  **Trigger 1**: Daily, whatever time - under the trigger's own Advanced settings, tick **"If
    the scheduled start is missed, run task as soon as possible."**
3.  **Trigger 2** (belt and suspenders): "At startup" - so a reboot also re-checks immediately.
4.  **Action**: `powershell.exe -File C:\code\run_sim_update.ps1`.
5.  Under Conditions, make sure "Start the task only if the computer is on AC power" matches how
    this machine is actually powered (a desktop on mains: untick it, it's irrelevant).

Running the check often is cheap - step 1 of the script's own prompt exits immediately once it
confirms there's no new tag, so firing it daily AND on every startup AND on catch-up is not wasted
work, just redundant safety.

## Phase 7 — Guardrails

1.  **Scope the credentials this task runs as.** `gh auth login`'s token (or an SSH deploy key, or
    a PAT) should have push access to just this one repo, not a broad/organization-wide
    credential - this machine runs unattended, so it's worth being deliberate about what it can
    reach.
2.  **A failed run is always safe.** Nothing reaches `master` unless the script's own real
    verification passes - a bad run just leaves the submodule bump and binaries sitting in the
    working tree (per step 7) for you to look at, never a half-broken `master`.
3.  **Configure Claude Code's own update channel deliberately**, in `%USERPROFILE%\.claude\settings.json`:

        {
          "autoUpdatesChannel": "stable"
        }

    The stable channel trails by about a week and skips releases with known major regressions - a
    sensible trade for a machine you don't watch closely.
4.  **Keep other secrets off it.** No password manager exports, no unrelated credentials - this
    machine's whole job is one repo, one task.
5.  **Back up** the repo state to the household NAS on a schedule, same idea as any other real
    working directory - though since everything meaningful here is already in git, `origin` is
    already the real backup for anything that matters.

## Quick reference

| Task                            | Command                                                     |
|----------------------------------|--------------------------------------------------------------|
| Check installation health        | `claude doctor`                                             |
| Run the daily job by hand        | `powershell -File C:\code\run_sim_update.ps1`               |
| Check today's log                | `type C:\code\sim-update-logs\<today's date>.log`           |
| Confirm no stale sim processes   | `Get-Process simserver -ErrorAction SilentlyContinue`       |
| SSH in                           | `ssh yourname@<this machine's IP>`                          |
| Update Claude Code manually      | `claude update`                                             |
| Confirm chassis model            | `Get-CimInstance Win32_ComputerSystem \| Select Model`       |

Claude Code documentation: `https://code.claude.com/docs/en/setup`
