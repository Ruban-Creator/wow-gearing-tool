; Ruban's Gearing Tool (RGT) installer (Inno Setup 6). Real payload trimmed
; 2026-08-30 after confirming (by grepping core/adapters/gui for actual
; reads) what the running app needs from sim/tbc-new/ at runtime: only
; assets/database/db.json (item lookups) and sim/**/*.go (core/set_bonus.py's
; own per-class text parser) - db.bin is embedded into wowsimcli.exe/
; simserver.exe at BUILD time (go:embed), never read from disk at runtime,
; and ui/, proto/, cmd/, docs/, tools/ are only touched by dev-only
; profile-building scripts, never by a real sweep. That's ~8.5MB out of the
; submodule's real 237MB working tree.
;
; Per-user install (no admin/UAC needed) - matches this being an early-stage
; personal tool heading toward wider sharing, not an enterprise deployment.
; Production Data lives entirely separately, under %LOCALAPPDATA%\GearingTool\
; (core/repo_root.py's USER_DATA_DIR) - untouched by install/uninstall either
; way, so an uninstall-then-reinstall (or an update) never loses real data.
;
; Build from repo root:
;   "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" packaging\installer.iss
; Output: packaging\output\RGT-Setup.exe

#define AppName "Ruban's Gearing Tool"
#define AppPublisher "Ruban-Creator"
#define AppURL "https://github.com/Ruban-Creator/wow-gearing-tool"
#define AppExeName "RGT.exe"
; Real app version - read from build/bin/sim_version_label.txt at compile
; time so the installer's own version always matches whatever sim build it
; actually contains, never hand-maintained/guessed separately.
#define AppVersion Trim(FileRead(FileOpen(SourcePath + "..\build\bin\sim_version_label.txt")))

[Setup]
AppId={{B4E3A6F1-6C6B-4A6E-9C3A-3B7C6C7A0F00}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={localappdata}\Programs\RubansGearingTool
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=RGT-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
; Real branding art (2026-08-30) - see ..\branding\source\ for the two
; original commissioned images these were cropped/composed from.
SetupIconFile=..\branding\app_icon.ico
WizardImageFile=..\branding\wizard_image.bmp
WizardSmallImageFile=..\branding\wizard_small_image.bmp
UninstallDisplayIcon={app}\build\dist\{#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\build\dist\{#AppExeName}"; DestDir: "{app}\build\dist"; Flags: ignoreversion
Source: "..\build\bin\*"; DestDir: "{app}\build\bin"; Flags: ignoreversion recursesubdirs
Source: "..\core\*.py"; DestDir: "{app}\core"; Flags: ignoreversion
Source: "..\core\report_template.html"; DestDir: "{app}\core"; Flags: ignoreversion
Source: "..\ingest\*.py"; DestDir: "{app}\ingest"; Flags: ignoreversion
Source: "..\adapters\tbc\*.py"; DestDir: "{app}\adapters\tbc"; Flags: ignoreversion
Source: "..\profiles\tbc\*"; DestDir: "{app}\profiles\tbc"; Flags: ignoreversion recursesubdirs
Source: "..\sim\tbc-new\assets\database\db.json"; DestDir: "{app}\sim\tbc-new\assets\database"; Flags: ignoreversion
Source: "..\sim\tbc-new\sim\*"; DestDir: "{app}\sim\tbc-new\sim"; Flags: ignoreversion recursesubdirs
Source: "..\addons\GearingToolCompanion\*"; DestDir: "{app}\addons\GearingToolCompanion"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\build\dist\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\build\dist\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\build\dist\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
