-- Companion to WowSimsExporter, covering everything it doesn't:
--   1. Bank: FillFromBagItems() only walks bagId 0..NUM_BAG_SLOTS, never the bank.
--   2. Bags: GenerateOutputBags() exists but its result only goes to the UI's
--      textbox for copy-paste - unlike the equipped-gear export, it is never
--      passed to SaveCharacterData, so nothing bag-related ever reaches disk.
--   3. Reputation standings and arena team ratings - WowSimsExporter doesn't
--      touch either at all, and the Gearing Tool needs them to tell "real
--      upgrade" apart from "real upgrade, but you can't actually buy it yet"
--      for reputation- and rating-gated items.
--   4. Character identity (name/realm/class/race/faction/level/professions) -
--      WowSimsExporter DOES capture this internally (its own savedCharacters
--      list, keyed by name-realm with a timestamp, confirmed by reading
--      ingest/build_character.py), but it's a third-party addon whose
--      internal format isn't ours to depend on long-term, and the current
--      Python ingest side only ever reads ONE hardcoded name_realm from it
--      anyway. Captured natively here instead, added 2026-08-24 for the
--      multi-class/spec support work (CLAUDE.md Stage 6) - GTCompanionDB was
--      already keyed per-character (see CharKey/Entry below), so "store
--      multiple characters" was already true structurally; what was missing
--      was capturing identity/professions at all, and a UI to see everything
--      that's actually been saved across characters at a glance.
--
-- NOT LIVE-TESTED YET (written away from the game client) - the profession
-- API in particular (GetProfessions/GetProfessionInfo) is long-documented
-- and stable across Classic/TBC/retail, but this file has already been
-- burned twice by this exact client (Interface 20506) behaving differently
-- than documented (the reputation hasRep bug, the arena team API). Verify
-- for real in-game before trusting the identity/professions output blindly -
-- print the identity block via /gtlist and eyeball it against the character
-- sheet and profession windows directly.
--
-- Everything here goes straight to SavedVariables, no clipboard step needed,
-- matching how the equipped-gear export already behaves.

GTCompanionDB = GTCompanionDB or {}

local STANDING_NAMES = {
    [1] = "Hated", [2] = "Hostile", [3] = "Unfriendly", [4] = "Neutral",
    [5] = "Friendly", [6] = "Honored", [7] = "Revered", [8] = "Exalted",
}

-- Reputation-gated gear (e.g. Band of the Eternal Champion, Exalted The
-- Scale of the Sands) needs standing to know what's actually obtainable
-- now vs. later. Walks headers too (so nothing nested/collapsed is
-- missed).
--
-- This client (TBC Anniversary, Interface 20506) does NOT have
-- C_Reputation at all - confirmed live, not assumed - so this always
-- runs the pre-11.0 GetNumFactions/GetFactionInfo globals. A real bug
-- lived here for a while: GetNumFactions() genuinely returned 43 (proven
-- via live debug print), but the row-counting condition additionally
-- required `hasRep` to be true, and hasRep is NOT "this row has valid
-- standing data" - a live dump of row 2 (Darnassus, isHeader=false,
-- hasRep=false, standingId=7/Revered - real data) proved hasRep is only
-- meaningful on HEADER rows (whether the header itself also carries its
-- own account-wide rep bar, rare) and is false/nil on every ordinary
-- leaf faction by design. That's why every real faction was silently
-- skipped despite the count being right all along. Fixed by keying off
-- `not isHeader and name and standingId` instead.
local function DumpReputation()
    local result = {}
    if C_Reputation and C_Reputation.GetNumFactions then
        local i = 1
        local numFactions = C_Reputation.GetNumFactions()
        while i <= numFactions do
            local data = C_Reputation.GetFactionDataByIndex(i)
            if data then
                if data.isHeader and data.isCollapsed then
                    if C_Reputation.ExpandFactionHeader then
                        C_Reputation.ExpandFactionHeader(i)
                    elseif ExpandFactionHeader then
                        ExpandFactionHeader(i)
                    end
                    numFactions = C_Reputation.GetNumFactions()
                end
                if not data.isHeader and data.name then
                    result[data.name] = STANDING_NAMES[data.reaction] or data.reaction
                end
            end
            i = i + 1
        end
    elseif GetNumFactions then
        local i = 1
        local numFactions = GetNumFactions()
        while i <= numFactions do
            local name, _, standingId, _, _, _, _, _, isHeader, isCollapsed = GetFactionInfo(i)
            if isHeader and isCollapsed and ExpandFactionHeader then
                ExpandFactionHeader(i)
                numFactions = GetNumFactions()
            end
            if not isHeader and name and standingId then
                result[name] = STANDING_NAMES[standingId] or standingId
            end
            i = i + 1
        end
    end
    return result
end

