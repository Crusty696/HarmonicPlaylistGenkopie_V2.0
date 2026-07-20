; Inno Setup Script for Harmonic Playlist Generator v3.7.0
; Creates professional Windows installer with Desktop icon and Start Menu entry
; Download Inno Setup: https://jrsoftware.org/isdl.php

#ifndef SourceExe
  #define SourceExe "HarmonicPlaylistGenerator.exe"
#endif

[Setup]
; Application Information
AppName=Harmonic Playlist Generator
AppVersion=3.7.0
AppPublisher=HPG Team
AppPublisherURL=https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0
AppSupportURL=https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0/issues
AppUpdatesURL=https://github.com/Crusty696/HarmonicPlaylistGenkopie_V2.0/releases
DefaultDirName={autopf}\HarmonicPlaylistGenerator
DefaultGroupName=Harmonic Playlist Generator
AllowNoIcons=yes
LicenseFile=LICENSE
OutputDir=installer_output
OutputBaseFilename=HPG_v3.7.0_Setup
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\HarmonicPlaylistGenerator.exe
ArchitecturesInstallIn64BitMode=x64

; Privileges
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Visual Style
;WizardImageFile=compiler:WizModernImage-IS.bmp
;WizardSmallImageFile=compiler:WizModernSmallImage-IS.bmp

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Main executable
Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "HarmonicPlaylistGenerator.exe"; Flags: ignoreversion

; Documentation
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

; License
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion

; Requirements file (for reference)
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu
Name: "{group}\Harmonic Playlist Generator"; Filename: "{app}\HarmonicPlaylistGenerator.exe"; IconFilename: "{app}\HarmonicPlaylistGenerator.exe"; Comment: "Professional DJ Playlist Generator"
Name: "{group}\README"; Filename: "{app}\README.md"; Comment: "Documentation"
Name: "{group}\Uninstall HPG"; Filename: "{uninstallexe}"; Comment: "Uninstall Harmonic Playlist Generator"

; Desktop Icon
Name: "{autodesktop}\Harmonic Playlist Generator"; Filename: "{app}\HarmonicPlaylistGenerator.exe"; IconFilename: "{app}\HarmonicPlaylistGenerator.exe"; Tasks: desktopicon; Comment: "Professional DJ Playlist Generator"

; Quick Launch (Windows 7 and earlier)
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\Harmonic Playlist Generator"; Filename: "{app}\HarmonicPlaylistGenerator.exe"; Tasks: quicklaunchicon

[Run]
; Offer to launch app after installation
Filename: "{app}\HarmonicPlaylistGenerator.exe"; Description: "{cm:LaunchProgram,Harmonic Playlist Generator}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up cache files on uninstall
Type: filesandordirs; Name: "{app}\hpg_cache_*.db"
Type: filesandordirs; Name: "{app}\hpg_cache_*.db-wal"
Type: filesandordirs; Name: "{app}\hpg_cache_*.db-shm"
Type: filesandordirs; Name: "{app}\hpg_cache_*.lock"
Type: filesandordirs; Name: "{app}\hpg_cache_*.dbm*"
Type: filesandordirs; Name: "{app}\*.log"

[Code]
// Custom installation messages and checks

function InitializeSetup(): Boolean;
begin
  Result := True;
  MsgBox('Welcome to Harmonic Playlist Generator v3.7.0 Setup!' + #13#10 + #13#10 +
         'This installer will install HPG on your computer.' + #13#10 + #13#10 +
         'Features:' + #13#10 +
         '  - 4-6x faster audio analysis (multi-core)' + #13#10 +
         '  - Optional Rekordbox integration (12x speedup)' + #13#10 +
         '  - 8 advanced playlist algorithms' + #13#10 +
         '  - DJ-optimized mix points (phrase-aligned)' + #13#10 +
         '  - M3U8 and Rekordbox XML export' + #13#10 + #13#10 +
         'Click Next to continue.',
         mbInformation, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    MsgBox('Installation Complete!' + #13#10 + #13#10 +
           'HPG has been successfully installed.' + #13#10 + #13#10 +
           'Quick Start:' + #13#10 +
           '  1. Launch HPG from Desktop or Start Menu' + #13#10 +
           '  2. Drag & drop your music folder' + #13#10 +
           '  3. Choose playlist strategy' + #13#10 +
           '  4. Click Generate Playlist' + #13#10 + #13#10 +
           'For Rekordbox integration, install pyrekordbox:' + #13#10 +
           '  pip install pyrekordbox' + #13#10 + #13#10 +
         'Enjoy harmonically optimized playlists!',
           mbInformation, MB_OK);
  end;
end;
