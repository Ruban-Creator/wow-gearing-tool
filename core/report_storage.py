"""Backlog #13 (CLAUDE.md Future Scope) - the one shared reports.json read/
migrate/write implementation, used by both gui/api.py and cli/gear.py so
neither hand-rolls its own read-modify-write (they used to, independently,
which is exactly how a fix applied to only one of them would have left the
other silently broken).

Real bug this exists to fix: reports.json used to be keyed by phase alone
(`{phase: {artifact_url, generated_at, notes?}}`) - no profile dimension at
all. Once a character could be reassigned to a different sim profile (the
GUI's "Change profile…" feature), running a report under a second profile
silently overwrote the first profile's report with no warning. Now keyed
`{profile_dir_name: {phase: {...}}}` - one branch per profile, phases
distinct within each.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
import character_profiles  # noqa: E402
USER_DATA_DIR = repo_root.USER_DATA_DIR

# Every real phase key ever written under the old flat schema looks like
# this ("phase1".."phase5" today) - confirmed safe as a migration-detection
# heuristic: no real profile dir name (profiles/tbc/*) matches this pattern.
_OLD_PHASE_KEY_RE = re.compile(r"^phase\d+$")


def _reports_path(name_realm: str) -> str:
    return os.path.join(USER_DATA_DIR, "characters", name_realm, "reports.json")


def _is_old_flat_schema(reports: dict) -> bool:
    return bool(reports) and any(_OLD_PHASE_KEY_RE.match(k) for k in reports)


def load_reports(name_realm: str) -> dict:
    """Returns the real, current-schema {profile_dir_name: {phase: {...}}}
    dict for this character - empty dict if no reports.json exists yet.

    Migrates a real, existing OLD flat-schema file (every one on disk before
    2026-08-31 was generated under exactly one profile per character, since
    profile-switching didn't exist before then) by wrapping it one level
    deeper under that character's CURRENTLY assigned profile - the only
    profile it could possibly have been generated under. Migration is lazy
    and one-time: it writes the migrated form back to disk immediately, so a
    second call sees the already-nested schema and does nothing. Old
    underlying HTML/cache files are never touched - a migrated entry keeps
    its existing absolute artifact_url, which still resolves correctly."""
    path = _reports_path(name_realm)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        reports = json.load(f)

    if _is_old_flat_schema(reports):
        profile_dir = character_profiles.SUPPORTED_CHARACTERS.get(name_realm)
        if profile_dir is None:
            # Real, honest fallback: no current profile assignment to
            # attribute this history to (e.g. she was unassigned after
            # these reports were generated) - keep it under a real,
            # visibly-labeled bucket rather than silently dropping it or
            # guessing a profile she may never have used.
            profile_dir_name = "unknown_profile"
        else:
            profile_dir_name = os.path.basename(os.path.normpath(profile_dir))
        reports = {profile_dir_name: reports}
        save_reports(name_realm, reports)

    return reports


def save_reports(name_realm: str, reports: dict) -> None:
    path = _reports_path(name_realm)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2)


def report_file_exists(artifact_url: str) -> bool:
    """Real fix, 2026-09-06: a stale reports.json entry (the underlying HTML
    moved, got deleted, or - as found live this session - pointed at the
    pre-2026-08-29 repo-relative data/ directory that no longer exists at
    all post-migration) used to still render as a clickable "View Report"
    button that threw a ValueError from gui/api.py's own open_url()
    allowlist check the moment it was clicked. This isn't just a one-time
    migration artifact to clean up - a user can delete or move a report file
    themselves at any time, so the check needs to be real and live, not a
    one-off fix. Only checked for file:// URLs (the only scheme this tool
    ever generates for a report artifact) - a hypothetical http(s) URL is
    assumed to exist, since there's no cheap way to check a remote resource
    here and nothing in this codebase produces one today."""
    parsed = urllib.parse.urlparse(artifact_url)
    if parsed.scheme != "file":
        return True
    local_path = urllib.request.url2pathname(parsed.path)
    return os.path.exists(local_path)


def filter_missing_reports(reports: dict) -> dict:
    """Display-only view of load_reports()'s own return value, with any
    phase entry whose real underlying file no longer exists dropped.

    Deliberately NEVER used to build a dict that then gets passed to
    save_reports() - report_storage.py's real job is being the one shared
    read/write implementation neither gui/api.py nor cli/gear.py hand-rolls,
    and both of them do a real load-mutate-save cycle (registering a fresh
    report for ONE phase) that would otherwise silently erase every OTHER
    phase's still-valid history the moment its own file happened to be
    temporarily missing/unmounted - this function exists specifically so
    that read-modify-write path never sees a filtered/lossy copy. Only ever
    call this on a dict about to be shown to a human, not saved back."""
    return {
        profile: {phase: entry for phase, entry in phases.items()
                  if report_file_exists(entry.get("artifact_url", ""))}
        for profile, phases in reports.items()
    }