-- Gladiator gear (e.g. Vengeful Gladiator's Rifle) is rating-gated, not
-- just points-gated. There's no persistent "arena team" object on this
-- client at all (confirmed by testing - GetArenaTeam(1..3) returned nil
-- for all three despite the character having real 2v2/3v3/5v5 personal
-- ratings visible in the PvP pane) - this client uses the modern
-- per-bracket PERSONAL rating system instead (GetPersonalRatedInfo,
-- bracket index 1=2v2, 2=3v3, 3=5v5). Falls back to GetArenaTeam if
-- GetPersonalRatedInfo isn't present.
local BRACKET_NAMES = { [1] = "2v2", [2] = "3v3", [3] = "5v5" }

local function DumpArena()
    local teams = {}
    if GetPersonalRatedInfo then
        for i = 1, 3 do
            local rating, seasonBest, weeklyBest, seasonPlayed, seasonWon, weeklyPlayed, weeklyWon, cap =
                GetPersonalRatedInfo(i)
            if rating then
                table.insert(teams, {
                    bracket = BRACKET_NAMES[i], rating = rating, seasonBest = seasonBest,
                    weeklyBest = weeklyBest, seasonPlayed = seasonPlayed, seasonWon = seasonWon,
                    weeklyPlayed = weeklyPlayed, weeklyWon = weeklyWon, cap = cap,
                })
            end
        end
    elseif GetArenaTeam then
        for i = 1, 3 do
            local name, size, rating, seasonWins, seasonGames, weekWins, weekGames = GetArenaTeam(i)
            if name then
                table.insert(teams, {
                    index = i, name = name, size = size, rating = rating,
                    seasonWins = seasonWins, seasonGames = seasonGames,
                    weekWins = weekWins, weekGames = weekGames,
                })
            end
        end
    end
    return teams
end

-- GetProfessions() returns up to 6 positional slots (primary1, primary2,
-- archaeology, fishing, cooking, firstAid) and ANY of them can be nil (e.g.
-- no archaeology in TBC, no second primary profession chosen yet) - collecting
-- them with `{ GetProfessions() }` + ipairs would silently stop at the first
-- nil hole, so each slot is checked explicitly instead. GetProfessionInfo's
-- signature (name, icon, skillLevel, maxSkillLevel, ...) is long-stable
-- Blizzard API, not guessed - still unverified on THIS client, see the file
-- header note.
-- Real, live-confirmed 2026-08-24: GetProfessions()/GetProfessionInfo()
-- return nothing at all on this client (all-nil, even for a character with
-- real Herbalism 375/375 + Mining 375/375, and even after opening the
-- Skills panel this session - ruling out the lazy-load theory that fixed
-- the analogous ReputationFrame quirk). The general skill-line API is what
-- actually works here, confirmed via /gtprofdebug's real output: skills
-- are a flat, ordered list of section HEADERS (isHeader=1, rank=0) each
-- followed by their real child skill lines (isHeader=nil, real rank/
-- maxRank) until the next header - "Professions" (index 5 in the real
-- dump) was directly followed by Herbalism (375/375) and Mining (375/375),
-- an exact match against her real in-game Skills panel. TRADE_SKILLS is
-- the real Blizzard global for the localized "Professions" header string
-- (avoids hardcoding the English word); falls back to the literal string
-- if that global isn't present for some reason.
local PROFESSIONS_HEADER = TRADE_SKILLS or "Professions"

local function DumpProfessions()
    local result = {}
    if not GetNumSkillLines then
        return result
    end
    local inProfessionsSection = false
    for i = 1, GetNumSkillLines() do
        local skillName, isHeader, _, skillRank, _, _, skillMaxRank = GetSkillLineInfo(i)
        if isHeader then
            inProfessionsSection = (skillName == PROFESSIONS_HEADER)
        elseif inProfessionsSection and skillName then
            table.insert(result, { name = skillName, level = skillRank, maxLevel = skillMaxRank })
        end
    end
    return result
end

-- englishClass/englishRace (not the localized display name) so this stays
-- comparable regardless of the client's UI language - matches the spirit of
-- how the sim/DB already key everything off stable English tokens, not
-- display strings. UnitFactionGroup returns "Alliance"/"Horde" directly,
-- needed for the Absolute BiS Simulator's faction-gated eligibility.
local function DumpIdentity()
    local _, classToken = UnitClass("player")
    local _, raceToken = UnitRace("player")
    return {
        name = UnitName("player"),
        realm = GetRealmName(),
        class = classToken,
        race = raceToken,
        faction = UnitFactionGroup("player"),
        level = UnitLevel("player"),
        professions = DumpProfessions(),
    }
end

local function DumpContainers(containers)
    local items = {}
    for _, bagId in ipairs(containers) do
        local numSlots = C_Container.GetContainerNumSlots(bagId)
        for slotId = 1, numSlots do
            local itemLink = C_Container.GetContainerItemLink(bagId, slotId)
            if itemLink then
                local _, itemId, enchantId, gemId1, gemId2, gemId3, gemId4 = strsplit(":", itemLink)
                table.insert(items, {
                    id = tonumber(itemId),
                    enchant = tonumber(enchantId) or 0,
                    gems = { tonumber(gemId1) or 0, tonumber(gemId2) or 0, tonumber(gemId3) or 0, tonumber(gemId4) or 0 },
                })
            end
        end
    end
    return items
end

local function BagContainers()
    local containers = {}
    for i = 0, NUM_BAG_SLOTS do
        table.insert(containers, i)
    end
    return containers
end

local function BankContainers()
    local containers = { -1 }
    for i = 1, (NUM_BANKBAGSLOTS or 6) do
        table.insert(containers, i + NUM_BAG_SLOTS)
    end
    return containers
end

local function CharKey()
    return UnitName("player") .. "-" .. GetRealmName()
end

local function Entry()
    local key = CharKey()
    GTCompanionDB[key] = GTCompanionDB[key]
        or { bags = {}, bank = {}, reputation = {}, arena = {}, identity = {}, timestamp = 0 }
    return GTCompanionDB[key]
end

-- Every character this addon has ever saved on this account, most-recently-
-- saved first - the actual data behind the "list showing all saved data with
-- timestamps" view. Reads whatever's already in GTCompanionDB; doesn't touch
-- other accounts' SavedVariables (out of reach from in-game Lua anyway).
local function AllCharacters()
    local list = {}
    for key, entry in pairs(GTCompanionDB) do
        table.insert(list, {
            key = key, identity = entry.identity or {}, timestamp = entry.timestamp or 0,
            wse_export_trigger = entry.wse_export_trigger,
        })
    end
    table.sort(list, function(a, b) return a.timestamp > b.timestamp end)
    return list
end

-- Real bug, found by the user AGAIN after the first fix attempt: bank bag
-- -1's SLOT COUNT is static (known to the client whether the bank is open
-- or not, since it's just "how many slots you've purchased"), so
-- GetContainerNumSlots(-1) == 0 never actually happens and never caught
-- "bank is closed" - only the per-slot ITEM LINKS go nil while closed,
-- which is what let a closed-bank save through and overwrite the last
-- good snapshot with an all-empty scan. Tracking real open/closed state
-- via BANKFRAME_OPENED/BANKFRAME_CLOSED events instead - not inferring it
-- from container data at all - is the actual fix.
--
-- MOVED here 2026-08-24 (was declared much later in the file, after
-- SaveBank() already referenced it): Lua has no hoisting - a `local`
-- declared later in a chunk is NOT visible to code textually written
-- before it, even in the same file. SaveBank() (below) was compiled
-- against a plain GLOBAL `bankIsOpen` (always nil, since every real
-- assignment targeted the local declared afterward), so `if not
-- bankIsOpen` was always true and SaveBank() always returned immediately
-- without saving anything - the exact bug this whole fix was written to
-- prevent, silently reintroduced by variable ordering. Not live-verified
-- that this was actually happening (no Lua interpreter available to
-- confirm outside the game client) - worth confirming for real in-game
-- (open the bank, /gtexport, check entry.bank isn't empty) now that the
-- declaration is in the right place.
local bankIsOpen = false

-- Bank containers only read valid data while the bank frame is open, so
-- bank is only ever re-scanned on BANKFRAME_OPENED; bags update on their
-- own event and must not overwrite the last-known bank snapshot.
local function SaveBags()
    local entry = Entry()
    entry.bags = DumpContainers(BagContainers())
    entry.timestamp = time()
end

-- Real bug, found by the user: SaveAll() (from /gtexport, a minimap
-- click, or the status panel button) called this unconditionally, and
-- bank container slots read as EMPTY whenever the bank frame isn't
-- currently open - so any manual save done outside the bank silently
-- overwrote the last good bank snapshot with zero items. Checking bank
-- bag -1's slot count directly (rather than a specific frame's
-- IsShown(), whose exact name isn't confirmed on this client) tests the
-- actual precondition: it reads 0 exactly when bank data isn't valid to
-- read, in which case this leaves entry.bank untouched instead of
-- clobbering it.
local function SaveBank()
    if not bankIsOpen then
        return
    end
    local entry = Entry()
    entry.bank = DumpContainers(BankContainers())
    entry.timestamp = time()
end

local function SaveReputationAndArena()
    local entry = Entry()
    entry.reputation = DumpReputation()
    entry.arena = DumpArena()
    entry.timestamp = time()
end

local function SaveIdentity()
    local entry = Entry()
    entry.identity = DumpIdentity()
    entry.timestamp = time()
end

-- Triggers WowSimsExporter's own real auto-save path directly, instead of
-- faking a UI interaction - WSE (confirmed by reading its real installed
-- source this session, WowSimsExporter.lua/SavedDataManager.lua) only
-- registers its gear/talent/enchant/glyph CHANGE listeners on initial
-- login; it never actually calls its own save function just from logging
-- in. A character who logs in and changes nothing that session never gets
-- freshly exported at all - confirmed as the real cause of a stale export
-- hit earlier this session (Lerynia's most recent WSE data had 0 gear).
--
-- WowSimsExporter is an AceAddon-3.0 addon (`LibStub("AceAddon-3.0"):
-- NewAddon("WowSimsExporter", ...)`, confirmed in its own source) - its
-- addon object is a `local` in WSE's own file, NOT a plain global, but
-- AceAddon-3.0's own documented `GetAddon(name)` is the real, standard way
-- any other addon retrieves it (LibStub itself IS a real shared global
-- once any Ace3-based addon has loaded, which WSE will have by the time
-- PLAYER_ENTERING_WORLD fires regardless of load order). Calling its real
-- `OnCharacterChanged("...")` method reuses WSE's own already-tested save
-- logic - which itself respects the user's real WSE settings
-- (autoSaveEnabled, supportedClasses, max-level gating - see
-- SavedDataManager.lua:OnCharacterChanged) rather than forcing a save WSE
-- itself wouldn't have made.
--
-- NOT LIVE-TESTED - written from reading WSE's real source, not guessed,
-- but never actually run in-game. Verify: log in, check /gtlist shows a
-- recent wse_export_trigger, and confirm WSE's OWN SavedVariables
-- timestamp for this character actually advanced too (open WowSimsExporter.lua
-- SavedVariables and check savedCharacters' timestamp, or just re-run
-- `gear sync` and see equipped items are no longer stale).
-- REAL BUG hit live 2026-08-24, fixed here: calling this at PLAYER_ENTERING_WORLD
-- reached WowSimsExporter's real OnCharacterChanged -> FillForExport ->
-- CreateTalentString -> GetNumTalents exactly as intended (confirmed by the
-- user's own in-game error frame trace matching this call chain precisely) -
-- but crashed INSIDE WSE's own extras.lua:49 ("attempt to get length of field
-- '?' (a nil value)"), the same "some Blizzard API isn't populated yet this
-- early after login" class of bug this addon has already hit itself with the
-- reputation panel. Two real fixes, not just one: (1) wse:OnCharacterChanged()
-- is now pcall-wrapped - without this, an uncaught error INSIDE WSE's code
-- would abort the rest of THIS function's caller too, silently skipping the
-- C_Timer.After(5, SaveReputationAndArena) call that follows it in the
-- PLAYER_ENTERING_WORLD handler - a real, separate consequence of the crash,
-- not just a cosmetic error message. (2) The call itself moves behind a
-- C_Timer.After delay at the call site (see PLAYER_ENTERING_WORLD below),
-- same reasoning already used for reputation - gives the client a moment to
-- finish warming up before asking WSE to read talent data.
local function TriggerWSEExport()
    local entry = Entry()
    if not LibStub then
        entry.wse_export_trigger = { ok = false, reason = "LibStub not found", at = time() }
        return
    end
    local libOk, aceAddon = pcall(LibStub, "AceAddon-3.0", true)
    if not libOk or not aceAddon then
        entry.wse_export_trigger = { ok = false, reason = "AceAddon-3.0 not found", at = time() }
        return
    end
    local wse = aceAddon:GetAddon("WowSimsExporter", true)
    if not wse or not wse.OnCharacterChanged then
        entry.wse_export_trigger = { ok = false, reason = "WowSimsExporter addon not found/loaded", at = time() }
        return
    end
    local callOk, err = pcall(wse.OnCharacterChanged, wse, "GearingToolCompanionLogin")
    if not callOk then
        entry.wse_export_trigger = { ok = false, reason = "WSE internal error: " .. tostring(err), at = time() }
        return
    end
    entry.wse_export_trigger = { ok = true, at = time() }
end

local function SaveAll()
    SaveBags()
    SaveBank()
    SaveReputationAndArena()
    SaveIdentity()
end

-- A chat print alone is easy to miss (scrolls away, chat window may not
-- even be visible) - UIErrorsFrame is the same floating on-screen text
-- Blizzard uses for things like "You are out of range", much harder to
-- miss than chat, used here for anything the user manually triggered
-- (slash command, minimap button click) where "did that actually work?"
-- matters. Passive/automatic saves (bag update, login) stay chat-only.
local function Announce(message)
    print(("[GearingToolCompanion] %s"):format(message))
    UIErrorsFrame:AddMessage(("GearingToolCompanion: %s"):format(message), 0.2, 1.0, 0.2, 1.0)
end

-- Throttled like WowSimsExporter's own auto-save (SavedDataManager.lua,
-- AUTO_SAVE_THROTTLE) - these events can all fire repeatedly in a burst
-- (a loot window with several items, several reputation ticks from one
-- kill, a full arena roster update) and there's no need to write to disk
-- more than once a second per category.
local BAG_SAVE_THROTTLE = 1
local lastBagSave = 0
local REP_ARENA_SAVE_THROTTLE = 1
local lastRepArenaSave = 0
local IDENTITY_SAVE_THROTTLE = 1
local lastIdentitySave = 0

-- C_Reputation.GetNumFactions() can return 0 until the reputation panel
-- has actually been shown at least once this session - a known Blizzard
-- API quirk (the backing list isn't populated until the panel itself
-- initializes it), not something UPDATE_FACTION alone catches, since
-- that only fires on an actual standing CHANGE, not on first becoming
-- readable. ReputationFrame itself may not exist yet at addon-load time
-- (it belongs to a separately, lazily-loaded Blizzard UI addon) - hooked
-- both immediately (covers a session where it's already open/loaded) and
-- again on ADDON_LOADED (covers the frame not existing yet at login).
local reputationFrameHooked = false
local function HookReputationFrame()
    if not reputationFrameHooked and ReputationFrame then
        reputationFrameHooked = true
        ReputationFrame:HookScript("OnShow", SaveReputationAndArena)
    end
end

-- Real diagnostic confirmed 2026-08-24: GetProfessions() returned all-nil
-- for a character with real, confirmed Herbalism 375/375 + Mining 375/375
-- (verified via /gtprofdebug against her own real Skills panel) - not a
-- signature mismatch, the function returned nothing at all. Same shape as
-- the ReputationFrame quirk above (backing data not populated until the
-- relevant panel has actually been shown this session), applied here on
-- the same reasoning, not re-verified independently yet - SkillFrame is
-- this client's real Classic-era skills panel name by convention (same
-- uncertainty flagged as ReputationFrame's own name above - not confirmed
-- on this specific client, hooked defensively so a wrong name just no-ops
-- rather than erroring).
local skillFrameHooked = false
local function HookSkillsFrame()
    if not skillFrameHooked and SkillFrame then
        skillFrameHooked = true
        SkillFrame:HookScript("OnShow", SaveIdentity)
    end
end

local f = CreateFrame("Frame")
f:RegisterEvent("BANKFRAME_OPENED")
f:RegisterEvent("BANKFRAME_CLOSED")
f:RegisterEvent("PLAYER_ENTERING_WORLD")
f:RegisterEvent("BAG_UPDATE_DELAYED")
f:RegisterEvent("ADDON_LOADED")
-- Reputation/arena rating change on their own during normal play, so
-- also catch real CHANGES (not just "the panel became readable", handled
-- above by the ReputationFrame hook) - e.g. reputation gained from a
-- quest turn-in updates this even if the reputation panel never gets
-- opened again this session.
f:RegisterEvent("UPDATE_FACTION")
f:RegisterEvent("ARENA_TEAM_UPDATE")
f:RegisterEvent("ARENA_TEAM_ROSTER_UPDATE")
-- Identity is mostly static but level and profession skill do change during
-- normal play - SKILL_LINES_CHANGED fires for any skill (including both
-- professions) leveling up, PLAYER_LEVEL_UP for character level.
f:RegisterEvent("PLAYER_LEVEL_UP")
f:RegisterEvent("SKILL_LINES_CHANGED")
f:SetScript("OnEvent", function(_, event)
    if event == "BANKFRAME_OPENED" then
        bankIsOpen = true
        SaveAll()
        local entry = Entry()
        print(("[GearingToolCompanion] Saved %d bag + %d bank items."):format(#entry.bags, #entry.bank))
    elseif event == "BANKFRAME_CLOSED" then
        bankIsOpen = false
    elseif event == "PLAYER_ENTERING_WORLD" then
        -- Bank needs the bank frame open to read valid data, arena is
        -- always readable, reputation MAY be empty until the reputation
        -- panel has been shown this session (see HookReputationFrame) -
        -- still worth trying here since it may already be warm from a
        -- previous /reload rather than a fresh login. Also retried a few
        -- seconds later regardless of any panel - the ReputationFrame
        -- hook depends on knowing the right frame name (unconfirmed on
        -- this client, still showing 0 even after reopening the tab), so
        -- this doesn't rely on that at all: just gives the client a
        -- moment to finish warming up its own faction data after login,
        -- independent of any UI being shown.
        SaveBags()
        SaveReputationAndArena()
        SaveIdentity()
        C_Timer.After(5, SaveReputationAndArena)
        -- Delayed, not called immediately here - real crash hit live inside
        -- WSE's own talent-reading code when triggered at this exact moment
        -- (see TriggerWSEExport's own comment for the full story and the
        -- pcall fix that's the actual safety net; this delay is the second,
        -- complementary fix - give WSE's own data more time to be ready).
        C_Timer.After(5, TriggerWSEExport)
    elseif event == "BAG_UPDATE_DELAYED" then
        local now = time()
        if now - lastBagSave < BAG_SAVE_THROTTLE then return end
        lastBagSave = now
        SaveBags()
    elseif event == "UPDATE_FACTION" or event == "ARENA_TEAM_UPDATE" or event == "ARENA_TEAM_ROSTER_UPDATE" then
        local now = time()
        if now - lastRepArenaSave < REP_ARENA_SAVE_THROTTLE then return end
        lastRepArenaSave = now
        SaveReputationAndArena()
    elseif event == "PLAYER_LEVEL_UP" or event == "SKILL_LINES_CHANGED" then
        local now = time()
        if now - lastIdentitySave < IDENTITY_SAVE_THROTTLE then return end
        lastIdentitySave = now
        SaveIdentity()
    elseif event == "ADDON_LOADED" then
        HookReputationFrame()
        HookSkillsFrame()
    end
end)

HookReputationFrame()  -- covers a session where the reputation panel was already loaded/shown
HookSkillsFrame()      -- same, for professions - see HookSkillsFrame's own comment

SLASH_GTEXPORT1 = "/gtexport"
SlashCmdList["GTEXPORT"] = function()
    SaveAll()
    Announce("Saved.")
end

-- Real diagnostic, not another guess: a live screenshot showed
-- "Professions: none captured" for a character with real, confirmed
-- Herbalism 375/375 and Mining 375/375 (visible in her own Skills panel),
-- meaning GetProfessions()/GetProfessionInfo() aren't behaving as
-- documented on this client - the same class of surprise this addon has
-- already hit twice (C_Reputation not existing, the arena team API).
-- Rather than guess a third fix blind, this prints the real raw return
-- values to chat so the actual shape can be seen and DumpProfessions()
-- fixed against real data.
SLASH_GTPROFDEBUG1 = "/gtprofdebug"
SlashCmdList["GTPROFDEBUG"] = function()
    local prof1, prof2, archaeology, fishing, cooking, firstAid = GetProfessions()
    print(("[GTDebug] GetProfessions() -> prof1=%s prof2=%s archaeology=%s fishing=%s cooking=%s firstAid=%s"):format(
        tostring(prof1), tostring(prof2), tostring(archaeology), tostring(fishing), tostring(cooking), tostring(firstAid)))
    for _, index in ipairs({ prof1, prof2, archaeology, fishing, cooking, firstAid }) do
        if index then
            local name, icon, skillLevel, maxSkillLevel, numAbilities, spelloffset, skillLine,
                  rank, modifier = GetProfessionInfo(index)
            print(("[GTDebug] GetProfessionInfo(%d) -> name=%s icon=%s skillLevel=%s maxSkillLevel=%s "
                .. "numAbilities=%s spelloffset=%s skillLine=%s rank=%s modifier=%s"):format(
                index, tostring(name), tostring(icon), tostring(skillLevel), tostring(maxSkillLevel),
                tostring(numAbilities), tostring(spelloffset), tostring(skillLine), tostring(rank), tostring(modifier)))
        end
    end
    -- Fallback data source, added after GetProfessions() came back all-nil
    -- for a character with real, confirmed professions - GetNumSkillLines/
    -- GetSkillLineInfo is the more general skill API professions are
    -- technically a subset of; useful cross-reference if the
    -- SkillFrame-hook fix (see HookSkillsFrame) doesn't resolve this.
    if GetNumSkillLines then
        print(("[GTDebug] GetNumSkillLines() -> %d"):format(GetNumSkillLines()))
        for i = 1, GetNumSkillLines() do
            local skillName, isHeader, isExpanded, skillRank, _, _, skillMaxRank = GetSkillLineInfo(i)
            print(("[GTDebug] GetSkillLineInfo(%d) -> name=%s isHeader=%s rank=%s maxRank=%s"):format(
                i, tostring(skillName), tostring(isHeader), tostring(skillRank), tostring(skillMaxRank)))
        end
    else
        print("[GTDebug] GetNumSkillLines does not exist on this client either.")
    end
    print("[GTDebug] Done - copy the lines above and share them so DumpProfessions() can be fixed against the real data.")
end

-- ============================================================
-- Minimap button + status panel - for less technical users who
-- won't remember or want to type a slash command. Both just call
-- the same SaveAll() everything else already uses; no new backend.
-- ============================================================

-- 200 (not 215) on purpose - 215 is a very common default among other
-- addons' hand-rolled minimap buttons (no shared positioning library
-- here), and stacking exactly on top of one of those is exactly what
-- ate the tooltip/click the first time around (whichever button is on
-- top at a given point gets ALL the mouse input, not just the top
-- pixels). Strata/level raised well above the MEDIUM/8 combo most of
-- those buttons default to, so this one wins the stacking order even
-- if something else still lands nearby. If it's ever still hidden
-- behind another button, hold-drag should still work since dragging
-- only needs the initial mousedown to land on visible pixels, and it
-- can always be pulled to a clear spot - but this should no longer be
-- necessary.
GTCompanionMinimapDB = GTCompanionMinimapDB or { angle = 200 }

local minimapButton = CreateFrame("Button", "GTCompanionMinimapButton", Minimap)
minimapButton:SetSize(31, 31)
minimapButton:SetFrameStrata("HIGH")
minimapButton:SetFrameLevel(20)
minimapButton:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
minimapButton:RegisterForClicks("LeftButtonUp", "RightButtonUp")
minimapButton:RegisterForDrag("LeftButton")
minimapButton:SetMovable(true)

-- Custom badge instead of a stock icon texture. The bow icon was already
-- picked up correctly by the minimap-button collector addon, so this
-- isn't a detection problem - but a plain "R" reads clearer at icon size
-- and is harder to mistake for someone else's button in a crowded
-- popout. No external texture file needed - just a solid background
-- plus a FontString, both plain Lua/UI, nothing to ship.
local iconBg = minimapButton:CreateTexture(nil, "BACKGROUND")
iconBg:SetSize(20, 20)
iconBg:SetPoint("CENTER", minimapButton, "CENTER", 0, 0)
iconBg:SetColorTexture(0.10, 0.09, 0.07, 1)

local iconLetter = minimapButton:CreateFontString(nil, "ARTWORK", "GameFontNormalLarge")
-- "R" has no descender, so a FontString's CENTER anchor (which centers the
-- whole line-height box, descender space included) leaves the visible
-- glyph sitting slightly above true center - nudged down 1px to compensate.
iconLetter:SetPoint("CENTER", minimapButton, "CENTER", 0, -1)
iconLetter:SetText("R")
iconLetter:SetTextColor(0.90, 0.70, 0.25, 1)

local overlay = minimapButton:CreateTexture(nil, "OVERLAY")
overlay:SetSize(53, 53)
overlay:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
overlay:SetPoint("TOPLEFT", 0, 0)

local function UpdateMinimapButtonPosition()
    local angle = math.rad(GTCompanionMinimapDB.angle or 200)
    local x, y = 80 * math.cos(angle), 80 * math.sin(angle)
    minimapButton:ClearAllPoints()
    minimapButton:SetPoint("CENTER", Minimap, "CENTER", x, y)
end

minimapButton:SetScript("OnDragStart", function(self)
    self:SetScript("OnUpdate", function()
        local mx, my = Minimap:GetCenter()
        local px, py = GetCursorPosition()
        local scale = Minimap:GetEffectiveScale()
        px, py = px / scale, py / scale
        GTCompanionMinimapDB.angle = math.deg(math.atan2(py - my, px - mx))
        UpdateMinimapButtonPosition()
    end)
end)
minimapButton:SetScript("OnDragStop", function(self)
    self:SetScript("OnUpdate", nil)
end)

-- Small status panel: shows what's actually been captured, not just a
-- print - lets a non-technical user SEE it worked instead of trusting a
-- chat message that scrolls away. Built with plain, long-stable
-- templates (UIPanelButtonTemplate/UIPanelCloseButton, manual backdrop)
-- rather than newer frame templates not confirmed present on this
-- TBC Anniversary client build.
local statusFrame = CreateFrame("Frame", "GTCompanionStatusFrame", UIParent,
    BackdropTemplateMixin and "BackdropTemplate" or nil)
-- Grown from 230 - real screenshot showed the WSE-trigger line (added
-- after this size was last tuned) overlapping the buttons at the bottom,
-- since the body FontString has no fixed height and just grows downward
-- with nothing to push the buttons out of the way.
statusFrame:SetSize(260, 290)
statusFrame:SetPoint("CENTER")
statusFrame:SetFrameStrata("DIALOG")
statusFrame:SetBackdrop({
    bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
    edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
    tile = true, tileSize = 32, edgeSize = 32,
    insets = { left = 11, right = 12, top = 12, bottom = 11 },
})
statusFrame:SetMovable(true)
statusFrame:EnableMouse(true)
statusFrame:RegisterForDrag("LeftButton")
statusFrame:SetScript("OnDragStart", statusFrame.StartMoving)
statusFrame:SetScript("OnDragStop", statusFrame.StopMovingOrSizing)
statusFrame:Hide()

local closeButton = CreateFrame("Button", nil, statusFrame, "UIPanelCloseButton")
closeButton:SetPoint("TOPRIGHT", -2, -2)

local title = statusFrame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
title:SetPoint("TOP", 0, -16)
title:SetText("Gearing Tool Companion")

local body = statusFrame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
body:SetPoint("TOPLEFT", 20, -44)
body:SetJustifyH("LEFT")
body:SetWidth(220)

-- Shared by the status panel and the all-characters list - one line
-- summarizing whether/when we last tried to trigger WowSimsExporter's own
-- export on this character's behalf. `full` (default true) includes the
-- real failure reason (used in /gtlist, which has room); the compact
-- status panel passes full=false - a real failure reason can be a long
-- sentence that wraps to multiple lines at this panel's fixed width,
-- which is exactly what pushed this text down into the buttons in a real
-- screenshot before this was split out.
local function WSETriggerText(entry, full)
    local t = entry.wse_export_trigger
    if not t then
        return "WSE export: not attempted yet"
    end
    if t.ok then
        return ("WSE export: OK (%s)"):format(date("%H:%M:%S", t.at))
    end
    if full == false then
        return ("WSE export: failed (%s)"):format(date("%H:%M:%S", t.at))
    end
    return ("WSE export trigger failed (%s): %s"):format(t.reason or "?", date("%H:%M:%S", t.at))
end

local function RefreshStatusFrame()
    local entry = Entry()
    local id = entry.identity or {}
    local repCount = 0
    for _ in pairs(entry.reputation or {}) do
        repCount = repCount + 1
    end
    local lastSaved = (entry.timestamp and entry.timestamp > 0) and date("%H:%M:%S", entry.timestamp) or "never"
    local profParts = {}
    for _, p in ipairs(id.professions or {}) do
        table.insert(profParts, ("%s %d"):format(p.name, p.level or 0))
    end
    local profText = #profParts > 0 and table.concat(profParts, ", ") or "none captured"
    body:SetText(
        ("%s\n%s %s, Lv %s\nProfessions: %s\n\nBags: %d items\nBank: %d items\nReputation: %d factions tracked\nArena teams: %d\n\nLast saved: %s\n%s"):format(
            id.name and (id.name .. "-" .. (id.realm or "?")) or CharKey(),
            id.race or "?", id.class or "?", tostring(id.level or "?"),
            profText,
            #entry.bags, #entry.bank, repCount, #(entry.arena or {}), lastSaved,
            WSETriggerText(entry, false)
        )
    )
end
statusFrame:SetScript("OnShow", RefreshStatusFrame)

local saveButton = CreateFrame("Button", nil, statusFrame, "UIPanelButtonTemplate")
saveButton:SetSize(110, 24)
saveButton:SetPoint("BOTTOM", 0, 16)
saveButton:SetText("Save Now")
saveButton:SetScript("OnClick", function()
    SaveAll()
    RefreshStatusFrame()
    Announce("Saved.")
end)

-- ============================================================
-- Character list: "a list showing all saved data with timestamps" across
-- EVERY character this addon has saved on this account, not just the one
-- currently logged in - the multi-character view the status panel above
-- can't show since it only ever reads the current character's own Entry().
--
-- Rebuilt 2026-08-24 from a plain text blob into real per-character rows
-- (icon/class-colored name/realm/search), matching the user's own bag
-- addon's character-picker style shown as a reference. Uses real, standard
-- Blizzard globals for class color/icon (RAID_CLASS_COLORS,
-- CLASS_ICON_TCOORDS, SearchBoxTemplate/SEARCH_BOX_TEMPLATE_INSTRUCTIONS) -
-- the same ones the default character/guild UI and search boxes use, not
-- hand-rolled. NOT LIVE-TESTED - written from documented Blizzard API, but
-- this file has real precedent for this exact client behaving differently
-- than documented (C_Reputation, the profession API just found not to
-- match either) - verify for real in-game: open /gtlist, confirm class
-- icons/colors render (not the raw unmasked icon sheet), confirm typing in
-- the search box actually filters rows, confirm clicking a row highlights
-- it without error.
-- ============================================================

local charListFrame = CreateFrame("Frame", "GTCompanionCharacterListFrame", UIParent,
    BackdropTemplateMixin and "BackdropTemplate" or nil)
charListFrame:SetSize(420, 420)
charListFrame:SetPoint("CENTER")
charListFrame:SetFrameStrata("DIALOG")
charListFrame:SetBackdrop({
    bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
    edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
    tile = true, tileSize = 32, edgeSize = 32,
    insets = { left = 11, right = 12, top = 12, bottom = 11 },
})
charListFrame:SetMovable(true)
charListFrame:EnableMouse(true)
charListFrame:RegisterForDrag("LeftButton")
charListFrame:SetScript("OnDragStart", charListFrame.StartMoving)
charListFrame:SetScript("OnDragStop", charListFrame.StopMovingOrSizing)
charListFrame:Hide()

local charListClose = CreateFrame("Button", nil, charListFrame, "UIPanelCloseButton")
charListClose:SetPoint("TOPRIGHT", -2, -2)

local charListTitle = charListFrame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
charListTitle:SetPoint("TOP", 0, -16)
charListTitle:SetText("Saved Characters")

-- SearchBoxTemplate is a real, standard Blizzard template (used by the
-- default UI's own bag/auction/etc search fields) - filters the row list
-- by name/realm as you type, matching the reference addon's own search box.
local charSearchBox = CreateFrame("EditBox", "GTCompanionCharSearchBox", charListFrame, "SearchBoxTemplate")
charSearchBox:SetSize(360, 20)
charSearchBox:SetPoint("TOP", 0, -42)

-- Standard Blizzard scroll template (same stability reasoning as
-- UIPanelButtonTemplate/UIPanelCloseButton elsewhere in this file) - the
-- character count here is expected to stay small (a handful of alts), but a
-- real scrollbar costs nothing and means this never silently clips.
local charScroll = CreateFrame("ScrollFrame", "GTCompanionCharListScroll", charListFrame, "UIPanelScrollFrameTemplate")
charScroll:SetPoint("TOPLEFT", 16, -70)
charScroll:SetPoint("BOTTOMRIGHT", -34, 16)

local charListBody = CreateFrame("Frame", nil, charScroll)
charListBody:SetSize(300, 1)
charScroll:SetScrollChild(charListBody)

-- englishClass is stored lowercase (WSE's own convention, e.g. "hunter") -
-- RAID_CLASS_COLORS/CLASS_ICON_TCOORDS (real, standard Blizzard globals,
-- the same ones the default character/guild UI uses - not a hand-rolled
-- color table) are keyed by the UPPERCASE English token.
local ROW_HEIGHT = 54
local selectedRowKey = nil
local charListRows = {}  -- reusable frame pool, indexed 1..N - never recreated per refresh

local function GetRow(index)
    local row = charListRows[index]
    if row then return row end

    row = CreateFrame("Button", nil, charListBody)
    row:SetSize(300, ROW_HEIGHT)
    row:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight")

    row.bg = row:CreateTexture(nil, "BACKGROUND")
    row.bg:SetAllPoints()
    row.bg:SetColorTexture(1, 1, 1, 0.04)

    row.icon = row:CreateTexture(nil, "ARTWORK")
    row.icon:SetSize(36, 36)
    row.icon:SetPoint("LEFT", 6, 0)
    row.icon:SetTexture("Interface\\TargetingFrame\\UI-Classes-Circles")

    row.name = row:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    row.name:SetPoint("TOPLEFT", row.icon, "TOPRIGHT", 8, -2)
    row.name:SetJustifyH("LEFT")

    row.realm = row:CreateFontString(nil, "OVERLAY", "GameFontDisable")
    row.realm:SetPoint("LEFT", row.name, "RIGHT", 4, 0)
    row.realm:SetJustifyH("LEFT")

    row.subtext = row:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    row.subtext:SetPoint("TOPLEFT", row.icon, "TOPRIGHT", 8, -18)
    row.subtext:SetPoint("RIGHT", row, "RIGHT", -6, 0)
    row.subtext:SetJustifyH("LEFT")
    row.subtext:SetWordWrap(false)

    row.wseLine = row:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    row.wseLine:SetPoint("TOPLEFT", row.icon, "TOPRIGHT", 8, -34)
    -- Real bug from a live screenshot: this FontString had no right-edge
    -- constraint (unlike row.subtext, which does), so a long line just ran
    -- past the row/frame edge and got clipped mid-word ("WSE ex...")
    -- instead of truncating cleanly with an ellipsis.
    row.wseLine:SetPoint("RIGHT", row, "RIGHT", -6, 0)
    row.wseLine:SetJustifyH("LEFT")
    row.wseLine:SetWordWrap(false)

    row:SetScript("OnClick", function(self)
        selectedRowKey = self.charKey
        for _, r in ipairs(charListRows) do
            r.bg:SetColorTexture(1, 1, 1, r.charKey == selectedRowKey and 0.10 or 0.04)
        end
        -- No detail view yet (character-list polish only, per plan) - the
        -- per-row selection state above is kept so a future "show this
        -- character's bags/bank" panel has a real hook to build on top of.
    end)

    charListRows[index] = row
    return row
end

local function RefreshCharacterList()
    -- SearchBoxTemplate's placeholder/instructions text is a separate
    -- overlay FontString, not real EditBox content - :GetText() reliably
    -- returns "" when nothing's been typed, no need to also compare
    -- against SEARCH_BOX_TEMPLATE_INSTRUCTIONS (removed: comparing it
    -- against a lowercased filter would never match anyway, a real bug
    -- caught in review before this shipped).
    local filter = charSearchBox:GetText():lower()
    if filter == "" then
        filter = nil
    end

    local chars = AllCharacters()
    local shown = 0
    for _, c in ipairs(chars) do
        local id = c.identity or {}
        local label = id.name and (id.name .. "-" .. (id.realm or "?")) or c.key
        if not filter or label:lower():find(filter, 1, true) then
            shown = shown + 1
            local row = GetRow(shown)
            row.charKey = c.key
            row:SetPoint("TOPLEFT", 0, -(shown - 1) * ROW_HEIGHT)
            row:Show()
            row.bg:SetColorTexture(1, 1, 1, c.key == selectedRowKey and 0.10 or 0.04)

            local classToken = id.class and id.class:upper()
            local classColor = classToken and RAID_CLASS_COLORS[classToken]
            local coords = classToken and CLASS_ICON_TCOORDS[classToken]
            if coords then
                -- unpack (not table.unpack) - this client's Lua runtime is
                -- 5.1-based, unpack is the correct global there.
                row.icon:SetTexCoord(unpack(coords))
                row.icon:Show()
            else
                -- Unknown class (identity not captured yet) - hide rather
                -- than show the full unmasked class-icon sheet, which
                -- looks like a rendering bug, not a real "no icon" state.
                row.icon:Hide()
            end

            row.name:SetText(id.name or c.key)
            if classColor then
                row.name:SetTextColor(classColor.r, classColor.g, classColor.b)
            else
                row.name:SetTextColor(1, 1, 1)
            end
            row.realm:SetText(id.realm and ("- " .. id.realm) or "")

            local raceClass = (id.race or id.class) and ("%s %s"):format(id.race or "?", id.class or "?") or "identity not captured yet"
            local levelText = id.level and (" · Lv " .. id.level) or ""
            row.subtext:SetText(raceClass .. levelText)

            local profParts = {}
            for _, p in ipairs(id.professions or {}) do
                table.insert(profParts, ("%s %d"):format(p.name, p.level or 0))
            end
            local profText = #profParts > 0 and table.concat(profParts, ", ") or "no professions captured"
            local when = c.timestamp > 0 and date("%H:%M", c.timestamp) or "never"
            -- Ultra-compact here on purpose (no timestamp on the WSE part -
            -- the row already has one via "saved %s") - the fuller
            -- WSETriggerText() forms were still too long for this row
            -- width even with the right-edge fix above, per a real
            -- screenshot showing "WSE ex..." getting clipped.
            local wseShort = "WSE: not tried"
            local trig = c.wse_export_trigger
            if trig then
                wseShort = trig.ok and "WSE: OK" or "WSE: failed"
            end
            row.wseLine:SetText(("%s · saved %s · %s"):format(profText, when, wseShort))
        end
    end

    for i = shown + 1, #charListRows do
        charListRows[i]:Hide()
    end

    if shown == 0 then
        local row = GetRow(1)
        row.charKey = nil
        row:SetPoint("TOPLEFT", 0, 0)
        row:Show()
        row.icon:Hide()
        row.name:SetText(#chars == 0 and "No characters saved yet." or "No characters match your search.")
        row.name:SetTextColor(0.6, 0.6, 0.6)
        row.realm:SetText("")
        row.subtext:SetText("")
        row.wseLine:SetText("")
        shown = 1
    end

    charListBody:SetHeight(math.max(shown * ROW_HEIGHT, 1))
end
charSearchBox:SetScript("OnTextChanged", function(self)
    SearchBoxTemplate_OnTextChanged(self)
    RefreshCharacterList()
end)
charListFrame:SetScript("OnShow", RefreshCharacterList)

SLASH_GTLIST1 = "/gtlist"
SlashCmdList["GTLIST"] = function()
    if charListFrame:IsShown() then
        charListFrame:Hide()
    else
        charListFrame:Show()
    end
end

local listButton = CreateFrame("Button", nil, statusFrame, "UIPanelButtonTemplate")
listButton:SetSize(140, 24)
listButton:SetPoint("BOTTOM", 0, 46)
listButton:SetText("All Characters")
listButton:SetScript("OnClick", function()
    charListFrame:Show()
end)

minimapButton:SetScript("OnClick", function(_, button)
    if button == "LeftButton" then
        if statusFrame:IsShown() then
            statusFrame:Hide()
        else
            statusFrame:Show()
        end
    else
        SaveAll()
        Announce("Saved.")
    end
end)

minimapButton:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:SetText("Gearing Tool Companion")
    GameTooltip:AddLine("Left-click: Show status", 1, 1, 1)
    GameTooltip:AddLine("Right-click: Save now", 1, 1, 1)
    GameTooltip:AddLine("/gtlist: All saved characters", 1, 1, 1)
    GameTooltip:Show()
end)
minimapButton:SetScript("OnLeave", function()
    GameTooltip:Hide()
end)

UpdateMinimapButtonPosition()
