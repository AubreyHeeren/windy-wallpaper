; Inno Setup script - builds the Windows installer for Windy Live Wallpaper
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{B3E5A1C2-7D44-4C8E-9A2B-5F1E6C0D9A11}
AppName=Windy Live Wallpaper
AppVersion={#AppVersion}
AppPublisher=Windy Live Wallpaper
DefaultDirName={autopf}\Windy Live Wallpaper
DefaultGroupName=Windy Live Wallpaper
DisableProgramGroupPage=yes
OutputDir=..\dist-installer
OutputBaseFilename=WindyWallpaper-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\WindyWallpaper.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Windows 10 version 2004 (build 19041) and newer, 64-bit
MinVersion=10.0.19041
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
AppMutex=WindyWallpaper
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked
Name: "autostart"; Description: "Start Windy Live Wallpaper when I sign in to Windows"

[Files]
Source: "..\dist\WindyWallpaper\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not WebView2Installed

[Icons]
Name: "{autoprograms}\Windy Live Wallpaper"; Filename: "{app}\WindyWallpaper.exe"
Name: "{autodesktop}\Windy Live Wallpaper"; Filename: "{app}\WindyWallpaper.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "WindyWallpaper"; ValueData: """{app}\WindyWallpaper.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft Edge WebView2 Runtime..."; Flags: waituntilterminated; Check: not WebView2Installed
Filename: "{app}\WindyWallpaper.exe"; Description: "Launch Windy Live Wallpaper"; Flags: nowait postinstall skipifsilent
; Relaunch after a silent auto-update
Filename: "{app}\WindyWallpaper.exe"; Flags: nowait runasoriginaluser; Check: WizardSilent

[Code]
function WebView2Installed: Boolean;
var
  v: String;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v) or
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v);
  if Result then
    Result := (v <> '') and (v <> '0.0.0.0');
end;
