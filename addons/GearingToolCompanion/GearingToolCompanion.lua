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
local function AddProfession(result, index)
    if not index then return end
    local name, _, skillLevel, maxSkillLevel = GetProfessionInfo(index)
    if name then
        table.insert(result, { name = name, level = skillLevel, maxLevel = maxSkillLevel })
    end
end

local function DumpProfessions()
    local result = {}
    local prof1, prof2, archaeology, fishing, cooking, firstAid = GetProfessions()
    AddProfession(result, prof1)
    AddProfession(result, prof2)
    AddProfession(result, archaeology)
    AddProfession(result, fishing)
    AddProfession(result, cooking)
    AddProfession(result, firstAid)
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
local function TriggerWSEExport()
    local entry = Entry()
    if not LibStub then
        entry.wse_export_trigger = { ok = false, reason = "LibStub not found", at = time() }
        return
    end
    local ok, aceAddon = pcall(LibStub, "AceAddon-3.0", true)
    if not ok or not aceAddon then
        entry.wse_export_trigger = { ok = false, reason = "AceAddon-3.0 not found", at = time() }
        return
    end
    local wse = aceAddon:GetAddon("WowSimsExporter", true)
    if not wse or not wse.OnCharacterChanged then
        entry.wse_export_trigger = { ok = false, reason = "WowSimsExporter addon not found/loaded", at = time() }
        return
    end
    wse:OnCharacterChanged("GearingToolCompanionLogin")
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
        TriggerWSEExport()
        C_Timer.After(5, SaveReputationAndArena)
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
    end
end)

HookReputationFrame()  -- covers a session where the reputation panel was already loaded/shown

SLASH_GTEXPORT1 = "/gtexport"
SlashCmdList["GTEXPORT"] = function()
    SaveAll()
    Announce("Saved.")
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
statusFrame:SetSize(260, 230)
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
-- export on this character's behalf, and why it didn't fire if it didn't
-- (WSE not installed, its own auto-save disabled, etc - see
-- TriggerWSEExport's real reasons above).
local function WSETriggerText(entry)
    local t = entry.wse_export_trigger
    if not t then
        return "WSE export trigger: not attempted yet"
    end
    if t.ok then
        return ("WSE export triggered: %s"):format(date("%H:%M:%S", t.at))
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
            WSETriggerText(entry)
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
-- ============================================================

local charListFrame = CreateFrame("Frame", "GTCompanionCharacterListFrame", UIParent,
    BackdropTemplateMixin and "BackdropTemplate" or nil)
charListFrame:SetSize(380, 320)
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

-- Standard Blizzard scroll template (same stability reasoning as
-- UIPanelButtonTemplate/UIPanelCloseButton elsewhere in this file) - the
-- character count here is expected to stay small (a handful of alts), but a
-- real scrollbar costs nothing and means this never silently clips.
local charScroll = CreateFrame("ScrollFrame", "GTCompanionCharListScroll", charListFrame, "UIPanelScrollFrameTemplate")
charScroll:SetPoint("TOPLEFT", 16, -44)
charScroll:SetPoint("BOTTOMRIGHT", -34, 16)

local charListBody = CreateFrame("Frame", nil, charScroll)
charListBody:SetSize(300, 1)
charScroll:SetScrollChild(charListBody)

local charListText = charListBody:CreateFontString(nil, "OVERLAY", "GameFontNormal")
charListText:SetPoint("TOPLEFT", 0, 0)
charListText:SetJustifyH("LEFT")
charListText:SetJustifyV("TOP")
charListText:SetWidth(300)

local function RefreshCharacterList()
    local chars = AllCharacters()
    local lines = {}
    for _, c in ipairs(chars) do
        local id = c.identity or {}
        local label = id.name and (id.name .. "-" .. (id.realm or "?")) or c.key
        local classRace = ("%s %s"):format(id.race or "?", id.class or "?")
        local when = c.timestamp > 0 and date("%Y-%m-%d %H:%M:%S", c.timestamp) or "never"
        local profParts = {}
        for _, p in ipairs(id.professions or {}) do
            table.insert(profParts, ("%s %d"):format(p.name, p.level or 0))
        end
        local profText = #profParts > 0 and table.concat(profParts, ", ") or "no professions captured"
        table.insert(lines, ("|cffffcc00%s|r  (%s, Lv %s)\n%s\nLast saved: %s\n%s"):format(
            label, classRace, tostring(id.level or "?"), profText, when,
            WSETriggerText({ wse_export_trigger = c.wse_export_trigger })))
    end
    if #lines == 0 then
        lines = { "No characters saved yet." }
    end
    charListText:SetText(table.concat(lines, "\n\n"))
    charListBody:SetHeight(math.max(charListText:GetStringHeight() + 10, 1))
end
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
